from __future__ import annotations

import logging
from collections import defaultdict

from src.contracts.ingest import IngestSettings
from src.contracts.pipeline_preflight import PipelinePreflightRequest
from src.contracts.publish import PublishSettings
from src.contracts.retry_telemetry import RetryDecisionTelemetryReport
from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    ConcurrencyDecision,
    ConcurrencyLimit,
    ConcurrencyObservation,
    OperationalMemoryRecommendation,
    OperationalMemoryRecord,
    OperationalObservation,
    ResolvedRetryPolicy,
    WorkflowContract,
    WorkflowControlSettings,
    WorkflowPreflightProfile,
    WorkflowRetryPolicyConfig,
    WorkflowTransition,
)
from src.orchestrators.pipeline_preflight_orchestrator import (
    report_pipeline_prompt_namespaces,
)
from src.orchestrators.retry_orchestrator import RetryPolicy
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.workflow_control_orchestrator")


def default_workflow_control_settings() -> WorkflowControlSettings:
    return WorkflowControlSettings(
        schema_version="1.0",
        preflight_profiles=_default_preflight_profiles(),
        retry_policies=_default_retry_policies(),
        workflow_contracts=_default_workflow_contracts(),
        concurrency=_default_concurrency_limits(),
        operational_memory_ttl_days=30,
        operational_memory_min_observations=2,
    )


def build_workflow_preflight_request(
    control_settings: WorkflowControlSettings,
    *,
    workflow_name: str,
    settings_obj: IngestSettings | None = None,
    settings: IngestSettings | None = None,
    publish_settings: PublishSettings | None = None,
    require_live_endpoints: bool = False,
    ctx: RunContext | None = None,
) -> PipelinePreflightRequest:
    ingest_settings = settings_obj or settings
    if ingest_settings is None:
        raise AppError(
            code="workflow_preflight_settings_missing",
            message="Ingest settings are required to build a workflow preflight request",
            retryable=False,
            context={"workflow": workflow_name},
        )
    profile = _profile(control_settings, workflow_name)
    prompt_namespaces = list(profile.prompt_namespaces)
    if profile.workflow in {"report_generation", "report_pipeline"}:
        prompt_namespaces = sorted(
            set(prompt_namespaces) | set(report_pipeline_prompt_namespaces(ingest_settings))
        )
    if ctx is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="workflow_preflight_profile_resolved",
                module=logger.name,
                fields={
                    "workflow": profile.workflow,
                    "planned_side_effects": list(profile.planned_side_effects),
                    "prompt_namespaces": list(prompt_namespaces),
                    "require_llm": profile.require_llm,
                    "require_drive": profile.require_drive,
                    "require_publish": profile.require_publish,
                    "require_browser": profile.require_browser,
                    "require_live_endpoints": require_live_endpoints,
                },
            )
        )
    return PipelinePreflightRequest(
        schema_version="1.0",
        workflow=profile.workflow,
        planned_side_effects=list(profile.planned_side_effects),
        settings=ingest_settings,
        prompt_namespaces=prompt_namespaces,
        require_llm=profile.require_llm,
        require_drive=profile.require_drive,
        require_publish=profile.require_publish,
        require_browser=profile.require_browser,
        require_live_endpoints=require_live_endpoints,
        publish_settings=publish_settings,
    )


def resolve_workflow_contract(
    settings: WorkflowControlSettings,
    workflow_name: str,
) -> WorkflowContract:
    key = _key(workflow_name)
    contract = settings.workflow_contracts.get(key)
    if contract is None:
        raise AppError(
            code="workflow_contract_missing",
            message="Workflow DAG/state-machine contract is not configured",
            retryable=False,
            context={"workflow": workflow_name},
        )
    _validate_workflow_contract(contract)
    return contract


def is_valid_transition(
    contract: WorkflowContract,
    *,
    from_state: str,
    to_state: str,
) -> bool:
    source = _key(from_state)
    target = _key(to_state)
    return any(
        _key(item.from_state) == source and _key(item.to_state) == target
        for item in contract.transitions
    )


