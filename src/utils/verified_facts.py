"""Canonical verified-fact projections used by the opt-in validation path.

Verified facts are produced by the visual authority stage.  Downstream
validation must check the integrity of that contract and the public
projections that cite it; it must not reconstruct the meaning of the source
PDF from legacy extraction packs.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any

from src.utils.errors import AppError

VERIFIED_FACT_EVIDENCE_PREFIX = "verified-fact:"
PDF_SHA256_RE = re.compile(
    r"(?:^|[|,; ])pdf-sha256[:=]([0-9a-f]{64})(?:$|[|,; ])", re.IGNORECASE
)

PROTECTED_METRIC_FIELDS = (
    "label",
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
    "subject",
    "cohort",
    "denominator",
    "observation_status",
    "forecast_status",
    "comparator",
    "baseline",
    "delta",
    "observations",
)


def verified_facts_mode(artifacts: object, validation_mode: str = "") -> bool:
    """Return whether the payload explicitly carries visual-authority facts."""

    if str(validation_mode or "").strip() == "verified_facts":
        return True
    if not isinstance(artifacts, Mapping):
        return False
    facts = artifacts.get("verified_facts")
    return isinstance(facts, list) and bool(facts)


def expected_pdf_sha256(source_identity: object) -> str:
    match = PDF_SHA256_RE.search(str(source_identity or "").strip())
    return match.group(1).lower() if match else ""


def _raw_facts(artifacts: object, evidence_packs: object) -> list[Mapping[str, Any]]:
    del evidence_packs
    values = artifacts.get("verified_facts") if isinstance(artifacts, Mapping) else None
    return [item for item in values or [] if isinstance(item, Mapping)]


def _positive_pages(value: object, *, field: str, fact_id: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise _invalid(f"{field} must contain one or more physical pages", fact_id)
    pages: list[int] = []
    for raw_page in value:
        if type(raw_page) is not int or raw_page <= 0:
            raise _invalid(f"{field} contains an invalid physical page", fact_id)
        pages.append(raw_page)
    if len(set(pages)) != len(pages):
        raise _invalid(f"{field} contains duplicate physical pages", fact_id)
    return sorted(pages)


def _invalid(message: str, fact_id: str = "") -> AppError:
    return AppError(
        code="verified_fact_snapshot_invalid",
        message=message,
        retryable=False,
        severity="error",
        context={"fact_id": fact_id} if fact_id else {},
    )


def validated_verified_facts(
    artifacts: object,
    evidence_packs: object = None,
    *,
    expected_source_identity: str = "",
    expected_pdf_sha256: str = "",
) -> dict[str, dict[str, Any]]:
    """Validate and index the complete visual-authority fact snapshot.

    The PDF hash embedded in the immutable source identity is the expected
    identity when available.  A verified fact without that binding is not
    eligible for downstream validation.
    """

    raw_facts = _raw_facts(artifacts, evidence_packs)
    if not raw_facts:
        raise _invalid("verified_facts snapshot is missing or empty")
    expected_identity = str(expected_source_identity or "").strip()
    expected_hash = (
        str(expected_pdf_sha256 or "").strip()
        or expected_pdf_sha256_from_identity(expected_identity)
    ).lower()
    facts: dict[str, dict[str, Any]] = {}
    source_identity = ""
    source_hash = ""
    for raw in raw_facts:
        fact = copy.deepcopy(dict(raw))
        fact_id = str(fact.get("fact_id") or "").strip()
        statement = str(fact.get("statement") or "").strip()
        metric = fact.get("metric")
        identity = str(fact.get("source_identity") or "").strip()
        fact_hash = str(fact.get("source_pdf_sha256") or "").strip().lower()
        outcome = str(fact.get("verification_outcome") or "").strip()
        if not fact_id or not statement or not isinstance(metric, Mapping):
            raise _invalid(
                "verified fact is missing its identity, statement, or metric",
                fact_id,
            )
        observations = metric.get("observations")
        if observations is not None and (
            not isinstance(observations, list)
            or any(not isinstance(observation, Mapping) for observation in observations)
        ):
            raise _invalid("verified fact observations are malformed", fact_id)
        if fact_id in facts:
            raise _invalid("verified fact IDs must be unique", fact_id)
        if not identity or not re.fullmatch(r"[0-9a-f]{64}", fact_hash):
            raise _invalid(
                "verified fact source identity or PDF hash is invalid", fact_id
            )
        embedded_hash = expected_pdf_sha256_from_identity(identity)
        if not embedded_hash or embedded_hash != fact_hash:
            raise _invalid(
                "verified fact PDF hash is inconsistent with source identity",
                fact_id,
            )
        if expected_identity and identity.casefold() != expected_identity.casefold():
            raise _invalid(
                "verified fact source identity conflicts with the request", fact_id
            )
        if expected_hash and fact_hash != expected_hash:
            raise _invalid(
                "verified fact PDF hash conflicts with the expected source", fact_id
            )
        if outcome not in {"verified", "verified_after_retry"}:
            raise _invalid(
                "verified fact has a non-terminal verification outcome", fact_id
            )
        supporting = _positive_pages(
            fact.get("supporting_physical_pages"),
            field="supporting_physical_pages",
            fact_id=fact_id,
        )
        provenance = fact.get("provenance")
        if not isinstance(provenance, Mapping):
            raise _invalid("verified fact provenance is missing", fact_id)
        inspected = _positive_pages(
            provenance.get("inspected_physical_pages"),
            field="provenance.inspected_physical_pages",
            fact_id=fact_id,
        )
        if not set(supporting).issubset(inspected):
            raise _invalid("supporting pages must be inspected physical pages", fact_id)
        notes = provenance.get("source_truth_notes_by_page")
        if not isinstance(notes, Mapping):
            raise _invalid("verified fact source-truth notes are missing", fact_id)
        normalized_notes = {
            str(key): str(value).strip()
            for key, value in notes.items()
            if str(value).strip()
        }
        if set(normalized_notes) != {str(page) for page in supporting}:
            raise _invalid(
                "verified fact source-truth notes do not match supporting pages",
                fact_id,
            )
        fact["supporting_physical_pages"] = supporting
        fact["provenance"] = dict(provenance)
        fact["provenance"]["inspected_physical_pages"] = inspected
        fact["provenance"]["source_truth_notes_by_page"] = normalized_notes
        facts[fact_id] = fact
        source_identity = source_identity or identity
        source_hash = source_hash or fact_hash
        if identity != source_identity or fact_hash != source_hash:
            raise _invalid(
                "verified facts contain conflicting source identities", fact_id
            )
    _validate_verified_pack_consistency(facts, evidence_packs)
    validate_verified_artifact_bindings(artifacts, facts)
    return facts


def expected_pdf_sha256_from_identity(source_identity: object) -> str:
    return expected_pdf_sha256(source_identity)


def _validate_verified_pack_consistency(
    facts: Mapping[str, Mapping[str, Any]], evidence_packs: object
) -> None:
    if not isinstance(evidence_packs, Mapping):
        return
    payload = evidence_packs.get("verified_facts")
    if not isinstance(payload, Mapping):
        return
    pack_facts = payload.get("verified_facts")
    if not isinstance(pack_facts, list):
        raise _invalid("verified_facts evidence pack is malformed")
    by_id = {
        str(item.get("fact_id") or "").strip(): item
        for item in pack_facts
        if isinstance(item, Mapping)
    }
    if set(by_id) != set(facts):
        raise _invalid("verified_facts evidence pack does not match the snapshot")
    for fact_id, fact in facts.items():
        packed = by_id[fact_id]
        if packed != fact:
            raise _invalid(
                "verified_facts evidence pack conflicts with the snapshot", fact_id
            )


def validate_verified_artifact_bindings(
    artifacts: object, facts: Mapping[str, Mapping[str, Any]]
) -> None:
    """Reject public references whose physical provenance contradicts a fact."""

    if not isinstance(artifacts, Mapping):
        return
    for family in (
        "insights_candidates",
        "insights_final",
        "quotes_final",
        "metric_spine",
        "key_figures",
        "chart_insight_cards",
    ):
        for index, item in enumerate(artifacts.get(family) or []):
            if not isinstance(item, Mapping):
                continue
            _validate_artifact_binding(
                item,
                facts,
                family=family,
                index=index,
                evidence_ids=[item.get("evidence_id")],
                spans=item.get("evidence_spans"),
            )

    summary = artifacts.get("summary")
    if isinstance(summary, Mapping):
        for index, claim in enumerate(summary.get("claim_evidence_map") or []):
            if not isinstance(claim, Mapping):
                continue
            _validate_artifact_binding(
                claim,
                facts,
                family="summary.claim_evidence_map",
                index=index,
                evidence_ids=[claim.get("evidence_id")],
                spans=claim.get("evidence_spans"),
            )

    provenance = artifacts.get("soft_copy_claim_provenance")
    if isinstance(provenance, Mapping):
        for index, claim in enumerate(provenance.get("claims") or []):
            if not isinstance(claim, Mapping):
                continue
            _validate_artifact_binding(
                claim,
                facts,
                family="soft_copy_claim_provenance",
                index=index,
                evidence_ids=claim.get("evidence_ids"),
                spans=claim.get("source_spans"),
            )


def _validate_artifact_binding(
    item: Mapping[str, Any],
    facts: Mapping[str, Mapping[str, Any]],
    *,
    family: str,
    index: int,
    evidence_ids: object,
    spans: object,
) -> None:
    raw_ids = evidence_ids if isinstance(evidence_ids, list) else [evidence_ids]
    verified_ids = [
        str(value).strip()
        for value in raw_ids
        if str(value or "").strip().startswith(VERIFIED_FACT_EVIDENCE_PREFIX)
    ]
    if not verified_ids and not (
        isinstance(spans, list)
        and any(
            str(span.get("evidence_id") or "")
            .strip()
            .startswith(VERIFIED_FACT_EVIDENCE_PREFIX)
            for span in spans
            if isinstance(span, Mapping)
        )
    ):
        return

    for evidence_id in verified_ids:
        fact = fact_for_evidence_id(facts, evidence_id)
        if fact is None:
            raise _invalid(
                f"{family}[{index}] references an unknown verified fact", evidence_id
            )
        _validate_pages(item, fact, family=family, index=index, fact_id=evidence_id)

    if spans is None:
        return
    if not isinstance(spans, list):
        raise _invalid(f"{family}[{index}] evidence spans are malformed")
    for span_index, span in enumerate(spans):
        if not isinstance(span, Mapping):
            raise _invalid(
                f"{family}[{index}] evidence span is malformed", str(span_index)
            )
        span_id = str(span.get("evidence_id") or "").strip()
        if verified_ids and span_id not in verified_ids:
            raise _invalid(
                f"{family}[{index}] evidence span does not match the item binding",
                span_id or str(span_index),
            )
        if not span_id.startswith(VERIFIED_FACT_EVIDENCE_PREFIX):
            continue
        fact = fact_for_evidence_id(facts, span_id)
        if fact is None:
            raise _invalid(
                f"{family}[{index}] evidence span references an unknown fact", span_id
            )
        _validate_span(span, fact, family=family, index=index, span_index=span_index)


def _validate_pages(
    item: Mapping[str, Any],
    fact: Mapping[str, Any],
    *,
    family: str,
    index: int,
    fact_id: str,
) -> None:
    supporting = set(fact.get("supporting_physical_pages") or [])
    raw_pages = item.get("pages")
    if raw_pages is not None:
        if not isinstance(raw_pages, list) or any(
            type(page) is not int or page <= 0 for page in raw_pages
        ):
            raise _invalid(f"{family}[{index}] pages are malformed", fact_id)
        if not set(raw_pages).issubset(supporting):
            raise _invalid(
                f"{family}[{index}] pages conflict with the verified fact", fact_id
            )
    for key in ("source_page", "physical_page", "physical_pdf_page", "page"):
        if key not in item or item.get(key) is None:
            continue
        page = item.get(key)
        if type(page) is not int or page <= 0 or page not in supporting:
            raise _invalid(
                f"{family}[{index}] physical page conflicts with the verified fact",
                fact_id,
            )


def _validate_span(
    span: Mapping[str, Any],
    fact: Mapping[str, Any],
    *,
    family: str,
    index: int,
    span_index: int,
) -> None:
    page = span.get("page")
    supporting = set(fact.get("supporting_physical_pages") or [])
    if page is not None and (
        type(page) is not int or page <= 0 or page not in supporting
    ):
        raise _invalid(
            f"{family}[{index}] span page conflicts with the verified fact",
            str(span_index),
        )
    source_pack = str(span.get("source_pack") or "").strip().casefold()
    if source_pack and source_pack != "verified_facts":
        raise _invalid(
            f"{family}[{index}] span uses a non-authoritative source pack",
            str(span_index),
        )
    for key in ("source_identity", "source_id"):
        source_identity = str(span.get(key) or "").strip()
        if source_identity and source_identity != str(
            fact.get("source_identity") or ""
        ):
            raise _invalid(
                f"{family}[{index}] span source identity conflicts with the fact",
                str(span_index),
            )


def canonical_fact_text(fact: Mapping[str, Any]) -> str:
    """Serialize structured fact fields for retrieval without PDF inference."""

    parts = [str(fact.get("statement") or "").strip()]
    for qualifier in fact.get("qualifiers") or []:
        if str(qualifier).strip():
            parts.append(str(qualifier).strip())
    metric = fact.get("metric")
    if isinstance(metric, Mapping):
        for field_name in PROTECTED_METRIC_FIELDS:
            value = metric.get(field_name)
            if field_name == "observations" and isinstance(value, list):
                for observation in value:
                    if isinstance(observation, Mapping):
                        parts.append(
                            " ".join(
                                str(observation.get(key) or "").strip()
                                for key in PROTECTED_METRIC_FIELDS
                                if key != "observations"
                                and str(observation.get(key) or "").strip()
                            )
                        )
            elif isinstance(value, (str, int, float)) and str(value).strip():
                parts.append(str(value).strip())
    return " ".join(part for part in parts if part)


def canonical_evidence_map(facts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {
        f"{VERIFIED_FACT_EVIDENCE_PREFIX}{fact_id}": canonical_fact_text(fact)
        for fact_id, fact in facts.items()
    }


def canonical_verified_evidence_packs(
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for fact_id, fact in facts.items():
        evidence_id = f"{VERIFIED_FACT_EVIDENCE_PREFIX}{fact_id}"
        notes = fact["provenance"]["source_truth_notes_by_page"]
        spans = [
            {
                "evidence_id": evidence_id,
                "source_pack": "verified_facts",
                "page": page,
                "text": notes[str(page)],
                "source_identity": fact["source_identity"],
            }
            for page in fact["supporting_physical_pages"]
        ]
        findings.append(
            {
                "id": evidence_id,
                "verified_fact_id": fact_id,
                "text": fact["statement"],
                "statement": fact["statement"],
                "evidence": fact["statement"],
                "metric": copy.deepcopy(dict(fact["metric"])),
                "pages": list(fact["supporting_physical_pages"]),
                "source_identity": fact["source_identity"],
                "evidence_spans": spans,
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
            "verified_facts": [copy.deepcopy(dict(fact)) for fact in facts.values()],
        },
    }


def metric_binding_mismatches(actual: object, authoritative: object) -> list[str]:
    actual_metric = dict(actual) if isinstance(actual, Mapping) else {}
    expected_metric = dict(authoritative) if isinstance(authoritative, Mapping) else {}
    mismatches: list[str] = []
    for field_name in PROTECTED_METRIC_FIELDS:
        left = actual_metric.get(field_name, "")
        right = expected_metric.get(field_name, "")
        if field_name == "observations":
            left_value = json.dumps(left or [], sort_keys=True, separators=(",", ":"))
            right_value = json.dumps(right or [], sort_keys=True, separators=(",", ":"))
        else:
            left_value = str(left or "").strip()
            right_value = str(right or "").strip()
        if left_value != right_value:
            mismatches.append(field_name)
    extra_fields = {
        str(key)
        for key, value in actual_metric.items()
        if str(key) not in PROTECTED_METRIC_FIELDS and str(value or "").strip()
    }
    mismatches.extend(sorted(extra_fields))
    return list(dict.fromkeys(mismatches))


def fact_for_evidence_id(
    facts: Mapping[str, Mapping[str, Any]], evidence_id: object
) -> Mapping[str, Any] | None:
    value = str(evidence_id or "").strip()
    if not value.startswith(VERIFIED_FACT_EVIDENCE_PREFIX):
        return None
    return facts.get(value.removeprefix(VERIFIED_FACT_EVIDENCE_PREFIX))
