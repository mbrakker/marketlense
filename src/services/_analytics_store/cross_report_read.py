from __future__ import annotations

"""Cross Report Read operations for the analytics store service."""

import hashlib
import json
import logging
import re
import sqlite3
from typing import Any, Sequence, cast

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportRawMetricReference,
    CrossReportSourceReportCandidate,
    ProjectionReadinessStatus,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.services._analytics_store.common import (
    _CROSS_REPORT_READ_CONTENT_CLASSES,
    _analytics_conn,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.verified_facts import (
    QUALIFIED_SOURCE_IDENTITY_RE,
    verified_source_identity_matches_runtime,
)

logger = logging.getLogger("market_lense.analytics_store_service")


def _normalized_filter_values(values: Sequence[str]) -> set[str]:
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _status_floor_values(
    status: ProjectionReadinessStatus,
) -> set[ProjectionReadinessStatus]:
    if status == "projected":
        return {"projected"}
    if status == "failed":
        return {"failed", "projected"}
    if status == "not_projected":
        return {"not_projected", "failed", "projected"}
    raise AppError(
        code="cross_report_projection_status_invalid",
        message="Cross-report projected data read received an invalid status floor",
        retryable=False,
        severity="error",
        context={"minimum_projection_status": status},
    )


def _json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _strict_json_list(value: Any) -> tuple[list[Any], bool]:
    if value is None or value == "":
        return [], False
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return [], False
    return (decoded, True) if isinstance(decoded, list) else ([], False)


def _strict_json_dict(value: Any) -> tuple[dict[str, Any], bool]:
    if value is None or value == "":
        return {}, False
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return {}, False
    return (decoded, True) if isinstance(decoded, dict) else ({}, False)


def _valid_page_list(value: list[Any]) -> bool:
    return all(
        isinstance(page, int) and not isinstance(page, bool) and page > 0
        for page in value
    )


def _valid_digest(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", value))


def _qualified_source_pdf_sha256(value: object) -> str:
    match = QUALIFIED_SOURCE_IDENTITY_RE.fullmatch(str(value or "").strip())
    return match.group("sha").lower() if match else ""


def _verified_source_eligibility(
    report_row: sqlite3.Row,
    expected_sources: dict[str, dict[str, str]],
    require_verified_source_lineage: bool = False,
) -> tuple[bool, str]:
    authority_mode = _row_text(report_row, "authority_mode").strip().casefold()
    if authority_mode not in {"normal", "verified"}:
        return False, "source_authority_mode_invalid"
    validation_status = _row_text(report_row, "validation_status").casefold()
    validation_severity = _row_text(report_row, "validation_severity").casefold()
    if validation_status != "pass":
        return False, "source_validation_not_passed"
    if validation_severity in {"error", "fail"}:
        return False, "source_validation_blocked"
    if not bool(report_row["source_validation_eligible"]):
        return False, "source_validation_not_passed"
    if authority_mode != "verified":
        if require_verified_source_lineage:
            return False, "verified_source_lineage_missing"
        return True, ""
    source_identity = _row_text(report_row, "verified_source_identity")
    source_pdf_sha256 = _row_text(report_row, "verified_source_pdf_sha256")
    fact_digest = _row_text(report_row, "verified_fact_digest")
    if not source_identity or not source_pdf_sha256 or not fact_digest:
        return False, "verified_authority_lineage_missing"
    embedded_pdf_sha256 = _qualified_source_pdf_sha256(source_identity)
    if not embedded_pdf_sha256:
        return False, "verified_source_identity_invalid"
    if (
        not embedded_pdf_sha256
        or embedded_pdf_sha256.casefold() != source_pdf_sha256.casefold()
    ):
        return False, "verified_source_identity_pdf_mismatch"
    if not _valid_digest(fact_digest):
        return False, "verified_fact_digest_invalid"
    expected = expected_sources.get(_row_text(report_row, "report_id"))
    if expected:
        expected_identity = str(expected.get("source_identity") or "").strip()
        expected_pdf = str(expected.get("source_pdf_sha256") or "").strip()
        expected_digest = str(expected.get("verified_fact_digest") or "").strip()
        if expected_identity and not verified_source_identity_matches_runtime(
            expected_identity, source_identity
        ):
            return False, "verified_source_identity_stale"
        if expected_pdf and source_pdf_sha256.casefold() != expected_pdf.casefold():
            return False, "verified_source_pdf_stale"
        if expected_digest and fact_digest.casefold() != expected_digest.casefold():
            return False, "verified_fact_digest_stale"
    return True, ""


def _fetch_grouped_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    report_ids: Sequence[str],
) -> dict[str, list[sqlite3.Row]]:
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE report_id IN ({placeholders}) ORDER BY report_id",
        tuple(report_ids),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["report_id"]), []).append(row)
    return grouped


