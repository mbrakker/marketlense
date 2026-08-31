from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlsplit

from src.contracts.report_store import (
    ReportMetadataDbAccessRequest,
    ReportMetadataDbAccessResponse,
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportMetadataUpsertRequest,
    ReportPublicationMetadataGetRequest,
    ReportPublicationMetadataGetResponse,
    ReportSourceIdentityGetRequest,
    ReportSourceIdentityGetResponse,
    ReportSourceIdentityResolveRequest,
    ReportSourceIdentityResolveResponse,
    ReportSourceReuseResolveRequest,
    ReportSourceReuseResolveResponse,
    ReportSourceReuseTelemetryRecord,
    ReportSourceReuseTelemetryRecordRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
    SourceIdentityObservationRecordResponse,
    SourceIdentityResolution,
    SourcePublicationMetadata,
    SourcePublicationMetadataUpsertRequest,
    SourcePublicationMetadataUpsertResponse,
    SourcePublicationObservedValue,
)
from src.contracts.run_context import RunContext
from src.services._sqlite_common import table_exists as _table_exists
from src.utils.cache_utils import sha256_json
from src.utils.coercion import clean_string_list, coerce_int
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import (
    ACCESS_TIMEOUT_SECONDS,
    _clean_metadata,
    _configure_sqlite_connection,
    _is_lock_error,
    logger,
)
from .connection import _metadata_conn

_PUBLICATION_EVIDENCE_STATUSES = {
    "verified",
    "unknown",
    "conflicting",
    "invalid",
    "legacy_unverified",
}
_PUBLICATION_EVIDENCE_KINDS = {
    "json_ld_date_published": 0,
    "open_graph_article_published_time": 1,
    "html_meta_published_time": 2,
    "visible_publication_label": 3,
}
_PUBLICATION_PRECISION = {"year": 1, "month": 2, "day": 3}
_IDENTITY_PUBLICATION_STATUSES = {
    "verified",
    "publisher_inferred",
    "document_inferred",
    "unknown",
}
_IDENTITY_CONFIDENCE = {"high", "medium", "low", "unknown"}
_IDENTITY_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
_IDENTITY_PUBLICATION_RANK = {
    "verified": 0,
    "publisher_inferred": 1,
    "document_inferred": 2,
    "unknown": 3,
}
_REPORT_METADATA_IDENTITY_PLACEHOLDERS = {
    "",
    "...",
    "not extracted",
    "not specified",
    "unknown",
    "unknown publisher",
    "n/a",
    "na",
    "-",
}
_REPORT_METADATA_IDENTITY_LEAKAGE_MARKERS = {
    "ocr text block",
    "table row",
    "table ",
    "row:",
    "cell_",
    "raw_page_text",
    "extracted_text",
    "text block",
}


def _safe_identity_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _safe_report_metadata_identity_text(value: object) -> str:
    text = " ".join(str(value or "").split())
    folded = text.casefold()
    if folded in _REPORT_METADATA_IDENTITY_PLACEHOLDERS or any(
        marker in folded for marker in _REPORT_METADATA_IDENTITY_LEAKAGE_MARKERS
    ):
        return ""
    return text


def _report_metadata_identity_resolution(
    conn: sqlite3.Connection, *, md5: Optional[str]
) -> tuple[SourceIdentityResolution, str]:
    """Resolve a canonical identity from unambiguous stored report metadata.

    This compatibility path is deliberately exact-content-hash-only. It does
    not use a title, filename, URL, or partial publisher match as an identity
    key, and it declines to choose between conflicting retained records.
    """

    clean_md5 = str(md5 or "").strip().casefold()
    if not clean_md5 or not _table_exists(conn, "reports"):
        return _resolve_identity_observations(()), "unresolved"
    rows = conn.execute(
        """
        SELECT file_id, title, publisher, publisher_id, source_url
        FROM reports
        WHERE lower(COALESCE(md5, ''))=? OR lower(COALESCE(source_md5, ''))=?
        ORDER BY file_id ASC
        """,
        (clean_md5, clean_md5),
    ).fetchall()
    candidates = [
        (
            _safe_report_metadata_identity_text(row[1]),
            _safe_report_metadata_identity_text(row[2]),
            str(row[3] or "").strip(),
            _safe_identity_url(row[4]),
        )
        for row in rows
    ]
    candidates = [
        candidate for candidate in candidates if candidate[0] and candidate[1]
    ]
    if not candidates:
        return _resolve_identity_observations(()), "report_metadata_md5_unusable"
    identities = {
        (title.casefold(), publisher.casefold())
        for title, publisher, _, _ in candidates
    }
    if len(identities) != 1:
        resolution = _resolve_identity_observations(())
        resolution = replace(
            resolution,
            identity_issues=(
                "identity_observation_missing",
                "report_metadata_identity_conflict",
            ),
            source_metadata_hash="",
        )
        return (
            replace(
                resolution,
                source_metadata_hash=_identity_resolution_hash(resolution),
            ),
            "report_metadata_md5_conflicting",
        )
    title, publisher, publisher_id, source_url = candidates[0]
    content_hash = f"md5:{clean_md5}"
    resolution = SourceIdentityResolution(
        schema_version="1.0",
        source_identity_id=f"source:{sha256_json({'identity': content_hash})[:32]}",
        canonical_title=title,
        title_evidence_locator="reports.title",
        publisher_id=publisher_id,
        publisher_name=publisher,
        canonical_landing_page_url=source_url,
        acquired_artifact_url=source_url,
        source_page_url=source_url,
        content_hash=content_hash,
        resolution_method="exact_md5_report_metadata",
        identity_confidence="medium",
        identity_issues=(() if source_url else ("canonical_landing_page_url_missing",)),
        identity_status="resolved",
    )
    return (
        replace(resolution, source_metadata_hash=_identity_resolution_hash(resolution)),
        "report_metadata_md5",
    )


def _validate_identity_observation_urls(observation: SourceIdentityObservation) -> None:
    for field_name in (
        "canonical_landing_page_url",
        "acquired_artifact_url",
        "source_page_url",
    ):
        raw_value = str(getattr(observation, field_name) or "").strip()
        if raw_value and not _safe_identity_url(raw_value):
            raise AppError(
                code="source_identity_url_invalid",
                message="Source identity observation contains an unsafe URL",
                retryable=False,
                context={"field_name": field_name},
            )


def _report_source_url_from_store(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    publisher: Optional[str],
    md5: Optional[str],
) -> Optional[str]:
    row, _ = _report_source_identity_row(
        conn,
        report_title=report_title,
        publisher=publisher,
        md5=md5,
        prefer_title=True,
    )
    value = _safe_identity_url(row[3]) if row is not None else ""
    return value or None


def _report_source_publisher_from_store(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    md5: Optional[str],
) -> Optional[str]:
    row, _ = _report_source_identity_row(
        conn,
        report_title=report_title,
        publisher=None,
        md5=md5,
        prefer_title=True,
    )
    return str(row[2] or "").strip() if row and str(row[2] or "").strip() else None


