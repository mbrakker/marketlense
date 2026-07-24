from __future__ import annotations

import json
import logging
import re
from hashlib import sha256
from typing import Any, Dict, List

from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.context_category_fit import (
    CategoryFitCandidate,
    ContextCategoryFitRequest,
    ContextCategoryFitResponse,
    ReportCategoryContext,
)
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services import prompt_service
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.context_category_fit_generator")

_STOP_WORDS = {
    "about",
    "across",
    "broader",
    "central",
    "centers",
    "dominant",
    "evidence",
    "focuses",
    "inside",
    "main",
    "mainly",
    "market",
    "models",
    "only",
    "overview",
    "primary",
    "really",
    "repeated",
    "repeatedly",
    "reject",
    "report",
    "reports",
    "shape",
    "subject",
    "supporting",
    "theme",
    "when",
    "where",
    "whose",
}
_HIGH_CONFIDENCE_FIT_THRESHOLD = 0.85


def fit_report_categories_from_context(
    request: ContextCategoryFitRequest,
    ctx,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    mapping_client=load_category_mappings,
) -> ContextCategoryFitResponse:
    openai_client = require_injected_model_client(
        openai_client,
        scope="context_category_fit",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_start",
            module=logger.name,
            fields={
                "report_id": request.context.report_id,
                "title": request.context.title,
                "prompt_namespace": request.prompt_namespace,
                "category_mapping_path": request.category_mapping_path,
                "declared_candidate_count": len(request.candidate_category_ids),
            },
        )
    )
    mappings_resp = mapping_client(
        CategoryMappingLoadRequest(
            schema_version="1.0",
            path=request.category_mapping_path,
            reload_if_changed=True,
        ),
        ctx,
    )
    category_profiles = [
        {
            "id": category.id,
            "label": category.label,
            "description": category.description,
            "definition": category.definition or category.description,
            "include_when": list(category.include_when or []),
            "exclude_when": list(category.exclude_when or []),
            "semantic_concepts": list(category.core_tags or []),
        }
        for category in mappings_resp.mappings.categories
        if category.portal_exposed
    ]
    declared_candidate_ids = tuple(
        dict.fromkeys(
            str(category_id or "").strip()
            for category_id in request.candidate_category_ids
            if str(category_id or "").strip()
        )
    )
    if declared_candidate_ids:
        declared_candidate_id_set = set(declared_candidate_ids)
        category_profiles = [
            profile
            for profile in category_profiles
            if str(profile["id"]) in declared_candidate_id_set
        ]
        if not category_profiles:
            raise AppError(
                code="context_category_fit_candidate_set_empty",
                message="Category reclassification has no declared portal candidates",
                retryable=False,
                context={"candidate_count": len(declared_candidate_ids)},
            )
    prompt_bundle = prepare_prompt_bundle(
        namespace=request.prompt_namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={
            "report_context_json": json.dumps(
                _serialize_context(request.context), ensure_ascii=True, indent=2
            ),
            "category_profiles_json": json.dumps(
                category_profiles, ensure_ascii=True, indent=2
            ),
            "repair_error": request.repair_error,
            "repair_attempt": request.repair_attempt,
            "repair_response": request.repair_response,
            "candidate_category_ids": list(declared_candidate_ids),
        },
        reload_if_changed=True,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": request.prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
                "resolved_model": prompt_bundle.resolved_model,
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
                "system_prompt_chars": len(prompt_bundle.system_prompt),
                "user_prompt_chars": len(prompt_bundle.user_prompt),
            },
        )
    )
    output_schema = provider_output_schema("context_category_fit")
    source_evidence = {
        "report_context": _serialize_context(request.context),
        "category_profiles": category_profiles,
        "candidate_category_ids": list(declared_candidate_ids),
    }

    def call_model(mode: str, original_response: str, schema_errors: str):
        bundle = prompt_bundle
        if mode != "primary":
            bundle = recovery_prompt_bundle(
                mode=mode,
                artifact_family="category_fit",
                schema_errors=schema_errors,
                original_response=original_response,
                output_schema=output_schema,
                source_evidence=source_evidence,
                settings=request.settings,
                ctx=ctx,
                prompt_client=prompt_client,
                vector_store_id=None,
            )
        return invoke_structured_output_model(
            openai_client=openai_client,
            prompt_bundle=bundle,
            settings=request.settings,
            ctx=ctx,
            vector_store_id=None,
            report_id=str(request.context.report_id),
            artifact_family="category_fit",
            stage=(
                "category_fit_repair"
                if request.repair_attempt or mode != "primary"
                else "category_fit"
            ),
            publisher_name=request.publisher_name,
            report_name=request.report_name,
            source_url=request.source_url,
            output_schema=output_schema,
            output_schema_identity="context_category_fit_v1",
            repair_attempt=(
                request.repair_attempt
                if mode == "primary" and request.repair_attempt
                else {"primary": 0, "model_repair": 1, "regeneration": 2}[mode]
            ),
        )

    recovery = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id=str(request.context.report_id),
            artifact_family="category_fit",
            schema_name="context_category_fit",
            model=prompt_bundle.resolved_model,
            terminal_failure_code="context_category_fit_invalid_json",
        ),
        ctx,
        call_model=call_model,
        normalize_payload=lambda payload: _normalize_fit_payload(dict(payload)),
        validate_payload=lambda payload: validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=payload,
                schema_name="context_category_fit",
            ),
            ctx,
        ),
        is_substantive=lambda payload: bool(
            isinstance(payload, dict) and payload.get("category_fits")
        ),
        model_pricing=request.settings.model_pricing,
    )
    payload = recovery.payload
    fit_response = _coerce_fit_response(
        payload=payload,
        report_id=request.context.report_id,
        category_profiles=category_profiles,
        context=request.context,
        ctx=ctx,
        model=str(recovery.model or prompt_bundle.resolved_model or ""),
        raw_response=json.dumps(payload, ensure_ascii=False),
        request_id=str(recovery.request_id or "") or None,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="context_category_fit_complete",
            module=logger.name,
            fields={
                "report_id": fit_response.report_id,
                "categories": fit_response.categories,
                "candidate_count": len(fit_response.fits),
                "topic_semantic_status_counts": _semantic_status_counts(
                    fit_response.fits
                ),
                "request_id": fit_response.request_id or "",
                "model": fit_response.model,
            },
        )
    )
    return fit_response