def resolve_retry_policy(
    settings: WorkflowControlSettings,
    *,
    workflow_name: str,
    step_name: str,
    ctx: RunContext,
) -> ResolvedRetryPolicy:
    workflow_key = _key(workflow_name)
    step_key = _key(step_name)
    workflow_policies = settings.retry_policies.get(workflow_key, {})
    policy_config = workflow_policies.get(step_key) or workflow_policies.get("*")
    if policy_config is None:
        policy_config = _default_retry_policies()["default"]["*"]
    resolved = ResolvedRetryPolicy(
        schema_version="1.0",
        workflow=workflow_key,
        step_name=step_key,
        policy_id=policy_config.policy_id,
        policy=RetryPolicy(
            retries=max(0, int(policy_config.retries)),
            base_delay_seconds=max(0.0, float(policy_config.base_delay_seconds)),
            backoff_step_seconds=max(0.0, float(policy_config.backoff_step_seconds)),
            jitter_seconds=max(0.0, float(policy_config.jitter_seconds)),
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="workflow_retry_policy_resolved",
            module=logger.name,
            fields={
                "workflow": resolved.workflow,
                "step": resolved.step_name,
                "policy_id": resolved.policy_id,
                "retries": resolved.policy.retries,
                "base_delay_seconds": resolved.policy.base_delay_seconds,
                "backoff_step_seconds": resolved.policy.backoff_step_seconds,
                "jitter_seconds": resolved.policy.jitter_seconds,
            },
        )
    )
    return resolved


def build_operational_memory(
    observations: list[OperationalObservation],
    *,
    retry_telemetry: RetryDecisionTelemetryReport | None = None,
) -> list[OperationalMemoryRecord]:
    grouped: dict[tuple[str, str, str], list[OperationalObservation]] = defaultdict(list)
    for observation in observations:
        grouped[
            (
                _stable_text(observation.publisher),
                _key(observation.workflow),
                _key(observation.route),
            )
        ].append(observation)

    retry_failures = _retry_failure_signatures(retry_telemetry)
    records: list[OperationalMemoryRecord] = []
    for key in sorted(grouped):
        publisher, workflow, route = key
        group = grouped[key]
        successes = [item for item in group if item.success]
        failures = [item for item in group if not item.success]
        local_failures = sorted(
            {
                _stable_text(item.failure_signature)
                for item in failures
                if _stable_text(item.failure_signature)
            }
        )
        telemetry_failures = sorted(
            retry_failures.get((publisher, workflow), set()) - set(local_failures)
        )
        failure_signatures = [*local_failures, *telemetry_failures]
        observation_count = len(group)
        success_count = len(successes)
        records.append(
            OperationalMemoryRecord(
                schema_version="1.0",
                publisher=publisher,
                workflow=workflow,
                route=route,
                observation_count=observation_count,
                success_count=success_count,
                failure_count=len(failures),
                success_rate=round(success_count / observation_count, 6),
                average_runtime_seconds=round(
                    sum(float(item.runtime_seconds) for item in group)
                    / observation_count,
                    6,
                ),
                average_cost_usd=round(
                    sum(float(item.cost_usd) for item in group) / observation_count,
                    6,
                ),
                pdf_extractable_rate=round(
                    sum(1 for item in group if item.pdf_extractable)
                    / observation_count,
                    6,
                ),
                credential_required=any(item.credential_required for item in group),
                failure_signatures=failure_signatures,
                recommended_retry_policy=f"{workflow}.{route}.v1",
            )
        )
    return records