def _report_source_identity_row(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    publisher: Optional[str],
    md5: Optional[str],
    prefer_title: bool = False,
) -> tuple[Optional[sqlite3.Row], str]:
    if not _table_exists(conn, "report_sources"):
        return None, "unresolved"

    def _md5_row() -> Optional[sqlite3.Row]:
        clean_md5 = str(md5 or "").strip()
        if not clean_md5:
            return None
        return conn.execute(
            """
            SELECT id, report_name, publisher_name, landing_page_url
            FROM report_sources
            WHERE md5=?
            ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (clean_md5,),
        ).fetchone()

    def _title_row() -> Optional[sqlite3.Row]:
        normalized_title = report_title.strip().casefold()
        normalized_publisher = str(publisher or "").strip().casefold()
        if not normalized_title:
            return None
        rows = conn.execute(
            """
            SELECT id, report_name, publisher_name, landing_page_url
            FROM report_sources
            WHERE lower(report_name)=?
              AND (?='' OR lower(COALESCE(publisher_name, ''))=?)
            ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
            LIMIT 2
            """,
            (normalized_title, normalized_publisher, normalized_publisher),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        return None

    normalized_publisher = str(publisher or "").strip().casefold()
    candidates = (
        (("title", _title_row), ("md5", _md5_row))
        if prefer_title
        else (("md5", _md5_row), ("title", _title_row))
    )
    for source, resolver in candidates:
        row = resolver()
        if row is not None:
            if source == "md5":
                return row, "md5"
            return row, (
                "title_publisher_unambiguous"
                if normalized_publisher
                else "title_unambiguous"
            )
    return None, "unresolved"


def resolve_report_source_identity(
    request: ReportSourceIdentityResolveRequest, ctx: RunContext
) -> ReportSourceIdentityResolveResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_identity_resolve_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "report_title": request.report_title,
                "has_md5": bool(str(request.md5 or "").strip()),
            },
        )
    )
    if not request.db_path or not request.db_path.strip():
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        row, source = _report_source_identity_row(
            conn,
            report_title=request.report_title,
            publisher=request.publisher_name,
            md5=request.md5,
        )
    if row is None:
        response = ReportSourceIdentityResolveResponse(
            schema_version="1.0",
            publisher_name=str(request.publisher_name or "").strip(),
            report_name=str(request.report_title or "").strip(),
            source_url="",
            resolution_source=source,
        )
    else:
        response = ReportSourceIdentityResolveResponse(
            schema_version="1.0",
            report_name=str(row[1] or "").strip()
            or str(request.report_title or "").strip(),
            publisher_name=str(row[2] or "").strip()
            or str(request.publisher_name or "").strip(),
            source_url=_safe_identity_url(row[3]),
            resolution_source=source,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_identity_resolve_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "report_name": response.report_name,
                "has_source_url": bool(response.source_url),
                "resolution_source": response.resolution_source,
            },
        )
    )
    return response


def _identity_issues_from_json(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw.strip():
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(sorted({str(item).strip() for item in values if str(item).strip()}))


def _identity_observation_from_row(
    row: tuple[object, ...],
) -> SourceIdentityObservation:
    return SourceIdentityObservation(
        schema_version=str(row[2] or "1.0"),
        source_record_id=coerce_int(row[1], min_value=0),
        canonical_title=str(row[3] or "").strip(),
        title_evidence_locator=str(row[4] or "").strip(),
        publisher_id=str(row[5] or "").strip(),
        publisher_name=str(row[6] or "").strip(),
        canonical_landing_page_url=_safe_identity_url(row[7]),
        acquired_artifact_url=_safe_identity_url(row[8]),
        source_page_url=_safe_identity_url(row[9]),
        publication_date=str(row[10] or "").strip(),
        publication_date_status=str(row[11] or "unknown").strip() or "unknown",
        publication_date_evidence_locator=str(row[12] or "").strip(),
        discovered_at_utc=str(row[13] or "").strip(),
        retrieved_at_utc=str(row[14] or "").strip(),
        acquisition_route=str(row[15] or "").strip(),
        content_hash=str(row[16] or "").strip(),
        resolution_method=str(row[17] or "").strip(),
        identity_confidence=str(row[18] or "unknown").strip() or "unknown",
        identity_issues=_identity_issues_from_json(row[19]),
        supersedes_source_identity_id=str(row[20] or "").strip(),
    )


def _identity_resolution_hash(resolution: SourceIdentityResolution) -> str:
    return sha256_json(
        {
            "schema_version": resolution.schema_version,
            "source_identity_id": resolution.source_identity_id,
            "canonical_title": resolution.canonical_title,
            "publisher_id": resolution.publisher_id,
            "publisher_name": resolution.publisher_name,
            "canonical_landing_page_url": resolution.canonical_landing_page_url,
            "acquired_artifact_url": resolution.acquired_artifact_url,
            "source_page_url": resolution.source_page_url,
            "publication_date": resolution.publication_date,
            "publication_date_status": resolution.publication_date_status,
            "publication_date_evidence_locator": resolution.publication_date_evidence_locator,
            "acquisition_route": resolution.acquisition_route,
            "content_hash": resolution.content_hash,
            "resolution_method": resolution.resolution_method,
            "identity_status": resolution.identity_status,
            "identity_issues": list(resolution.identity_issues),
            "supersedes_source_identity_id": resolution.supersedes_source_identity_id,
        }
    )


def _identity_resolution_from_row(row: tuple[object, ...]) -> SourceIdentityResolution:
    resolution = SourceIdentityResolution(
        schema_version=str(row[1] or "1.0"),
        source_record_id=coerce_int(row[0], min_value=0),
        source_identity_id=str(row[2] or "").strip(),
        canonical_title=str(row[3] or "").strip(),
        title_evidence_locator=str(row[4] or "").strip(),
        publisher_id=str(row[5] or "").strip(),
        publisher_name=str(row[6] or "").strip(),
        canonical_landing_page_url=_safe_identity_url(row[7]),
        acquired_artifact_url=_safe_identity_url(row[8]),
        source_page_url=_safe_identity_url(row[9]),
        publication_date=str(row[10] or "").strip(),
        publication_date_status=str(row[11] or "unknown").strip() or "unknown",
        publication_date_evidence_locator=str(row[12] or "").strip(),
        discovered_at_utc=str(row[13] or "").strip(),
        retrieved_at_utc=str(row[14] or "").strip(),
        acquisition_route=str(row[15] or "").strip(),
        content_hash=str(row[16] or "").strip(),
        resolution_method=str(row[17] or "").strip(),
        identity_confidence=str(row[18] or "unknown").strip() or "unknown",
        identity_issues=_identity_issues_from_json(row[19]),
        supersedes_source_identity_id=str(row[20] or "").strip(),
        identity_status=str(row[21] or "unknown").strip() or "unknown",
        source_metadata_hash=str(row[22] or "").strip(),
        observation_count=coerce_int(row[23], min_value=0),
    )
    return (
        resolution
        if resolution.source_metadata_hash
        else replace(
            resolution, source_metadata_hash=_identity_resolution_hash(resolution)
        )
    )


def _observation_sort_key(observation: SourceIdentityObservation) -> tuple[object, ...]:
    return (
        _IDENTITY_PUBLICATION_RANK.get(observation.publication_date_status, 99),
        _IDENTITY_CONFIDENCE_RANK.get(observation.identity_confidence, 99),
        0 if observation.title_evidence_locator else 1,
        0 if observation.canonical_landing_page_url else 1,
        observation.resolution_method,
        observation.canonical_title.casefold(),
        observation.publisher_name.casefold(),
        observation.content_hash,
    )


def _first_identity_value(
    observations: tuple[SourceIdentityObservation, ...], field_name: str
) -> str:
    for observation in sorted(observations, key=_observation_sort_key):
        value = str(getattr(observation, field_name) or "").strip()
        if value:
            return value
    return ""


def _identity_conflict_issues(
    observations: tuple[SourceIdentityObservation, ...],
) -> tuple[str, ...]:
    issues = {
        issue
        for observation in observations
        for issue in observation.identity_issues
        if issue
    }
    for field_name, issue in (
        ("canonical_title", "canonical_title_conflict"),
        ("publisher_name", "publisher_name_conflict"),
        ("canonical_landing_page_url", "canonical_landing_page_url_conflict"),
    ):
        values = {
            str(getattr(observation, field_name) or "").strip().casefold()
            for observation in observations
            if str(getattr(observation, field_name) or "").strip()
        }
        if len(values) > 1:
            issues.add(issue)
    dates = {
        observation.publication_date
        for observation in observations
        if observation.publication_date_status == "verified"
        and observation.publication_date
    }
    if len(dates) > 1:
        issues.add("publication_date_conflict")
    if not _first_identity_value(observations, "canonical_landing_page_url"):
        issues.add("canonical_landing_page_url_missing")
    if not _first_identity_value(observations, "canonical_title"):
        issues.add("canonical_title_missing")
    return tuple(sorted(issues))


def _resolve_identity_observations(
    observations: tuple[SourceIdentityObservation, ...],
) -> SourceIdentityResolution:
    if not observations:
        resolution = SourceIdentityResolution(
            schema_version="1.0",
            identity_status="unknown",
            identity_issues=("identity_observation_missing",),
        )
        return replace(
            resolution, source_metadata_hash=_identity_resolution_hash(resolution)
        )
    chosen = min(observations, key=_observation_sort_key)
    issues = _identity_conflict_issues(observations)
    content_hash = _first_identity_value(observations, "content_hash")
    identity_material = content_hash or "|".join(
        (
            _first_identity_value(observations, "canonical_landing_page_url"),
            _first_identity_value(observations, "publisher_name").casefold(),
            _first_identity_value(observations, "canonical_title").casefold(),
        )
    )
    source_identity_id = (
        f"source:{sha256_json({'identity': identity_material})[:32]}"
        if identity_material
        else ""
    )
    date_conflict = "publication_date_conflict" in issues
    publication_date = "" if date_conflict else chosen.publication_date
    publication_status = "unknown" if date_conflict else chosen.publication_date_status
    identity_status = "resolved" if source_identity_id else "unknown"
    if date_conflict:
        identity_status = "conflicting"
    confidence = chosen.identity_confidence
    if issues and confidence == "high":
        confidence = "medium"
    resolution = SourceIdentityResolution(
        schema_version="1.0",
        source_record_id=chosen.source_record_id,
        source_identity_id=source_identity_id,
        canonical_title=_first_identity_value(observations, "canonical_title"),
        title_evidence_locator=_first_identity_value(
            observations, "title_evidence_locator"
        ),
        publisher_id=_first_identity_value(observations, "publisher_id"),
        publisher_name=_first_identity_value(observations, "publisher_name"),
        canonical_landing_page_url=_first_identity_value(
            observations, "canonical_landing_page_url"
        ),
        acquired_artifact_url=_first_identity_value(
            observations, "acquired_artifact_url"
        ),
        source_page_url=_first_identity_value(observations, "source_page_url"),
        publication_date=publication_date,
        publication_date_status=publication_status,
        publication_date_evidence_locator=(
            "" if date_conflict else chosen.publication_date_evidence_locator
        ),
        discovered_at_utc=_first_identity_value(observations, "discovered_at_utc"),
        retrieved_at_utc=_first_identity_value(observations, "retrieved_at_utc"),
        acquisition_route=_first_identity_value(observations, "acquisition_route"),
        content_hash=content_hash,
        resolution_method=(
            "publisher_evidence_preferred"
            if chosen.publication_date_status == "verified"
            else chosen.resolution_method or "deterministic_observation_resolver"
        ),
        identity_confidence=confidence,
        identity_issues=issues,
        supersedes_source_identity_id=_first_identity_value(
            observations, "supersedes_source_identity_id"
        ),
        identity_status=identity_status,
        observation_count=len(observations),
    )
    return replace(
        resolution, source_metadata_hash=_identity_resolution_hash(resolution)
    )


def _legacy_identity_resolution(
    conn: sqlite3.Connection, source_record_id: int
) -> SourceIdentityResolution:
    row = conn.execute(
        """
        SELECT id, report_name, publisher_name, landing_page_url, source_page_url,
               discovered_at_utc, downloaded_at_utc, md5
        FROM report_sources WHERE id=?
        """,
        (source_record_id,),
    ).fetchone()
    if row is None:
        return _resolve_identity_observations(())
    md5 = str(row[7] or "").strip().lower()
    content_hash = f"md5:{md5}" if md5 else ""
    source_identity_id = (
        f"source:{sha256_json({'identity': content_hash})[:32]}" if content_hash else ""
    )
    resolution = SourceIdentityResolution(
        schema_version="1.0",
        source_record_id=coerce_int(row[0], min_value=0),
        source_identity_id=source_identity_id,
        canonical_title=str(row[1] or "").strip(),
        title_evidence_locator="legacy_report_sources.report_name",
        publisher_name=str(row[2] or "").strip(),
        canonical_landing_page_url=_safe_identity_url(row[3]),
        source_page_url=_safe_identity_url(row[4] or row[3]),
        discovered_at_utc=str(row[5] or "").strip(),
        retrieved_at_utc=str(row[6] or "").strip(),
        acquisition_route="legacy_report_source",
        content_hash=content_hash,
        resolution_method="legacy_report_sources",
        identity_confidence="low",
        identity_issues=("identity_observation_missing", "legacy_source_unverified"),
        identity_status="legacy_unverified",
    )
    return replace(
        resolution, source_metadata_hash=_identity_resolution_hash(resolution)
    )


def _identity_observations_for_source(
    conn: sqlite3.Connection, source_record_id: int
) -> tuple[SourceIdentityObservation, ...]:
    rows = conn.execute(
        """
        SELECT observation_id, source_record_id, schema_version, canonical_title,
               title_evidence_locator, publisher_id, publisher_name,
               canonical_landing_page_url, acquired_artifact_url, source_page_url,
               publication_date, publication_date_status,
               publication_date_evidence_locator, discovered_at_utc,
               retrieved_at_utc, acquisition_route, content_hash,
               resolution_method, identity_confidence, identity_issues_json,
               supersedes_source_identity_id
        FROM source_identity_observations
        WHERE source_record_id=?
        ORDER BY observation_id ASC
        """,
        (source_record_id,),
    ).fetchall()
    return tuple(_identity_observation_from_row(row) for row in rows)


def _store_identity_resolution(
    conn: sqlite3.Connection, resolution: SourceIdentityResolution
) -> None:
    columns = (
        "source_record_id",
        "schema_version",
        "source_identity_id",
        "canonical_title",
        "title_evidence_locator",
        "publisher_id",
        "publisher_name",
        "canonical_landing_page_url",
        "acquired_artifact_url",
        "source_page_url",
        "publication_date",
        "publication_date_status",
        "publication_date_evidence_locator",
        "discovered_at_utc",
        "retrieved_at_utc",
        "acquisition_route",
        "content_hash",
        "resolution_method",
        "identity_confidence",
        "identity_issues_json",
        "supersedes_source_identity_id",
        "identity_status",
        "source_metadata_hash",
        "observation_count",
        "resolved_at_utc",
    )
    values = (
        resolution.source_record_id,
        resolution.schema_version,
        resolution.source_identity_id,
        resolution.canonical_title,
        resolution.title_evidence_locator,
        resolution.publisher_id,
        resolution.publisher_name,
        resolution.canonical_landing_page_url,
        resolution.acquired_artifact_url,
        resolution.source_page_url,
        resolution.publication_date,
        resolution.publication_date_status,
        resolution.publication_date_evidence_locator,
        resolution.discovered_at_utc,
        resolution.retrieved_at_utc,
        resolution.acquisition_route,
        resolution.content_hash,
        resolution.resolution_method,
        resolution.identity_confidence,
        json.dumps(
            list(resolution.identity_issues), ensure_ascii=True, separators=(",", ":")
        ),
        resolution.supersedes_source_identity_id,
        resolution.identity_status,
        resolution.source_metadata_hash,
        resolution.observation_count,
        "strftime('%Y-%m-%dT%H:%M:%fZ','now')",
    )
    placeholders = ", ".join("?" for _ in columns[:-1]) + ", " + values[-1]
    update_columns = [column for column in columns[1:] if column != "resolved_at_utc"]
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in update_columns
    )
    conn.execute(
        f"INSERT INTO source_identity_resolutions({', '.join(columns)}) "
        f"VALUES({placeholders}) ON CONFLICT(source_record_id) DO UPDATE SET {update_clause}, "
        "resolved_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')",
        values[:-1],
    )


def record_source_identity_observation(
    request: SourceIdentityObservationRecordRequest, ctx: RunContext
) -> SourceIdentityObservationRecordResponse:
    observation = request.observation
    if not request.db_path.strip():
        raise AppError(
            code="source_identity_db_missing",
            message="Reports database path is required for source identity persistence",
            retryable=False,
        )
    if observation.source_record_id <= 0:
        raise AppError(
            code="source_identity_source_missing",
            message="Source identity observation requires a persisted source record",
            retryable=False,
        )
    if observation.publication_date_status not in _IDENTITY_PUBLICATION_STATUSES:
        raise AppError(
            code="source_identity_publication_status_invalid",
            message="Source identity observation has an unsupported publication-date status",
            retryable=False,
            context={"publication_date_status": observation.publication_date_status},
        )
    if observation.identity_confidence not in _IDENTITY_CONFIDENCE:
        raise AppError(
            code="source_identity_confidence_invalid",
            message="Source identity observation has an unsupported confidence",
            retryable=False,
            context={"identity_confidence": observation.identity_confidence},
        )
    _validate_identity_observation_urls(observation)
    observation_id = sha256_json(asdict(observation))
    with _metadata_conn(request.db_path, ctx) as conn:
        source_exists = conn.execute(
            "SELECT 1 FROM report_sources WHERE id=?", (observation.source_record_id,)
        ).fetchone()
        if source_exists is None:
            raise AppError(
                code="source_identity_source_missing",
                message="Source identity observation references no report source",
                retryable=False,
                context={"source_record_id": observation.source_record_id},
            )
        existing = conn.execute(
            "SELECT source_metadata_hash FROM source_identity_resolutions WHERE source_record_id=?",
            (observation.source_record_id,),
        ).fetchone()
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO source_identity_observations(
                observation_id, source_record_id, schema_version, canonical_title,
                title_evidence_locator, publisher_id, publisher_name,
                canonical_landing_page_url, acquired_artifact_url, source_page_url,
                publication_date, publication_date_status,
                publication_date_evidence_locator, discovered_at_utc, retrieved_at_utc,
                acquisition_route, content_hash, resolution_method, identity_confidence,
                identity_issues_json, supersedes_source_identity_id, created_at_utc
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            """,
            (
                observation_id,
                observation.source_record_id,
                observation.schema_version,
                observation.canonical_title,
                observation.title_evidence_locator,
                observation.publisher_id,
                observation.publisher_name,
                observation.canonical_landing_page_url,
                observation.acquired_artifact_url,
                observation.source_page_url,
                observation.publication_date,
                observation.publication_date_status,
                observation.publication_date_evidence_locator,
                observation.discovered_at_utc,
                observation.retrieved_at_utc,
                observation.acquisition_route,
                observation.content_hash,
                observation.resolution_method,
                observation.identity_confidence,
                json.dumps(
                    list(observation.identity_issues),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                observation.supersedes_source_identity_id,
            ),
        )
        resolution = _resolve_identity_observations(
            _identity_observations_for_source(conn, observation.source_record_id)
        )
        _store_identity_resolution(conn, resolution)
    created = cur.rowcount > 0
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_identity_observation_recorded",
            module=logger.name,
            fields={
                "source_record_id": observation.source_record_id,
                "observation_id": observation_id,
                "created": created,
                "publication_date_status": observation.publication_date_status,
                "acquisition_route": observation.acquisition_route,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_identity_resolved",
            module=logger.name,
            fields={
                "source_record_id": resolution.source_record_id,
                "source_identity_id": resolution.source_identity_id,
                "identity_status": resolution.identity_status,
                "publication_date_status": resolution.publication_date_status,
                "observation_count": resolution.observation_count,
            },
        )
    )
    if resolution.identity_status == "conflicting" or any(
        issue.endswith("_conflict") for issue in resolution.identity_issues
    ):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="source_identity_conflict",
                module=logger.name,
                fields={
                    "source_record_id": resolution.source_record_id,
                    "identity_status": resolution.identity_status,
                    "issue_count": len(resolution.identity_issues),
                },
            )
        )
    if resolution.publication_date_status == "unknown":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="source_identity_unknown_publication_date",
                module=logger.name,
                fields={"source_record_id": resolution.source_record_id},
            )
        )
    old_hash = str(existing[0] or "").strip() if existing else ""
    if old_hash and old_hash != resolution.source_metadata_hash:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="source_metadata_hash_changed",
                module=logger.name,
                fields={
                    "source_record_id": resolution.source_record_id,
                    "source_identity_id": resolution.source_identity_id,
                },
            )
        )
    return SourceIdentityObservationRecordResponse(
        schema_version="1.0",
        observation_id=observation_id,
        created=created,
        resolution=resolution,
    )


