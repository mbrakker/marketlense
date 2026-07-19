from __future__ import annotations

from src.contracts.run_context import RunContext
from src.contracts.state import (
    SourceQuarantineGetRequest,
    SourceQuarantineGetResponse,
    SourceQuarantineListRequest,
    SourceQuarantineListResponse,
    SourceQuarantineRecord,
    SourceQuarantineUpsertRequest,
    SourceQuarantineUpsertResponse,
)
from src.services._state_service.common import _state_conn, logger
from src.utils.logging import log_event


def _record(row: tuple) -> SourceQuarantineRecord:
    return SourceQuarantineRecord(
        schema_version=str(row[3]),
        source_file_id=str(row[0]),
        content_checksum=str(row[1]),
        validator_version=str(row[2]),
        status=str(row[4]),
        size_bytes=int(row[5]),
        failure_code=str(row[6]),
        next_operator_action=str(row[7]),
        first_observed_at_utc=str(row[8]),
        latest_observed_at_utc=str(row[9]),
        failed_validation_count=int(row[10]),
        replacement_checksum=str(row[11] or ""),
        cleared_at_utc=str(row[12] or ""),
    )


_COLUMNS = (
    "source_file_id,content_checksum,validator_version,schema_version,status,"
    "size_bytes,failure_code,next_operator_action,first_observed_at_utc,"
    "latest_observed_at_utc,failed_validation_count,replacement_checksum,cleared_at_utc"
)


def get_source_quarantine(
    request: SourceQuarantineGetRequest,
    ctx: RunContext,
) -> SourceQuarantineGetResponse:
    with _state_conn(request.state_db, ctx) as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM source_quarantine_records "
            "WHERE source_file_id=? AND content_checksum=? AND validator_version=?",
            (
                request.source_file_id.strip(),
                request.content_checksum.strip(),
                request.validator_version.strip(),
            ),
        ).fetchone()
    record = _record(row) if row else None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_quarantine_lookup",
            module=logger.name,
            fields={
                "source_file_id": request.source_file_id,
                "found": bool(record),
                "status": record.status if record else "",
            },
        )
    )
    return SourceQuarantineGetResponse(schema_version="1.0", record=record)


def upsert_source_quarantine(
    request: SourceQuarantineUpsertRequest,
    ctx: RunContext,
) -> SourceQuarantineUpsertResponse:
    record = request.record
    key = (record.source_file_id, record.content_checksum, record.validator_version)
    with _state_conn(request.state_db, ctx) as conn:
        existing = conn.execute(
            "SELECT 1 FROM source_quarantine_records "
            "WHERE source_file_id=? AND content_checksum=? AND validator_version=?",
            key,
        ).fetchone()
        if record.status in {"active", "cleared"}:
            conn.execute(
                """
                UPDATE source_quarantine_records
                SET status='superseded', replacement_checksum=?,
                    latest_observed_at_utc=?
                WHERE source_file_id=? AND validator_version=?
                  AND content_checksum<>? AND status='active'
                """,
                (
                    record.content_checksum,
                    record.latest_observed_at_utc,
                    record.source_file_id,
                    record.validator_version,
                    record.content_checksum,
                ),
            )
        conn.execute(
            """
            INSERT INTO source_quarantine_records(
              source_file_id,content_checksum,validator_version,schema_version,status,
              size_bytes,failure_code,next_operator_action,first_observed_at_utc,
              latest_observed_at_utc,failed_validation_count,replacement_checksum,
              cleared_at_utc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_file_id,content_checksum,validator_version) DO UPDATE SET
              status=excluded.status,
              size_bytes=excluded.size_bytes,
              failure_code=excluded.failure_code,
              next_operator_action=excluded.next_operator_action,
              latest_observed_at_utc=excluded.latest_observed_at_utc,
              failed_validation_count=CASE
                WHEN excluded.status='active'
                THEN source_quarantine_records.failed_validation_count+1
                ELSE source_quarantine_records.failed_validation_count
              END,
              replacement_checksum=excluded.replacement_checksum,
              cleared_at_utc=excluded.cleared_at_utc
            """,
            (
                *key,
                record.schema_version,
                record.status,
                max(0, int(record.size_bytes)),
                record.failure_code,
                record.next_operator_action,
                record.first_observed_at_utc,
                record.latest_observed_at_utc,
                max(0, int(record.failed_validation_count)),
                record.replacement_checksum,
                record.cleared_at_utc,
            ),
        )
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM source_quarantine_records "
            "WHERE source_file_id=? AND content_checksum=? AND validator_version=?",
            key,
        ).fetchone()
    stored = _record(row)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="source_quarantine_upserted",
            module=logger.name,
            fields={
                "source_file_id": stored.source_file_id,
                "status": stored.status,
                "failure_code": stored.failure_code,
                "created": existing is None,
                "failed_validation_count": stored.failed_validation_count,
            },
        )
    )
    return SourceQuarantineUpsertResponse(
        schema_version="1.0", record=stored, created=existing is None
    )


def list_source_quarantines(
    request: SourceQuarantineListRequest,
    ctx: RunContext,
) -> SourceQuarantineListResponse:
    statuses = sorted(
        {str(value).strip() for value in request.statuses if str(value).strip()}
    )
    where = ""
    params: list[object] = []
    if statuses:
        where = " WHERE status IN (" + ",".join("?" for _ in statuses) + ")"
        params.extend(statuses)
    params.append(max(1, min(500, int(request.limit))))
    with _state_conn(request.state_db, ctx) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM source_quarantine_records{where} "
            "ORDER BY latest_observed_at_utc DESC, source_file_id, "
            "content_checksum LIMIT ?",
            tuple(params),
        ).fetchall()
    return SourceQuarantineListResponse(
        schema_version="1.0", records=[_record(row) for row in rows]
    )


__all__ = [
    "get_source_quarantine",
    "list_source_quarantines",
    "upsert_source_quarantine",
]
