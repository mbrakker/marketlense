from __future__ import annotations

import logging

from src.contracts.ingest import IngestSettings
from src.contracts.report_store import ReportMetadataDbAccessRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateDbAccessRequest
from src.services.report_store_service import check_report_db_access
from src.services.state_service import check_state_db_access
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


logger = logging.getLogger("market_lense.ingest_orchestrator")
DB_ACCESS_TIMEOUT_SECONDS = 0.0


def verify_ingest_db_access(settings: IngestSettings, root_ctx: RunContext) -> None:
    db_ctx = child_context(root_ctx, task_id="ingest_db_access")
    logger.info(
        log_event(
            db_ctx,
            role="orchestrator",
            event="ingest_db_access_start",
            module=logger.name,
            fields={
                "state_db": settings.state_db,
                "reports_db": settings.reports_db,
            },
        )
    )
    state_access = check_state_db_access(
        StateDbAccessRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            timeout_seconds=DB_ACCESS_TIMEOUT_SECONDS,
        ),
        db_ctx,
    )
    report_access = check_report_db_access(
        ReportMetadataDbAccessRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            timeout_seconds=DB_ACCESS_TIMEOUT_SECONDS,
        ),
        db_ctx,
    )
    if state_access.accessible and report_access.accessible:
        logger.info(
            log_event(
                db_ctx,
                role="orchestrator",
                event="ingest_db_access_complete",
                module=logger.name,
                fields={
                    "state_db": settings.state_db,
                    "reports_db": settings.reports_db,
                },
            )
        )
        return
    locked = []
    if state_access.locked:
        locked.append(f"state_db={settings.state_db}")
    if report_access.locked:
        locked.append(f"reports_db={settings.reports_db}")
    reason = ", ".join(locked) if locked else "unknown"
    logger.info(
        log_event(
            db_ctx,
            role="orchestrator",
            event="ingest_db_access_blocked",
            module=logger.name,
            fields={
                "state_db_accessible": state_access.accessible,
                "state_db_locked": state_access.locked,
                "reports_db_accessible": report_access.accessible,
                "reports_db_locked": report_access.locked,
                "reason": reason,
            },
        )
    )
    raise AppError(
        code="db_locked",
        message=f"Database locked: {reason}",
        retryable=False,
        context={
            "state_db": settings.state_db,
            "reports_db": settings.reports_db,
            "state_db_locked": state_access.locked,
            "reports_db_locked": report_access.locked,
        },
    )