def get_report_source_identity(
    request: ReportSourceIdentityGetRequest, ctx: RunContext
) -> ReportSourceIdentityGetResponse:
    if not request.db_path.strip():
        raise AppError(
            code="source_identity_db_missing",
            message="Reports database path is required for source identity lookup",
            retryable=False,
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        row, resolution_source = _report_source_identity_row(
            conn,
            report_title=request.report_title,
            publisher=request.publisher_name,
            md5=request.md5,
        )
        if row is None:
            resolution, resolution_source = _report_metadata_identity_resolution(
                conn,
                md5=request.md5,
            )
        else:
            source_record_id = coerce_int(row[0], min_value=0)
            resolution_row = conn.execute(
                """
                SELECT source_record_id, schema_version, source_identity_id,
                       canonical_title, title_evidence_locator, publisher_id,
                       publisher_name, canonical_landing_page_url,
                       acquired_artifact_url, source_page_url, publication_date,
                       publication_date_status, publication_date_evidence_locator,
                       discovered_at_utc, retrieved_at_utc, acquisition_route,
                       content_hash, resolution_method, identity_confidence,
                       identity_issues_json, supersedes_source_identity_id,
                       identity_status, source_metadata_hash, observation_count
                FROM source_identity_resolutions WHERE source_record_id=?
                """,
                (source_record_id,),
            ).fetchone()
            resolution = (
                _identity_resolution_from_row(resolution_row)
                if resolution_row is not None
                else _legacy_identity_resolution(conn, source_record_id)
            )
            legacy_resolution = _legacy_identity_resolution(conn, source_record_id)
            if not resolution.publisher_name and legacy_resolution.publisher_name:
                resolution = replace(
                    resolution,
                    publisher_id=legacy_resolution.publisher_id,
                    publisher_name=legacy_resolution.publisher_name,
                    resolution_method="legacy_report_sources_publisher_fallback",
                    identity_confidence="medium",
                )
                resolution = replace(
                    resolution,
                    source_metadata_hash=_identity_resolution_hash(resolution),
                )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_identity_resolved",
            module=logger.name,
            fields={
                "source_record_id": resolution.source_record_id,
                "source_identity_id": resolution.source_identity_id,
                "identity_status": resolution.identity_status,
                "resolution_source": resolution_source,
            },
        )
    )
    return ReportSourceIdentityGetResponse(
        schema_version="1.0",
        resolution=resolution,
        resolution_source=resolution_source,
    )


