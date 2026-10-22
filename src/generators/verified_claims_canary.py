"""Admission of independently verified visual facts into an isolated canary.

The visual evaluator remains shadow-only. This adapter converts its terminal
verified results into a small, source-hash-bound fact snapshot for an explicit
editorial canary; original candidate bindings remain discovery diagnostics.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from src.contracts.verified_claims import VisualClaimEvaluationResponse
from src.generators.verified_claims_recovery import (
    build_verified_claims_shadow_request,
    source_pdf_sha256,
)
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.utils.cache_utils import sha256_json
from src.utils.coercion import stripped_string_value
from src.utils.errors import AppError

_TERMINAL_VERIFIED_OUTCOMES = frozenset({"verified", "verified_after_retry"})
_SCORE_ONLY_FIELDS = frozenset(
    {
        "editorial_score",
        "relevance_score",
        "score",
        "rank",
        "selection_rank",
        "_selection_score",
    }
)


@dataclass(frozen=True)
class VisualAuthorityAdmission:
    """Private verified-fact canary result; not a persisted/public contract."""

    admitted_candidates: List[Dict[str, Any]] = field(default_factory=list)
    verified_facts: List[Dict[str, Any]] = field(default_factory=list)
    verified_evidence_packs: Dict[str, Any] = field(default_factory=dict)
    digest: str = ""
    audit: Dict[str, Any] = field(default_factory=dict)


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

    del doc_map
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
        config.output_dir or Path(default_output_dir) / "verified_claims_visual_canary"
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
            doc_map={},
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
    """Project complete terminal visual results into verified facts.

    doc_map and evidence_packs are accepted for the existing callback boundary
    and discovery trace. They are never used to authorize a fact.
    """

    del doc_map, evidence_packs
    expected_source_identity = str(source_identity or "").strip()
    expected_sha = source_pdf_sha256(expected_source_identity)
    audit: Dict[str, Any] = {
        "enabled": True,
        "evaluated_count": 0,
        "expected_count": 0,
        "admitted_count": 0,
        "verified_fact_count": 0,
        "quarantined_count": 0,
        "coverage_complete": False,
        "quarantined": [],
    }
    if not expected_sha:
        return _empty_admission(audit, "source_pdf_hash_missing")
    if not _response_is_shadow(evaluation):
        return _empty_admission(audit, "evaluation_not_shadow")
    raw_results = _response_claims(evaluation)
    if raw_results is None:
        return _empty_admission(audit, "evaluation_claims_malformed")

    raw_candidate_list = [
        deepcopy(dict(candidate))
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    candidate_groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in raw_candidate_list:
        candidate_id = _candidate_id(candidate)
        if candidate_id:
            candidate_groups.setdefault(candidate_id, []).append(candidate)
        else:
            _record_quarantine(audit, "", "candidate_id_missing")
    audit["expected_count"] = len(candidate_groups)
    conflicting_ids = {
        candidate_id
        for candidate_id, group in candidate_groups.items()
        if len({_candidate_signature(item) for item in group}) > 1
    }
    for candidate_id in sorted(conflicting_ids):
        _record_quarantine(audit, candidate_id, "candidate_factual_conflict")

    # Equivalent representations are one expected fact.  Keep the first
    # source-order representation only after the score-free factual signature
    # has established that the duplicates are equivalent.  Conflicting IDs
    # remain in the expected set so coverage fails closed below.
    candidate_list: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    for candidate in raw_candidate_list:
        candidate_id = _candidate_id(candidate)
        if (
            not candidate_id
            or candidate_id in seen_candidate_ids
            or candidate_id in conflicting_ids
        ):
            continue
        seen_candidate_ids.add(candidate_id)
        candidate_list.append(candidate)

    results_by_id: dict[str, Any] = {}
    duplicate_result_ids: set[str] = set()
    for raw_result in raw_results:
        candidate_id = _result_field(raw_result, "candidate_id")
        if not candidate_id:
            _record_quarantine(audit, "", "candidate_id_missing")
            continue
        audit["evaluated_count"] += 1
        if candidate_id in results_by_id:
            duplicate_result_ids.add(candidate_id)
            continue
        results_by_id[candidate_id] = raw_result

    expected_ids = set(candidate_groups)
    result_ids = set(results_by_id)
    missing_ids = expected_ids - result_ids
    extra_ids = result_ids - expected_ids
    for candidate_id in sorted(duplicate_result_ids):
        _record_quarantine(audit, candidate_id, "duplicate_evaluation_id")
    for candidate_id in sorted(missing_ids):
        _record_quarantine(audit, candidate_id, "evaluation_missing")
    for candidate_id in sorted(extra_ids):
        _record_quarantine(audit, candidate_id, "evaluation_unexpected_id")
    audit["coverage_complete"] = (
        bool(expected_ids)
        and not missing_ids
        and not extra_ids
        and not duplicate_result_ids
        and not conflicting_ids
        and audit["evaluated_count"] == len(expected_ids)
    )
    if not audit["coverage_complete"]:
        audit["quarantined_count"] = len(audit["quarantined"])
        return _empty_admission(audit, "evaluation_coverage_incomplete")

    facts: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    for candidate in candidate_list:
        candidate_id = _candidate_id(candidate)
        if not candidate_id or candidate_id in conflicting_ids:
            continue
        result = results_by_id[candidate_id]
        reason, fact = _verified_fact_from_result(
            candidate=candidate,
            result=result,
            expected_source_identity=expected_source_identity,
            expected_sha=expected_sha,
        )
        if reason:
            _record_quarantine(audit, candidate_id, reason)
            continue
        facts.append(fact)
        projections.append(_fact_projection(fact))

    facts_by_id: dict[str, dict[str, Any]] = {}
    unique_projections: list[dict[str, Any]] = []
    for fact, projection in zip(facts, projections, strict=True):
        fact_id = str(fact["fact_id"])
        if fact_id in facts_by_id:
            _record_quarantine(audit, fact_id, "duplicate_verified_fact_id")
            continue
        facts_by_id[fact_id] = fact
        unique_projections.append(projection)

    verified_evidence_packs = _verified_evidence_packs(list(facts_by_id.values()))
    audit["admitted_count"] = len(unique_projections)
    audit["verified_fact_count"] = len(facts_by_id)
    audit["quarantined_count"] = len(audit["quarantined"])
    digest = sha256_json(
        {
            "source_identity": expected_source_identity,
            "verified_facts": list(facts_by_id.values()),
        }
    )
    audit["digest"] = digest
    return VisualAuthorityAdmission(
        admitted_candidates=unique_projections,
        verified_facts=list(facts_by_id.values()),
        verified_evidence_packs=verified_evidence_packs,
        digest=digest,
        audit=audit,
    )


def _verified_fact_from_result(
    *,
    candidate: Mapping[str, Any],
    result: Any,
    expected_source_identity: str,
    expected_sha: str,
) -> tuple[str, dict[str, Any]]:
    if _result_field(result, "outcome").lower() not in _TERMINAL_VERIFIED_OUTCOMES:
        return "outcome_not_verified", {}
    if _result_field(result, "source_identity") != expected_source_identity:
        return "source_identity_mismatch", {}

    raw_fact = _result_mapping(result, "verified_fact")
    fact_id = _field_text(raw_fact, "fact_id")
    if fact_id and fact_id != _candidate_id(candidate):
        return "verified_fact_id_mismatch", {}
    fact_source_identity = _field_text(raw_fact, "source_identity")
    if fact_source_identity and fact_source_identity != expected_source_identity:
        return "verified_fact_source_identity_mismatch", {}
    fact_outcome = _field_text(raw_fact, "verification_outcome").lower()
    result_outcome = _result_field(result, "outcome").lower()
    if fact_outcome and fact_outcome != result_outcome:
        return "verified_fact_outcome_mismatch", {}
    statement = _field_text(raw_fact, "statement")
    metric = raw_fact.get("metric")
    if not statement:
        return "verified_fact_missing", {}
    if not isinstance(metric, Mapping):
        return "verified_fact_metric_malformed", {}
    metric_payload = deepcopy(dict(metric))
    if metric_payload.get("value") and (
        not _field_text(metric_payload, "label")
        or not _field_text(metric_payload, "unit")
    ):
        return "verified_fact_metric_incomplete", {}

    qualifiers = raw_fact.get("qualifiers", [])
    if not isinstance(qualifiers, list) or any(
        not isinstance(item, str) or not item.strip() for item in qualifiers
    ):
        return "verified_fact_qualifiers_invalid", {}

    inspected_pages = _result_pages(
        result, ("inspected_physical_pages", "physical_pages")
    )
    if not inspected_pages:
        return "verified_fact_inspected_pages_missing", {}
    result_supporting_pages = _result_pages(result, ("supporting_physical_pages",))
    fact_supporting_pages = _pages(raw_fact.get("supporting_physical_pages"))
    if (
        result_supporting_pages
        and fact_supporting_pages
        and (result_supporting_pages != fact_supporting_pages)
    ):
        return "verified_fact_supporting_pages_conflict", {}
    supporting_pages = _result_pages(result, ("supporting_physical_pages",))
    if not supporting_pages:
        raw_fact_pages = raw_fact.get("supporting_physical_pages")
        supporting_pages = _pages(raw_fact_pages)
    if not supporting_pages:
        return "verified_fact_supporting_pages_missing", {}
    if inspected_pages and not set(supporting_pages).issubset(inspected_pages):
        return "verified_fact_supporting_page_not_inspected", {}

    result_hash = _result_field(result, "source_pdf_sha256").lower()
    fact_hash = _field_text(raw_fact, "source_pdf_sha256").lower()
    if result_hash and result_hash != expected_sha:
        return "verified_fact_source_hash_mismatch", {}
    if fact_hash != expected_sha:
        return "verified_fact_source_hash_mismatch", {}

    raw_provenance = raw_fact.get("provenance")
    provenance = dict(raw_provenance) if isinstance(raw_provenance, Mapping) else {}
    source_notes = _result_mapping(result, "source_truth_notes_by_page")
    if not source_notes:
        raw_notes = provenance.get("source_truth_notes_by_page")
        source_notes = (
            {
                str(key): str(value)
                for key, value in raw_notes.items()
                if str(value).strip()
            }
            if isinstance(raw_notes, Mapping)
            else {}
        )
    if not source_notes or any(
        str(page) not in source_notes for page in supporting_pages
    ):
        return "verified_fact_source_notes_incomplete", {}

    fact = {
        "schema_version": "1.0",
        "fact_id": _candidate_id(candidate),
        "statement": statement,
        "metric": metric_payload,
        "qualifiers": [item.strip() for item in qualifiers],
        "source_identity": expected_source_identity,
        "source_pdf_sha256": expected_sha,
        "supporting_physical_pages": supporting_pages,
        "verification_outcome": _result_field(result, "outcome").lower(),
        "provenance": {
            "inspected_physical_pages": inspected_pages,
            "source_truth_notes_by_page": deepcopy(source_notes),
            "discovery_candidate_id": _candidate_id(candidate),
            "discovery_evidence_ids": _candidate_evidence_ids(candidate),
        },
    }
    return "", fact


def _fact_projection(fact: Mapping[str, Any]) -> dict[str, Any]:
    fact_id = _field_text(fact, "fact_id")
    evidence_id = f"verified-fact:{fact_id}"
    pages = _pages(fact.get("supporting_physical_pages"))
    raw_provenance = fact.get("provenance")
    notes = (
        raw_provenance.get("source_truth_notes_by_page", {})
        if isinstance(raw_provenance, Mapping)
        else {}
    )
    spans = [
        {
            "evidence_id": evidence_id,
            "source_pack": "verified_facts",
            "page": page,
            "text": _field_text(notes, str(page)) or _field_text(fact, "statement"),
            "source_identity": _field_text(fact, "source_identity"),
        }
        for page in pages
    ]
    return {
        "id": fact_id,
        "verified_fact_id": fact_id,
        "text": _field_text(fact, "statement"),
        "evidence_id": evidence_id,
        "evidence": _field_text(fact, "statement"),
        "evidence_spans": spans,
        "pages": pages,
        "metric": deepcopy(fact.get("metric") or {}),
        "source_identity": _field_text(fact, "source_identity"),
        "verified_fact": deepcopy(dict(fact)),
    }


def project_verified_facts_as_insights(
    facts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic artifact-shaped projections from verified facts."""

    return [
        _fact_projection(fact)
        for fact in facts
        if isinstance(fact, Mapping) and _field_text(fact, "fact_id")
    ]