def _fetch_vector_hashes(
    conn: sqlite3.Connection, report_ids: Sequence[str]
) -> dict[str, dict[str, str]]:
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    rows = conn.execute(
        """
        SELECT report_id, entity_uid, content_hash
        FROM vector_projection_queue
        WHERE report_id IN ({placeholders})
        ORDER BY report_id, entity_uid
        """.format(placeholders=placeholders),
        tuple(report_ids),
    ).fetchall()
    hashes: dict[str, dict[str, str]] = {}
    for row in rows:
        content_hash = str(row["content_hash"] or "").strip()
        entity_uid = str(row["entity_uid"] or "").strip()
        report_id = str(row["report_id"] or "").strip()
        if content_hash and entity_uid and report_id:
            hashes.setdefault(report_id, {})[entity_uid] = content_hash
    return hashes


def _aggregate_content_hash(report_row: sqlite3.Row, hashes: dict[str, str]) -> str:
    if hashes:
        payload = "|".join(f"{key}={hashes[key]}" for key in sorted(hashes))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    fallback = "|".join(
        str(report_row[key] or "")
        for key in (
            "report_id",
            "source_md5",
            "md5",
            "projection_generated_at_utc",
        )
    )
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _report_period(report_row: sqlite3.Row) -> str:
    return str(report_row["time_period"] or "").strip()


def _report_date(report_row: sqlite3.Row) -> str:
    period = _report_period(report_row)
    if period:
        return period
    generated_at = str(report_row["projection_generated_at_utc"] or "").strip()
    return generated_at[:10]


def _row_text(row: sqlite3.Row, column: str) -> str:
    return str(row[column] or "").strip()


def _report_publisher(report_row: sqlite3.Row) -> str:
    publisher = _row_text(report_row, "publisher") or _row_text(
        report_row, "publisher_id"
    )
    if publisher:
        return publisher
    report_id = _row_text(report_row, "report_id")
    if _row_text(report_row, "projection_status") != "projected":
        return report_id
    return "Unknown publisher"


def _stable_row_id(row: sqlite3.Row, primary_column: str, fallback_column: str) -> str:
    return _row_text(row, primary_column) or _row_text(row, fallback_column)


def _scoped_row_id(
    row: sqlite3.Row, primary_column: str, fallback_column: str, entity_kind: str
) -> str:
    raw_id = _stable_row_id(row, primary_column, fallback_column)
    report_id = _row_text(row, "report_id")
    if not raw_id or raw_id.startswith(f"{report_id}:"):
        return raw_id
    return f"{report_id}:{entity_kind}:{raw_id}"


def _report_passes_filters(
    report_row: sqlite3.Row,
    *,
    request: CrossReportProjectedDataReadRequest,
    tags: list[sqlite3.Row],
    categories: list[sqlite3.Row],
) -> bool:
    publisher_filters = _normalized_filter_values(request.publisher_filters)
    if publisher_filters:
        publisher_values = {
            _row_text(report_row, "publisher").casefold(),
            _row_text(report_row, "publisher_id").casefold(),
        }
        if not publisher_filters.intersection(publisher_values):
            return False

    report_date = _report_period(report_row)
    if request.date_range_start and (
        not report_date or report_date < request.date_range_start
    ):
        return False
    if request.date_range_end and (
        not report_date or report_date > request.date_range_end
    ):
        return False

    tag_filters = _normalized_filter_values(request.tag_filters)
    if tag_filters:
        report_tags = {_row_text(row, "tag").casefold() for row in tags}
        if not tag_filters.intersection(report_tags):
            return False

    category_filters = _normalized_filter_values(request.category_filters)
    if category_filters:
        category_values = set()
        for row in categories:
            category_values.add(_row_text(row, "category_id").casefold())
            category_values.add(_row_text(row, "label").casefold())
        if not category_filters.intersection(category_values):
            return False

    return True