def _unknown_publication_metadata(
    *,
    source_record_id: int = 0,
    source_url: str = "",
    legacy: bool = False,
) -> SourcePublicationMetadata:
    return SourcePublicationMetadata(
        schema_version="1.0",
        source_record_id=source_record_id,
        source_identity=(
            f"report_source:{source_record_id}" if source_record_id else ""
        ),
        source_url=source_url,
        evidence_status="legacy_unverified" if legacy else "unknown",
        contradiction_status="not_applicable",
    )


def _observations_from_json(raw: object) -> tuple[SourcePublicationObservedValue, ...]:
    if not isinstance(raw, str) or not raw.strip():
        return ()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    observations: list[SourcePublicationObservedValue] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            observations.append(SourcePublicationObservedValue(**item))
        except TypeError:
            continue
    return tuple(observations)


def _publication_metadata_from_row(
    row: tuple[object, ...],
) -> SourcePublicationMetadata:
    source_record_id = coerce_int(row[0], min_value=0)
    return SourcePublicationMetadata(
        schema_version=str(row[1] or "1.0"),
        source_record_id=source_record_id,
        source_identity=f"report_source:{source_record_id}",
        publication_date=str(row[2] or "").strip(),
        publication_date_precision=str(row[3] or "").strip(),
        source_url=str(row[4] or "").strip(),
        retrieved_at_utc=str(row[5] or "").strip(),
        evidence_kind=str(row[6] or "").strip(),
        evidence_locator=str(row[7] or "").strip(),
        evidence_value_hash=str(row[8] or "").strip(),
        evidence_status=str(row[9] or "unknown").strip() or "unknown",
        contradiction_status=str(row[10] or "not_applicable").strip()
        or "not_applicable",
        observed_values=_observations_from_json(row[11]),
    )


