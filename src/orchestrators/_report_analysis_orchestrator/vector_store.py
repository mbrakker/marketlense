"""Vector-store readiness waiting for report analysis.

This module owns deterministic polling, timeout, and status normalization for
the vector-store phase used by the report-analysis orchestrator.
"""

from __future__ import annotations

from math import ceil
from typing import Optional

from src.contracts.vector_store import VectorStoreStatusRequest
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_analysis_generator import VectorStoreIndexingState
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.utils.errors import AppError
from src.utils.logging import log_event

__all__ = [
    "VECTOR_STORE_FAILED_STATUSES",
    "VECTOR_STORE_POLL_INTERVAL_SECONDS",
    "VECTOR_STORE_READY_STATUSES",
    "_await_vector_store_indexing",
    "_is_vector_store_ready",
]


VECTOR_STORE_READY_STATUSES = {"completed", "ready", "indexed"}


VECTOR_STORE_FAILED_STATUSES = {"failed", "errored"}


def _await_vector_store_indexing(
    state: VectorStoreIndexingState,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
) -> VectorStoreIndexingState:
    vector_store_id = state.vector_store_id
    if not vector_store_id:
        raise AppError(
            code="vector_store_missing",
            message="vector_store_id is required before awaiting indexing",
            retryable=False,
        )
    if _is_vector_store_ready(state.vector_store_status):
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="vector_store_wait_skipped",
                module=logger.name,
                fields={
                    "vector_store_id": vector_store_id,
                    "status": state.vector_store_status or "",
                    "indexed_at_utc": state.indexed_at_utc or "",
                },
            )
        )
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="vector_store_ready",
                module=logger.name,
                fields={
                    "vector_store_id": vector_store_id,
                    "status": state.vector_store_status or "",
                    "indexed_at_utc": state.indexed_at_utc or "",
                },
            )
        )
        return state

    timeout_seconds = max(1, int(runtime.settings.openai_timeout_seconds))
    poll_interval_seconds = VECTOR_STORE_POLL_INTERVAL_SECONDS
    max_attempts = max(1, int(ceil(timeout_seconds / poll_interval_seconds)))
    last_status = state.vector_store_status or ""
    last_error = state.last_error
    last_indexed_at = state.indexed_at_utc

    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="vector_store_wait_start",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "status": last_status,
                "timeout_s": timeout_seconds,
                "poll_interval_s": poll_interval_seconds,
                "max_attempts": max_attempts,
            },
        )
    )

    def _poll_status():
        nonlocal last_status, last_error, last_indexed_at
        status_resp = dependencies.vector_store_get_status(
            VectorStoreStatusRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
            ),
            mode_ctx,
        )
        last_status = status_resp.status
        last_error = status_resp.last_error
        last_indexed_at = status_resp.indexed_at_utc
        normalized_status = str(status_resp.status or "").strip().lower()
        if normalized_status in VECTOR_STORE_READY_STATUSES:
            return status_resp
        if normalized_status in VECTOR_STORE_FAILED_STATUSES:
            raise AppError(
                code="vector_store_index_failed",
                message=(
                    "Vector store indexing failed: "
                    f"{status_resp.last_error or status_resp.status}"
                ),
                retryable=False,
                context={
                    "vector_store_id": vector_store_id,
                    "last_status": status_resp.status,
                    "last_error": status_resp.last_error,
                },
            )
        raise AppError(
            code="vector_store_index_pending",
            message="Vector store indexing is still in progress",
            retryable=True,
            context={
                "vector_store_id": vector_store_id,
                "last_status": status_resp.status,
                "last_error": status_resp.last_error,
                "indexed_at_utc": status_resp.indexed_at_utc,
            },
        )

    try:
        status_resp = run_with_retry(
            step_name="vector_store_index_status",
            operation=_poll_status,
            ctx=mode_ctx,
            logger=logger,
            module_name=logger.name,
            policy=RetryPolicy(
                retries=max_attempts - 1,
                base_delay_seconds=float(poll_interval_seconds),
                backoff_step_seconds=0.0,
                jitter_seconds=0.0,
            ),
            retry_event="vector_store_wait_retry",
            retry_fields_builder=lambda exc, attempt: {
                "step": "vector_store_index_status",
                "attempt": attempt + 1,
                "vector_store_id": vector_store_id,
                "status": (
                    exc.context.get("last_status", "")
                    if isinstance(exc, AppError) and isinstance(exc.context, dict)
                    else last_status
                ),
                "timeout_s": timeout_seconds,
                "poll_interval_s": poll_interval_seconds,
            },
            failure_event="vector_store_wait_failed",
            failure_fields_builder=lambda exc, attempt, retryable: {
                "step": "vector_store_index_status",
                "attempt": attempt + 1,
                "retryable": retryable,
                "vector_store_id": vector_store_id,
                "status": (
                    exc.context.get("last_status", "")
                    if isinstance(exc, AppError) and isinstance(exc.context, dict)
                    else last_status
                ),
                "code": exc.code if isinstance(exc, AppError) else "",
                "error": exc.message if isinstance(exc, AppError) else str(exc),
            },
            is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
        )
    except AppError as exc:
        if exc.code == "vector_store_index_pending":
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="vector_store_wait_timeout",
                    module=logger.name,
                    fields={
                        "vector_store_id": vector_store_id,
                        "last_status": last_status,
                        "timeout_s": timeout_seconds,
                        "poll_interval_s": poll_interval_seconds,
                        "max_attempts": max_attempts,
                    },
                )
            )
            raise AppError(
                code="vector_store_index_timeout",
                message="Timed out waiting for vector store indexing",
                retryable=True,
                context={
                    "vector_store_id": vector_store_id,
                    "last_status": last_status or None,
                    "last_error": last_error,
                    "timeout_s": timeout_seconds,
                    "poll_interval_s": poll_interval_seconds,
                    "max_attempts": max_attempts,
                },
            ) from exc
        raise

    ready_state = VectorStoreIndexingState(
        vector_store_id=vector_store_id,
        openai_file_id=state.openai_file_id,
        vector_store_status=status_resp.status,
        indexed_at_utc=status_resp.indexed_at_utc,
        last_error=status_resp.last_error,
    )
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="vector_store_ready",
            module=logger.name,
            fields={
                "vector_store_id": ready_state.vector_store_id,
                "status": ready_state.vector_store_status or "",
                "indexed_at_utc": ready_state.indexed_at_utc or "",
            },
        )
    )
    return ready_state


VECTOR_STORE_POLL_INTERVAL_SECONDS = 5


def _is_vector_store_ready(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in VECTOR_STORE_READY_STATUSES