def _verified_evidence_packs(facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    findings = []
    for fact in facts:
        projection = _fact_projection(fact)
        findings.append(
            {
                "id": projection["evidence_id"],
                "verified_fact_id": projection["verified_fact_id"],
                "text": projection["text"],
                "statement": projection["text"],
                "evidence": projection["evidence"],
                "evidence_spans": projection["evidence_spans"],
                "pages": projection["pages"],
                "metric": projection["metric"],
                "source_identity": projection["source_identity"],
            }
        )
    return {
        "findings": {
            "family_status": {
                "family": "findings",
                "source": "verified_facts",
                "status": "generated",
                "policy_action": "keep",
            },
            "findings": findings,
        },
        "verified_facts": {
            "family_status": {
                "family": "verified_facts",
                "source": "visual_verification",
                "status": "generated",
                "policy_action": "keep",
            },
            "verified_facts": [deepcopy(dict(fact)) for fact in facts],
        },
    }


def _empty_admission(audit: Dict[str, Any], reason: str) -> VisualAuthorityAdmission:
    audit["terminal_error"] = reason
    audit["digest"] = sha256_json({"terminal_error": reason})
    audit["quarantined_count"] = len(audit.get("quarantined") or [])
    return VisualAuthorityAdmission(
        admitted_candidates=[],
        verified_facts=[],
        verified_evidence_packs={},
        digest=audit["digest"],
        audit=audit,
    )


def _record_quarantine(audit: Dict[str, Any], candidate_id: str, reason: str) -> None:
    audit.setdefault("quarantined", []).append(
        {"candidate_id": candidate_id, "reason": reason}
    )


def _response_is_shadow(response: Any) -> bool:
    raw = (
        response.get("shadow_mode")
        if isinstance(response, Mapping)
        else getattr(response, "shadow_mode", False)
    )
    return raw is True


def _response_claims(response: Any) -> list[Any] | None:
    claims = (
        response.get("claims")
        if isinstance(response, Mapping)
        else getattr(response, "claims", None)
    )
    return claims if isinstance(claims, list) else None


def _result_field(value: Any, field_name: str) -> str:
    if isinstance(value, Mapping):
        return stripped_string_value(value.get(field_name)).strip()
    return stripped_string_value(getattr(value, field_name, "")).strip()


def _result_mapping(value: Any, field_name: str) -> dict[str, Any]:
    raw = (
        value.get(field_name)
        if isinstance(value, Mapping)
        else getattr(value, field_name, {})
    )
    return dict(raw) if isinstance(raw, Mapping) else {}


def _result_pages(value: Any, fields: Sequence[str]) -> list[int]:
    for field_name in fields:
        raw = (
            value.get(field_name)
            if isinstance(value, Mapping)
            else getattr(value, field_name, [])
        )
        pages = _pages(raw)
        if pages:
            return pages
    return []


def _pages(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    pages: list[int] = []
    for raw_page in value:
        if isinstance(raw_page, bool):
            continue
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    return pages


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    for key in ("id", "stable_candidate_id", "candidate_id"):
        value = _field_text(candidate, key)
        if value:
            return value
    return ""


def _candidate_signature(candidate: Mapping[str, Any]) -> str:
    payload = {
        key: deepcopy(value)
        for key, value in candidate.items()
        if key not in _SCORE_ONLY_FIELDS
    }
    return sha256_json(payload)


def _candidate_evidence_ids(candidate: Mapping[str, Any]) -> list[str]:
    values = [candidate.get("evidence_id")]
    raw_ids = candidate.get("evidence_ids")
    if isinstance(raw_ids, list):
        values.extend(raw_ids)
    ids: list[str] = []
    for value in values:
        text = stripped_string_value(value).strip()
        if text and text not in ids:
            ids.append(text)
    return ids


def _field_text(value: Mapping[str, Any], field_name: str) -> str:
    return stripped_string_value(value.get(field_name)).strip()


__all__ = [
    "VisualAuthorityCanaryConfig",
    "VisualAuthorityAdmission",
    "admit_visual_authority_candidates",
    "build_visual_authority_admitter",
    "project_verified_facts_as_insights",
]