def _source_candidate(
    report_row: sqlite3.Row,
    *,
    tags: list[sqlite3.Row],
    categories: list[sqlite3.Row],
    claims: list[sqlite3.Row],
    findings: list[sqlite3.Row],
    quotes: list[sqlite3.Row],
    metrics: list[sqlite3.Row],
    content_hashes: dict[str, str],
    source_validation_eligible: bool | None = None,
) -> CrossReportSourceReportCandidate:
    claim_count = len(claims)
    finding_count = len(findings)
    quote_count = len(quotes)
    metric_count = len(metrics)
    evidence_count = claim_count + finding_count + quote_count
    report_id = _row_text(report_row, "report_id")
    publisher = _report_publisher(report_row)
    publisher_id = _row_text(report_row, "publisher_id") or publisher
    projection_status = cast(
        ProjectionReadinessStatus, _row_text(report_row, "projection_status")
    )
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=_row_text(report_row, "title"),
        publisher=publisher,
        publisher_id=publisher_id,
        report_date=_report_date(report_row),
        projection_status=projection_status,
        content_hash=_aggregate_content_hash(report_row, content_hashes),
        category_labels=sorted(
            {_row_text(row, "label") for row in categories if _row_text(row, "label")}
        ),
        category_ids=sorted(
            {
                _row_text(row, "category_id")
                for row in categories
                if _row_text(row, "category_id")
            }
        ),
        source_url=_row_text(report_row, "source_url"),
        authority_mode=_row_text(report_row, "authority_mode") or "normal",
        source_validation_eligible=(
            bool(report_row["source_validation_eligible"])
            if source_validation_eligible is None
            else source_validation_eligible
        ),
        verified_source_identity=_row_text(report_row, "verified_source_identity"),
        verified_source_pdf_sha256=_row_text(report_row, "verified_source_pdf_sha256"),
        verified_fact_digest=_row_text(report_row, "verified_fact_digest"),
        tags=sorted({_row_text(row, "tag") for row in tags if _row_text(row, "tag")}),
        evidence_count=evidence_count,
        claim_count=claim_count,
        finding_count=finding_count,
        quote_count=quote_count,
        metric_count=metric_count,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=float(evidence_count),
        total_score=0.0,
        selection_reasons=[f"projection_status:{projection_status}"],
        rejection_reasons=[],
    )


def _verified_row_source_reason(
    row: sqlite3.Row,
    *,
    report_row: sqlite3.Row,
) -> str:
    if _row_text(row, "report_id") != _row_text(report_row, "report_id"):
        return "row_report_id_mismatch"
    source_identity = _row_text(row, "source_identity")
    source_pdf_sha256 = _row_text(row, "source_pdf_sha256")
    fact_digest = _row_text(row, "verified_fact_digest")
    report_identity = _row_text(report_row, "verified_source_identity")
    report_pdf_sha256 = _row_text(report_row, "verified_source_pdf_sha256")
    report_fact_digest = _row_text(report_row, "verified_fact_digest")
    if not source_identity or not source_pdf_sha256 or not fact_digest:
        return "row_verified_binding_missing"
    if not _qualified_source_pdf_sha256(source_identity):
        return "row_source_identity_invalid"
    if not verified_source_identity_matches_runtime(report_identity, source_identity):
        return "row_source_identity_mismatch"
    if source_pdf_sha256.casefold() != report_pdf_sha256.casefold():
        return "row_source_pdf_mismatch"
    embedded_pdf_sha256 = _qualified_source_pdf_sha256(source_identity)
    if (
        not embedded_pdf_sha256
        or embedded_pdf_sha256.casefold() != source_pdf_sha256.casefold()
    ):
        return "row_source_identity_pdf_mismatch"
    if not _valid_digest(fact_digest):
        return "row_verified_fact_digest_invalid"
    if fact_digest.casefold() != report_fact_digest.casefold():
        return "row_verified_fact_digest_mismatch"
    return ""


