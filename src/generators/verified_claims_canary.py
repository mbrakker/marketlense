"""Admission of shadow visual results into an isolated editorial canary.

This module is deliberately a narrow adapter.  The visual evaluator remains
shadow-only; this code only decides which already-selected candidates may be
used by an explicitly opted-in generation run.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from src.contracts.verified_claims import VisualClaimEvaluationResponse
from src.generators.artifact_normalization import (
    METRIC_BINDING_FIELDS,
    METRIC_FIELDS,
    artifact_evidence_span_index,
    eligible_final_insight_candidates,
)
from src.generators.verified_claims_recovery import (
    build_verified_claims_shadow_request,
    source_pdf_sha256,
)
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    _claims_have_identical_proposition,
    evaluate_shortlisted_claims,
)
from src.utils.cache_utils import sha256_json
from src.utils.coercion import stripped_string_value
from src.utils.errors import AppError
from src.utils.text_normalization import normalize_for_lookup

_TERMINAL_VERIFIED_OUTCOMES = {"verified", "verified_after_retry"}
_INDEPENDENT_BINDING_STATUSES = {"bound", "independently_bound"}


@dataclass(frozen=True)
class VisualAuthorityAdmission:
    """Private canary admission result; not a persisted/public contract."""

    admitted_candidates: List[Dict[str, Any]]
    digest: str
    audit: Dict[str, Any]


@dataclass(frozen=True)
class VisualAuthorityCanaryConfig:
    """Explicit opt-in settings for one isolated visual canary run."""

    source_identity: str
    output_dir: str = ""
    dpi: int = 216
    recovery_enabled: bool = False
    recovery_limit: int = 3
    dependencies: VerifiedClaimsVisualDependencies | None = None


def build_visual_authority_admitter(
    *,
    config: VisualAuthorityCanaryConfig,
    pdf_path: str,
    default_output_dir: str,
    report_name: str,
    evidence_packs: Mapping[str, Any],
    ctx: Any,
    settings: Any,
    doc_map: Mapping[str, Any],
):
    """Build the explicit canary callback consumed by artifact generation."""

    source_identity = str(config.source_identity or "").strip()
    if not source_identity or not source_pdf_sha256(source_identity):
        raise AppError(
            code="visual_authority_canary_source_hash_missing",
            message="Visual authority canary requires a hash-bearing source identity",
            retryable=False,
        )
    resolved_pdf_path = str(pdf_path or "").strip()
    if not resolved_pdf_path:
        raise AppError(
            code="visual_authority_canary_pdf_missing",
            message="Visual authority canary requires the retained source PDF",
            retryable=False,
        )
    output_dir = str(
        config.output_dir
        or Path(default_output_dir) / "verified_claims_visual_canary"
    )

    def admit(candidates: Sequence[Mapping[str, Any]]) -> VisualAuthorityAdmission:
        request, _audit = build_verified_claims_shadow_request(
            source_identity=source_identity,
            pdf_path=resolved_pdf_path,
            output_dir=output_dir,
            report_name=report_name,
            evidence_packs=evidence_packs,
            shortlisted_insights=candidates,
            ctx=ctx,
            dpi=config.dpi,
            recovery_enabled=config.recovery_enabled,
            recovery_limit=config.recovery_limit,
        )
        evaluation = evaluate_shortlisted_claims(
            request=request,
            settings=settings,
            ctx=ctx,
            dependencies=config.dependencies,
        )
        return admit_visual_authority_candidates(
            candidates=candidates,
            evaluation=evaluation,
            source_identity=source_identity,
            doc_map=doc_map,
            evidence_packs=evidence_packs,
        )

    return admit


def admit_visual_authority_candidates(
    *,
    candidates: Sequence[Mapping[str, Any]],
    evaluation: VisualClaimEvaluationResponse,
    source_identity: str,
    doc_map: Mapping[str, Any],
    evidence_packs: Mapping[str, Any],
) -> VisualAuthorityAdmission:
    """Admit only source-bound terminal visual results.

    The PDF hash itself is checked by ``evaluate_shortlisted_claims`` before
    it returns.  Requiring the same hash-bearing identity here prevents a
    caller from accidentally combining a response from another source with
    this candidate pool.
    """

    candidate_list = [
        deepcopy(dict(candidate))
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    audit: Dict[str, Any] = {
        "enabled": True,
        "evaluated_count": 0,
        "admitted_count": 0,
        "quarantined_count": 0,
        "quarantined": [],
    }

    expected_source_identity = str(source_identity or "").strip()
    if not source_pdf_sha256(expected_source_identity):
        return _empty_admission(audit, "source_pdf_hash_missing")

    if not _response_is_shadow(evaluation):
        return _empty_admission(audit, "evaluation_not_shadow")
    raw_results = _response_claims(evaluation)
    if raw_results is None:
        return _empty_admission(audit, "evaluation_claims_malformed")

    authoritative_candidates = eligible_final_insight_candidates(candidate_list)
    authoritative_by_id = {
        _candidate_id(candidate): candidate
        for candidate in authoritative_candidates
        if _candidate_id(candidate)
    }
    candidate_ids = {
        _candidate_id(candidate)
        for candidate in candidate_list
        if _candidate_id(candidate)
    }
    conflicting_ids = candidate_ids - set(authoritative_by_id)
    span_index = artifact_evidence_span_index(
        doc_map=dict(doc_map or {}), evidence_packs=dict(evidence_packs or {})
    )
    results_by_id: Dict[str, Any] = {}
    for raw_result in raw_results:
        candidate_id = _result_field(raw_result, "candidate_id")
        if not candidate_id:
            _record_quarantine(audit, "", "candidate_id_missing")
            continue
        audit["evaluated_count"] += 1
        if candidate_id in results_by_id:
            _record_quarantine(audit, candidate_id, "duplicate_evaluation_id")
            results_by_id.pop(candidate_id, None)
            continue
        results_by_id[candidate_id] = raw_result

    admitted: List[Dict[str, Any]] = []
    for candidate_id, result in results_by_id.items():
        candidate = authoritative_by_id.get(candidate_id)
        if candidate is None:
            reason = (
                "candidate_factual_conflict"
                if candidate_id in conflicting_ids
                else "candidate_not_authoritative"
            )
            _record_quarantine(audit, candidate_id, reason)
            continue
        reason, admitted_candidate = _admit_one(
            candidate=candidate,
            result=result,
            expected_source_identity=expected_source_identity,
            span_index=span_index,
        )
        if reason:
            _record_quarantine(audit, candidate_id, reason)
            continue
        admitted.append(admitted_candidate)

    candidate_order = {
        _candidate_id(candidate): index
        for index, candidate in enumerate(candidate_list)
        if _candidate_id(candidate)
    }
    admitted.sort(
        key=lambda item: candidate_order.get(
            _candidate_id(item), len(candidate_order)
        )
    )
    audit["admitted_count"] = len(admitted)
    audit["quarantined_count"] = len(audit["quarantined"])
    digest = sha256_json(
        {
            "source_identity": expected_source_identity,
            "admitted_candidates": admitted,
        }
    )
    audit["digest"] = digest
    return VisualAuthorityAdmission(
        admitted_candidates=admitted,
        digest=digest,
        audit=audit,
    )


def _admit_one(
    *,
    candidate: Dict[str, Any],
    result: Any,
    expected_source_identity: str,
    span_index: Dict[str, List[Dict[str, Any]]],
) -> tuple[str, Dict[str, Any]]:
    outcome = _result_field(result, "outcome").lower()
    if outcome not in _TERMINAL_VERIFIED_OUTCOMES:
        return "outcome_not_verified", {}
    if _result_field(result, "source_identity") != expected_source_identity:
        return "source_identity_mismatch", {}

    original_evidence_id = _field_text(candidate, "evidence_id")
    if not original_evidence_id:
        return "candidate_evidence_id_missing", {}
    if _result_ids(result, "evidence_ids") != [original_evidence_id]:
        return "original_evidence_binding_mismatch", {}
    if not _metric_matches(
        _result_mapping(result, "original_metric_binding"),
        _complete_metric(candidate.get("metric")),
    ):
        return "original_metric_binding_mismatch", {}
    reason = _validate_result_binding(
        result=result,
        evidence_ids=[original_evidence_id],
        spans=_result_list(result, "evidence_spans"),
        span_index=span_index,
        source_identity=expected_source_identity,
    )
    if reason:
        return reason, {}
    if not _positive_int(_result_field(result, "physical_page")):
        return "physical_page_missing", {}

    final_claim = _result_field(result, "final_claim").strip()
    original_claim = _field_text(candidate, "text")
    binding_status = _result_field(result, "corrected_source_binding_status").lower()
    if not final_claim:
        return "final_claim_missing", {}
    if binding_status == "retained":
        if not _claims_have_identical_proposition(original_claim, final_claim):
            return "retained_binding_changed", {}
        if _result_ids(result, "corrected_evidence_ids") != [original_evidence_id]:
            return "retained_binding_mismatch", {}
        if not _metric_matches(
            _result_mapping(result, "corrected_metric_binding"),
            _complete_metric(candidate.get("metric")),
        ):
            return "retained_metric_binding_mismatch", {}
        corrected_spans = _result_list(result, "corrected_evidence_spans")
        reason = _validate_result_binding(
            result=result,
            evidence_ids=[original_evidence_id],
            spans=corrected_spans,
            span_index=span_index,
            source_identity=expected_source_identity,
        )
        if reason:
            return reason, {}
        admitted = deepcopy(candidate)
        admitted["text"] = final_claim
        return "", admitted

    if binding_status == "unbound":
        return "corrected_binding_unbound", {}
    if binding_status not in _INDEPENDENT_BINDING_STATUSES:
        return "corrected_binding_status_invalid", {}

    corrected_ids = _result_ids(result, "corrected_evidence_ids")
    if len(corrected_ids) != 1:
        return "corrected_evidence_binding_ambiguous", {}
    corrected_id = corrected_ids[0]
    corrected_metric = _result_mapping(result, "corrected_metric_binding")
    if not _complete_metric_is_present(corrected_metric):
        return "corrected_metric_binding_incomplete", {}
    corrected_spans = _result_list(result, "corrected_evidence_spans")
    reason = _validate_result_binding(
        result=result,
        evidence_ids=[corrected_id],
        spans=corrected_spans,
        span_index=span_index,
        source_identity=expected_source_identity,
    )
    if reason:
        return reason, {}
    canonical_spans = _canonical_spans(span_index, corrected_id)
    if not canonical_spans:
        return "corrected_evidence_id_unknown", {}
    admitted = deepcopy(candidate)
    admitted["text"] = final_claim
    admitted["evidence_id"] = corrected_id
    admitted["pages"] = _span_pages(canonical_spans)
    admitted["evidence_spans"] = deepcopy(canonical_spans)
    canonical_text = _canonical_excerpt(canonical_spans)
    if canonical_text:
        admitted["evidence"] = canonical_text
    admitted["metric"] = _complete_metric(corrected_metric)
    return "", admitted


def _validate_result_binding(
    *,
    result: Any,
    evidence_ids: List[str],
    spans: List[Any],
    span_index: Dict[str, List[Dict[str, Any]]],
    source_identity: str,
) -> str:
    if not spans:
        return "evidence_spans_missing"
    expected_ids = {value.casefold() for value in evidence_ids}
    matched_pages: set[int] = set()
    for raw_span in spans:
        if not isinstance(raw_span, Mapping):
            return "evidence_span_malformed"
        span_id = _field_text(raw_span, "evidence_id")
        if span_id.casefold() not in expected_ids:
            return "evidence_span_id_mismatch"
        for field_name in ("source_identity", "source_id"):
            declared_source = _field_text(raw_span, field_name)
            if declared_source and declared_source != source_identity:
                return "evidence_span_source_mismatch"
        page = _positive_int(raw_span.get("page"))
        if page is None:
            return "evidence_span_page_missing"
        matching = [
            span
            for span in _canonical_spans(span_index, span_id)
            if _positive_int(span.get("page")) == page
        ]
        if not matching:
            return "evidence_page_not_supported"
        raw_text = _field_text(raw_span, "text")
        if raw_text and not any(
            _texts_are_compatible(raw_text, _field_text(span, "text"))
            for span in matching
            if _field_text(span, "text")
        ):
            return "evidence_excerpt_mismatch"
        matched_pages.add(page)
    if not matched_pages:
        return "evidence_page_missing"
    physical_page = _positive_int(_result_field(result, "physical_page"))
    known_pages = {
        page
        for evidence_id in evidence_ids
        for page in _span_pages(_canonical_spans(span_index, evidence_id))
    }
    if physical_page is None or physical_page not in known_pages:
        # A materially corrected result may be visually inspected on a page
        # represented only by the corrected binding, so this check is applied
        # by the caller to the supplied binding pages instead.
        corrected_ids = _result_ids(result, "corrected_evidence_ids")
        corrected_pages = {
            page
            for evidence_id in corrected_ids
            for page in _span_pages(_canonical_spans(span_index, evidence_id))
        }
        if physical_page is None or physical_page not in corrected_pages:
            return "physical_page_not_supported"
    return ""


def _empty_admission(audit: Dict[str, Any], reason: str) -> VisualAuthorityAdmission:
    audit["quarantined_count"] = 0
    audit["terminal_error"] = reason
    digest = sha256_json({"terminal_error": reason})
    audit["digest"] = digest
    return VisualAuthorityAdmission(admitted_candidates=[], digest=digest, audit=audit)


def _record_quarantine(audit: Dict[str, Any], candidate_id: str, reason: str) -> None:
    quarantined = audit["quarantined"]
    quarantined.append({"candidate_id": candidate_id, "reason": reason})


def _response_is_shadow(response: Any) -> bool:
    raw = response.get("shadow_mode") if isinstance(response, Mapping) else getattr(
        response, "shadow_mode", False
    )
    return raw is True


def _response_claims(response: Any) -> List[Any] | None:
    claims = response.get("claims") if isinstance(response, Mapping) else getattr(
        response, "claims", None
    )
    return claims if isinstance(claims, list) else None


def _result_field(value: Any, field_name: str) -> str:
    if isinstance(value, Mapping):
        return stripped_string_value(value.get(field_name))
    return stripped_string_value(getattr(value, field_name, ""))


def _result_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    raw = value.get(field_name) if isinstance(value, Mapping) else getattr(
        value, field_name, {}
    )
    return dict(raw) if isinstance(raw, Mapping) else {}


def _result_list(value: Any, field_name: str) -> List[Any]:
    raw = value.get(field_name) if isinstance(value, Mapping) else getattr(
        value, field_name, []
    )
    return list(raw) if isinstance(raw, list) else []


def _result_ids(value: Any, field_name: str) -> List[str]:
    return [
        stripped_string_value(item).strip()
        for item in _result_list(value, field_name)
        if stripped_string_value(item).strip()
    ]


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    return stripped_string_value(candidate.get("id")).strip()


def _field_text(value: Mapping[str, Any], field_name: str) -> str:
    return stripped_string_value(value.get(field_name)).strip()


def _complete_metric(metric: Any) -> Dict[str, Any]:
    metric = metric if isinstance(metric, Mapping) else {}
    return {
        field_name: deepcopy(metric.get(field_name, ""))
        for field_name in (*METRIC_FIELDS, *METRIC_BINDING_FIELDS)
    }


def _complete_metric_is_present(metric: Mapping[str, Any]) -> bool:
    if not isinstance(metric, Mapping):
        return False
    return all(
        field_name in metric
        for field_name in (*METRIC_FIELDS, *METRIC_BINDING_FIELDS)
    )


def _metric_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if not _complete_metric_is_present(left):
        return False
    return _complete_metric(left) == _complete_metric(right)


def _canonical_spans(
    span_index: Dict[str, List[Dict[str, Any]]], evidence_id: str
) -> List[Dict[str, Any]]:
    return span_index.get(str(evidence_id).casefold(), [])


def _span_pages(spans: Sequence[Mapping[str, Any]]) -> List[int]:
    return list(
        dict.fromkeys(
            page
            for span in spans
            for page in [_positive_int(span.get("page"))]
            if page is not None
        )
    )


def _canonical_excerpt(spans: Sequence[Mapping[str, Any]]) -> str:
    return " ".join(
        dict.fromkeys(
            _field_text(span, "text") for span in spans if _field_text(span, "text")
        )
    )


def _texts_are_compatible(left: str, right: str) -> bool:
    left_key = normalize_for_lookup(left)
    right_key = normalize_for_lookup(right)
    return bool(
        left_key
        and right_key
        and (left_key == right_key or left_key in right_key or right_key in left_key)
    )


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


__all__ = [
    "VisualAuthorityCanaryConfig",
    "VisualAuthorityAdmission",
    "admit_visual_authority_candidates",
    "build_visual_authority_admitter",
]
