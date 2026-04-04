from __future__ import annotations

import sqlite3

from src.contracts.run_context import RunContext
from src.contracts.state import StateDbAccessRequest, StateDbAccessResponse
from src.services._state_common import ACCESS_TIMEOUT_SECONDS, _is_lock_error, logger
from src.utils.errors import AppError
from src.utils.logging import log_event


def check_state_db_access(
    request: StateDbAccessRequest, ctx: RunContext
) -> StateDbAccessResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_db_access_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    if not request.state_db or not request.state_db.strip():
        raise AppError(
            code="state_db_missing",
            message="State DB path is required",
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
            event="state_db_access_config",
            module=logger.name,
            fields={"timeout_seconds": timeout},
        )
    )
    try:
        conn = sqlite3.connect(request.state_db, timeout=timeout)
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="state_db_access_connect_failed",
                module=logger.name,
                fields={"state_db": request.state_db, "error": str(exc)},
            )
        )
        raise AppError(
            code="state_db_unavailable",
            message="Failed to open state DB",
            cause=exc,
            retryable=True,
            context={"state_db": request.state_db},
        ) from exc
    try:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="state_db_access_probe",
                module=logger.name,
                fields={"state_db": request.state_db},
            )
        )
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            message = str(exc)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="state_db_access_locked",
                    module=logger.name,
                    fields={"state_db": request.state_db, "error": message},
                )
            )
            response = StateDbAccessResponse(
                schema_version="1.0",
                state_db=request.state_db,
                accessible=False,
                locked=True,
                message=message,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="state_db_access_complete",
                    module=logger.name,
                    fields={
                        "state_db": response.state_db,
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
                event="state_db_access_failed",
                module=logger.name,
                fields={"state_db": request.state_db, "error": str(exc)},
            )
        )
        raise AppError(
            code="state_db_unavailable",
            message="State DB is not accessible",
            cause=exc,
            retryable=True,
            context={"state_db": request.state_db},
        ) from exc
    finally:
        conn.close()
    response = StateDbAccessResponse(
        schema_version="1.0",
        state_db=request.state_db,
        accessible=True,
        locked=False,
        message="",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_db_access_complete",
            module=logger.name,
            fields={
                "state_db": response.state_db,
                "accessible": response.accessible,
                "locked": response.locked,
                "message": response.message,
            },
        )
    )
    return response