def _verified_rows_for_report(
    report_row: sqlite3.Row,
    *,
    findings: list[sqlite3.Row],
    metrics: list[sqlite3.Row],
    excluded_counts: dict[str, int],
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], dict[str, dict[str, Any]]]:
    bindings: dict[str, dict[str, Any]] = {}
    valid_findings: list[sqlite3.Row] = []
    valid_metrics: list[sqlite3.Row] = []

    def exclude(reason: str) -> None:
        excluded_counts[reason] = excluded_counts.get(reason, 0) + 1

    for row in findings:
        fact_id = _row_text(row, "verified_fact_id")
        evidence_id = _row_text(row, "evidence_id")
        if not fact_id:
            exclude("row_verified_binding_missing")
            continue
        canonical_evidence_id = f"verified-fact:{fact_id}"
        if evidence_id != canonical_evidence_id:
            exclude("row_verified_evidence_id_mismatch")
            continue
        reason = _verified_row_source_reason(row, report_row=report_row)
        if reason:
            exclude(reason)
            continue
        pages, pages_valid = _strict_json_list(row["pages_json"])
        spans, spans_valid = _strict_json_list(row["evidence_spans_json"])
        _, metric_context_valid = _strict_json_dict(row["metric_context_json"])
        if not pages_valid or not _valid_page_list(pages) or not pages:
            exclude("row_finding_pages_invalid")
            continue
        if not spans_valid or any(not isinstance(span, dict) for span in spans):
            exclude("row_finding_evidence_spans_invalid")
            continue
        if not metric_context_valid:
            exclude("row_finding_metric_context_malformed")
            continue
        bindings[canonical_evidence_id] = {
            "verified_fact_id": fact_id,
            "source_identity": _row_text(row, "source_identity"),
            "source_pdf_sha256": _row_text(row, "source_pdf_sha256"),
            "verified_fact_digest": _row_text(row, "verified_fact_digest"),
            "pages": pages,
            "evidence_spans": spans,
        }
        valid_findings.append(row)

    for row in metrics:
        fact_id = _row_text(row, "verified_fact_id")
        evidence_id = _row_text(row, "evidence_id")
        if not fact_id:
            exclude("row_verified_binding_missing")
            continue
        metric_context, metric_context_valid = _strict_json_dict(
            row["metric_context_json"]
        )
        if not metric_context_valid:
            exclude("row_metric_context_malformed")
            continue
        if not metric_context:
            exclude("row_metric_context_missing")
            continue
        canonical_evidence_id = f"verified-fact:{fact_id}"
        if evidence_id != canonical_evidence_id or evidence_id not in bindings:
            exclude("row_metric_evidence_id_mismatch")
            continue
        reason = _verified_row_source_reason(row, report_row=report_row)
        if reason:
            exclude(reason)
            continue
        pages, pages_valid = _strict_json_list(row["pages_json"])
        spans, spans_valid = _strict_json_list(row["evidence_spans_json"])
        if not pages_valid or not _valid_page_list(pages) or not pages:
            exclude("row_metric_pages_invalid")
            continue
        if not spans_valid or any(not isinstance(span, dict) for span in spans):
            exclude("row_metric_evidence_spans_invalid")
            continue
        valid_metrics.append(row)

    return valid_findings, valid_metrics, bindings


