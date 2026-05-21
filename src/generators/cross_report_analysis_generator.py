from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportAnalysisSection,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportGeneratedAnalysisResult,
    CrossReportSignalScoreResult,
    validate_cross_report_contract,
)
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import llm_service, prompt_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cross_report_analysis_generator")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _known_evidence_ids(evidence_inputs: CrossReportEvidenceInputResult) -> set[str]:
    return {item.evidence_id for item in evidence_inputs.evidence}


def _known_raw_metric_ids(evidence_inputs: CrossReportEvidenceInputResult) -> set[str]:
    return {item.metric_id for item in evidence_inputs.raw_metrics}


def _prompt_variables(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    signal_result: CrossReportSignalScoreResult,
    agreement_result: CrossReportEvidenceAgreementResult,
    *,
    max_prompt_chars: int,
) -> dict[str, str]:
    return {
        "request_json": _json(asdict(request)),
        "selected_theme_json": _json(asdict(signal_result.selected_theme)),
        "selected_sources_json": _json(
            [asdict(source) for source in evidence_inputs.selected_sources]
        ),
        "signal_scores_json": _json(
            [asdict(score) for score in signal_result.signal_scores]
        ),
        "evidence_groups_json": _json(
            [asdict(group) for group in agreement_result.evidence_groups]
        ),
        "evidence_json": _json([asdict(item) for item in evidence_inputs.evidence]),
        "raw_metrics_json": _json(
            [asdict(metric) for metric in evidence_inputs.raw_metrics]
        ),
        "generation_policy_json": _json(
            {
                "raw_metric_policy": signal_result.raw_metric_policy,
                "max_prompt_chars": max_prompt_chars,
                "prompt_input_chars": evidence_inputs.prompt_input_chars,
                "required_claim_evidence_ids": True,
            }
        ),
    }


def _response_payload(response: OpenAIResponseResult) -> dict[str, Any]:
    if isinstance(response.parsed_json, dict):
        return dict(response.parsed_json)
    raise AppError(
        code="cross_report_analysis_invalid_json",
        message="Cross-report analysis synthesis returned no JSON object",
        retryable=False,
        severity="error",
        context={"response_preview": str(response.text or "")[:400]},
    )


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = str(payload.get(field_name) or "").strip()
    if not value:
        raise AppError(
            code="cross_report_analysis_output_invalid",
            message=f"Cross-report analysis response missing {field_name}",
            retryable=False,
            severity="error",
            context={"field": field_name},
        )
    return value


def _section_text(section: dict[str, Any], field_name: str) -> str:
    value = str(section.get(field_name) or "").strip()
    if not value:
        raise AppError(
            code="cross_report_analysis_output_invalid",
            message=f"Cross-report analysis section missing {field_name}",
            retryable=False,
            severity="error",
            context={"field": field_name, "section": section},
        )
    return value


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_references(
    *,
    evidence_ids: list[str],
    raw_metric_ids: list[str],
    known_evidence: set[str],
    known_raw_metrics: set[str],
    context: dict[str, Any],
) -> None:
    missing_evidence = sorted(
        {
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id not in known_evidence
        }
    )
    if missing_evidence:
        raise AppError(
            code="cross_report_analysis_evidence_invalid",
            message="Cross-report analysis referenced unknown evidence ids",
            retryable=False,
            severity="error",
            context={**context, "missing_evidence_ids": missing_evidence},
        )
    missing_metrics = sorted(
        {
            metric_id
            for metric_id in raw_metric_ids
            if metric_id not in known_raw_metrics
        }
    )
    if missing_metrics:
        raise AppError(
            code="cross_report_analysis_metric_invalid",
            message="Cross-report analysis referenced unknown raw metric ids",
            retryable=False,
            severity="error",
            context={**context, "missing_raw_metric_ids": missing_metrics},
        )


def _sections_from_payload(
    payload: dict[str, Any],
    *,
    known_evidence: set[str],
    known_raw_metrics: set[str],
) -> list[CrossReportAnalysisSection]:
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise AppError(
            code="cross_report_analysis_output_invalid",
            message="Cross-report analysis response must include non-empty sections",
            retryable=False,
            severity="error",
            context={"field": "sections"},
        )
    sections: list[CrossReportAnalysisSection] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise AppError(
                code="cross_report_analysis_output_invalid",
                message="Cross-report analysis section must be an object",
                retryable=False,
                severity="error",
                context={"section": raw_section},
            )
        evidence_ids = _text_list(raw_section.get("evidence_ids"))
        raw_metric_ids = _text_list(raw_section.get("raw_metric_ids"))
        _validate_references(
            evidence_ids=evidence_ids,
            raw_metric_ids=raw_metric_ids,
            known_evidence=known_evidence,
            known_raw_metrics=known_raw_metrics,
            context={"section_id": raw_section.get("section_id")},
        )
        sections.append(
            CrossReportAnalysisSection(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                section_id=_section_text(raw_section, "section_id"),
                heading=_section_text(raw_section, "heading"),
                body=_section_text(raw_section, "body"),
                evidence_ids=evidence_ids,
                raw_metric_ids=raw_metric_ids,
            )
        )
    source_notes = _text_list(payload.get("source_notes"))
    if source_notes:
        first_evidence = next(iter(sorted(known_evidence)), "")
        sections.append(
            CrossReportAnalysisSection(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                section_id="source-notes",
                heading="Source notes",
                body="\n".join(source_notes),
                evidence_ids=[first_evidence] if first_evidence else [],
                raw_metric_ids=[],
            )
        )
    return sections