def recommend_from_operational_memory(
    records: list[OperationalMemoryRecord],
    *,
    publisher: str,
    workflow_name: str,
) -> OperationalMemoryRecommendation:
    publisher_key = _stable_text(publisher)
    workflow_key = _key(workflow_name)
    candidates = [
        item
        for item in records
        if item.publisher == publisher_key and item.workflow == workflow_key
    ]
    if not candidates:
        return OperationalMemoryRecommendation(
            schema_version="1.0",
            publisher=publisher_key,
            workflow=workflow_key,
            recommended_route="",
            confidence=0.0,
            reason="no_memory",
            failure_signatures=[],
            recommended_retry_policy="",
        )
    selected = sorted(
        candidates,
        key=lambda item: (
            -_memory_confidence(item),
            item.average_runtime_seconds,
            item.average_cost_usd,
            item.route,
        ),
    )[0]
    selected_signatures = [item for item in selected.failure_signatures if item]
    other_signatures = sorted(
        {
            signature
            for item in candidates
            for signature in item.failure_signatures
            if signature and signature not in set(selected_signatures)
        }
    )
    failure_signatures = [*selected_signatures, *other_signatures]
    confidence = _memory_confidence(selected)
    return OperationalMemoryRecommendation(
        schema_version="1.0",
        publisher=publisher_key,
        workflow=workflow_key,
        recommended_route=selected.route,
        confidence=round(confidence, 6),
        reason="highest_success_fastest_route",
        failure_signatures=failure_signatures,
        recommended_retry_policy=selected.recommended_retry_policy,
    )


def _memory_confidence(record: OperationalMemoryRecord) -> float:
    return min(1.0, record.success_rate * min(1.0, record.observation_count / 2.0))


def resolve_adaptive_concurrency(
    limit: ConcurrencyLimit,
    observation: ConcurrencyObservation,
) -> ConcurrencyDecision:
    bounded_current = _bounded(
        int(observation.current_limit),
        minimum=int(limit.min_limit),
        maximum=int(limit.max_limit),
    )
    pressure = (
        observation.retry_rate >= limit.high_retry_rate
        or observation.p95_latency_ms >= limit.high_latency_ms
        or observation.sqlite_lock_count > 0
        or observation.browser_failure_rate >= limit.high_retry_rate
        or observation.budget_burn_rate >= 1.0
    )
    stable = (
        observation.retry_rate <= limit.low_retry_rate
        and observation.p95_latency_ms <= limit.low_latency_ms
        and observation.sqlite_lock_count == 0
        and observation.browser_failure_rate <= limit.low_retry_rate
        and observation.budget_burn_rate < 0.75
    )
    if pressure:
        selected = max(int(limit.min_limit), bounded_current - 1)
        reason = "pressure_detected"
    elif stable:
        selected = min(int(limit.max_limit), bounded_current + 1)
        reason = "stable_headroom" if selected != bounded_current else "max_bound"
    else:
        selected = bounded_current
        reason = "hold"
    return ConcurrencyDecision(
        schema_version="1.0",
        resource=_key(limit.resource),
        previous_limit=bounded_current,
        selected_limit=selected,
        reason=reason,
        evidence={
            "retry_rate": float(observation.retry_rate),
            "p95_latency_ms": int(observation.p95_latency_ms),
            "sqlite_lock_count": int(observation.sqlite_lock_count),
            "browser_failure_rate": float(observation.browser_failure_rate),
            "budget_burn_rate": float(observation.budget_burn_rate),
        },
    )


def _profile(
    settings: WorkflowControlSettings,
    workflow_name: str,
) -> WorkflowPreflightProfile:
    profile = settings.preflight_profiles.get(_key(workflow_name))
    if profile is None:
        raise AppError(
            code="workflow_preflight_profile_missing",
            message="Workflow preflight profile is not configured",
            retryable=False,
            context={"workflow": workflow_name},
        )
    return profile


def _validate_workflow_contract(contract: WorkflowContract) -> None:
    states = {_key(item) for item in contract.states}
    if _key(contract.initial_state) not in states:
        raise AppError(
            code="workflow_contract_invalid",
            message="Workflow contract initial state is not listed in states",
            retryable=False,
            context={"workflow": contract.workflow},
        )
    for transition in contract.transitions:
        if _key(transition.from_state) not in states or _key(transition.to_state) not in states:
            raise AppError(
                code="workflow_contract_invalid",
                message="Workflow transition references an unknown state",
                retryable=False,
                context={
                    "workflow": contract.workflow,
                    "from_state": transition.from_state,
                    "to_state": transition.to_state,
                },
            )