def _verified_analyst_row_binding_details(
    row: sqlite3.Row,
    *,
    bindings: dict[str, dict[str, Any]],
    is_quote: bool,
) -> tuple[dict[str, Any] | None, str]:
    evidence_id = _row_text(row, "evidence_id")
    binding = bindings.get(evidence_id)
    if binding is None:
        return None, ""
    binding_pages = binding.get("pages")
    if not isinstance(binding_pages, list) or not _valid_page_list(binding_pages):
        return None, "row_finding_pages_invalid"
    if is_quote:
        page = row["page"]
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            return None, "row_quote_page_invalid"
        if page not in binding_pages:
            return None, "row_quote_page_not_supported"
        return binding, ""
    pages, pages_valid = _strict_json_list(row["pages_json"])
    if not pages_valid or not _valid_page_list(pages) or not pages:
        return None, "row_claim_pages_invalid"
    if not set(pages).issubset(set(binding_pages)):
        return None, "row_claim_pages_not_supported"
    return binding, ""


def _verified_analyst_row_binding(
    row: sqlite3.Row,
    *,
    bindings: dict[str, dict[str, Any]],
    is_quote: bool,
) -> dict[str, Any] | None:
    binding, _ = _verified_analyst_row_binding_details(
        row, bindings=bindings, is_quote=is_quote
    )
    return binding


def _claim_evidence(
    row: sqlite3.Row,
    *,
    report_row: sqlite3.Row,
    binding: dict[str, Any] | None = None,
    source_validation_eligible: bool | None = None,
) -> CrossReportEvidenceReference:
    resolved_binding = binding or {}
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_scoped_row_id(row, "evidence_id", "claim_uid", "claim"),
        report_id=_row_text(row, "report_id"),
        publisher=_report_publisher(report_row),
        title=_row_text(report_row, "title"),
        source_table="report_claims",
        entity_uid=_row_text(row, "claim_uid"),
        content_class="claim",
        text=_row_text(row, "claim"),
        source_metadata={
            "evidence": _row_text(row, "evidence"),
            "pages": _json_list(row["pages_json"]),
            "source_url": _row_text(report_row, "source_url"),
            "authority_mode": _row_text(report_row, "authority_mode") or "normal",
            "source_validation_eligible": (
                bool(report_row["source_validation_eligible"])
                if source_validation_eligible is None
                else source_validation_eligible
            ),
        },
        verified_fact_id=str(resolved_binding.get("verified_fact_id") or ""),
        source_identity=str(
            resolved_binding.get("source_identity")
            or _row_text(report_row, "verified_source_identity")
        ),
        source_pdf_sha256=str(
            resolved_binding.get("source_pdf_sha256")
            or _row_text(report_row, "verified_source_pdf_sha256")
        ),
        verified_fact_digest=str(
            resolved_binding.get("verified_fact_digest")
            or _row_text(report_row, "verified_fact_digest")
        ),
    )


def _finding_evidence(
    row: sqlite3.Row,
    *,
    report_row: sqlite3.Row,
    binding: dict[str, Any] | None = None,
    source_validation_eligible: bool | None = None,
) -> CrossReportEvidenceReference:
    resolved_binding = binding or {}
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_scoped_row_id(row, "evidence_id", "finding_uid", "finding"),
        report_id=_row_text(row, "report_id"),
        publisher=_report_publisher(report_row),
        title=_row_text(report_row, "title"),
        source_table="report_findings",
        entity_uid=_row_text(row, "finding_uid"),
        content_class="finding",
        text=_row_text(row, "text"),
        source_metadata={
            "evidence": _row_text(row, "evidence"),
            "confidence": _row_text(row, "confidence"),
            "pages": _json_list(row["pages_json"]),
            "source_url": _row_text(report_row, "source_url"),
            "metric_context": _json_dict(row["metric_context_json"]),
            "evidence_spans": _json_list(row["evidence_spans_json"]),
            "authority_mode": _row_text(report_row, "authority_mode") or "normal",
            "source_validation_eligible": (
                bool(report_row["source_validation_eligible"])
                if source_validation_eligible is None
                else source_validation_eligible
            ),
        },
        verified_fact_id=str(
            resolved_binding.get("verified_fact_id")
            or _row_text(row, "verified_fact_id")
        ),
        source_identity=str(
            resolved_binding.get("source_identity")
            or _row_text(row, "source_identity")
            or _row_text(report_row, "verified_source_identity")
        ),
        source_pdf_sha256=str(
            resolved_binding.get("source_pdf_sha256")
            or _row_text(row, "source_pdf_sha256")
            or _row_text(report_row, "verified_source_pdf_sha256")
        ),
        verified_fact_digest=str(
            resolved_binding.get("verified_fact_digest")
            or _row_text(row, "verified_fact_digest")
            or _row_text(report_row, "verified_fact_digest")
        ),
    )


