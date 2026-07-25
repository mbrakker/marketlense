"""Deterministic candidate checks used before regeneration promotion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from src.contracts.regeneration import RegenerationEvidenceLineage
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.validation import ValidationIssue
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
        span.get("page")
        for span in evidence_spans or []
        if isinstance(span, dict)
    )
    pages = _positive_ints(
        page_values
    )
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
        source_pages = _positive_ints(
            page_values
        )
        pages.setdefault(key, set()).update(source_pages)

    if not isinstance(evidence_packs, dict):
        return pages
    for pack_name, item_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
        ("key_metrics", "key_metrics"),
        ("risk_register", "risk_register"),
        ("recommendations", "recommendations"),
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
            int(value)
            for value in values
            if isinstance(value, int) and value > 0
        )
    )
