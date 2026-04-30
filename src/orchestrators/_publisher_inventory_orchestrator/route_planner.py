from __future__ import annotations

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryRoutePolicySignal,
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
                "has_remembered_route_trace": bool(request.remembered_route_trace),
                "remembered_scenario_class": (
                    request.remembered_scenario_summary.scenario_class
                    if request.remembered_scenario_summary is not None
                    else ""
                ),
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
                "route_policy_order": [
                    signal.route_kind for signal in request.route_policy
                ],
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
                "uses_memory_route": [
                    step.uses_memory_route for step in response.steps
                ],
                "route_policy_order": [
                    signal.route_kind for signal in request.route_policy
                ],
            },
        )
    )
    return response


def _build_plan(
    request: PublisherInventoryRoutePlanRequest,
) -> PublisherInventoryRoutePlanResponse:
    steps: list[PublisherInventoryRoutePlanStep] = []
    if (
        request.enable_structured_route_reuse
        and request.remembered_route_trace is not None
        and request.remembered_route_summary
    ):
        steps.append(
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_with_structured_memory_route",
                route_kind_hint=request.remembered_route_kind,
                route_hint=request.remembered_route_summary,
                uses_memory_route=True,
                fallback_on_retryable_error=True,
            )
        )
        steps.extend(_default_non_memory_steps(request))
        return PublisherInventoryRoutePlanResponse(
            schema_version="1.0",
            steps=_dedupe_steps(steps),
            planning_reason=(
                "Reuse the structured remembered route first, then fall back to the default route order only on retryable failure."
            ),
        )
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
    policy_signal = _preferred_route_policy_signal(request.route_policy)
    if policy_signal is not None and not request.force_browser:
        policy_steps = _policy_guided_steps(policy_signal, request)
        return PublisherInventoryRoutePlanResponse(
            schema_version="1.0",
            steps=policy_steps,
            planning_reason=(
                "Publisher inventory route-policy history prefers "
                f"{policy_signal.route_kind} "
                f"(success rate {policy_signal.success_rate:.3f}, confidence {policy_signal.confidence_score:.3f}), "
                "so start discovery with the learned route before static fallback."
            ),
        )
    default_steps = _scenario_guided_steps(request)
    return PublisherInventoryRoutePlanResponse(
        schema_version="1.0",
        steps=default_steps,
        planning_reason=(
            "No remembered route is available, so use scenario-guided routing before falling back to the default order."
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


def _scenario_guided_steps(
    request: PublisherInventoryRoutePlanRequest,
) -> list[PublisherInventoryRoutePlanStep]:
    scenario_class = (
        request.remembered_scenario_summary.scenario_class
        if request.remembered_scenario_summary is not None
        else ""
    )
    if scenario_class in {
        "filtered_archive",
        "tabbed_archive",
        "mixed_content_hub",
        "js_hydrated_archive",
        "challenge_prone",
    }:
        return [
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
    return _default_non_memory_steps(request)


def _preferred_route_policy_signal(
    signals: list[PublisherInventoryRoutePolicySignal],
) -> PublisherInventoryRoutePolicySignal | None:
    for signal in signals:
        if signal.route_kind not in {"http_parse", "browser_render"}:
            continue
        if signal.attempts < 3:
            continue
        if signal.successful_attempts < 2:
            continue
        if signal.success_rate < 0.667:
            continue
        if signal.confidence_score < 0.65:
            continue
        if signal.rank_score < 0.65:
            continue
        if (
            signal.review_required_attempts
            and (signal.review_required_attempts / signal.attempts) > 0.25
        ):
            continue
        return signal
    return None


def _policy_guided_steps(
    signal: PublisherInventoryRoutePolicySignal,
    request: PublisherInventoryRoutePlanRequest,
) -> list[PublisherInventoryRoutePlanStep]:
    first_kind = signal.route_kind
    if first_kind == "browser_render":
        steps = [
            PublisherInventoryRoutePlanStep(
                schema_version="1.0",
                step_name="publisher_inventory_discovery_policy_browser",
                route_kind_hint="browser_render",
                route_hint=None,
                uses_memory_route=False,
                fallback_on_retryable_error=True,
            )
        ]
        if not request.force_browser:
            steps.append(
                PublisherInventoryRoutePlanStep(
                    schema_version="1.0",
                    step_name="publisher_inventory_discovery_http",
                    route_kind_hint="http_parse",
                    route_hint=None,
                    uses_memory_route=False,
                    fallback_on_retryable_error=True,
                )
            )
        return _dedupe_steps(steps)
    return _default_non_memory_steps(request)


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