def _retry_failure_signatures(
    telemetry: RetryDecisionTelemetryReport | None,
) -> dict[tuple[str, str], set[str]]:
    signatures: dict[tuple[str, str], set[str]] = defaultdict(set)
    if telemetry is None:
        return signatures
    for row in telemetry.rows:
        publisher = _stable_text(row.publisher)
        workflow = _key(row.workflow)
        if publisher and workflow and row.error_code:
            signatures[(publisher, workflow)].add(_stable_text(row.error_code))
    return signatures


def _default_preflight_profiles() -> dict[str, WorkflowPreflightProfile]:
    raw = {
        "report_generation": (["pdf", "model"], True, False, False, False, []),
        "publisher_inventory": (
            ["network", "browser", "drive", "model"],
            True,
            True,
            False,
            True,
            [
                "publisher_inventory/discovery",
                "publisher_inventory/meaningful_candidate_screen",
            ],
        ),
        "report_download": (
            ["network", "browser", "drive"],
            False,
            True,
            False,
            True,
            ["browser_report_download/browser_route"],
        ),
        "cross_report_analysis": (
            ["model", "analytics_store"],
            True,
            False,
            False,
            False,
            ["cross_report_analysis/synthesis"],
        ),
        "publishing": (["wordpress", "publish"], False, False, True, False, []),
        "ui_replay": (["filesystem"], False, False, False, False, []),
        "wordpress_sync": (["wordpress"], False, False, True, False, []),
        "browser_acquisition": (
            ["network", "browser"],
            False,
            False,
            False,
            True,
            ["browser_report_download/browser_route"],
        ),
    }
    return {
        name: WorkflowPreflightProfile(
            schema_version="1.0",
            workflow=name,
            planned_side_effects=list(values[0]),
            require_llm=bool(values[1]),
            require_drive=bool(values[2]),
            require_publish=bool(values[3]),
            require_browser=bool(values[4]),
            prompt_namespaces=list(values[5]),
        )
        for name, values in raw.items()
    }


def _default_retry_policies() -> dict[str, dict[str, WorkflowRetryPolicyConfig]]:
    def policy(policy_id: str, retries: int) -> WorkflowRetryPolicyConfig:
        return WorkflowRetryPolicyConfig(
            schema_version="1.0",
            policy_id=policy_id,
            retries=retries,
            base_delay_seconds=1.0,
            backoff_step_seconds=1.0,
            jitter_seconds=0.25,
        )

    return {
        "default": {"*": policy("default.v1", 1)},
        "report_generation": {
            "report_pipeline": policy("report_generation.report_pipeline.v1", 2),
            "doc_map": policy("report_generation.doc_map.v1", 2),
        },
        "report_download": {
            "http_pdf": policy("report_download.http_pdf.v1", 1),
            "browser_acquisition": policy("report_download.browser_acquisition.v1", 1),
            "drive_archive": policy("report_download.drive_archive.v1", 1),
        },
        "publisher_inventory": {
            "discovery": policy("publisher_inventory.discovery.v1", 1),
            "candidate_screening": policy("publisher_inventory.candidate_screening.v1", 1),
        },
        "publishing": {
            "wordpress_publish": policy("publishing.wordpress_publish.v1", 1),
        },
    }


