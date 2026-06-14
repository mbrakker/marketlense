from __future__ import annotations

import hashlib
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
    CrossReportPublishPackage,
    CrossReportSignalScoreResult,
    CrossReportValidationResult,
    validate_cross_report_contract,
)
from src.contracts.publish import PublishEntityMetadata
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.generators.cross_report_publish_html import build_cross_report_html_document
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import llm_service, prompt_service
from src.utils.coercion import ordered_unique_strings as _unique_ordered
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cross_report_analysis_generator")
_METRIC_NORMALIZATION_PHRASES = (
    "normalized average",
    "average across publishers",
    "weighted average",
    "converted to a common unit",
    "normalized across sources",
    "like-for-like metric comparison",
)


def _hash_contract_payload(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _source_metadata(
    generated: CrossReportGeneratedAnalysisResult,
) -> list[dict[str, Any]]:
    return [
        {
            "report_id": source.report_id,
            "title": source.title,
            "publisher": source.publisher,
            "publisher_id": source.publisher_id,
            "report_date": source.report_date,
            "rank": source.rank,
            "evidence_count": source.evidence_count,
            "category_labels": list(source.category_labels),
            "tags": list(source.tags),
            "source_url": source.source_url,
        }
        for source in generated.selected_sources
    ]


def _known_evidence_ids(evidence_inputs: CrossReportEvidenceInputResult) -> set[str]:
    return {item.evidence_id for item in evidence_inputs.evidence}


def _known_evidence_aliases(
    evidence_inputs: CrossReportEvidenceInputResult,
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    alias_sources: dict[str, set[str]] = {}
    projected_prefix_sources: dict[str, set[str]] = {}

    def _record_alias(alias: str, evidence_id: str) -> None:
        owners = alias_sources.setdefault(alias, set())
        owners.add(evidence_id)
        if len(owners) > 1:
            raise AppError(
                code="cross_report_analysis_evidence_alias_collision",
                message="Cross-report evidence aliases must not collide across evidence rows",
                retryable=False,
                severity="error",
                context={
                    "alias": alias,
                    "conflicting_evidence_ids": sorted(owners),
                },
            )
        aliases[alias] = evidence_id

    def _projected_prefix_alias(value: str) -> str:
        parts = value.split(":", 2)
        if len(parts) != 3:
            return ""
        report_id, content_kind, local_id = parts
        if not report_id.strip() or not content_kind.strip():
            return ""
        local_prefix = local_id.split("_", 1)[0].strip()
        if not local_prefix or local_prefix == local_id:
            return ""
        return f"{report_id.strip()}:{content_kind.strip()}:{local_prefix}"

    def _record_projected_prefix_candidate(value: str, evidence_id: str) -> None:
        alias = _projected_prefix_alias(value)
        if alias:
            projected_prefix_sources.setdefault(alias, set()).add(evidence_id)

    for item in evidence_inputs.evidence:
        evidence_id = str(item.evidence_id or "").strip()
        if not evidence_id:
            continue
        _record_alias(evidence_id, evidence_id)
        _record_projected_prefix_candidate(evidence_id, evidence_id)
        entity_uid = str(item.entity_uid or "").strip()
        if entity_uid:
            _record_alias(entity_uid, evidence_id)
            _record_projected_prefix_candidate(entity_uid, evidence_id)
    for alias, owners in projected_prefix_sources.items():
        if len(owners) == 1:
            _record_alias(alias, next(iter(owners)))
    return aliases


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


def _canonical_ids(values: list[str], aliases: dict[str, str]) -> list[str]:
    return [aliases.get(value, value) for value in values]


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
    evidence_aliases: dict[str, str],
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
        evidence_ids = _canonical_ids(
            _text_list(raw_section.get("evidence_ids")),
            evidence_aliases,
        )
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
    return sections


def _evidence_map(
    payload: dict[str, Any],
    *,
    known_evidence: set[str],
    evidence_aliases: dict[str, str],
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
        evidence_ids = _canonical_ids(_text_list(value), evidence_aliases)
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


def _artifact_evidence_ids(generated: CrossReportGeneratedAnalysisResult) -> set[str]:
    evidence_ids: set[str] = set()
    for section in generated.sections:
        evidence_ids.update(section.evidence_ids)
    for mapped_ids in generated.evidence_map.values():
        evidence_ids.update(mapped_ids)
    return evidence_ids


def _metric_normalization_violations(
    generated: CrossReportGeneratedAnalysisResult,
) -> list[str]:
    text = " ".join(
        [
            generated.title,
            generated.executive_summary,
            *[section.heading for section in generated.sections],
            *[section.body for section in generated.sections],
        ]
    ).casefold()
    return [phrase for phrase in _METRIC_NORMALIZATION_PHRASES if phrase in text]


def validate_cross_report_generated_analysis(
    generated: CrossReportGeneratedAnalysisResult,
    ctx: RunContext,
    *,
    prompt_budget_chars: int = 0,
    max_prompt_chars: int = 60000,
    raise_on_failure: bool = True,
) -> CrossReportValidationResult:
    known_evidence_ids = {item.evidence_id for item in generated.evidence}
    cited_evidence_ids = _artifact_evidence_ids(generated)
    checked_evidence_ids = sorted(cited_evidence_ids or known_evidence_ids)
    missing_evidence_ids = sorted(cited_evidence_ids - known_evidence_ids)
    issues: list[str] = []
    if not generated.sections:
        issues.append("sections_empty")
    for section in generated.sections:
        if not section.evidence_ids:
            issues.append(f"section_missing_evidence:{section.section_id}")
        if not section.heading.strip():
            issues.append(f"section_missing_heading:{section.section_id}")
        if not section.body.strip():
            issues.append(f"section_missing_body:{section.section_id}")
    if not generated.evidence_map:
        issues.append("evidence_map_empty")
    for key, evidence_ids in generated.evidence_map.items():
        if not str(key).strip():
            issues.append("evidence_map_key_empty")
        if not evidence_ids:
            issues.append(f"evidence_map_missing_evidence:{key}")
    if missing_evidence_ids:
        issues.append("unknown_evidence_ids")
    metric_violations = _metric_normalization_violations(generated)
    if metric_violations:
        issues.append("metric_normalization_language")
    if prompt_budget_chars > max_prompt_chars:
        issues.append("prompt_budget_exceeded")

    passed = not issues and not missing_evidence_ids and not metric_violations
    result = CrossReportValidationResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        status="pass" if passed else "fail",
        checked_evidence_ids=checked_evidence_ids,
        missing_evidence_ids=missing_evidence_ids,
        issues=issues,
        metric_normalization_violations=metric_violations,
        prompt_budget_chars=prompt_budget_chars,
        passed=passed,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_analysis_validation_complete",
            module=logger.name,
            fields={
                "analysis_id": generated.analysis_id,
                "status": result.status,
                "passed": result.passed,
                "checked_evidence_ids": result.checked_evidence_ids,
                "missing_evidence_ids": result.missing_evidence_ids,
                "issues": result.issues,
                "metric_normalization_violations": result.metric_normalization_violations,
                "prompt_budget_chars": result.prompt_budget_chars,
                "max_prompt_chars": max_prompt_chars,
            },
        )
    )
    if not passed and raise_on_failure:
        raise AppError(
            code="cross_report_analysis_validation_failed",
            message="Cross-report analysis deterministic validation failed",
            retryable=False,
            severity="error",
            context={
                "analysis_id": generated.analysis_id,
                "issues": result.issues,
                "missing_evidence_ids": result.missing_evidence_ids,
                "metric_normalization_violations": result.metric_normalization_violations,
                "prompt_budget_chars": result.prompt_budget_chars,
                "max_prompt_chars": max_prompt_chars,
            },
        )
    validate_cross_report_contract(result)
    return result


def build_cross_report_publish_package(
    generated: CrossReportGeneratedAnalysisResult,
    validation_result: CrossReportValidationResult,
    agreement_result: CrossReportEvidenceAgreementResult,
    ctx: RunContext,
    *,
    artifact_path: str,
    html_path: str,
    publish_requires_validation_pass: bool = True,
    target_route: str = "wordpress:ml_briefing",
) -> CrossReportPublishPackage:
    validate_cross_report_contract(generated)
    validate_cross_report_contract(validation_result)
    validate_cross_report_contract(agreement_result)
    if publish_requires_validation_pass and not validation_result.passed:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_publish_package_validation_blocked",
                module=logger.name,
                fields={
                    "analysis_id": generated.analysis_id,
                    "validation_status": validation_result.status,
                    "issues": validation_result.issues,
                },
            )
        )
        raise AppError(
            code="cross_report_publish_validation_failed",
            message="Cross-report publish package requires a passed validation result",
            retryable=False,
            severity="error",
            context={
                "analysis_id": generated.analysis_id,
                "validation_status": validation_result.status,
                "issues": validation_result.issues,
            },
        )

    source_metadata = _source_metadata(generated)
    category_labels = _unique_ordered(
        [
            category
            for source in generated.selected_sources
            for category in source.category_labels
        ]
    )
    tag_labels = _unique_ordered(
        [tag for source in generated.selected_sources for tag in source.tags]
    )
    selected_report_ids = [source.report_id for source in generated.selected_sources]
    evidence_reference_ids = [item.evidence_id for item in generated.evidence]
    raw_metric_ids = [item.metric_id for item in generated.raw_metrics]
    package_id = f"cross-report:{generated.analysis_id}"
    entity_type_by_route = {
        "wordpress:ml_briefing": "briefing",
        "wordpress:ml_signal": "signal",
    }
    entity_type = entity_type_by_route.get(target_route)
    if entity_type is None:
        raise AppError(
            code="publish_entity_metadata_unsupported",
            message="Cross-report package target route is not a supported public entity route.",
            retryable=False,
            severity="error",
            context={"target_route": target_route},
        )
    publish_entity_metadata = PublishEntityMetadata(
        schema_version="1.0",
        entity_type=entity_type,
        source_artifact_id=package_id,
        canonical_route_intent=target_route,
        publish_eligible=True,
    )
    machine_metadata = {
        "schema_version": CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        "analysis_id": generated.analysis_id,
        "selected_theme_id": generated.selected_theme.theme_id,
        "selected_report_ids": selected_report_ids,
        "evidence_reference_ids": evidence_reference_ids,
        "raw_metric_ids": raw_metric_ids,
        "canonical_artifact_path": artifact_path,
        "prompt_hashes": dict(generated.prompt_hashes),
        "validation_status": validation_result.status,
        "public_entity_metadata": asdict(publish_entity_metadata),
    }
    body_html, html_text = build_cross_report_html_document(
        generated=generated,
        agreement_result=agreement_result,
        source_metadata=source_metadata,
        machine_metadata=machine_metadata,
        file_id=package_id,
        publish_entity_metadata=publish_entity_metadata,
    )
    package = CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id=package_id,
        file_id=package_id,
        target_route=target_route,
        title=generated.title,
        slug=generated.slug,
        excerpt=generated.executive_summary,
        body_html=body_html,
        html_text=html_text,
        html_path=html_path,
        canonical_artifact_path=artifact_path,
        artifact_sha256=_hash_contract_payload(asdict(generated)),
        validation_sha256=_hash_contract_payload(asdict(validation_result)),
        selected_theme_id=generated.selected_theme.theme_id,
        selected_report_ids=selected_report_ids,
        source_metadata=source_metadata,
        category_labels=category_labels,
        tag_labels=tag_labels,
        evidence_reference_ids=evidence_reference_ids,
        raw_metric_ids=raw_metric_ids,
        prompt_hashes=dict(generated.prompt_hashes),
        machine_metadata=machine_metadata,
    )
    validate_cross_report_contract(package)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_publish_package_built",
            module=logger.name,
            fields={
                "analysis_id": generated.analysis_id,
                "package_id": package.package_id,
                "html_path": package.html_path,
                "target_route": package.target_route,
                "selected_report_ids": package.selected_report_ids,
                "evidence_count": len(package.evidence_reference_ids),
                "raw_metric_count": len(package.raw_metric_ids),
            },
        )
    )
    return package


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
    max_prompt_chars: int | None = None,
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
    resolved_max_prompt_chars = int(
        max_prompt_chars
        if max_prompt_chars is not None
        else getattr(settings, "cross_report_analysis_max_prompt_chars", 60000)
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
        max_prompt_chars=resolved_max_prompt_chars,
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
    rendered_prompt_chars = len(prompt_bundle.system_prompt) + len(
        prompt_bundle.user_prompt
    )
    if rendered_prompt_chars > resolved_max_prompt_chars:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_prompt_budget_exceeded",
                module=logger.name,
                fields={
                    "request_id": request.request_id,
                    "rendered_prompt_chars": rendered_prompt_chars,
                    "max_prompt_chars": resolved_max_prompt_chars,
                    "namespace": namespace,
                },
            )
        )
        raise AppError(
            code="cross_report_prompt_budget_exceeded",
            message="Rendered cross-report prompts exceed the configured character budget",
            retryable=False,
            severity="error",
            context={
                "request_id": request.request_id,
                "rendered_prompt_chars": rendered_prompt_chars,
                "max_prompt_chars": resolved_max_prompt_chars,
                "operator_action": (
                    "Reduce source/evidence limits or increase the cross-report prompt "
                    "budget before retrying."
                ),
            },
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
    evidence_aliases = _known_evidence_aliases(evidence_inputs)
    known_raw_metrics = _known_raw_metric_ids(evidence_inputs)
    sections = _sections_from_payload(
        payload,
        known_evidence=known_evidence,
        evidence_aliases=evidence_aliases,
        known_raw_metrics=known_raw_metrics,
    )
    evidence_map = _evidence_map(
        payload,
        known_evidence=known_evidence,
        evidence_aliases=evidence_aliases,
    )
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
    validation_result = validate_cross_report_generated_analysis(
        result,
        ctx,
        prompt_budget_chars=evidence_inputs.prompt_input_chars,
        max_prompt_chars=resolved_max_prompt_chars,
    )
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
                "validation_status": validation_result.status,
                "post_processed_output": asdict(result),
            },
        )
    )
    return result