def _evidence_map(
    payload: dict[str, Any],
    *,
    known_evidence: set[str],
) -> dict[str, list[str]]:
    raw_map = payload.get("evidence_map")
    if not isinstance(raw_map, dict) or not raw_map:
        raise AppError(
            code="cross_report_analysis_output_invalid",
            message="Cross-report analysis response must include evidence_map",
            retryable=False,
            severity="error",
            context={"field": "evidence_map"},
        )
    mapped: dict[str, list[str]] = {}
    for key, value in raw_map.items():
        claim_key = str(key or "").strip()
        evidence_ids = _text_list(value)
        if not claim_key or not evidence_ids:
            raise AppError(
                code="cross_report_analysis_output_invalid",
                message="Cross-report analysis evidence_map entries must be populated",
                retryable=False,
                severity="error",
                context={"claim_key": claim_key},
            )
        _validate_references(
            evidence_ids=evidence_ids,
            raw_metric_ids=[],
            known_evidence=known_evidence,
            known_raw_metrics=set(),
            context={"claim_key": claim_key},
        )
        mapped[claim_key] = evidence_ids
    return mapped


def generate_cross_report_analysis(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    signal_result: CrossReportSignalScoreResult,
    agreement_result: CrossReportEvidenceAgreementResult,
    settings: Any,
    ctx: RunContext,
    *,
    prompt_client: Any = prompt_service,
    openai_client: Any | None = None,
) -> CrossReportGeneratedAnalysisResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(signal_result)
    validate_cross_report_contract(agreement_result)
    namespace = str(
        getattr(
            settings,
            "cross_report_analysis_prompt_namespace",
            "cross_report_analysis/synthesis",
        )
    ).strip()
    max_prompt_chars = int(
        getattr(settings, "cross_report_analysis_max_prompt_chars", 60000)
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_analysis_generation_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "prompt_namespace": namespace,
                "selected_theme_id": signal_result.selected_theme.theme_id,
                "selected_report_ids": [
                    source.report_id for source in evidence_inputs.selected_sources
                ],
                "signal_ids": signal_result.selected_signal_ids,
                "evidence_count": len(evidence_inputs.evidence),
                "raw_metric_count": len(evidence_inputs.raw_metrics),
            },
        )
    )
    variables = _prompt_variables(
        request,
        evidence_inputs,
        signal_result,
        agreement_result,
        max_prompt_chars=max_prompt_chars,
    )
    prompt_bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables=variables,
        reload_if_changed=True,
        default_model=str(getattr(settings, "cross_report_analysis_model", "") or ""),
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_analysis_prompt_rendered",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "namespace": namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
                "rendered_system_prompt": prompt_bundle.system_prompt,
                "rendered_user_prompt": prompt_bundle.user_prompt,
                "model": prompt_bundle.resolved_model,
                "temperature": float(
                    getattr(settings, "cross_report_analysis_temperature", 1.0)
                ),
            },
        )
    )
    openai_client = openai_client or llm_service.build_openai_client_for_settings(
        settings,
        scope="cross_report_analysis",
    )
    response: OpenAIResponseResult = openai_client.openai_chat_json(
        OpenAIJSONPromptRequest(
            schema_version="1.0",
            system_prompt=prompt_bundle.system_prompt,
            user_prompt=prompt_bundle.user_prompt,
            model=prompt_bundle.resolved_model,
            temperature=float(
                getattr(settings, "cross_report_analysis_temperature", 1.0)
            ),
            api_key=str(getattr(settings, "openai_api_key", "")),
            seed=getattr(settings, "openai_seed", None),
            timeout_seconds=float(
                getattr(settings, "cross_report_analysis_timeout_seconds", 600.0)
            ),
            cost_ledger_path=str(getattr(settings, "cost_ledger_path", "")),
            cost_daily_path=str(getattr(settings, "cost_daily_path", "")),
            model_pricing=dict(getattr(settings, "model_pricing", {}) or {}),
            response_cache_enabled=bool(
                getattr(settings, "cross_report_analysis_cache_enabled", True)
            ),
            response_cache_dir=str(getattr(settings, "cache_dir", "./cache")),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_analysis_raw_response",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "provider_request_id": response.request_id or "",
                "model": response.model,
                "raw_response": response.text,
            },
        )
    )
    payload = _response_payload(response)
    known_evidence = _known_evidence_ids(evidence_inputs)
    known_raw_metrics = _known_raw_metric_ids(evidence_inputs)
    sections = _sections_from_payload(
        payload,
        known_evidence=known_evidence,
        known_raw_metrics=known_raw_metrics,
    )
    evidence_map = _evidence_map(payload, known_evidence=known_evidence)
    result = CrossReportGeneratedAnalysisResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_id=_required_text(payload, "analysis_id"),
        title=_required_text(payload, "title"),
        slug=_required_text(payload, "slug"),
        executive_summary=_required_text(payload, "executive_summary"),
        selected_theme=signal_result.selected_theme,
        selected_sources=evidence_inputs.selected_sources,
        evidence=evidence_inputs.evidence,
        signal_scores=signal_result.signal_scores,
        raw_metrics=evidence_inputs.raw_metrics,
        sections=sections,
        evidence_map=evidence_map,
        prompt_hashes={
            "system": prompt_bundle.prompt_set.system.sha256,
            "user": prompt_bundle.prompt_set.user.sha256,
        },
        model=str(response.model or prompt_bundle.resolved_model),
        cost_summary={
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
            "request_id": response.request_id or "",
        },
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_analysis_generation_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "analysis_id": result.analysis_id,
                "title": result.title,
                "section_count": len(result.sections),
                "evidence_map_keys": sorted(result.evidence_map.keys()),
                "provider_request_id": response.request_id or "",
                "post_processed_output": asdict(result),
            },
        )
    )
    return result