def _default_workflow_contracts() -> dict[str, WorkflowContract]:
    report_transitions = [
        ("pending", "preflighted", "preflight", "default.v1", []),
        (
            "preflighted",
            "source_prepared",
            "source_preparation",
            "default.v1",
            ["pdf"],
        ),
        (
            "source_prepared",
            "selection_complete",
            "figure_selection",
            "default.v1",
            ["pdf", "model"],
        ),
        (
            "selection_complete",
            "analysis_complete",
            "report_analysis",
            "report_generation.report_pipeline.v1",
            ["model"],
        ),
        (
            "analysis_complete",
            "render_complete",
            "render_projection",
            "default.v1",
            ["filesystem"],
        ),
        ("render_complete", "processed", "finish", "default.v1", []),
    ]
    contracts = {
        "report_generation": _contract(
            "report_generation",
            states=[
                "pending",
                "preflighted",
                "source_prepared",
                "selection_complete",
                "analysis_complete",
                "render_complete",
                "processed",
                "error",
            ],
            transitions=report_transitions,
            checkpoint_outputs=[
                "source_prepared",
                "selection_complete",
                "analysis_complete",
                "render_complete",
            ],
            validation_gates=["preflight", "artifact_integrity", "report_validation"],
            terminal_outcomes=["processed", "skipped", "error"],
        )
    }
    for name in (
        "publisher_inventory",
        "report_download",
        "cross_report_analysis",
        "publishing",
        "ui_replay",
        "wordpress_sync",
        "browser_acquisition",
    ):
        contracts[name] = _contract(
            name,
            states=["pending", "preflighted", "running", "completed", "failed"],
            transitions=[
                ("pending", "preflighted", "preflight", "default.v1", []),
                ("preflighted", "running", "execute", "default.v1", []),
                ("running", "completed", "complete", "default.v1", []),
                ("running", "failed", "fail", "default.v1", []),
            ],
            checkpoint_outputs=[],
            validation_gates=["preflight"],
            terminal_outcomes=["completed", "failed"],
        )
    return contracts


def _contract(
    workflow: str,
    *,
    states: list[str],
    transitions: list[tuple[str, str, str, str, list[str]]],
    checkpoint_outputs: list[str],
    validation_gates: list[str],
    terminal_outcomes: list[str],
) -> WorkflowContract:
    return WorkflowContract(
        schema_version="1.0",
        workflow=workflow,
        version="1.0",
        states=list(states),
        initial_state=states[0],
        transitions=[
            WorkflowTransition(
                schema_version="1.0",
                from_state=source,
                to_state=target,
                step_name=step,
                retry_policy_ref=retry_policy,
                side_effects=list(side_effects),
            )
            for source, target, step, retry_policy, side_effects in transitions
        ],
        prerequisites={"preflighted": ["preflight"]},
        checkpoint_outputs=list(checkpoint_outputs),
        validation_gates=list(validation_gates),
        terminal_outcomes=list(terminal_outcomes),
    )


def _default_concurrency_limits() -> dict[str, ConcurrencyLimit]:
    raw = {
        "model": (1, 4, 2, 0.25, 5000, 0.05, 1500),
        "pdf": (1, 4, 2, 0.20, 4000, 0.02, 1000),
        "browser": (1, 2, 1, 0.20, 10000, 0.02, 3000),
        "drive": (1, 4, 2, 0.20, 3000, 0.02, 800),
        "wordpress": (1, 4, 2, 0.20, 3000, 0.02, 800),
    }
    return {
        resource: ConcurrencyLimit(
            schema_version="1.0",
            resource=resource,
            min_limit=values[0],
            max_limit=values[1],
            default_limit=values[2],
            high_retry_rate=values[3],
            high_latency_ms=values[4],
            low_retry_rate=values[5],
            low_latency_ms=values[6],
        )
        for resource, values in raw.items()
    }


def _stable_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: object) -> str:
    return _stable_text(value).lower().replace("-", "_").replace(" ", "_")


def _bounded(value: int, *, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, value))


__all__ = [
    "ConcurrencyDecision",
    "ConcurrencyLimit",
    "ConcurrencyObservation",
    "OperationalMemoryRecommendation",
    "OperationalMemoryRecord",
    "OperationalObservation",
    "ResolvedRetryPolicy",
    "WorkflowContract",
    "WorkflowControlSettings",
    "WorkflowPreflightProfile",
    "WorkflowRetryPolicyConfig",
    "WorkflowTransition",
    "build_operational_memory",
    "build_workflow_preflight_request",
    "default_workflow_control_settings",
    "is_valid_transition",
    "recommend_from_operational_memory",
    "resolve_adaptive_concurrency",
    "resolve_retry_policy",
    "resolve_workflow_contract",
]