def _serialize_context(context: ReportCategoryContext) -> Dict[str, Any]:
    return {
        "report_id": context.report_id,
        "title": context.title,
        "publisher": context.publisher,
        "region": context.region,
        "time_period": context.time_period,
        "overview": context.overview,
        "methods": list(context.methods),
        "key_findings": list(context.key_findings),
        "limitations": list(context.limitations),
        "sections": [
            {
                "section_label": section.section_label,
                "source_pack": section.source_pack,
                "summary": section.summary,
                "key_points": list(section.key_points),
            }
            for section in context.sections
        ],
    }


def _normalize_fit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "schema_version": str(payload.get("schema_version") or "1.0"),
        "selected_category_ids": [],
        "category_fits": [],
    }
    for category_id in payload.get("selected_category_ids") or []:
        text = str(category_id or "").strip()
        if text:
            normalized["selected_category_ids"].append(text)
    for item in payload.get("category_fits") or []:
        if not isinstance(item, dict):
            continue
        normalized["category_fits"].append(
            {
                "category_id": item.get("category_id"),
                "label": item.get("label"),
                "fit_score": item.get("fit_score"),
                "decision": item.get("decision"),
                "why_fit": str(item.get("why_fit") or ""),
                "why_not_fit": str(item.get("why_not_fit") or ""),
                "evidence_sections": item.get("evidence_sections") or [],
            }
        )
    return normalized


def _context_search_text(context: ReportCategoryContext) -> str:
    parts: list[str] = [
        context.title,
        context.publisher,
        context.region,
        context.time_period,
        context.overview,
        *context.methods,
        *context.key_findings,
        *context.limitations,
    ]
    for section in context.sections:
        parts.extend([section.section_label, section.summary, *section.key_points])
    return " ".join(str(part or "") for part in parts).casefold()


