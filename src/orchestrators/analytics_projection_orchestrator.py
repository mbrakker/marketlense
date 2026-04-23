from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from src.contracts.analytics_projection import (
    AnalyticsProjectionBatch,
    AnalyticsProjectionBuildRequest,
    AnalyticsProjectionFailureRequest,
    AnalyticsProjectionRunRequest,
    AnalyticsProjectionUpsertRequest,
    AnalyticsProjectionUpsertResponse,
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
)
from src.contracts.run_context import RunContext
from src.generators.analytics_projection_generator import build_projection
from src.services.analytics_store_service import (
    record_projection_failure,
    upsert_projection,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.analytics_projection_orchestrator")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class AnalyticsProjectionDependencies:
    build_projection: Callable[
        [AnalyticsProjectionBuildRequest],
        AnalyticsProjectionBatch,
    ] = field(metadata={"doc": "Generator boundary for analytics projection rows."})
    upsert_projection: Callable[
        [AnalyticsProjectionUpsertRequest, RunContext],
        AnalyticsProjectionUpsertResponse,
    ] = field(metadata={"doc": "Service boundary for analytics projection upserts."})
    record_projection_failure: Callable[
        [AnalyticsProjectionFailureRequest, RunContext],
        object,
    ] = field(metadata={"doc": "Service boundary for projection failure metadata."})
    utc_now: Callable[[], str] = field(
        metadata={"doc": "Clock boundary used to stamp projection attempts."}
    )
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Dependency contract schema version."},
    )

    @classmethod
    def default(cls) -> "AnalyticsProjectionDependencies":
        return cls(
            build_projection=build_projection,
            upsert_projection=upsert_projection,
            record_projection_failure=record_projection_failure,
            utc_now=_utc_now,
        )


def _projection_error(exc: Exception, report_id: str) -> AppError:
    if isinstance(exc, AppError):
        return exc
    return AppError(
        code="analytics_projection_failed",
        message="Analytics projection failed",
        cause=exc,
        retryable=False,
        severity="error",
        context={"report_id": report_id},
    )


def _record_failure(
    *,
    request: AnalyticsProjectionRunRequest,
    generated_at_utc: str,
    error: AppError,
    dependencies: AnalyticsProjectionDependencies,
) -> None:
    failure_ctx = child_context(
        request.ctx,
        task_id=f"{request.ctx.task_id}:analytics_projection_failure",
    )
    dependencies.record_projection_failure(
        AnalyticsProjectionFailureRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=request.db_path,
            report_id=request.analysis.runtime.file.file_id,
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            projection_version=PROJECTION_VERSION,
            generated_at_utc=generated_at_utc,
            error_code=error.code,
            error_message=error.message,
            error_retryable=error.retryable,
        ),
        failure_ctx,
    )


def run_analytics_projection(
    request: AnalyticsProjectionRunRequest,
    *,
    dependencies: AnalyticsProjectionDependencies | None = None,
) -> AnalyticsProjectionUpsertResponse:
    deps = dependencies or AnalyticsProjectionDependencies.default()
    report_id = str(request.analysis.runtime.file.file_id)
    generated_at_utc = deps.utc_now()
    projection_ctx = child_context(
        request.ctx,
        task_id=f"{request.ctx.task_id}:analytics_projection",
    )
    logger.info(
        log_event(
            projection_ctx,
            role="orchestrator",
            event="analytics_projection_start",
            module=logger.name,
            fields={
                "report_id": report_id,
                "db_path": request.db_path,
                "rendered_html_path": request.rendered_html_path,
                "projection_version": PROJECTION_VERSION,
            },
        )
    )
    try:
        batch = deps.build_projection(
            AnalyticsProjectionBuildRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                analysis=request.analysis,
                rendered_html_path=request.rendered_html_path,
                generated_at_utc=generated_at_utc,
            )
        )
        response = deps.upsert_projection(
            AnalyticsProjectionUpsertRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                db_path=request.db_path,
                batch=batch,
            ),
            projection_ctx,
        )
    except Exception as exc:
        error = _projection_error(exc, report_id)
        try:
            _record_failure(
                request=request,
                generated_at_utc=generated_at_utc,
                error=error,
                dependencies=deps,
            )
        except Exception as record_exc:
            record_error = _projection_error(record_exc, report_id)
            logger.error(
                log_event(
                    projection_ctx,
                    role="orchestrator",
                    event="analytics_projection_failure_record_error",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "error_code": record_error.code,
                        "error_retryable": record_error.retryable,
                    },
                )
            )
        logger.error(
            log_event(
                projection_ctx,
                role="orchestrator",
                event="analytics_projection_failed",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "error_code": error.code,
                    "error_retryable": error.retryable,
                    "error_message": error.message,
                },
            )
        )
        raise error from error.cause

    logger.info(
        log_event(
            projection_ctx,
            role="orchestrator",
            event="analytics_projection_complete",
            module=logger.name,
            fields={
                "report_id": report_id,
                "projection_attempt_count": response.projection_attempt_count,
                "rows_upserted": response.rows_upserted,
                "vector_queue_count": response.vector_queue_count,
            },
        )
    )
    return response
