from __future__ import annotations

"""Signals operations for the analytics store service."""

import json
import logging
import sqlite3
from dataclasses import asdict
from typing import Any, cast
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateReadRequest,
    SignalCandidateReadResponse,
    SignalCandidateSourceRef,
    SignalCandidateStoreRequest,
    SignalCandidateStoreResponse,
    validate_signal_candidate_contract,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from src.services._analytics_store.common import (
    _analytics_conn,
    _json,
)

logger = logging.getLogger("market_lense.analytics_store_service")


def _candidate_source_ref_from_dict(
    payload: dict[str, Any],
) -> SignalCandidateSourceRef:
    return SignalCandidateSourceRef(
        schema_version=str(payload["schema_version"]),
        report_id=str(payload["report_id"]),
        evidence_id=str(payload["evidence_id"]),
        source_table=str(payload["source_table"]),
        entity_uid=str(payload["entity_uid"]),
        content_class=str(payload["content_class"]),
        page_refs=[int(value) for value in payload.get("page_refs", [])],
        source_metadata=dict(payload.get("source_metadata") or {}),
    )


def _candidate_from_row(row: sqlite3.Row) -> SignalCandidate:
    candidate = SignalCandidate(
        schema_version=str(row["schema_version"]),
        candidate_id=str(row["candidate_id"]),
        candidate_type=cast(Any, row["candidate_type"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        confidence=float(row["confidence"]),
        strength=float(row["strength"]),
        support_level=cast(Any, row["support_level"]),
        caveats=[str(value) for value in json.loads(row["caveats_json"])],
        source_report_ids=[
            str(value) for value in json.loads(row["source_report_ids_json"])
        ],
        evidence_ids=[str(value) for value in json.loads(row["evidence_ids_json"])],
        source_refs=[
            _candidate_source_ref_from_dict(item)
            for item in json.loads(row["source_refs_json"])
        ],
        raw_source_context=dict(json.loads(row["raw_source_context_json"])),
        validation_status=cast(Any, row["validation_status"]),
        validation_notes=[
            str(value) for value in json.loads(row["validation_notes_json"])
        ],
        group_id=str(row["group_id"]),
        extraction_request_id=str(row["extraction_request_id"]),
        generated_at_utc=str(row["generated_at_utc"]),
    )
    validate_signal_candidate_contract(candidate)
    return candidate


def _group_from_row(row: sqlite3.Row) -> SignalCandidateGroup:
    group = SignalCandidateGroup(
        schema_version=str(row["schema_version"]),
        group_id=str(row["group_id"]),
        stable_key=str(row["stable_key"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        support_level=cast(Any, row["support_level"]),
        candidate_ids=[str(value) for value in json.loads(row["candidate_ids_json"])],
        source_report_ids=[
            str(value) for value in json.loads(row["source_report_ids_json"])
        ],
        evidence_ids=[str(value) for value in json.loads(row["evidence_ids_json"])],
        caveats=[str(value) for value in json.loads(row["caveats_json"])],
        raw_group_context=dict(json.loads(row["raw_group_context_json"])),
        validation_status=cast(Any, row["validation_status"]),
        extraction_request_id=str(row["extraction_request_id"]),
        generated_at_utc=str(row["generated_at_utc"]),
    )
    validate_signal_candidate_contract(group)
    return group


def _delete_stale_signal_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    id_column: str,
    extraction_request_id: str,
    active_ids: set[str],
) -> int:
    before = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE extraction_request_id=?",
        (extraction_request_id,),
    ).fetchone()[0]
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE extraction_request_id=?
              AND {id_column} NOT IN ({placeholders})
            """,
            (extraction_request_id, *sorted(active_ids)),
        )
    else:
        conn.execute(
            f"DELETE FROM {table} WHERE extraction_request_id=?",
            (extraction_request_id,),
        )
    after = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE extraction_request_id=?",
        (extraction_request_id,),
    ).fetchone()[0]
    return max(int(before) - int(after), 0)


def _upsert_signal_group(conn: sqlite3.Connection, group: SignalCandidateGroup) -> None:
    conn.execute(
        """
        INSERT INTO signal_candidate_groups(
            group_id, extraction_request_id, stable_key, title, summary,
            support_level, candidate_ids_json, source_report_ids_json,
            evidence_ids_json, caveats_json, raw_group_context_json,
            validation_status, schema_version, generated_at_utc, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
        ON CONFLICT(group_id) DO UPDATE SET
            extraction_request_id=excluded.extraction_request_id,
            stable_key=excluded.stable_key,
            title=excluded.title,
            summary=excluded.summary,
            support_level=excluded.support_level,
            candidate_ids_json=excluded.candidate_ids_json,
            source_report_ids_json=excluded.source_report_ids_json,
            evidence_ids_json=excluded.evidence_ids_json,
            caveats_json=excluded.caveats_json,
            raw_group_context_json=excluded.raw_group_context_json,
            validation_status=excluded.validation_status,
            schema_version=excluded.schema_version,
            generated_at_utc=excluded.generated_at_utc,
            updated_at=strftime('%s','now')
        """,
        (
            group.group_id,
            group.extraction_request_id,
            group.stable_key,
            group.title,
            group.summary,
            group.support_level,
            _json(group.candidate_ids),
            _json(group.source_report_ids),
            _json(group.evidence_ids),
            _json(group.caveats),
            _json(group.raw_group_context),
            group.validation_status,
            group.schema_version,
            group.generated_at_utc,
        ),
    )


def _upsert_signal_candidate(
    conn: sqlite3.Connection, candidate: SignalCandidate
) -> None:
    conn.execute(
        """
        INSERT INTO signal_candidates(
            candidate_id, extraction_request_id, candidate_type, title, summary,
            confidence, strength, support_level, caveats_json,
            source_report_ids_json, evidence_ids_json, source_refs_json,
            raw_source_context_json, validation_status, validation_notes_json,
            group_id, schema_version, generated_at_utc, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
        ON CONFLICT(candidate_id) DO UPDATE SET
            extraction_request_id=excluded.extraction_request_id,
            candidate_type=excluded.candidate_type,
            title=excluded.title,
            summary=excluded.summary,
            confidence=excluded.confidence,
            strength=excluded.strength,
            support_level=excluded.support_level,
            caveats_json=excluded.caveats_json,
            source_report_ids_json=excluded.source_report_ids_json,
            evidence_ids_json=excluded.evidence_ids_json,
            source_refs_json=excluded.source_refs_json,
            raw_source_context_json=excluded.raw_source_context_json,
            validation_status=excluded.validation_status,
            validation_notes_json=excluded.validation_notes_json,
            group_id=excluded.group_id,
            schema_version=excluded.schema_version,
            generated_at_utc=excluded.generated_at_utc,
            updated_at=strftime('%s','now')
        """,
        (
            candidate.candidate_id,
            candidate.extraction_request_id,
            candidate.candidate_type,
            candidate.title,
            candidate.summary,
            candidate.confidence,
            candidate.strength,
            candidate.support_level,
            _json(candidate.caveats),
            _json(candidate.source_report_ids),
            _json(candidate.evidence_ids),
            _json([asdict(item) for item in candidate.source_refs]),
            _json(candidate.raw_source_context),
            candidate.validation_status,
            _json(candidate.validation_notes),
            candidate.group_id,
            candidate.schema_version,
            candidate.generated_at_utc,
        ),
    )


def upsert_signal_candidates(
    request: SignalCandidateStoreRequest,
    ctx: RunContext,
) -> SignalCandidateStoreResponse:
    validate_signal_candidate_contract(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="signal_candidate_store_upsert_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "extraction_request_id": request.extraction_request_id,
                "candidate_count": len(request.candidates),
                "group_count": len(request.groups),
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            for group in request.groups:
                _upsert_signal_group(conn, group)
            for candidate in request.candidates:
                _upsert_signal_candidate(conn, candidate)
            stale_candidate_count = _delete_stale_signal_rows(
                conn,
                table="signal_candidates",
                id_column="candidate_id",
                extraction_request_id=request.extraction_request_id,
                active_ids={candidate.candidate_id for candidate in request.candidates},
            )
            stale_group_count = _delete_stale_signal_rows(
                conn,
                table="signal_candidate_groups",
                id_column="group_id",
                extraction_request_id=request.extraction_request_id,
                active_ids={group.group_id for group in request.groups},
            )
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="signal_candidate_store_upsert_failed",
            message="Failed to upsert Signal candidates",
            cause=exc,
            retryable=True,
            severity="error",
            context={
                "db_path": request.db_path,
                "extraction_request_id": request.extraction_request_id,
            },
        ) from exc

    response = SignalCandidateStoreResponse(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        db_path=request.db_path,
        extraction_request_id=request.extraction_request_id,
        candidate_count=len(request.candidates),
        group_count=len(request.groups),
        stale_candidate_count=stale_candidate_count,
        stale_group_count=stale_group_count,
    )
    validate_signal_candidate_contract(response)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="signal_candidate_store_upsert_complete",
            module=logger.name,
            fields={
                "schema_version": response.schema_version,
                "extraction_request_id": response.extraction_request_id,
                "candidate_count": response.candidate_count,
                "group_count": response.group_count,
                "stale_candidate_count": response.stale_candidate_count,
                "stale_group_count": response.stale_group_count,
            },
        )
    )
    return response


def _candidate_matches_read_request(
    candidate: SignalCandidate,
    request: SignalCandidateReadRequest,
) -> bool:
    if (
        request.extraction_request_id
        and candidate.extraction_request_id != request.extraction_request_id
    ):
        return False
    if request.candidate_ids and candidate.candidate_id not in set(
        request.candidate_ids
    ):
        return False
    if request.group_ids and candidate.group_id not in set(request.group_ids):
        return False
    if request.validation_statuses and candidate.validation_status not in set(
        request.validation_statuses
    ):
        return False
    if request.source_report_ids and not set(request.source_report_ids).intersection(
        candidate.source_report_ids
    ):
        return False
    if request.evidence_ids and not set(request.evidence_ids).intersection(
        candidate.evidence_ids
    ):
        return False
    topic_filters = [
        value.casefold() for value in request.topic_filters if value.strip()
    ]
    if topic_filters:
        haystack = (
            f"{candidate.title} {candidate.summary} "
            f"{json.dumps(candidate.raw_source_context, sort_keys=True, default=str)}"
        ).casefold()
        if not any(topic in haystack for topic in topic_filters):
            return False
    return True


def read_signal_candidates(
    request: SignalCandidateReadRequest,
    ctx: RunContext,
) -> SignalCandidateReadResponse:
    validate_signal_candidate_contract(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="signal_candidate_store_read_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "extraction_request_id": request.extraction_request_id,
                "candidate_ids": request.candidate_ids,
                "group_ids": request.group_ids,
                "validation_statuses": request.validation_statuses,
                "source_report_ids": request.source_report_ids,
                "evidence_ids": request.evidence_ids,
                "topic_filters": request.topic_filters,
                "limit": request.limit,
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            candidate_rows = conn.execute(
                """
                SELECT *
                FROM signal_candidates
                ORDER BY strength DESC, candidate_id ASC
                """
            ).fetchall()
            candidates = [
                candidate
                for candidate in (_candidate_from_row(row) for row in candidate_rows)
                if _candidate_matches_read_request(candidate, request)
            ][: request.limit]
            group_ids = sorted({candidate.group_id for candidate in candidates})
            groups: list[SignalCandidateGroup] = []
            if group_ids:
                placeholders = ",".join("?" for _ in group_ids)
                group_rows = conn.execute(
                    f"""
                    SELECT *
                    FROM signal_candidate_groups
                    WHERE group_id IN ({placeholders})
                    ORDER BY group_id ASC
                    """,
                    tuple(group_ids),
                ).fetchall()
                groups = [_group_from_row(row) for row in group_rows]
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="signal_candidate_store_read_failed",
            message="Failed to read Signal candidates",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc

    response = SignalCandidateReadResponse(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        db_path=request.db_path,
        candidates=candidates,
        groups=groups,
    )
    validate_signal_candidate_contract(response)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="signal_candidate_store_read_complete",
            module=logger.name,
            fields={
                "db_path": response.db_path,
                "candidate_count": len(response.candidates),
                "group_count": len(response.groups),
                "candidate_ids": [
                    candidate.candidate_id for candidate in response.candidates
                ],
                "group_ids": [group.group_id for group in response.groups],
            },
        )
    )
    return response