def _quote_evidence(
    row: sqlite3.Row,
    *,
    report_row: sqlite3.Row,
    binding: dict[str, Any] | None = None,
    source_validation_eligible: bool | None = None,
) -> CrossReportEvidenceReference:
    resolved_binding = binding or {}
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_scoped_row_id(row, "evidence_id", "quote_uid", "quote"),
        report_id=_row_text(row, "report_id"),
        publisher=_report_publisher(report_row),
        title=_row_text(report_row, "title"),
        source_table="report_quotes",
        entity_uid=_row_text(row, "quote_uid"),
        content_class="quote",
        text=_row_text(row, "text"),
        source_metadata={
            "speaker": _row_text(row, "speaker"),
            "citation": _row_text(row, "citation"),
            "page": row["page"],
            "source_url": _row_text(report_row, "source_url"),
            "quote_id": _row_text(row, "quote_id"),
            "authority_mode": _row_text(report_row, "authority_mode") or "normal",
            "source_validation_eligible": (
                bool(report_row["source_validation_eligible"])
                if source_validation_eligible is None
                else source_validation_eligible
            ),
        },
        verified_fact_id=str(resolved_binding.get("verified_fact_id") or ""),
        source_identity=str(
            resolved_binding.get("source_identity")
            or _row_text(report_row, "verified_source_identity")
        ),
        source_pdf_sha256=str(
            resolved_binding.get("source_pdf_sha256")
            or _row_text(report_row, "verified_source_pdf_sha256")
        ),
        verified_fact_digest=str(
            resolved_binding.get("verified_fact_digest")
            or _row_text(report_row, "verified_fact_digest")
        ),
    )


def _raw_metric(
    row: sqlite3.Row,
    *,
    report_row: sqlite3.Row,
    source_validation_eligible: bool | None = None,
) -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id=_scoped_row_id(row, "metric_uid", "metric_uid", "metric"),
        report_id=_row_text(row, "report_id"),
        publisher=_report_publisher(report_row),
        label=_row_text(row, "metric"),
        raw_value=_row_text(row, "value"),
        unit=_row_text(row, "unit"),
        context=f"pages={_json_list(row['pages_json'])}",
        evidence_id=_scoped_row_id(row, "evidence_id", "metric_uid", "metric"),
        source_metadata={
            "source_table": "report_metrics",
            "entity_uid": _row_text(row, "metric_uid"),
            "pages": _json_list(row["pages_json"]),
            "source_url": _row_text(report_row, "source_url"),
            "metric_context": _json_dict(row["metric_context_json"]),
            "evidence_spans": _json_list(row["evidence_spans_json"]),
            "authority_mode": _row_text(report_row, "authority_mode") or "normal",
            "source_validation_eligible": (
                bool(report_row["source_validation_eligible"])
                if source_validation_eligible is None
                else source_validation_eligible
            ),
        },
        verified_fact_id=_row_text(row, "verified_fact_id"),
        source_identity=_row_text(row, "source_identity")
        or _row_text(report_row, "verified_source_identity"),
        source_pdf_sha256=_row_text(row, "source_pdf_sha256")
        or _row_text(report_row, "verified_source_pdf_sha256"),
        verified_fact_digest=_row_text(row, "verified_fact_digest")
        or _row_text(report_row, "verified_fact_digest"),
        metric_context=_json_dict(row["metric_context_json"]),
    )


def _requested_content_classes(
    request: CrossReportProjectedDataReadRequest,
) -> set[str]:
    requested: set[str] = (
        set(request.content_classes)
        if request.content_classes
        else set(_CROSS_REPORT_READ_CONTENT_CLASSES)
    )
    invalid = requested - set(_CROSS_REPORT_READ_CONTENT_CLASSES)
    if invalid:
        raise AppError(
            code="cross_report_content_class_invalid",
            message="Cross-report projected data read received invalid content classes",
            retryable=False,
            severity="error",
            context={"content_classes": sorted(invalid)},
        )
    return requested


