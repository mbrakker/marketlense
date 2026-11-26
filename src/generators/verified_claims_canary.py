"""Admission of independently verified visual facts into an isolated canary.

The visual evaluator remains shadow-only. This adapter converts its terminal
verified results into a small, source-hash-bound fact snapshot for an explicit
editorial canary; original candidate bindings remain discovery diagnostics.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from src.contracts.verified_claims import VisualClaimEvaluationResponse
from src.generators.artifact_normalization import bind_artifact_evidence_spans
from src.generators.verified_claims_recovery import (
    build_verified_claims_shadow_request,
    candidate_roster_digest,
    source_pdf_sha256,
)
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.utils.cache_utils import sha256_json
from src.utils.coercion import stripped_string_value
from src.utils.errors import AppError
from src.utils.text_normalization import normalize_for_lookup
from src.utils.verified_facts import (
    PROTECTED_METRIC_FIELDS,
    canonical_fact_text,
    validated_verified_facts,
)

_TERMINAL_VERIFIED_OUTCOMES = frozenset({"verified", "verified_after_retry"})
_TERMINAL_EVALUATION_OUTCOMES = frozenset(
    {
        *_TERMINAL_VERIFIED_OUTCOMES,
        "unresolved",
        "failed_verification",
        "skipped",
    }
)
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


def default_visual_authority_output_dir(default_output_dir: str) -> str:
    """Keep rendered canary pages short enough for PDF fingerprint sidecars."""

    return str(
        Path(str(default_output_dir or ".")).parent / "verified_claims_visual_canary"
    )


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
    visual_quarantine: Mapping[str, Any] | None = None,
    source_spans: Sequence[Mapping[str, Any]] = (),
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
        config.output_dir or default_visual_authority_output_dir(default_output_dir)
    )

    def admit(candidates: Sequence[Mapping[str, Any]]) -> VisualAuthorityAdmission:
        evaluation_candidates = [
            deepcopy(dict(candidate))
            for candidate in candidates
            if isinstance(candidate, Mapping)
        ]
        visual_evidence = deepcopy(dict(evidence_packs))
        bound_page_text: dict[int, list[str]] = {}
        raw_quarantine = (
            visual_quarantine if isinstance(visual_quarantine, Mapping) else {}
        )
        findings = raw_quarantine.get("findings")
        if (
            raw_quarantine.get("schema_version") == "1.0"
            and raw_quarantine.get("source_identity") == source_identity
            and isinstance(findings, list)
        ):
            existing_ids = {
                str(item.get("evidence_id") or "").strip()
                for item in evaluation_candidates
            }
            ids = [
                str(item["finding"].get("id") or "").strip()
                for item in findings
                if isinstance(item, dict) and isinstance(item.get("finding"), dict)
            ]
            spans_by_id: dict[str, list[Mapping[str, Any]]] = {}
            for span in source_spans:
                if isinstance(span, Mapping) and isinstance(span.get("id"), str):
                    spans_by_id.setdefault(span["id"].strip(), []).append(span)
            if len(ids) == len(findings) and len(set(ids)) == len(ids):
                for entry in findings:
                    finding = entry["finding"]
                    finding_id = str(finding.get("id") or "").strip()
                    text = finding.get("text")
                    evidence = finding.get("evidence")
                    pages = finding.get("pages")
                    references = entry.get("source_references")
                    if (
                        not finding_id
                        or finding_id in existing_ids
                        or not isinstance(text, str)
                        or not text.strip()
                        or not isinstance(evidence, str)
                        or not evidence.strip()
                        or not isinstance(pages, list)
                        or not pages
                        or any(type(page) is not int or page <= 0 for page in pages)
                        or not isinstance(references, list)
                        or not references
                    ):
                        continue
                    source_texts = []
                    bound_pages = set()
                    for ref in references:
                        if not isinstance(ref, dict):
                            break
                        reference_id = ref.get("evidence_id")
                        if not isinstance(reference_id, str):
                            break
                        matches = spans_by_id.get(reference_id, [])
                        if len(matches) != 1:
                            break
                        span = matches[0]
                        span_text = span.get("text")
                        page = span.get("page")
                        if (
                            not isinstance(span_text, str)
                            or not span_text.strip()
                            or type(page) is not int
                            or page <= 0
                            or ref.get("page") != page
                            or ref.get("text_hash") != sha256_json(span_text.strip())
                        ):
                            break
                        source_texts.append(span_text.strip())
                        bound_pages.add(page)
                    else:
                        if bound_pages != set(pages):
                            continue
                        pack = visual_evidence.get("findings")
                        if not isinstance(pack, dict) or not isinstance(
                            pack.get("findings"), list
                        ):
                            continue
                        evidence = "\n".join(source_texts)
                        for ref, source_text in zip(
                            references, source_texts, strict=True
                        ):
                            page = ref["page"]
                            values = bound_page_text.setdefault(page, [])
                            if source_text not in values:
                                values.append(source_text)
                        finding = {**finding, "evidence": evidence}
                        evaluation_candidates.append(
                            {
                                "id": finding_id,
                                "text": text,
                                "evidence_id": finding_id,
                                "evidence": evidence,
                                "pages": pages,
                                "metric": {},
                            }
                        )
                        pack["findings"].append(deepcopy(finding))
                        continue
        # Candidate pages are discovery metadata until the retained finding
        # binder resolves them.  Apply the existing direct-evidence binding
        # before rendering visual pages so a model-supplied stale page cannot
        # become the visual authority.  DocMap sections are deliberately not
        # consulted here: navigation/context is not source evidence.
        bind_artifact_evidence_spans(
            summary={},
            insights_candidates=evaluation_candidates,
            insights_final=[],
            quotes_final=[],
            doc_map={},
            evidence_packs=(visual_evidence),
        )
        evaluation_candidates = _canonical_candidate_roster(evaluation_candidates)
        request, _audit = build_verified_claims_shadow_request(
            source_identity=source_identity,
            pdf_path=resolved_pdf_path,
            output_dir=output_dir,
            report_name=report_name,
            evidence_packs=visual_evidence,
            shortlisted_insights=evaluation_candidates,
            ctx=ctx,
            dpi=config.dpi,
            recovery_enabled=config.recovery_enabled,
            recovery_limit=config.recovery_limit,
        )
        request = replace(
            request,
            source_page_text_by_physical_page={
                **{page: "\n".join(texts) for page, texts in bound_page_text.items()},
                **request.source_page_text_by_physical_page,
            },
        )
        evaluation = evaluate_shortlisted_claims(
            request=request,
            settings=settings,
            ctx=ctx,
            dependencies=config.dependencies,
        )
        return admit_visual_authority_candidates(
            candidates=evaluation_candidates,
            evaluation=evaluation,
            source_identity=source_identity,
            doc_map={},
            evidence_packs=visual_evidence,
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
        "outcome_counts": {},
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
    expected_roster_digest = candidate_roster_digest(
        _canonical_candidate_roster(raw_candidate_list)
    )
    actual_roster_digest = _response_field(evaluation, "candidate_roster_digest")
    audit["candidate_roster_digest"] = expected_roster_digest
    if actual_roster_digest and actual_roster_digest != expected_roster_digest:
        audit["evaluation_candidate_roster_digest"] = actual_roster_digest
        return _empty_admission(audit, "evaluation_candidate_roster_mismatch")
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
    malformed_result_ids: set[str] = set()
    snapshot_mismatch_ids: set[str] = set()
    canonical_candidates_by_id = {
        _candidate_id(candidate): candidate
        for candidate in candidate_list
        if _candidate_id(candidate)
    }
    for raw_result in raw_results:
        candidate_id = _result_field(raw_result, "candidate_id")
        if not candidate_id:
            _record_quarantine(audit, "", "candidate_id_missing")
            continue
        audit["evaluated_count"] += 1
        if candidate_id in results_by_id:
            duplicate_result_ids.add(candidate_id)
            continue
        outcome = _result_field(raw_result, "outcome").lower()
        if outcome not in _TERMINAL_EVALUATION_OUTCOMES:
            malformed_result_ids.add(candidate_id)
            continue
        expected_candidate = canonical_candidates_by_id.get(candidate_id)
        if expected_candidate is not None and not _result_matches_candidate_snapshot(
            raw_result, expected_candidate
        ):
            snapshot_mismatch_ids.add(candidate_id)
            continue
        results_by_id[candidate_id] = raw_result
        outcome_counts = audit["outcome_counts"]
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    expected_ids = set(candidate_groups)
    result_ids = set(results_by_id)
    missing_ids = (
        expected_ids - result_ids - malformed_result_ids - snapshot_mismatch_ids
    )
    extra_ids = result_ids - expected_ids
    for candidate_id in sorted(duplicate_result_ids):
        _record_quarantine(audit, candidate_id, "duplicate_evaluation_id")
    for candidate_id in sorted(missing_ids):
        _record_quarantine(audit, candidate_id, "evaluation_missing")
    for candidate_id in sorted(extra_ids):
        _record_quarantine(audit, candidate_id, "evaluation_unexpected_id")
    for candidate_id in sorted(malformed_result_ids):
        _record_quarantine(audit, candidate_id, "evaluation_outcome_invalid")
    for candidate_id in sorted(snapshot_mismatch_ids):
        _record_quarantine(
            audit, candidate_id, "evaluation_candidate_snapshot_mismatch"
        )
    audit["coverage_complete"] = (
        bool(expected_ids)
        and len(raw_candidate_list) == len(candidates)
        and all(_candidate_id(candidate) for candidate in raw_candidate_list)
        and not missing_ids
        and not extra_ids
        and not duplicate_result_ids
        and not malformed_result_ids
        and not snapshot_mismatch_ids
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
        outcome = _result_field(result, "outcome").lower()
        if outcome not in _TERMINAL_VERIFIED_OUTCOMES:
            _record_quarantine(audit, candidate_id, f"outcome_{outcome}")
            continue
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

    try:
        canonical_facts = validated_verified_facts(
            {"verified_facts": list(facts_by_id.values())}
        )
    except AppError:
        return _empty_admission(audit, "verified_fact_snapshot_invalid")
    facts_by_id = canonical_facts
    unique_projections = [_fact_projection(fact) for fact in facts_by_id.values()]
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

    corrected_binding_reason = _corrected_binding_conflict_reason(
        candidate=candidate,
        result=result,
        raw_fact=raw_fact,
        expected_source_identity=expected_source_identity,
        supporting_pages=supporting_pages,
    )
    if corrected_binding_reason:
        return corrected_binding_reason, {}

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


def _corrected_binding_conflict_reason(
    *,
    candidate: Mapping[str, Any],
    result: Any,
    raw_fact: Mapping[str, Any],
    expected_source_identity: str,
    supporting_pages: Sequence[int],
) -> str:
    """Reject corrected-binding metadata that contradicts the final fact.

    A changed proposition is authoritative only through its complete verified
    fact.  The optional corrected-binding fields are therefore either empty
    (the normal visual-generator representation) or a complete, source-
    consistent binding.  A retained binding is allowed only for an unchanged
    proposition and must match the requested candidate exactly.
    """

    status = _result_field(result, "corrected_source_binding_status").lower()
    status = status or "unbound"
    if status not in {"retained", "unbound", "independently_bound"}:
        return "verified_fact_corrected_binding_conflict"

    raw_ids = _result_value(result, "corrected_evidence_ids")
    if raw_ids is None:
        corrected_ids: list[str] = []
    elif isinstance(raw_ids, list) and all(
        isinstance(item, str) and item.strip() for item in raw_ids
    ):
        corrected_ids = [item.strip() for item in raw_ids]
    else:
        return "verified_fact_corrected_binding_conflict"
    if len(set(corrected_ids)) != len(corrected_ids):
        return "verified_fact_corrected_binding_conflict"

    raw_spans = _result_value(result, "corrected_evidence_spans")
    if raw_spans is None:
        corrected_spans: list[dict[str, Any]] = []
    elif isinstance(raw_spans, list) and all(
        isinstance(item, Mapping) for item in raw_spans
    ):
        corrected_spans = [dict(item) for item in raw_spans]
    else:
        return "verified_fact_corrected_binding_conflict"

    raw_metric = _result_value(result, "corrected_metric_binding")
    if raw_metric is None:
        corrected_metric: dict[str, Any] = {}
    elif isinstance(raw_metric, Mapping):
        corrected_metric = dict(raw_metric)
    else:
        return "verified_fact_corrected_binding_conflict"

    final_claim = _result_field(result, "final_claim")
    candidate_claim = _field_text(candidate, "text") or _field_text(candidate, "claim")
    same_proposition = bool(final_claim) and normalize_for_lookup(
        final_claim
    ) == normalize_for_lookup(candidate_claim)

    if status == "unbound":
        # The authoritative verified_fact is the only binding for a changed
        # proposition.  Carrying any copied discovery fields here would make
        # the old candidate look authoritative again.
        if corrected_ids or corrected_spans or corrected_metric:
            return "verified_fact_corrected_binding_conflict"
        return ""

    candidate_ids = _candidate_evidence_ids(candidate)
    if status == "retained":
        if not same_proposition:
            return "verified_fact_corrected_binding_conflict"
        if corrected_ids != candidate_ids:
            return "verified_fact_corrected_binding_conflict"
        candidate_spans = _result_list_of_mappings(candidate, "evidence_spans")
        if candidate_spans is None or _canonical_evidence_spans(
            corrected_spans
        ) != _canonical_evidence_spans(candidate_spans):
            return "verified_fact_corrected_binding_conflict"
        if _canonical_metric(corrected_metric) != _canonical_metric(
            candidate.get("metric")
        ):
            return "verified_fact_corrected_binding_conflict"
        candidate_pages = set(_pages(candidate.get("pages")))
        candidate_pages.update(
            page for span in candidate_spans for page in _pages([span.get("page")])
        )
        if not candidate_pages or not candidate_pages.issubset(set(supporting_pages)):
            return "verified_fact_corrected_binding_conflict"
        return ""

    # An explicitly independently-bound representation is accepted for
    # callers that carry corrected evidence metadata, but every protected
    # binding dimension must agree with the authoritative fact and pages.
    if not corrected_ids or not corrected_spans or not corrected_metric:
        return "verified_fact_corrected_binding_conflict"
    fact_metric = raw_fact.get("metric")
    if _protected_metric(corrected_metric) != _protected_metric(fact_metric):
        return "verified_fact_corrected_binding_conflict"
    span_ids: list[str] = []
    span_pages: list[int] = []
    for span in corrected_spans:
        evidence_id = _field_text(span, "evidence_id")
        page = span.get("page")
        if not evidence_id or type(page) is not int or page <= 0:
            return "verified_fact_corrected_binding_conflict"
        span_ids.append(evidence_id)
        span_pages.append(page)
        span_identity = _field_text(span, "source_identity")
        if span_identity and span_identity != expected_source_identity:
            return "verified_fact_corrected_binding_conflict"
    if set(span_ids) != set(corrected_ids) or set(span_pages) != set(supporting_pages):
        return "verified_fact_corrected_binding_conflict"
    return ""


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
        "evidence": canonical_fact_text(fact),
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
    packed_facts = []
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
        packed_fact = deepcopy(dict(fact))
        supporting_pages = packed_fact.get("supporting_physical_pages")
        if isinstance(supporting_pages, list):
            packed_fact["supporting_physical_pages"] = sorted(supporting_pages)
        provenance = packed_fact.get("provenance")
        if isinstance(provenance, Mapping):
            packed_provenance = deepcopy(dict(provenance))
            inspected_pages = packed_provenance.get("inspected_physical_pages")
            if isinstance(inspected_pages, list):
                packed_provenance["inspected_physical_pages"] = sorted(inspected_pages)
            packed_fact["provenance"] = packed_provenance
        packed_facts.append(packed_fact)
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
            "verified_facts": packed_facts,
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


def _response_field(value: Any, field_name: str) -> str:
    if isinstance(value, Mapping):
        return stripped_string_value(value.get(field_name)).strip()
    return stripped_string_value(getattr(value, field_name, "")).strip()


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


def _result_value(value: Any, field_name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


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


def _canonical_candidate_roster(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Remove only equivalent score-only duplicate representations."""

    raw = [
        deepcopy(dict(candidate))
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in raw:
        candidate_id = _candidate_id(candidate)
        if candidate_id:
            groups.setdefault(candidate_id, []).append(candidate)

    roster: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in raw:
        candidate_id = _candidate_id(candidate)
        if not candidate_id or candidate_id in seen_ids:
            continue
        group = groups[candidate_id]
        if len({_candidate_signature(item) for item in group}) == 1:
            roster.append(candidate)
        else:
            roster.extend(group)
        seen_ids.add(candidate_id)
    return roster


def _result_matches_candidate_snapshot(
    result: Any, candidate: Mapping[str, Any]
) -> bool:
    """Bind a response without a roster digest to its requested candidate."""

    original_claim = _result_field(result, "original_claim")
    candidate_text = _field_text(candidate, "text") or _field_text(candidate, "claim")
    if not original_claim or normalize_for_lookup(
        original_claim
    ) != normalize_for_lookup(candidate_text):
        return False
    result_evidence_ids = _result_list(result, "evidence_ids")
    if result_evidence_ids != _candidate_evidence_ids(candidate):
        return False
    result_spans = _result_list_of_mappings(result, "evidence_spans")
    candidate_spans = candidate.get("evidence_spans")
    if not isinstance(candidate_spans, list) or result_spans is None:
        return False
    if _canonical_evidence_spans(result_spans) != _canonical_evidence_spans(
        candidate_spans
    ):
        return False
    result_metric = _result_mapping(result, "original_metric_binding")
    return bool(result_metric) and (
        _canonical_metric(result_metric) == _canonical_metric(candidate.get("metric"))
    )


def _result_list(value: Any, field_name: str) -> list[str]:
    raw = (
        value.get(field_name)
        if isinstance(value, Mapping)
        else getattr(value, field_name, [])
    )
    if not isinstance(raw, list):
        return []
    return [item for item in (str(value or "").strip() for value in raw) if item]


def _result_list_of_mappings(
    value: Any, field_name: str
) -> list[dict[str, Any]] | None:
    raw = (
        value.get(field_name)
        if isinstance(value, Mapping)
        else getattr(value, field_name, None)
    )
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        return None
    return [dict(item) for item in raw]


def _canonical_evidence_spans(
    value: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [{str(key): deepcopy(item) for key, item in span.items()} for span in value]


def _canonical_metric(value: Any) -> dict[str, Any]:
    metric = dict(value) if isinstance(value, Mapping) else {}
    canonical = {
        field_name: deepcopy(
            metric.get(field_name, [] if field_name == "observations" else "")
        )
        for field_name in PROTECTED_METRIC_FIELDS
    }
    canonical.update(
        {
            str(key): deepcopy(item)
            for key, item in metric.items()
            if str(key) not in PROTECTED_METRIC_FIELDS
        }
    )
    if canonical["observations"] in (None, "", []):
        canonical["observations"] = []
    for field_name in PROTECTED_METRIC_FIELDS:
        if field_name != "observations" and canonical[field_name] is None:
            canonical[field_name] = ""
    return canonical


def _protected_metric(value: Any) -> dict[str, Any]:
    metric = dict(value) if isinstance(value, Mapping) else {}
    return {
        field_name: deepcopy(
            metric.get(field_name, [] if field_name == "observations" else "")
        )
        for field_name in PROTECTED_METRIC_FIELDS
    }


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
