from __future__ import annotations

import logging
from dataclasses import replace

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")


def apply_browser_route_budget(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserReportDownloadRequest:
    route_family = str(request.route_family_hint or "").strip()
    matched_budget = next(
        (
            budget
            for budget in request.settings.route_budgets
            if budget.route_family == route_family
        ),
        None,
    )
    if matched_budget is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_route_budget_resolved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "route_family": route_family,
                    "budget_configured": False,
                    "effective_max_steps": request.settings.max_steps,
                    "effective_timeout_seconds": request.settings.timeout_seconds,
                },
            )
        )
        return request

    effective_max_steps = request.settings.max_steps
    if matched_budget.max_steps is not None:
        effective_max_steps = min(effective_max_steps, int(matched_budget.max_steps))
    effective_timeout_seconds = request.settings.timeout_seconds
    if matched_budget.timeout_seconds is not None:
        effective_timeout_seconds = min(
            effective_timeout_seconds,
            float(matched_budget.timeout_seconds),
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_route_budget_resolved",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "route_family": route_family,
                "budget_configured": True,
                "configured_max_steps": matched_budget.max_steps,
                "configured_timeout_seconds": matched_budget.timeout_seconds,
                "global_max_steps": request.settings.max_steps,
                "global_timeout_seconds": request.settings.timeout_seconds,
                "effective_max_steps": effective_max_steps,
                "effective_timeout_seconds": effective_timeout_seconds,
            },
        )
    )
    if (
        effective_max_steps == request.settings.max_steps
        and effective_timeout_seconds == request.settings.timeout_seconds
    ):
        return request
    return replace(
        request,
        settings=replace(
            request.settings,
            max_steps=effective_max_steps,
            timeout_seconds=effective_timeout_seconds,
        ),
    )