def _semantic_terms(value: str) -> list[str]:
    """Return ordered, explicit concepts while discarding only prose connectors."""
    return [
        token.strip("_-' ")
        for token in re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", value.casefold())
        if token.strip("_-' ") not in _STOP_WORDS
    ]


def _normalized_phrase(value: str) -> str:
    return " ".join(_semantic_terms(value))


def _rule_id(category_id: str, rule_kind: str, position: int, rule: str) -> str:
    stable_payload = "\x1f".join(
        (category_id, rule_kind, str(position), _normalized_phrase(rule))
    )
    return f"{category_id}:{rule_kind}:{sha256(stable_payload.encode('utf-8')).hexdigest()[:16]}"


def _rule_has_explicit_concept(rule: str, context_text: str) -> bool:
    """Match a rule by an exact multi-term concept, never independent token overlap."""
    context = _normalized_phrase(context_text)
    terms = _semantic_terms(rule)
    if not context or len(terms) < 2:
        return False
    for width in range(min(4, len(terms)), 1, -1):
        for start in range(0, len(terms) - width + 1):
            if " ".join(terms[start : start + width]) in context:
                return True
    return False


def _matching_rules(
    rules: list[str],
    *,
    category_id: str,
    rule_kind: str,
    context_text: str,
) -> list[tuple[str, str]]:
    matched: list[tuple[str, str]] = []
    for position, raw_rule in enumerate(rules):
        rule = str(raw_rule or "").strip()
        if rule and _rule_has_explicit_concept(rule, context_text):
            matched.append((_rule_id(category_id, rule_kind, position, rule), rule))
    return matched


def _central_context_text(context: ReportCategoryContext) -> str:
    """Use the report's title, overview and key findings as centrality evidence."""
    return " ".join((context.title, context.overview, *context.key_findings))


def _apply_topic_semantics(
    *,
    candidate: CategoryFitCandidate,
    profile: dict[str, Any],
    context_text: str,
    central_text: str,
) -> CategoryFitCandidate:
    include_rules = [str(item) for item in profile.get("include_when") or []]
    exclude_rules = [str(item) for item in profile.get("exclude_when") or []]
    supported_matches = _matching_rules(
        include_rules,
        category_id=candidate.category_id,
        rule_kind="include",
        context_text=context_text,
    )
    rejected_matches = _matching_rules(
        exclude_rules,
        category_id=candidate.category_id,
        rule_kind="exclude",
        context_text=context_text,
    )
    central_matches = _matching_rules(
        include_rules,
        category_id=candidate.category_id,
        rule_kind="include",
        context_text=central_text,
    )
    supported_rule_ids = [rule_id for rule_id, _rule in supported_matches]
    supported_rules = [rule for _rule_id_value, rule in supported_matches]
    rejected_rule_ids = [rule_id for rule_id, _rule in rejected_matches]
    rejected_rules = [rule for _rule_id_value, rule in rejected_matches]
    decision = candidate.decision
    status = "not_evaluated"
    remediation_signal = ""
    why_not_fit = candidate.why_not_fit
    if rejected_rules and decision != "reject":
        decision = "reject"
        status = "rejected"
        remediation_signal = "topic_semantics_exclusion_conflict"
        if not why_not_fit:
            why_not_fit = "Canonical Topic exclusion rule matched the report context."
    elif (
        decision == "reject"
        and candidate.fit_score >= _HIGH_CONFIDENCE_FIT_THRESHOLD
        and supported_rules
        and central_matches
    ):
        decision = "primary"
        status = "supported"
    elif decision == "reject":
        status = "rejected"
    elif supported_rules:
        status = "supported"
    else:
        status = "ambiguous"
        remediation_signal = "topic_semantics_ambiguous"

    return CategoryFitCandidate(
        schema_version=candidate.schema_version,
        category_id=candidate.category_id,
        label=candidate.label,
        fit_score=candidate.fit_score,
        decision=decision,
        why_fit=candidate.why_fit,
        why_not_fit=why_not_fit,
        evidence_sections=list(candidate.evidence_sections),
        semantic_rule_status=status,
        supported_topic_rules=supported_rules,
        supported_topic_rule_ids=supported_rule_ids,
        rejected_topic_rules=rejected_rules,
        rejected_topic_rule_ids=rejected_rule_ids,
        rule_evidence_sections=list(candidate.evidence_sections),
        remediation_signal=remediation_signal,
    )