def _publication_observation_key(
    observation: SourcePublicationObservedValue,
) -> tuple[str, ...]:
    return (
        observation.publication_date,
        observation.publication_date_precision,
        observation.source_url,
        observation.retrieved_at_utc,
        observation.evidence_kind,
        observation.evidence_locator,
        observation.evidence_value_hash,
        observation.evidence_status,
    )


def _merged_observations(
    *values: tuple[SourcePublicationObservedValue, ...],
) -> tuple[SourcePublicationObservedValue, ...]:
    unique = {
        _publication_observation_key(observation): observation
        for group in values
        for observation in group
    }
    return tuple(unique[key] for key in sorted(unique))


def _dates_are_compatible(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}-") or right.startswith(f"{left}-")


def _best_publication_observation(
    observations: tuple[SourcePublicationObservedValue, ...],
) -> SourcePublicationObservedValue | None:
    verified = [
        item
        for item in observations
        if item.evidence_status == "verified" and item.publication_date
    ]
    if not verified:
        return None
    return min(
        verified,
        key=lambda item: (
            _PUBLICATION_EVIDENCE_KINDS.get(item.evidence_kind, 99),
            -_PUBLICATION_PRECISION.get(item.publication_date_precision, 0),
            item.publication_date,
            item.evidence_locator,
            item.evidence_value_hash,
        ),
    )


def _merged_publication_metadata(
    *,
    existing: SourcePublicationMetadata | None,
    incoming: SourcePublicationMetadata,
) -> SourcePublicationMetadata:
    observations = _merged_observations(
        existing.observed_values if existing else (), incoming.observed_values
    )
    if not observations and incoming.evidence_status in {"unknown", "invalid"}:
        observations = (
            SourcePublicationObservedValue(
                schema_version="1.0",
                publication_date=incoming.publication_date,
                publication_date_precision=incoming.publication_date_precision,
                source_url=incoming.source_url,
                retrieved_at_utc=incoming.retrieved_at_utc,
                evidence_kind=incoming.evidence_kind,
                evidence_locator=incoming.evidence_locator,
                evidence_value_hash=incoming.evidence_value_hash,
                evidence_status=incoming.evidence_status,
            ),
        )
    verified_dates = [
        item.publication_date
        for item in observations
        if item.evidence_status == "verified" and item.publication_date
    ]
    conflicting = any(
        not _dates_are_compatible(left, right)
        for index, left in enumerate(verified_dates)
        for right in verified_dates[index + 1 :]
    )
    best = _best_publication_observation(observations)
    if conflicting:
        status = "conflicting"
        contradiction_status = "conflicting"
    elif best is not None:
        status = "verified"
        contradiction_status = "none"
    elif any(item.evidence_status == "invalid" for item in observations):
        status = "invalid"
        contradiction_status = "not_applicable"
    elif existing is not None and existing.evidence_status == "legacy_unverified":
        status = "legacy_unverified"
        contradiction_status = "not_applicable"
    else:
        status = "unknown"
        contradiction_status = "not_applicable"
    selected = best or next(
        (item for item in observations if item.evidence_status == "invalid"), None
    )
    return SourcePublicationMetadata(
        schema_version="1.0",
        source_record_id=incoming.source_record_id,
        source_identity=f"report_source:{incoming.source_record_id}",
        publication_date=selected.publication_date if selected else "",
        publication_date_precision=(
            selected.publication_date_precision if selected else ""
        ),
        source_url=(selected.source_url if selected else incoming.source_url),
        retrieved_at_utc=(
            selected.retrieved_at_utc if selected else incoming.retrieved_at_utc
        ),
        evidence_kind=selected.evidence_kind if selected else incoming.evidence_kind,
        evidence_locator=(
            selected.evidence_locator if selected else incoming.evidence_locator
        ),
        evidence_value_hash=(
            selected.evidence_value_hash if selected else incoming.evidence_value_hash
        ),
        evidence_status=status,
        contradiction_status=contradiction_status,
        observed_values=observations,
    )


