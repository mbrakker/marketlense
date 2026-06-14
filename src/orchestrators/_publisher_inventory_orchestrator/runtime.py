from __future__ import annotations

"""Runtime controls for publisher-inventory orchestration.

This module owns discovery retry execution, time-budget enforcement, failure
status mapping, and timestamp generation used by the coordinator.
"""

import logging
import time
from dataclasses import replace

from src.contracts.publisher_inventory import (
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.utils.clock import utc_now_seconds_z as _utc_now_iso
from src.contracts.report_store import (
    PublisherInventoryStateResponse,
    PublisherInventoryTestStatusRecordRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.orchestrators._publisher_inventory_orchestrator.idempotency import (
    _record_test_status_if_needed,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


def _record_discovery_test_status_on_failure(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_state: PublisherInventoryStateResponse,
    code: str,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    status = _discovery_test_status_for_error_code(code)
    try:
        _record_test_status_if_needed(
            request=PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status=status,
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_test_status_record_failed",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "normalized_url": normalized_url,
                    "status": status,
                    "error": str(exc),
                },
            )
        )


def _discovery_test_status_for_error_code(code: str) -> str:
    normalized = str(code or "").strip()
    if not normalized:
        return "failed:unknown"
    if normalized == "publisher_inventory_browser_pagination_limit":
        return f"bounded:{normalized}"
    return f"failed:{normalized}"


def _run_discovery_attempt(
    *,
    request: PublisherInventoryDiscoveryRequest,
    ctx: RunContext,
    policy: RetryPolicy,
    dependencies: PublisherInventoryDependencies,
    route_hint: str | None,
    route_kind_hint: str | None,
    step_name: str,
    deadline_monotonic: float,
) -> PublisherInventoryServiceResponse:
    return run_with_retry(
        step_name=step_name,
        operation=lambda: dependencies.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url=request.insights_url,
                settings=_settings_with_time_budget(
                    request.settings,
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalize_url(request.insights_url),
                    step_name=step_name,
                    ctx=ctx,
                ),
                route_hint=route_hint,
                route_kind_hint=route_kind_hint,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="publisher_inventory_discovery_retry",
        failure_event="publisher_inventory_discovery_failed",
    )


def _remaining_time_budget_seconds(*, deadline_monotonic: float) -> float:
    return max(0.0, float(deadline_monotonic) - time.monotonic())


def _assert_time_budget_remaining(
    *,
    deadline_monotonic: float,
    normalized_url: str,
    step_name: str,
    ctx: RunContext,
    minimum_seconds: float = 1.0,
) -> float:
    remaining_seconds = _remaining_time_budget_seconds(
        deadline_monotonic=deadline_monotonic
    )
    if remaining_seconds >= minimum_seconds:
        return remaining_seconds
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_time_budget_exceeded",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "step_name": step_name,
                "remaining_seconds": remaining_seconds,
                "minimum_seconds": minimum_seconds,
            },
        )
    )
    raise AppError(
        code="publisher_inventory_time_budget_exceeded",
        message="Publisher inventory discovery exceeded the configured per-publisher time budget",
        retryable=False,
        severity="error",
        context={
            "normalized_url": normalized_url,
            "step_name": step_name,
            "remaining_seconds": remaining_seconds,
        },
    )


def _settings_with_time_budget(
    settings,
    *,
    deadline_monotonic: float,
    normalized_url: str,
    step_name: str,
    ctx: RunContext,
):
    remaining_seconds = _assert_time_budget_remaining(
        deadline_monotonic=deadline_monotonic,
        normalized_url=normalized_url,
        step_name=step_name,
        ctx=ctx,
    )
    return replace(
        settings,
        timeout_seconds=max(1.0, min(settings.timeout_seconds, remaining_seconds)),
        candidate_screening_timeout_seconds=max(
            1.0,
            min(settings.candidate_screening_timeout_seconds, remaining_seconds),
        ),
        candidate_quality_check_timeout_seconds=max(
            1.0,
            min(settings.candidate_quality_check_timeout_seconds, remaining_seconds),
        ),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