def _semantic_status_counts(fits: list[CategoryFitCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fit in fits:
        status = str(fit.semantic_rule_status or "not_evaluated")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _coerce_fit_response(
    *,
    payload: dict,
    report_id: str,
    category_profiles: List[dict[str, Any]],
    context: ReportCategoryContext,
    ctx,
    model: str,
    raw_response: str,
    request_id: str | None,
) -> ContextCategoryFitResponse:
    profile_by_id = {str(item["id"]): item for item in category_profiles}
    context_text = _context_search_text(context)
    central_text = _central_context_text(context)
    fits: List[CategoryFitCandidate] = []
    for item in payload.get("category_fits") or []:
        if not isinstance(item, dict):
            continue
        category_id = str(item.get("category_id") or "").strip()
        if category_id not in profile_by_id:
            continue
        label = str(item.get("label") or profile_by_id[category_id]["label"]).strip()
        decision = str(item.get("decision") or "").strip().lower()
        if decision not in {"primary", "secondary", "reject"}:
            decision = "reject"
        try:
            raw_fit_score = item.get("fit_score")
            if raw_fit_score is None:
                raise ValueError("missing fit_score")
            fit_score = float(raw_fit_score)
        except (TypeError, ValueError):
            fit_score = 0.0
        fit_score = max(0.0, min(1.0, fit_score))
        evidence_sections = []
        for value in item.get("evidence_sections") or []:
            text = str(value or "").strip()
            if text and text not in evidence_sections:
                evidence_sections.append(text)
        fit = CategoryFitCandidate(
            schema_version="1.0",
            category_id=category_id,
            label=label or profile_by_id[category_id]["label"],
            fit_score=fit_score,
            decision=decision,
            why_fit=str(item.get("why_fit") or "").strip(),
            why_not_fit=str(item.get("why_not_fit") or "").strip(),
            evidence_sections=evidence_sections,
        )
        fits.append(
            _apply_topic_semantics(
                candidate=fit,
                profile=profile_by_id[category_id],
                context_text=context_text,
                central_text=central_text,
            )
        )
    fits.sort(
        key=lambda item: (
            0
            if item.decision == "primary"
            else 1
            if item.decision == "secondary"
            else 2,
            -item.fit_score,
            item.category_id,
        )
    )
    selected_ids: List[str] = []
    for category_id in payload.get("selected_category_ids") or []:
        text = str(category_id or "").strip()
        selected_fit = next((fit for fit in fits if fit.category_id == text), None)
        if (
            text in profile_by_id
            and text not in selected_ids
            and (
                selected_fit is None
                or (
                    selected_fit.decision != "reject"
                    and selected_fit.semantic_rule_status != "ambiguous"
                )
            )
        ):
            selected_ids.append(text)
    if not selected_ids:
        for fit in fits:
            if (
                fit.decision in {"primary", "secondary"}
                and fit.semantic_rule_status != "ambiguous"
                and fit.category_id not in selected_ids
            ):
                selected_ids.append(fit.category_id)
            if len(selected_ids) >= 2:
                break
    selected_ids = selected_ids[:2]
    rejected_conflicts = [
        fit.category_id
        for fit in fits
        if fit.remediation_signal == "topic_semantics_exclusion_conflict"
    ]
    ambiguous = [
        fit.category_id
        for fit in fits
        if fit.remediation_signal == "topic_semantics_ambiguous"
    ]
    if rejected_conflicts or ambiguous:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="context_category_fit_topic_semantics_remediation",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "rejected_conflicts": rejected_conflicts,
                    "ambiguous": ambiguous,
                },
            )
        )
    labels = [profile_by_id[item]["label"] for item in selected_ids]
    return ContextCategoryFitResponse(
        schema_version="1.0",
        report_id=ReportId(report_id),
        categories=selected_ids,
        category_labels=labels,
        fits=fits,
        request_id=request_id,
        model=model,
        raw_response=raw_response,
    )
