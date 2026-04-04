from __future__ import annotations

import json
from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateBatchCheckResponse,
    StateCheckRequest,
    StateGetRequest,
    StateGetResponse,
    StateIngestCursorGetRequest,
    StateIngestCursorGetResponse,
    StateIngestCursorSetRequest,
    StateProcessedListRequest,
    StateProcessedListResponse,
    StateProcessedRow,
    StateRecordRequest,
)
from src.services._state_common import (
    BATCH_STATE_CHECK_MAX_PAIRS,
    _normalize_batch_items,
    _parse_dict,
    _parse_int_list,
    _state_conn,
    logger,
)
from src.utils.logging import log_event


def get_ingest_cursor(
    request: StateIngestCursorGetRequest, ctx: RunContext
) -> StateIngestCursorGetResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_cursor_get_start",
            module=logger.name,
            fields={"state_db": request.state_db},
        )
    )
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT value FROM ingest_state WHERE key=?",
            ("last_successful_ingest_utc",),
        )
        row = cur.fetchone()
    value = row[0] if row else None
    response = StateIngestCursorGetResponse(
        schema_version="1.0",
        state_db=request.state_db,
        last_successful_ingest_utc=value,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_cursor_get_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "last_successful_ingest_utc": value or "",
            },
        )
    )
    return response


def set_ingest_cursor(request: StateIngestCursorSetRequest, ctx: RunContext) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_cursor_set_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "last_successful_ingest_utc": request.last_successful_ingest_utc,
            },
        )
    )
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_state(key, value, updated_at) VALUES(?, ?, strftime('%s','now'))",
            ("last_successful_ingest_utc", request.last_successful_ingest_utc),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ingest_cursor_set_complete",
            module=logger.name,
            fields={"state_db": request.state_db},
        )
    )


def already_processed(request: StateCheckRequest, ctx: RunContext) -> bool:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_check_start",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT 1 FROM processed WHERE file_id=? AND md5=?",
            (request.file_id, request.md5),
        )
        result = cur.fetchone() is not None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_check_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "already_processed": result},
        )
    )
    return result


def already_processed_batch(
    request: StateBatchCheckRequest, ctx: RunContext
) -> StateBatchCheckResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_check_batch_start",
            module=logger.name,
            fields={"state_db": request.state_db, "requested": len(request.items)},
        )
    )
    items = _normalize_batch_items(request.items)
    if not items:
        response = StateBatchCheckResponse(
            schema_version="1.0",
            state_db=request.state_db,
            processed_items=[],
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="state_check_batch_complete",
                module=logger.name,
                fields={"state_db": request.state_db, "checked": 0, "matched": 0},
            )
        )
        return response

    matched: list[StateBatchCheckItem] = []
    with _state_conn(request.state_db) as conn:
        for idx in range(0, len(items), BATCH_STATE_CHECK_MAX_PAIRS):
            chunk = items[idx : idx + BATCH_STATE_CHECK_MAX_PAIRS]
            where = " OR ".join("(file_id=? AND md5=?)" for _ in chunk)
            params: list[str] = []
            for item in chunk:
                params.extend((item.file_id, item.md5))
            cur = conn.execute(
                f"SELECT file_id, md5 FROM processed WHERE {where}",
                params,
            )
            for file_id, md5 in cur.fetchall():
                matched.append(
                    StateBatchCheckItem(schema_version="1.0", file_id=file_id, md5=md5)
                )

    response = StateBatchCheckResponse(
        schema_version="1.0",
        state_db=request.state_db,
        processed_items=matched,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_check_batch_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "checked": len(items),
                "matched": len(matched),
            },
        )
    )
    return response


def record(request: StateRecordRequest, ctx: RunContext) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_record_start",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO processed("
            "file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json, "
            "ocr_fallback_used, ocr_pdf_path"
            ") VALUES(?, ?, strftime('%s','now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.file_id,
                request.md5,
                request.openai_file_id,
                request.vector_store_id,
                request.vector_store_status,
                request.indexed_at_utc,
                request.last_error,
                request.text_validation_status,
                request.text_validation_reason,
                json.dumps(request.text_validation_pages)
                if request.text_validation_pages is not None
                else None,
                json.dumps(request.doc_map_summary)
                if request.doc_map_summary is not None
                else None,
                1 if request.ocr_fallback_used else 0,
                request.ocr_pdf_path,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_record_complete",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )


def get(request: StateGetRequest, ctx: RunContext) -> Optional[StateGetResponse]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_get_start",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json, "
            "ocr_fallback_used, ocr_pdf_path "
            "FROM processed WHERE file_id=?",
            (request.file_id,),
        )
        row = cur.fetchone()
    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="state_get_complete",
                module=logger.name,
                fields={"file_id": request.file_id, "found": False},
            )
        )
        return None
    (
        file_id,
        md5,
        processed_at,
        openai_file_id,
        vector_store_id,
        vector_store_status,
        indexed_at_utc,
        last_error,
        text_validation_status,
        text_validation_reason,
        text_validation_pages_json,
        doc_map_summary_json,
        ocr_fallback_used,
        ocr_pdf_path,
    ) = row
    text_validation_pages = _parse_int_list(text_validation_pages_json)
    doc_map_summary = _parse_dict(doc_map_summary_json)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": True},
        )
    )
    return StateGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        processed_at=processed_at,
        openai_file_id=openai_file_id,
        vector_store_id=vector_store_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        last_error=last_error,
        text_validation_status=text_validation_status,
        text_validation_reason=text_validation_reason,
        text_validation_pages=text_validation_pages,
        doc_map_summary=doc_map_summary,
        ocr_fallback_used=bool(ocr_fallback_used),
        ocr_pdf_path=ocr_pdf_path,
    )


def list_processed(
    request: StateProcessedListRequest, ctx: RunContext
) -> StateProcessedListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_processed_list_start",
            module=logger.name,
            fields={"state_db": request.state_db, "limit": request.limit},
        )
    )
    limit = int(request.limit) if isinstance(request.limit, int) else 200
    if limit <= 0:
        limit = 200
    rows: list[StateProcessedRow] = []
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json, "
            "ocr_fallback_used, ocr_pdf_path "
            "FROM processed ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        )
        for (
            file_id,
            md5,
            processed_at,
            openai_file_id,
            vector_store_id,
            vector_store_status,
            indexed_at_utc,
            last_error,
            text_validation_status,
            text_validation_reason,
            text_validation_pages_json,
            doc_map_summary_json,
            ocr_fallback_used,
            ocr_pdf_path,
        ) in cur.fetchall():
            rows.append(
                StateProcessedRow(
                    schema_version="1.0",
                    file_id=file_id,
                    md5=md5,
                    processed_at=int(processed_at),
                    openai_file_id=openai_file_id,
                    vector_store_id=vector_store_id,
                    vector_store_status=vector_store_status,
                    indexed_at_utc=indexed_at_utc,
                    last_error=last_error,
                    text_validation_status=text_validation_status,
                    text_validation_reason=text_validation_reason,
                    text_validation_pages=_parse_int_list(text_validation_pages_json),
                    doc_map_summary=_parse_dict(doc_map_summary_json),
                    ocr_fallback_used=bool(ocr_fallback_used),
                    ocr_pdf_path=ocr_pdf_path,
                )
            )
    response = StateProcessedListResponse(schema_version="1.0", rows=rows)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_processed_list_complete",
            module=logger.name,
            fields={"state_db": request.state_db, "count": len(rows)},
        )
    )
    return response