def upsert_source_publication_metadata(
    request: SourcePublicationMetadataUpsertRequest,
    ctx: RunContext,
) -> SourcePublicationMetadataUpsertResponse:
    incoming = request.metadata
    if not request.db_path.strip():
        raise AppError(
            code="source_publication_metadata_db_missing",
            message="Reports database path is required for publication metadata",
            retryable=False,
        )
    if incoming.source_record_id <= 0:
        raise AppError(
            code="source_publication_metadata_source_missing",
            message="Publication metadata requires a persisted report source record",
            retryable=False,
        )
    if incoming.evidence_status not in _PUBLICATION_EVIDENCE_STATUSES:
        raise AppError(
            code="source_publication_metadata_status_invalid",
            message="Publication metadata has an unsupported evidence status",
            retryable=False,
            context={"evidence_status": incoming.evidence_status},
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        source_exists = conn.execute(
            "SELECT 1 FROM report_sources WHERE id=?", (incoming.source_record_id,)
        ).fetchone()
        if source_exists is None:
            raise AppError(
                code="source_publication_metadata_source_missing",
                message="Publication metadata source record does not exist",
                retryable=False,
                context={"source_record_id": incoming.source_record_id},
            )
        row = conn.execute(
            """
            SELECT source_record_id, schema_version, publication_date,
                   publication_date_precision, source_url, retrieved_at_utc,
                   evidence_kind, evidence_locator, evidence_value_hash,
                   evidence_status, contradiction_status, observed_values_json
            FROM source_publication_metadata
            WHERE source_record_id=?
            """,
            (incoming.source_record_id,),
        ).fetchone()
        existing = _publication_metadata_from_row(row) if row else None
        merged = _merged_publication_metadata(existing=existing, incoming=incoming)
        changed = merged != existing
        if changed:
            observed_values_json = json.dumps(
                [asdict(item) for item in merged.observed_values],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            conn.execute(
                """
                INSERT INTO source_publication_metadata(
                    source_record_id, schema_version, publication_date,
                    publication_date_precision, source_url, retrieved_at_utc,
                    evidence_kind, evidence_locator, evidence_value_hash,
                    evidence_status, contradiction_status, observed_values_json,
                    created_at_utc, updated_at_utc
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                       strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(source_record_id) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    publication_date=excluded.publication_date,
                    publication_date_precision=excluded.publication_date_precision,
                    source_url=excluded.source_url,
                    retrieved_at_utc=excluded.retrieved_at_utc,
                    evidence_kind=excluded.evidence_kind,
                    evidence_locator=excluded.evidence_locator,
                    evidence_value_hash=excluded.evidence_value_hash,
                    evidence_status=excluded.evidence_status,
                    contradiction_status=excluded.contradiction_status,
                    observed_values_json=excluded.observed_values_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    merged.source_record_id,
                    merged.schema_version,
                    merged.publication_date,
                    merged.publication_date_precision,
                    merged.source_url,
                    merged.retrieved_at_utc,
                    merged.evidence_kind,
                    merged.evidence_locator,
                    merged.evidence_value_hash,
                    merged.evidence_status,
                    merged.contradiction_status,
                    observed_values_json,
                ),
            )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_publication_metadata_upserted",
            module=logger.name,
            fields={
                "source_record_id": merged.source_record_id,
                "evidence_status": merged.evidence_status,
                "contradiction_status": merged.contradiction_status,
                "evidence_kind": merged.evidence_kind,
                "evidence_locator": merged.evidence_locator,
                "evidence_value_hash": merged.evidence_value_hash,
                "observed_value_count": len(merged.observed_values),
                "changed": changed,
            },
        )
    )
    return SourcePublicationMetadataUpsertResponse(
        schema_version="1.0", metadata=merged, changed=changed
    )


def get_report_publication_metadata(
    request: ReportPublicationMetadataGetRequest,
    ctx: RunContext,
) -> ReportPublicationMetadataGetResponse:
    if not request.db_path.strip():
        raise AppError(
            code="source_publication_metadata_db_missing",
            message="Reports database path is required for publication metadata lookup",
            retryable=False,
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        row, resolution_source = _report_source_identity_row(
            conn,
            report_title=request.report_title,
            publisher=request.publisher_name,
            md5=request.md5,
        )
        if row is None:
            metadata = _unknown_publication_metadata()
        else:
            source_record_id = int(row[0])
            metadata_row = conn.execute(
                """
                SELECT source_record_id, schema_version, publication_date,
                       publication_date_precision, source_url, retrieved_at_utc,
                       evidence_kind, evidence_locator, evidence_value_hash,
                       evidence_status, contradiction_status, observed_values_json
                FROM source_publication_metadata
                WHERE source_record_id=?
                """,
                (source_record_id,),
            ).fetchone()
            metadata = (
                _publication_metadata_from_row(metadata_row)
                if metadata_row
                else _unknown_publication_metadata(
                    source_record_id=source_record_id,
                    source_url=str(row[3] or "").strip(),
                    legacy=True,
                )
            )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_publication_metadata_resolved",
            module=logger.name,
            fields={
                "source_record_id": metadata.source_record_id,
                "resolution_source": resolution_source,
                "evidence_status": metadata.evidence_status,
                "contradiction_status": metadata.contradiction_status,
                "evidence_kind": metadata.evidence_kind,
                "evidence_locator": metadata.evidence_locator,
                "evidence_value_hash": metadata.evidence_value_hash,
            },
        )
    )
    return ReportPublicationMetadataGetResponse(
        schema_version="1.0",
        metadata=metadata,
        resolution_source=resolution_source,
    )


def _row_to_metadata_response(row: tuple, ctx: RunContext) -> ReportMetadataGetResponse:
    file_id = row[0]
    taxonomy_json = row[4] or "[]"
    categories_json = row[5] or "[]"
    page_count_raw = row[11]
    contents_page_raw = row[12]
    metadata_json = row[13] or "{}"
    analysis_mode = row[14] or "vector_store"
    vector_store_id = row[15]
    evidence_packs_json = row[16] or "{}"
    taxonomy: List[str] = []
    categories: List[str] = []
    pdf_metadata: dict[str, str] = {}
    page_count: Optional[int] = None
    contents_page_number = 0
    evidence_pack_paths: dict[str, str] = {}
    raw_time_period = row[7] if isinstance(row[7], str) else None
    time_period = raw_time_period

    try:
        parsed = json.loads(taxonomy_json)
        if isinstance(parsed, list):
            taxonomy = clean_string_list([str(item) for item in parsed])
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_taxonomy_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        parsed_cats = json.loads(categories_json)
        if isinstance(parsed_cats, list):
            categories = clean_string_list([str(item) for item in parsed_cats])
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_categories_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        parsed_meta = json.loads(metadata_json)
        if isinstance(parsed_meta, dict):
            pdf_metadata = _clean_metadata({str(k): v for k, v in parsed_meta.items()})
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_pdf_metadata_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        if page_count_raw is not None:
            page_int = int(page_count_raw)
            page_count = page_int if page_int >= 0 else None
    except (TypeError, ValueError):
        page_count = None
    try:
        if contents_page_raw is not None:
            contents_int = int(contents_page_raw)
            contents_page_number = contents_int if contents_int >= 0 else 0
    except (TypeError, ValueError):
        contents_page_number = 0
    try:
        parsed_packs = json.loads(evidence_packs_json)
        if isinstance(parsed_packs, dict):
            evidence_pack_paths = {
                str(k): str(v)
                for k, v in parsed_packs.items()
                if str(k).strip() and str(v).strip()
            }
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_evidence_packs_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    return ReportMetadataGetResponse(
        schema_version="1.1",
        file_id=str(file_id),
        file_name=str(row[1] or "").strip() or None,
        title=str(row[2] or ""),
        publisher=str(row[3] or "") or None,
        taxonomy=taxonomy,
        categories=categories,
        region=str(row[6] or "") or None,
        time_period=time_period,
        source_url=str(row[8] or "") or None,
        html_path=str(row[9] or "") or None,
        md5=str(row[10] or "") or None,
        page_count=page_count,
        contents_page_number=contents_page_number,
        pdf_metadata=pdf_metadata,
        created_at=int(row[17]),
        updated_at=int(row[18]),
        analysis_mode=str(analysis_mode),
        vector_store_id=vector_store_id,
        evidence_pack_paths=evidence_pack_paths,
        source_identity_id=str(row[19] or "").strip(),
        source_metadata_hash=str(row[20] or "").strip(),
        source_identity_status=str(row[21] or "unknown").strip() or "unknown",
        source_publication_date_status=str(row[22] or "unknown").strip() or "unknown",
    )


def check_report_db_access(
    request: ReportMetadataDbAccessRequest, ctx: RunContext
) -> ReportMetadataDbAccessResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_db_access_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    if not request.db_path or not request.db_path.strip():
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    timeout = (
        request.timeout_seconds
        if request.timeout_seconds >= 0
        else ACCESS_TIMEOUT_SECONDS
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_db_access_config",
            module=logger.name,
            fields={"timeout_seconds": timeout},
        )
    )
    try:
        conn = sqlite3.connect(request.db_path, timeout=timeout)
    except sqlite3.Error as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_connect_failed",
                module=logger.name,
                fields={"db_path": request.db_path, "error": str(exc)},
            )
        )
        raise AppError(
            code="metadata_db_unavailable",
            message="Failed to open report metadata DB",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path},
        ) from exc
    try:
        _configure_sqlite_connection(conn, busy_timeout_seconds=timeout)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_probe",
                module=logger.name,
                fields={"db_path": request.db_path},
            )
        )
        conn.execute("PRAGMA schema_version")
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            message = str(exc)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="report_db_access_locked",
                    module=logger.name,
                    fields={"db_path": request.db_path, "error": message},
                )
            )
            response = ReportMetadataDbAccessResponse(
                schema_version="1.0",
                db_path=request.db_path,
                accessible=False,
                locked=True,
                message=message,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="report_db_access_complete",
                    module=logger.name,
                    fields={
                        "db_path": response.db_path,
                        "accessible": response.accessible,
                        "locked": response.locked,
                        "message": response.message,
                    },
                )
            )
            return response
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_failed",
                module=logger.name,
                fields={"db_path": request.db_path, "error": str(exc)},
            )
        )
        raise AppError(
            code="metadata_db_unavailable",
            message="Report metadata DB is not accessible",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path},
        ) from exc
    finally:
        conn.close()
    response = ReportMetadataDbAccessResponse(
        schema_version="1.0",
        db_path=request.db_path,
        accessible=True,
        locked=False,
        message="",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_db_access_complete",
            module=logger.name,
            fields={
                "db_path": response.db_path,
                "accessible": response.accessible,
                "locked": response.locked,
                "message": response.message,
            },
        )
    )
    return response


def upsert_metadata(request: ReportMetadataUpsertRequest, ctx: RunContext) -> None:
    if not request.file_id.strip():
        raise AppError(
            code="metadata_file_id_missing",
            message="file_id is required for metadata upsert",
            retryable=False,
            severity="error",
        )
    if not request.title.strip():
        raise AppError(
            code="metadata_title_missing",
            message="title is required for metadata upsert",
            retryable=False,
            severity="error",
        )

    title = request.title.strip()
    file_name = (
        request.file_name.strip()
        if request.file_name and request.file_name.strip()
        else None
    )
    publisher = (
        request.publisher.strip()
        if request.publisher and request.publisher.strip()
        else None
    )
    source_url = (
        request.source_url.strip()
        if request.source_url and request.source_url.strip()
        else None
    )
    html_path = (
        request.html_path.strip()
        if request.html_path and request.html_path.strip()
        else None
    )
    md5 = request.md5.strip() if request.md5 and request.md5.strip() else None
    page_count = (
        request.page_count
        if isinstance(request.page_count, int) and request.page_count >= 0
        else None
    )
    contents_page = (
        request.contents_page_number
        if isinstance(request.contents_page_number, int)
        and request.contents_page_number >= 0
        else 0
    )
    taxonomy = clean_string_list(request.taxonomy)
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=True)
    categories = clean_string_list(request.categories)
    categories_json = json.dumps(categories, ensure_ascii=True)
    region = (
        request.region.strip() if request.region and request.region.strip() else None
    )
    raw_time_period = (
        request.time_period.strip()
        if request.time_period and request.time_period.strip()
        else None
    )
    time_period = raw_time_period
    metadata_clean = _clean_metadata(request.pdf_metadata)
    metadata_json = json.dumps(metadata_clean, ensure_ascii=True)
    analysis_mode = (
        request.analysis_mode.strip() if request.analysis_mode else "vector_store"
    )
    vector_store_id = (
        request.vector_store_id.strip() if request.vector_store_id else None
    )
    evidence_packs = request.evidence_pack_paths or {}
    evidence_packs_json = json.dumps(evidence_packs, ensure_ascii=False)
    source_identity_id = request.source_identity_id.strip()
    source_metadata_hash = request.source_metadata_hash.strip()
    source_identity_status = request.source_identity_status.strip() or "unknown"
    source_publication_date_status = (
        request.source_publication_date_status.strip() or "unknown"
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_upsert_start",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "db_path": request.db_path,
                "file_name": file_name,
                "title": title,
                "publisher": publisher,
                "taxonomy_count": len(taxonomy),
                "region": region,
                "time_period": time_period,
                "raw_time_period": raw_time_period,
                "categories_count": len(categories),
                "page_count": page_count,
                "contents_page": contents_page,
                "metadata_keys": list(metadata_clean.keys()),
            },
        )
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        resolved_publisher = publisher or _report_source_publisher_from_store(
            conn,
            report_title=title,
            md5=md5,
        )
        resolved_source_url = source_url or _report_source_url_from_store(
            conn,
            report_title=title,
            publisher=resolved_publisher,
            md5=md5,
        )
        conn.execute(
            """
            INSERT INTO reports(file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, source_identity_id, source_metadata_hash, source_identity_status, source_publication_date_status, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(file_id) DO UPDATE SET
                file_name=COALESCE(excluded.file_name, reports.file_name),
                title=excluded.title,
                publisher=excluded.publisher,
                taxonomy_json=excluded.taxonomy_json,
                categories_json=excluded.categories_json,
                region=excluded.region,
                time_period=excluded.time_period,
                source_url=excluded.source_url,
                html_path=excluded.html_path,
                md5=excluded.md5,
                page_count=excluded.page_count,
                contents_page=excluded.contents_page,
                pdf_metadata_json=excluded.pdf_metadata_json,
                analysis_mode=excluded.analysis_mode,
                vector_store_id=excluded.vector_store_id,
                evidence_packs_json=excluded.evidence_packs_json,
                source_identity_id=COALESCE(NULLIF(excluded.source_identity_id, ''), reports.source_identity_id),
                source_metadata_hash=COALESCE(NULLIF(excluded.source_metadata_hash, ''), reports.source_metadata_hash),
                source_identity_status=COALESCE(NULLIF(excluded.source_identity_status, ''), reports.source_identity_status),
                source_publication_date_status=COALESCE(NULLIF(excluded.source_publication_date_status, ''), reports.source_publication_date_status),
                updated_at=strftime('%s','now')
            """,
            (
                request.file_id,
                file_name,
                title,
                resolved_publisher,
                taxonomy_json,
                categories_json,
                region,
                time_period,
                resolved_source_url,
                html_path,
                md5,
                page_count,
                contents_page,
                metadata_json,
                analysis_mode,
                vector_store_id,
                evidence_packs_json,
                source_identity_id,
                source_metadata_hash,
                source_identity_status,
                source_publication_date_status,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_upsert_complete",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )


def get_metadata(
    request: ReportMetadataGetRequest, ctx: RunContext
) -> Optional[ReportMetadataGetResponse]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_get_start",
            module=logger.name,
            fields={"file_id": request.file_id, "db_path": request.db_path},
        )
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at, source_identity_id, source_metadata_hash, source_identity_status, source_publication_date_status
            FROM reports
            WHERE file_id=?
            """,
            (request.file_id,),
        )
        row = cur.fetchone()
        fallback_source_url = None
        fallback_publisher = None
        if row and not str(row[3] or "").strip():
            fallback_publisher = _report_source_publisher_from_store(
                conn,
                report_title=str(row[2] or ""),
                md5=str(row[10] or "") or None,
            )
        if row and not str(row[8] or "").strip():
            fallback_source_url = _report_source_url_from_store(
                conn,
                report_title=str(row[2] or ""),
                publisher=str(row[3] or "") or fallback_publisher,
                md5=str(row[10] or "") or None,
            )

    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_get_complete",
                module=logger.name,
                fields={"file_id": request.file_id, "found": False},
            )
        )
        return None

    response = _row_to_metadata_response(row, ctx)
    if fallback_source_url or fallback_publisher:
        response = replace(
            response,
            source_url=fallback_source_url or response.source_url,
            publisher=fallback_publisher or response.publisher,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": True},
        )
    )
    return response


