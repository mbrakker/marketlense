from __future__ import annotations

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryRoutePlanRequest,
    PublisherInventoryRoutePlanResponse,
    PublisherInventoryRoutePlanStep,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_route_planner")


def plan_publisher_inventory_routes(
    request: PublisherInventoryRoutePlanRequest,
    ctx: RunContext,
) -> PublisherInventoryRoutePlanResponse:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_route_plan_start",
            module=logger.name,
            fields={
                "normalized_url": request.normalized_url,
                "force_browser": request.force_browser,
                "remembered_route_kind": request.remembered_route_kind or "",
                "has_remembered_route_summary": bool(request.remembered_route_summary),
                "previous_quality_outcome": (
                    request.previous_run_quality_summary.outcome
                    if request.previous_run_quality_summary is not None
                    else ""
                ),
                "previous_recommended_route_kind": (
                    request.previous_run_quality_summary.recommended_route_kind
                    if request.previous_run_quality_summary is not None
                    else ""
                ),
            },
        )
    )
    response = _build_plan(request)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_route_plan_complete",
            module=logger.name,
            fields={
                "normalized_url": request.normalized_url,
                "planning_reason": response.planning_reason,
                "step_names": [step.step_name for step in response.steps],
                "route_kinds": [step.route_kind_hint or "" for step in response.steps],
                "uses_memory_route": [step.uses_memory_route for step in response.steps],
            },
        )
    )
    return response


def _build_plan(
    request: PublisherInventoryRoutePlanRequest,
) -> PublisherInventoryRoutePlanResponse:
    steps: list[PublisherInventoryRoutePlanStep] = []
    if request.remembered_route_summary:
        steps.append(
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_with_memory_route",
                route_kind_hint=request.remembered_route_kind,
                route_hint=request.remembered_route_summary,
                uses_memory_route=True,
                fallback_on_retryable_error=True,
            )
        )
        if request.force_browser:
            steps.append(
                PublisherInventoryRoutePlanStep(
                    schema_version="1.0",
                    step_name="publisher_inventory_discovery_browser",
                    route_kind_hint="browser_render",
                    route_hint=None,
                    uses_memory_route=False,
                    fallback_on_retryable_error=False,
                )
            )
            return PublisherInventoryRoutePlanResponse(
                schema_version="1.0",
                steps=steps,
                planning_reason=(
                    "Reuse the remembered route first, then force a browser retry if the remembered path fails with a retryable error."
                ),
            )
        steps.extend(_default_non_memory_steps(request))
        return PublisherInventoryRoutePlanResponse(
            schema_version="1.0",
            steps=_dedupe_steps(steps),
            planning_reason=(
                "Reuse the remembered route first, then follow the default fallback order only on retryable failure."
            ),
        )

    default_steps = _default_non_memory_steps(request)
    previous_quality = request.previous_run_quality_summary
    if (
        not request.force_browser
        and previous_quality is not None
        and previous_quality.recommended_route_kind == "browser_render"
        and previous_quality.requires_review
    ):
        default_steps = [
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_browser",
                route_kind_hint="browser_render",
                route_hint=None,
                uses_memory_route=False,
                fallback_on_retryable_error=False,
            ),
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_http",
                route_kind_hint="http_parse",
                route_hint=None,
                uses_memory_route=False,
                fallback_on_retryable_error=True,
            ),
        ]
        return PublisherInventoryRoutePlanResponse(
            schema_version="1.0",
            steps=default_steps,
            planning_reason=(
                "The previous run-quality summary flagged drift, so the next run should start with the stronger browser route before falling back to direct HTTP."
            ),
        )
    return PublisherInventoryRoutePlanResponse(
        schema_version="1.0",
        steps=default_steps,
        planning_reason=(
            "No remembered route is available, so use the default direct-HTTP-first plan unless browser use was forced."
        ),
    )


def _default_non_memory_steps(
    request: PublisherInventoryRoutePlanRequest,
) -> list[PublisherInventoryRoutePlanStep]:
    if request.force_browser:
        return [
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_browser",
                route_kind_hint="browser_render",
                route_hint=None,
                uses_memory_route=False,
                fallback_on_retryable_error=False,
            )
        ]
    return [
        PublisherInventoryRoutePlanStep(
            schema_version="1.0",
            step_name="publisher_inventory_discovery_http",
            route_kind_hint="http_parse",
            route_hint=None,
            uses_memory_route=False,
            fallback_on_retryable_error=True,
        ),
        PublisherInventoryRoutePlanStep(
            schema_version="1.0",
            step_name="publisher_inventory_discovery_browser",
            route_kind_hint="browser_render",
            route_hint=None,
            uses_memory_route=False,
            fallback_on_retryable_error=False,
        ),
    ]


def _dedupe_steps(
    steps: list[PublisherInventoryRoutePlanStep],
) -> list[PublisherInventoryRoutePlanStep]:
    deduped: list[PublisherInventoryRoutePlanStep] = []
    seen: set[tuple[str, str, str]] = set()
    for step in steps:
        key = (
            step.step_name,
            str(step.route_kind_hint or "").strip(),
            str(step.route_hint or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(step)
    return deduped