def read_cross_report_projected_data(
    request: CrossReportProjectedDataReadRequest,
    ctx: RunContext,
) -> CrossReportProjectedDataReadResponse:
    validate_cross_report_contract(request)
    requested_content_classes = _requested_content_classes(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cross_report_projected_data_read_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "publisher_filters": request.publisher_filters,
                "category_filters": request.category_filters,
                "tag_filters": request.tag_filters,
                "date_range_start": request.date_range_start,
                "date_range_end": request.date_range_end,
                "content_classes": sorted(requested_content_classes),
                "minimum_projection_status": request.minimum_projection_status,
                "source_report_id_count": len(request.source_report_ids),
                "evidence_id_count": len(request.evidence_ids),
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            status_floor = _status_floor_values(request.minimum_projection_status)
            all_rows = conn.execute(
                """
                SELECT file_id, report_id, title, publisher, publisher_id, source_md5,
                       source_url, md5, time_period, projection_status,
                       projection_generated_at_utc, authority_mode,
                       validation_status, validation_severity,
                       source_validation_eligible, verified_source_identity,
                       verified_source_pdf_sha256, verified_fact_digest
                FROM reports
                ORDER BY report_id
                """
            ).fetchall()
            status_rows = [
                row
                for row in all_rows
                if _row_text(row, "projection_status") in status_floor
            ]
            requested_source_ids = set(request.source_report_ids)
            if requested_source_ids:
                status_rows = [
                    row
                    for row in status_rows
                    if _row_text(row, "report_id") in requested_source_ids
                ]
            status_report_ids = [_row_text(row, "report_id") for row in status_rows]
            tags_by_report = _fetch_grouped_rows(
                conn, table="report_tags", report_ids=status_report_ids
            )
            categories_by_report = _fetch_grouped_rows(
                conn, table="report_categories", report_ids=status_report_ids
            )
            claims_by_report = _fetch_grouped_rows(
                conn, table="report_claims", report_ids=status_report_ids
            )
            findings_by_report = _fetch_grouped_rows(
                conn, table="report_findings", report_ids=status_report_ids
            )
            quotes_by_report = _fetch_grouped_rows(
                conn, table="report_quotes", report_ids=status_report_ids
            )
            metrics_by_report = _fetch_grouped_rows(
                conn, table="report_metrics", report_ids=status_report_ids
            )
            content_hashes = _fetch_vector_hashes(conn, status_report_ids)

            filtered_rows = [
                row
                for row in status_rows
                if _report_passes_filters(
                    row,
                    request=request,
                    tags=tags_by_report.get(_row_text(row, "report_id"), []),
                    categories=categories_by_report.get(
                        _row_text(row, "report_id"), []
                    ),
                )
            ]
            report_rows = {_row_text(row, "report_id"): row for row in filtered_rows}
            authority_status = {
                report_id: _verified_source_eligibility(
                    row,
                    request.expected_verified_sources,
                    request.require_verified_source_lineage
                    or bool(request.expected_verified_sources),
                )
                for report_id, row in report_rows.items()
            }
            excluded_counts: dict[str, int] = {}
            for eligible, reason in authority_status.values():
                if not eligible and reason:
                    excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
            source_candidates: list[CrossReportSourceReportCandidate] = []
            evidence: list[CrossReportEvidenceReference] = []
            raw_metrics: list[CrossReportRawMetricReference] = []
            for report_id in sorted(report_rows):
                report_row = report_rows[report_id]
                authority_mode = (
                    _row_text(report_row, "authority_mode").strip().casefold()
                )
                report_findings = findings_by_report.get(report_id, [])
                report_metrics = metrics_by_report.get(report_id, [])
                report_claims = claims_by_report.get(report_id, [])
                report_quotes = quotes_by_report.get(report_id, [])
                bindings: dict[str, dict[str, Any]] = {}
                if authority_mode == "verified":
                    report_findings, report_metrics, bindings = (
                        _verified_rows_for_report(
                            report_row,
                            findings=report_findings,
                            metrics=report_metrics,
                            excluded_counts=excluded_counts,
                        )
                    )
                    bound_claims: list[sqlite3.Row] = []
                    for row in report_claims:
                        binding, binding_reason = _verified_analyst_row_binding_details(
                            row, bindings=bindings, is_quote=False
                        )
                        if binding is None:
                            reason = binding_reason or "unbound_verified_claim"
                            excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
                            continue
                        bound_claims.append(row)
                    report_claims = bound_claims
                    bound_quotes: list[sqlite3.Row] = []
                    for row in report_quotes:
                        binding, binding_reason = _verified_analyst_row_binding_details(
                            row, bindings=bindings, is_quote=True
                        )
                        if binding is None:
                            reason = binding_reason or "unbound_verified_quote"
                            excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
                            continue
                        bound_quotes.append(row)
                    report_quotes = bound_quotes
                elif authority_mode not in {"normal", "verified"}:
                    report_findings = []
                    report_metrics = []
                    report_claims = []
                    report_quotes = []
                source_candidates.append(
                    _source_candidate(
                        report_row,
                        tags=tags_by_report.get(report_id, []),
                        categories=categories_by_report.get(report_id, []),
                        claims=report_claims,
                        findings=report_findings,
                        quotes=report_quotes,
                        metrics=report_metrics,
                        content_hashes=content_hashes.get(report_id, {}),
                        source_validation_eligible=authority_status[report_id][0],
                    )
                )
                if "claim" in requested_content_classes:
                    evidence.extend(
                        _claim_evidence(
                            row,
                            report_row=report_row,
                            binding=(
                                bindings.get(_row_text(row, "evidence_id"))
                                if authority_mode == "verified"
                                else None
                            ),
                            source_validation_eligible=authority_status[report_id][0],
                        )
                        for row in report_claims
                    )
                if "finding" in requested_content_classes:
                    evidence.extend(
                        _finding_evidence(
                            row,
                            report_row=report_row,
                            binding=(
                                bindings.get(_row_text(row, "evidence_id"))
                                if authority_mode == "verified"
                                else None
                            ),
                            source_validation_eligible=authority_status[report_id][0],
                        )
                        for row in report_findings
                    )
                if "quote" in requested_content_classes:
                    evidence.extend(
                        _quote_evidence(
                            row,
                            report_row=report_row,
                            binding=(
                                bindings.get(_row_text(row, "evidence_id"))
                                if authority_mode == "verified"
                                else None
                            ),
                            source_validation_eligible=authority_status[report_id][0],
                        )
                        for row in report_quotes
                    )
                if "metric" in requested_content_classes:
                    raw_metrics.extend(
                        _raw_metric(
                            row,
                            report_row=report_row,
                            source_validation_eligible=authority_status[report_id][0],
                        )
                        for row in report_metrics
                    )
            if request.evidence_ids:
                requested_evidence_ids = set(request.evidence_ids)
                evidence = [
                    item
                    for item in evidence
                    if item.evidence_id in requested_evidence_ids
                ]
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="cross_report_projected_data_read_failed",
            message="Failed to read cross-report projected data",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc

    response = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=source_candidates,
        evidence=evidence,
        raw_metrics=raw_metrics,
        content_hashes={
            report_id: content_hashes.get(report_id, {})
            for report_id in sorted(report_rows)
        },
        excluded_report_counts={
            "filtered": max(len(status_rows) - len(source_candidates), 0),
            **excluded_counts,
        },
    )
    validate_cross_report_contract(response)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cross_report_projected_data_read_complete",
            module=logger.name,
            fields={
                "source_candidate_count": len(response.source_candidates),
                "evidence_count": len(response.evidence),
                "requested_source_report_id_count": len(request.source_report_ids),
                "requested_evidence_id_count": len(request.evidence_ids),
                "raw_metric_count": len(response.raw_metrics),
                "excluded_report_counts": response.excluded_report_counts,
                "selected_report_ids": [
                    candidate.report_id for candidate in response.source_candidates
                ],
            },
        )
    )
    return response
