"""Deterministic candidate checks used before regeneration promotion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from src.contracts.regeneration import RegenerationEvidenceLineage
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_from_payload,
    soft_copy_public_text,
    valid_soft_copy_evidence_selection,
)
from src.contracts.validation import ValidationIssue
from src.generators.artifact_normalization import artifact_evidence_span_index
from src.generators.soft_copy_claim_provenance import (
    retained_soft_copy_claims_cover_text,
)
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.errors import AppError

from .shared import issue, s


@dataclass(frozen=True)
class CandidateIntegrityResult:
    """Result of deterministic checks that must complete before model checks."""

    issues: list[ValidationIssue]
    evidence_lineage: list[RegenerationEvidenceLineage]

    @property
    def passed(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)


@dataclass(frozen=True)
class _EvidenceRecord:
    entity_kind: str
    entity_id: str
    evidence_ids: tuple[str, ...]
    source_pages: tuple[int, ...]
    material: bool

    @property
    def key(self) -> tuple[str, str]:
        return self.entity_kind, self.entity_id


_SOFT_COPY_FAMILIES = ("expert_comment", "linkedin_post")


def validate_regeneration_candidate(
    *,
    current_artifacts: dict[str, Any],
    candidate_artifacts: dict[str, Any],
    evidence_packs: dict[str, Any],
    ctx: RunContext,
) -> CandidateIntegrityResult:
    """Validate candidate schema, IDs, source pages, and material continuity.

    This intentionally performs no provider I/O.  It is the complete
    deterministic grounding check that may make a later provider outage a
    warning rather than a publish blocker.
    """

    issues: list[ValidationIssue] = []
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=candidate_artifacts,
                schema_name="artifacts",
            ),
            ctx,
        )
    except AppError as exc:
        issues.append(
            issue(
                rule_id="regeneration_schema",
                message=f"Candidate artifact schema validation failed: {exc.message}",
                severity="error",
                section="artifacts",
            )
        )

    try:
        validate_evidence_references(candidate_artifacts, evidence_packs, ctx)
    except AppError as exc:
        missing = _string_values(exc.context.get("missing_references", []))
        if missing:
            for evidence_id in missing:
                issues.append(
                    issue(
                        rule_id="grounding",
                        message=(
                            "[grounding|hallucinated_evidence_id] Candidate "
                            f"references unknown evidence_id '{evidence_id}'."
                        ),
                        severity="error",
                        section="grounding",
                    )
                )
        else:
            issues.append(
                issue(
                    rule_id="grounding",
                    message=(
                        "[grounding|missing_material_evidence] Candidate evidence "
                        f"validation failed: {exc.message}"
                    ),
                    severity="error",
                    section="grounding",
                )
            )

    current_records = _records(current_artifacts)
    candidate_records = _records(candidate_artifacts)
    evidence_pages = _evidence_source_pages(evidence_packs)
    _validate_soft_copy_claim_provenance(
        current_artifacts=current_artifacts,
        candidate_artifacts=candidate_artifacts,
        evidence_packs=evidence_packs,
        issues=issues,
    )
    candidate_by_key = {record.key: record for record in candidate_records}
    current_by_key = {record.key: record for record in current_records}

    for record in candidate_records:
        if not record.material:
            continue
        if not record.evidence_ids:
            issues.append(
                _material_evidence_issue(
                    record,
                    "Candidate material content has no evidence identifier.",
                )
            )
            continue
        for evidence_id in record.evidence_ids:
            expected_pages = evidence_pages.get(evidence_id.casefold())
            if expected_pages is None:
                # The service check above supplies the authoritative unknown-ID
                # issue.  Avoid a duplicate that obscures the useful diagnosis.
                continue
            if expected_pages and not record.source_pages:
                issues.append(
                    _source_page_issue(
                        record,
                        "Candidate material content omits retained source pages.",
                    )
                )
                continue
            if expected_pages and not set(record.source_pages).issubset(expected_pages):
                issues.append(
                    _source_page_issue(
                        record,
                        "Candidate source pages do not match the referenced evidence.",
                    )
                )

    abstained_families = _abstained_families(candidate_artifacts)
    for key, original in current_by_key.items():
        if not original.material or not original.evidence_ids:
            continue
        candidate = candidate_by_key.get(key)
        if candidate is not None and candidate.evidence_ids:
            continue
        if _has_unique_evidence_continuity_match(original, candidate_records):
            continue
        if _family_for_kind(original.entity_kind) in abstained_families:
            continue
        issues.append(
            _material_evidence_issue(
                original,
                "Candidate lost the original material evidence reference.",
            )
        )

    lineage = _build_lineage(
        current_records=current_records,
        candidate_records=candidate_records,
        issues=issues,
    )
    return CandidateIntegrityResult(issues=issues, evidence_lineage=lineage)


def _validate_soft_copy_claim_provenance(
    *,
    current_artifacts: dict[str, Any],
    candidate_artifacts: dict[str, Any],
    evidence_packs: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    """Validate factual Expert View and LinkedIn claim provenance in-place."""

    current_claims, current_error = _soft_copy_claims(current_artifacts)
    candidate_claims, candidate_error = _soft_copy_claims(candidate_artifacts)
    if candidate_error == "invalid":
        issues.append(
            _soft_copy_provenance_issue(
                family="soft_copy",
                claim_id="",
                message="Candidate soft-copy claim provenance is invalid.",
            )
        )
        return
    if current_error:
        # A legacy or malformed retained predecessor cannot establish lineage.
        current_claims = []

    raw_doc_map = evidence_packs.get("doc_map")
    canonical_doc_map: dict[str, Any] = (
        raw_doc_map if isinstance(raw_doc_map, dict) else {}
    )
    canonical_spans = artifact_evidence_span_index(
        doc_map=canonical_doc_map,
        evidence_packs=evidence_packs,
    )
    current_by_family = _claims_by_family(current_claims)
    candidate_by_family = _claims_by_family(candidate_claims)

    for family in _SOFT_COPY_FAMILIES:
        originals = current_by_family.get(family, [])
        candidates = candidate_by_family.get(family, [])
        text = soft_copy_public_text(family, candidate_artifacts.get(family))
        provenance_required = bool(originals or candidates)
        if not provenance_required:
            continue
        if _family_is_abstained(candidate_artifacts, family) and not text:
            continue
        if not retained_soft_copy_claims_cover_text(text=text, claims=candidates):
            issues.append(
                _soft_copy_provenance_issue(
                    family=family,
                    claim_id="",
                    message=(
                        "Candidate soft-copy claim provenance does not exactly cover "
                        "the retained public copy."
                    ),
                )
            )
            continue

        original_by_hash = {
            claim.text_hash: claim
            for claim in originals
            if claim.classification == "factual"
        }
        candidate_hashes = {claim.text_hash for claim in candidates}
        for original_hash, original in original_by_hash.items():
            if original_hash not in candidate_hashes:
                continue
            matching = next(
                (
                    claim
                    for claim in candidates
                    if claim.text_hash == original_hash
                    and claim.classification == "factual"
                ),
                None,
            )
            if matching != original:
                issues.append(
                    _soft_copy_provenance_issue(
                        family=family,
                        claim_id=original.claim_id,
                        message=(
                            "An unchanged factual soft-copy claim must retain its "
                            "original claim provenance lineage."
                        ),
                    )
                )

        for claim in candidates:
            if claim.classification != "factual":
                continue
            original_claim = original_by_hash.get(claim.text_hash)
            selection, lineage_error = _repair_selection_for_claim(
                artifacts=candidate_artifacts,
                claim=claim,
                require_selection=bool(originals) and original_claim is None,
            )
            if lineage_error:
                issues.append(
                    _soft_copy_provenance_issue(
                        family=claim.artifact_family,
                        claim_id=claim.claim_id,
                        message=lineage_error,
                    )
                )
            _validate_factual_soft_copy_claim(
                claim=claim,
                original=original_claim,
                canonical_spans=canonical_spans,
                quarantined_ids=_selection_evidence_ids(
                    selection, "quarantined_evidence_ids"
                )
                if selection is not None
                else _quarantined_evidence_ids(
                    candidate_artifacts, family, claim.claim_id
                ),
                selected_evidence_ids=_selection_evidence_ids(
                    selection, "selected_evidence_ids"
                ),
                issues=issues,
            )


def _soft_copy_claims(
    artifacts: dict[str, Any],
) -> tuple[list[SoftCopyClaimProvenance], str]:
    if "soft_copy_claim_provenance" not in artifacts:
        return [], "missing"
    try:
        return (
            soft_copy_claim_provenance_from_payload(
                artifacts.get("soft_copy_claim_provenance")
            ),
            "",
        )
    except (AppError, TypeError, ValueError):
        return [], "invalid"


def _claims_by_family(
    claims: Sequence[SoftCopyClaimProvenance],
) -> dict[str, list[SoftCopyClaimProvenance]]:
    grouped: dict[str, list[SoftCopyClaimProvenance]] = {}
    for claim in claims:
        if claim.artifact_family in _SOFT_COPY_FAMILIES:
            grouped.setdefault(claim.artifact_family, []).append(claim)
    return grouped


def _validate_factual_soft_copy_claim(
    *,
    claim: SoftCopyClaimProvenance,
    original: SoftCopyClaimProvenance | None,
    canonical_spans: dict[str, list[dict[str, Any]]],
    quarantined_ids: set[str],
    selected_evidence_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    if not claim.evidence_ids:
        issues.append(
            _soft_copy_provenance_issue(
                family=claim.artifact_family,
                claim_id=claim.claim_id,
                message="Factual soft-copy claim has no evidence identifier.",
                grounding_code="missing_material_evidence",
            )
        )
        return
    if original is None and (
        claim.regeneration_attempt < 1 or not claim.producing_prompt_identity
    ):
        issues.append(
            _soft_copy_provenance_issue(
                family=claim.artifact_family,
                claim_id=claim.claim_id,
                message=(
                    "A repaired factual soft-copy claim must declare explicit new "
                    "lineage."
                ),
            )
        )
    evidence_ids = {evidence_id.casefold() for evidence_id in claim.evidence_ids}
    if evidence_ids & quarantined_ids:
        issues.append(
            _soft_copy_provenance_issue(
                family=claim.artifact_family,
                claim_id=claim.claim_id,
                message="Factual soft-copy claim references quarantined evidence.",
            )
        )
    if selected_evidence_ids and not evidence_ids.issubset(selected_evidence_ids):
        issues.append(
            _soft_copy_provenance_issue(
                family=claim.artifact_family,
                claim_id=claim.claim_id,
                message=(
                    "Factual soft-copy claim references evidence outside its "
                    "retained repair selection."
                ),
            )
        )
    for evidence_id in claim.evidence_ids:
        canonical = canonical_spans.get(evidence_id.casefold(), [])
        claimed_spans = [
            span
            for span in claim.source_spans
            if str(span.get("evidence_id") or "").strip().casefold()
            == evidence_id.casefold()
        ]
        if canonical and not claimed_spans:
            issues.append(
                _source_page_issue(
                    _EvidenceRecord(
                        entity_kind=claim.artifact_family,
                        entity_id=claim.claim_id,
                        evidence_ids=claim.evidence_ids,
                        source_pages=(),
                        material=True,
                    ),
                    "Factual soft-copy claim omits retained source-span provenance.",
                )
            )
            continue
        for span in claimed_spans:
            if canonical and not _source_span_is_compatible(span, canonical):
                issues.append(
                    _source_page_issue(
                        _EvidenceRecord(
                            entity_kind=claim.artifact_family,
                            entity_id=claim.claim_id,
                            evidence_ids=claim.evidence_ids,
                            source_pages=(),
                            material=True,
                        ),
                        "Factual soft-copy source pages or spans do not match "
                        "the referenced evidence.",
                    )
                )


def _source_span_is_compatible(
    claimed: dict[str, Any], canonical: Sequence[dict[str, Any]]
) -> bool:
    fields = ("source_pack", "page", "section_id", "start_offset", "end_offset")
    for reference in canonical:
        if all(
            field not in claimed
            or field not in reference
            or claimed[field] == reference[field]
            for field in fields
        ):
            return True
    return False


def _quarantined_evidence_ids(
    artifacts: dict[str, Any], family: str, claim_id: str
) -> set[str]:
    selections = artifacts.get("_repair_evidence_selection")
    if not isinstance(selections, dict):
        return set()
    selection = selections.get(f"{family}:{claim_id}")
    if not isinstance(selection, dict):
        return set()
    return {
        s(evidence_id).strip().casefold()
        for evidence_id in selection.get("quarantined_evidence_ids") or []
        if s(evidence_id).strip()
    }


def _repair_selection_for_claim(
    *,
    artifacts: dict[str, Any],
    claim: SoftCopyClaimProvenance,
    require_selection: bool,
) -> tuple[dict[str, Any] | None, str]:
    original_claim_id = claim.repaired_from_claim_id
    if not original_claim_id:
        return (
            (
                None,
                "A repaired factual soft-copy claim is missing repair-selection lineage.",
            )
            if require_selection
            else (None, "")
        )
    selections = artifacts.get("_repair_evidence_selection")
    selection = (
        selections.get(f"{claim.artifact_family}:{original_claim_id}")
        if isinstance(selections, dict)
        else None
    )
    if not isinstance(selection, dict):
        return (
            None,
            "A repaired factual soft-copy claim is missing repair-selection lineage.",
        )
    if (
        selection.get("claim_id") != original_claim_id
        or selection.get("repaired_claim_id") != claim.claim_id
        or not valid_soft_copy_evidence_selection(
            f"{claim.artifact_family}:{original_claim_id}",
            selection,
            require_selected_evidence_entries=True,
        )
    ):
        return (
            None,
            "A repaired factual soft-copy claim has corrupt repair-selection lineage.",
        )
    if selection.get("strategy") == "abstain" or not _selection_evidence_ids(
        selection, "selected_evidence_ids"
    ):
        return (
            None,
            "A repaired factual soft-copy claim has no selected evidence in its repair selection.",
        )
    return selection, ""


def _selection_evidence_ids(selection: dict[str, Any] | None, field: str) -> set[str]:
    if selection is None:
        return set()
    return {
        s(evidence_id).strip().casefold()
        for evidence_id in selection.get(field) or []
        if s(evidence_id).strip()
    }


def _family_is_abstained(artifacts: dict[str, Any], family: str) -> bool:
    status = artifacts.get("family_status")
    payload = status.get(family) if isinstance(status, dict) else None
    return (
        isinstance(payload, dict)
        and str(payload.get("status") or "").strip().lower() == "abstained"
    )


def _soft_copy_provenance_issue(
    *,
    family: str,
    claim_id: str,
    message: str,
    grounding_code: str = "",
) -> ValidationIssue:
    prefix = f"[grounding|{grounding_code}] " if grounding_code else ""
    return issue(
        rule_id="grounding" if grounding_code else "soft_copy_claim_provenance",
        message=f"{prefix}{message}",
        severity="error",
        section=f"{family}:{claim_id}".rstrip(":"),
        repair_target=family,
        entity_id=claim_id,
    )


def _has_unique_evidence_continuity_match(
    original: _EvidenceRecord,
    candidate_records: Sequence[_EvidenceRecord],
) -> bool:
    """Accept only an unambiguous same-family identifier normalization.

    Regeneration may normalize a malformed internal artifact identifier while
    preserving the material evidence and exact source pages.  The candidate is
    continuous only when exactly one material record in the same artifact
    family has the original evidence set and source-page set; multiple matches
    remain a validation failure rather than an arbitrary choice.
    """

    original_evidence_ids = frozenset(original.evidence_ids)
    original_source_pages = frozenset(original.source_pages)
    if not original_evidence_ids or not original_source_pages:
        return False
    matches = [
        candidate
        for candidate in candidate_records
        if candidate.entity_kind == original.entity_kind
        and candidate.material
        and frozenset(candidate.evidence_ids) == original_evidence_ids
        and frozenset(candidate.source_pages) == original_source_pages
    ]
    return len(matches) == 1


def _records(artifacts: dict[str, Any]) -> list[_EvidenceRecord]:
    if not isinstance(artifacts, dict):
        return []
    records: list[_EvidenceRecord] = []
    summary = artifacts.get("summary")
    if isinstance(summary, dict):
        for index, item in enumerate(summary.get("claim_evidence_map") or [], start=1):
            if isinstance(item, dict):
                records.append(
                    _record(
                        "summary_claim",
                        _record_id(item, index, "claim"),
                        item,
                        material=bool(s(item.get("claim")).strip()),
                    )
                )
    for section in ("insights_candidates", "insights_final"):
        for index, item in enumerate(artifacts.get(section) or [], start=1):
            if isinstance(item, dict):
                metric = item.get("metric")
                records.append(
                    _record(
                        section,
                        _record_id(item, index, "insight"),
                        item,
                        material=bool(s(item.get("text")).strip())
                        or bool(s(metric.get("value")).strip())
                        if isinstance(metric, dict)
                        else bool(s(item.get("text")).strip()),
                    )
                )
    for index, item in enumerate(artifacts.get("quotes_final") or [], start=1):
        if isinstance(item, dict):
            records.append(
                _record(
                    "quotes_final",
                    _record_id(item, index, "quote"),
                    item,
                    material=bool(s(item.get("text")).strip()),
                )
            )
    return records


def _record(
    entity_kind: str,
    entity_id: str,
    item: dict[str, Any],
    *,
    material: bool,
) -> _EvidenceRecord:
    evidence_spans = item.get("evidence_spans")
    span_ids = [
        span.get("evidence_id")
        for span in evidence_spans or []
        if isinstance(span, dict)
    ]
    ids = _string_values(
        [
            item.get("evidence_id"),
            *span_ids,
        ]
    )
    raw_pages = item.get("pages")
    page_values: list[object] = list(raw_pages) if isinstance(raw_pages, list) else []
    page_values.append(item.get("page"))
    page_values.extend(
        span.get("page") for span in evidence_spans or [] if isinstance(span, dict)
    )
    pages = _positive_ints(page_values)
    return _EvidenceRecord(
        entity_kind=entity_kind,
        entity_id=entity_id,
        evidence_ids=tuple(ids),
        source_pages=tuple(pages),
        material=material,
    )


def _record_id(item: dict[str, Any], index: int, prefix: str) -> str:
    value = s(item.get("id")).strip()
    return value or f"{prefix}_{index}"


def _evidence_source_pages(evidence_packs: dict[str, Any]) -> dict[str, set[int]]:
    pages: dict[str, set[int]] = {}

    def add(evidence_id: object, item: dict[str, Any]) -> None:
        key = s(evidence_id).strip().casefold()
        if not key:
            return
        raw_pages = item.get("pages")
        page_values: list[object] = (
            list(raw_pages) if isinstance(raw_pages, list) else []
        )
        page_values.append(item.get("page"))
        source_pages = _positive_ints(page_values)
        pages.setdefault(key, set()).update(source_pages)

    if not isinstance(evidence_packs, dict):
        return pages
    for pack_name, item_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
    ):
        pack = evidence_packs.get(pack_name)
        if not isinstance(pack, dict):
            continue
        for item in pack.get(item_key) or []:
            if isinstance(item, dict):
                add(item.get("id") or item.get("evidence_id"), item)
    doc_map = evidence_packs.get("doc_map")
    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                add(section.get("id"), section)
    return pages


def _build_lineage(
    *,
    current_records: Sequence[_EvidenceRecord],
    candidate_records: Sequence[_EvidenceRecord],
    issues: Sequence[ValidationIssue],
) -> list[RegenerationEvidenceLineage]:
    current_by_key = {record.key: record for record in current_records}
    candidate_by_key = {record.key: record for record in candidate_records}
    lineage: list[RegenerationEvidenceLineage] = []
    for key in sorted(set(current_by_key) | set(candidate_by_key)):
        original = current_by_key.get(key)
        candidate = candidate_by_key.get(key)
        entity_kind, entity_id = key
        lineage.append(
            RegenerationEvidenceLineage(
                entity_kind=entity_kind,
                entity_id=entity_id,
                original_evidence_ids=list(original.evidence_ids) if original else [],
                candidate_evidence_ids=list(candidate.evidence_ids)
                if candidate
                else [],
                original_source_pages=list(original.source_pages) if original else [],
                candidate_source_pages=list(candidate.source_pages)
                if candidate
                else [],
                validation_issues=_issues_for_record(issues, entity_kind, entity_id),
            )
        )
    return lineage


def _issues_for_record(
    issues: Sequence[ValidationIssue], entity_kind: str, entity_id: str
) -> list[str]:
    prefixes = {
        "summary_claim": ("summary",),
        "insights_candidates": ("insights:candidate", "insights_candidates"),
        "insights_final": (f"insights:{entity_id}", "insights_final"),
        "quotes_final": (f"quotes:{entity_id}", "quotes_final"),
    }.get(entity_kind, ())
    return sorted(
        {
            str(item.rule_id or "validation")
            for item in issues
            if str(item.affected_section or "").startswith(prefixes)
        }
    )


def _material_evidence_issue(record: _EvidenceRecord, message: str) -> ValidationIssue:
    return issue(
        rule_id="grounding",
        message=f"[grounding|missing_material_evidence] {message}",
        severity="error",
        section=f"{record.entity_kind}:{record.entity_id}",
        repair_target=_repair_target(record.entity_kind),
        entity_id=record.entity_id,
    )


def _source_page_issue(record: _EvidenceRecord, message: str) -> ValidationIssue:
    return issue(
        rule_id="regeneration_source_page",
        message=message,
        severity="error",
        section=f"{record.entity_kind}:{record.entity_id}",
        repair_target=_repair_target(record.entity_kind),
        entity_id=record.entity_id,
    )


def _repair_target(entity_kind: str) -> str:
    if entity_kind == "summary_claim":
        return "summary"
    if entity_kind.startswith("insights"):
        return "insights_bundle"
    if entity_kind == "quotes_final":
        return "quotes"
    if entity_kind in _SOFT_COPY_FAMILIES:
        return entity_kind
    return ""


def _family_for_kind(entity_kind: str) -> str:
    if entity_kind == "summary_claim":
        return "summary"
    if entity_kind.startswith("insights"):
        return "insights_bundle"
    if entity_kind == "quotes_final":
        return "quotes"
    return ""


def _abstained_families(artifacts: dict[str, Any]) -> set[str]:
    status = artifacts.get("family_status") if isinstance(artifacts, dict) else None
    if not isinstance(status, dict):
        return set()
    return {
        str(family).strip()
        for family, payload in status.items()
        if isinstance(payload, dict)
        and str(payload.get("status") or "").strip().lower() == "abstained"
    }


def _string_values(values: Iterable[object]) -> list[str]:
    normalized = (s(item).strip() for item in values)
    return list(dict.fromkeys(value for value in normalized if value))


def _positive_ints(values: Iterable[object]) -> list[int]:
    return list(
        dict.fromkeys(
            int(value) for value in values if isinstance(value, int) and value > 0
        )
    )