def list_metadata(
    request: ReportMetadataListRequest, ctx: RunContext
) -> ReportMetadataListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_list_start",
            module=logger.name,
            fields={"db_path": request.db_path},
        )
    )
    rows: List[ReportMetadataGetResponse] = []
    with _metadata_conn(request.db_path, ctx) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at, source_identity_id, source_metadata_hash, source_identity_status, source_publication_date_status
            FROM reports
            ORDER BY created_at ASC
            """
        )
        for row in cur.fetchall():
            rows.append(_row_to_metadata_response(row, ctx))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_list_complete",
            module=logger.name,
            fields={"db_path": request.db_path, "count": len(rows)},
        )
    )
    return ReportMetadataListResponse(schema_version="1.1", records=rows)


def record_report_source_reuse_telemetry(
    request: ReportSourceReuseTelemetryRecordRequest,
    ctx: RunContext,
) -> None:
    """Persist one bounded, idempotent decision without retaining route references."""
    record = request.record
    reference_hash = sha256_json(str(record.incoming_source_reference or ""))
    decision_id = sha256_json(
        {
            "incoming_file_id": str(record.incoming_file_id or ""),
            "incoming_source_reference_hash": reference_hash,
            "canonical_source_identity": record.canonical_source_identity,
            "source_content_hash": record.source_content_hash,
            "matched_report_id": record.matched_report_id,
            "decision": record.decision,
        }
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        conn.execute(
            """
            INSERT INTO report_source_reuse_telemetry(
              decision_id, schema_version, incoming_file_id,
              incoming_source_reference_hash, canonical_source_identity,
              source_content_hash, matched_report_id,
              matched_source_metadata_hash, decision, decision_reason,
              highest_reused_checkpoint, reused_stages_json,
              regenerated_stages_json, acquisition_actions_avoided,
              browser_launches_avoided, pdf_parse_avoided, ocr_avoided,
              extraction_avoided, vector_work_avoided, model_calls_avoided_status,
              model_calls_avoided, tokens_avoided_status, input_tokens_avoided,
              output_tokens_avoided, estimated_cost_avoided_status,
              estimated_cost_avoided_usd, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET
              decision_reason=excluded.decision_reason,
              highest_reused_checkpoint=excluded.highest_reused_checkpoint,
              reused_stages_json=excluded.reused_stages_json,
              regenerated_stages_json=excluded.regenerated_stages_json,
              acquisition_actions_avoided=excluded.acquisition_actions_avoided,
              browser_launches_avoided=excluded.browser_launches_avoided,
              pdf_parse_avoided=excluded.pdf_parse_avoided,
              ocr_avoided=excluded.ocr_avoided,
              extraction_avoided=excluded.extraction_avoided,
              vector_work_avoided=excluded.vector_work_avoided,
              model_calls_avoided_status=excluded.model_calls_avoided_status,
              model_calls_avoided=excluded.model_calls_avoided,
              tokens_avoided_status=excluded.tokens_avoided_status,
              input_tokens_avoided=excluded.input_tokens_avoided,
              output_tokens_avoided=excluded.output_tokens_avoided,
              estimated_cost_avoided_status=excluded.estimated_cost_avoided_status,
              estimated_cost_avoided_usd=excluded.estimated_cost_avoided_usd
            """,
            (
                decision_id,
                record.schema_version,
                str(record.incoming_file_id or ""),
                reference_hash,
                record.canonical_source_identity,
                record.source_content_hash,
                record.matched_report_id,
                record.matched_source_metadata_hash,
                record.decision,
                record.decision_reason,
                record.highest_reused_checkpoint,
                json.dumps(record.reused_stages, separators=(",", ":")),
                json.dumps(record.regenerated_stages, separators=(",", ":")),
                record.acquisition_actions_avoided,
                record.browser_launches_avoided,
                record.pdf_parse_avoided,
                record.ocr_avoided,
                record.extraction_avoided,
                record.vector_work_avoided,
                record.model_calls_avoided_status,
                record.model_calls_avoided,
                record.tokens_avoided_status,
                record.input_tokens_avoided,
                record.output_tokens_avoided,
                record.estimated_cost_avoided_status,
                record.estimated_cost_avoided_usd,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _source_reuse_telemetry_request(
    request: ReportSourceReuseResolveRequest,
    response: ReportSourceReuseResolveResponse,
) -> ReportSourceReuseTelemetryRecordRequest:
    return ReportSourceReuseTelemetryRecordRequest(
        schema_version="1.0",
        db_path=request.db_path,
        record=ReportSourceReuseTelemetryRecord(
            schema_version="1.0",
            incoming_file_id=request.incoming_file_id,
            incoming_source_reference=request.incoming_source_reference,
            canonical_source_identity=response.canonical_source_identity,
            source_content_hash=response.source_content_hash,
            matched_report_id=response.report_id,
            matched_source_metadata_hash=response.source_metadata_hash,
            decision=response.decision,
            decision_reason=response.reason,
            highest_reused_checkpoint=response.highest_reusable_checkpoint,
        ),
    )


def resolve_report_source_reuse(
    request: ReportSourceReuseResolveRequest, ctx: RunContext
) -> ReportSourceReuseResolveResponse:
    """Return a retained package only when canonical identity and bytes match."""

    identity = str(request.canonical_source_identity or "").strip()
    identity_status = str(request.canonical_source_identity_status or "unknown").strip()
    content_hash = str(request.source_content_hash or "").strip().lower()
    md5 = content_hash.removeprefix("md5:") if content_hash.startswith("md5:") else ""
    if not identity:
        reason = "canonical_source_identity_missing"
    elif identity_status != "resolved":
        reason = "canonical_source_identity_unproven"
    elif (
        not md5 or len(md5) != 32 or any(char not in "0123456789abcdef" for char in md5)
    ):
        reason = "source_content_hash_unverifiable"
    else:
        with _metadata_conn(request.db_path, ctx) as conn:
            rows = conn.execute(
                """
                SELECT file_id, html_path, md5, source_metadata_hash,
                       source_identity_status, updated_at
                FROM reports
                WHERE source_identity_id=?
                ORDER BY updated_at DESC, file_id ASC
                """,
                (identity,),
            ).fetchall()
        candidates = [
            row
            for row in rows
            if str(row[2] or "").strip().lower() == md5
            and str(row[4] or "").strip() == "resolved"
            and str(row[1] or "").strip()
        ]
        if candidates:
            row = candidates[0]
            response = ReportSourceReuseResolveResponse(
                schema_version="1.0",
                decision="reuse",
                reason="canonical_identity_and_content_hash_match",
                canonical_source_identity=identity,
                source_content_hash=content_hash,
                report_id=str(row[0] or "").strip(),
                html_path=str(row[1] or "").strip(),
                highest_reusable_checkpoint="render_complete",
                source_metadata_hash=str(row[3] or "").strip(),
            )
            record_report_source_reuse_telemetry(
                _source_reuse_telemetry_request(request, response), ctx
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="report_source_reuse_resolved",
                    module=logger.name,
                    fields={
                        "incoming_file_id": request.incoming_file_id,
                        "incoming_source_reference_hash": sha256_json(
                            str(request.incoming_source_reference or "")
                        ),
                        "canonical_source_identity": identity,
                        "matched_report_id": response.report_id,
                        "decision": response.decision,
                        "reason": response.reason,
                        "highest_reusable_checkpoint": response.highest_reusable_checkpoint,
                    },
                )
            )
            return response
        reason = (
            "matching_package_missing"
            if not rows
            else "matching_package_content_or_validation_incompatible"
        )
    response = ReportSourceReuseResolveResponse(
        schema_version="1.0",
        decision="process",
        reason=reason,
        canonical_source_identity=identity,
        source_content_hash=content_hash,
    )
    record_report_source_reuse_telemetry(
        _source_reuse_telemetry_request(request, response), ctx
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_reuse_resolved",
            module=logger.name,
            fields={
                "incoming_file_id": request.incoming_file_id,
                "incoming_source_reference_hash": sha256_json(
                    str(request.incoming_source_reference or "")
                ),
                "canonical_source_identity": identity,
                "decision": response.decision,
                "reason": response.reason,
            },
        )
    )
    return response
