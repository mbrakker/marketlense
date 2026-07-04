from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Callable, TypeVar, cast

from src.contracts.ingest import IngestSettings
from src.contracts.pipeline_preflight import (
    PipelinePreflightRequest,
    PipelinePreflightReport,
)
from src.contracts.publish import PublishSettings
from src.contracts.retry_telemetry import RetryDecisionTelemetryReport
from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    ConcurrencyDecision,
    ConcurrencyLimit,
    ConcurrencyObservation,
    ModelCallAuditRecord,
    ModelCallReplayBundle,
    OperationalMemoryRecommendation,
    OperationalMemoryRecord,
    OperationalObservation,
    PreLlmDataQualityDecision,
    PreLlmDataQualityInput,
    PreflightRemediationAction,
    PreflightRemediationArtifact,
    PublishPolicyDecision,
    PublishPolicyInput,
    ResolvedRetryPolicy,
    ResolvedRunIntent,
    RunIntent,
    WorkflowContract,
    WorkflowControlSettings,
    WorkflowControlObservation,
    WorkflowGateOutcome,
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
_T = TypeVar("_T")
_SAFE_PREFLIGHT_ACTIONS = {
    "output_dir_created": ("create_local_path", "file_service"),
    "cache_dir_created": ("create_local_path", "file_service"),
    "drive_oauth_credentials_refreshed": (
        "refresh_available_credentials",
        "drive_service",
    ),
}
_INTENT_MAP = {
    "ingest_new_reports": (
        "report_generation",
        "safe_default",
        ["pdf", "model"],
        "latest_safe",
    ),
    "update_existing_report": (
        "report_generation",
        "safe_default",
        ["pdf", "model"],
        "latest_safe",
    ),
    "acquire_missing_pdf": (
        "report_download",
        "safe_default",
        ["network", "browser", "drive"],
        "",
    ),
    "repair_failed_report": (
        "report_generation",
        "repair_failed",
        ["pdf", "model"],
        "latest_safe",
    ),
    "publish_ready_reports": (
        "publishing",
        "publish_ready",
        ["wordpress", "publish"],
        "",
    ),
    "refresh_publisher_inventory": (
        "publisher_inventory",
        "safe_default",
        ["network", "browser", "drive", "model"],
        "",
    ),
    "audit_acquisition": (
        "browser_acquisition",
        "safe_default",
        ["network", "browser"],
        "",
    ),
    "replay_ui_run": ("ui_replay", "safe_default", ["filesystem"], ""),
}
_AMBIGUOUS_INTENTS = {"run", "process", "start", "continue", "auto"}


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
            set(prompt_namespaces)
            | set(report_pipeline_prompt_namespaces(ingest_settings))
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
    grouped: dict[tuple[str, str, str], list[OperationalObservation]] = defaultdict(
        list
    )
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


def build_preflight_remediation_artifact(
    report: PipelinePreflightReport,
    ctx: RunContext,
) -> PreflightRemediationArtifact:
    actions: list[PreflightRemediationAction] = []
    relevant_checks = [
        *report.auto_fixable_issues,
        *[item for item in report.checks if item.auto_fix_applied],
        *[
            item
            for item in report.checks
            if item.status in {"blocker", "warning"} and not item.auto_fix_applied
        ],
        *report.blockers,
        *report.warnings,
    ]
    seen: set[tuple[str, str]] = set()
    for check in relevant_checks:
        key = (check.check_name, check.code)
        if key in seen:
            continue
        seen.add(key)
        mapped = _SAFE_PREFLIGHT_ACTIONS.get(check.code)
        if mapped is not None and check.auto_fix_applied:
            action_name, boundary = mapped
            action = PreflightRemediationAction(
                schema_version="1.0",
                check_name=check.check_name,
                action=action_name,
                result="already_applied",
                safe_to_auto_apply=True,
                side_effect_boundary=boundary,
                before_status="blocker_or_missing",
                after_status="pass",
                code=check.code,
                message=check.message,
                metadata=dict(check.metadata),
            )
        else:
            action = PreflightRemediationAction(
                schema_version="1.0",
                check_name=check.check_name,
                action="user_action_required",
                result="blocked",
                safe_to_auto_apply=False,
                side_effect_boundary="operator",
                before_status=str(check.status),
                after_status=str(check.status),
                code=check.code,
                message=check.message,
                metadata=dict(check.metadata),
            )
        actions.append(action)
    artifact = PreflightRemediationArtifact(
        schema_version="1.0",
        workflow=report.workflow,
        actions=actions,
        auto_applied_count=sum(
            1 for item in actions if item.result == "already_applied"
        ),
        user_action_required_count=sum(
            1 for item in actions if item.action == "user_action_required"
        ),
        blocked_unsafe_count=sum(1 for item in actions if not item.safe_to_auto_apply),
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="workflow_preflight_remediation_artifact",
            module=logger.name,
            fields={
                "workflow": artifact.workflow,
                "action_count": len(artifact.actions),
                "auto_applied_count": artifact.auto_applied_count,
                "user_action_required_count": artifact.user_action_required_count,
                "blocked_unsafe_count": artifact.blocked_unsafe_count,
                "action_codes": [item.code for item in artifact.actions],
            },
        )
    )
    return artifact


def resolve_run_intent(
    intent: RunIntent,
    settings: WorkflowControlSettings,
    *,
    ctx: RunContext,
) -> ResolvedRunIntent:
    intent_key = _intent_key(intent.intent)
    if intent_key in _AMBIGUOUS_INTENTS:
        resolved = ResolvedRunIntent(
            schema_version="1.0",
            status="ambiguous",
            intent_key=intent_key,
            workflow="",
            preflight_profile="",
            budget_profile="",
            resume_stage="",
            side_effect_plan=[],
            alternatives=sorted(_INTENT_MAP),
            blockers=[],
            explanation="ambiguous_intent",
        )
    elif intent_key not in _INTENT_MAP:
        resolved = ResolvedRunIntent(
            schema_version="1.0",
            status="unsupported",
            intent_key=intent_key,
            workflow="",
            preflight_profile="",
            budget_profile="",
            resume_stage="",
            side_effect_plan=[],
            alternatives=[],
            blockers=["unsupported_intent"],
            explanation="unsupported_intent",
        )
    else:
        workflow_name, budget_profile, side_effects, resume_stage = _INTENT_MAP[
            intent_key
        ]
        blockers: list[str] = []
        if _key(workflow_name) not in settings.preflight_profiles:
            blockers.append("preflight_profile_missing")
        if _key(workflow_name) not in settings.workflow_contracts:
            blockers.append("workflow_contract_missing")
        resolved = ResolvedRunIntent(
            schema_version="1.0",
            status="blocked" if blockers else "resolved",
            intent_key=intent_key,
            workflow=workflow_name if not blockers else "",
            preflight_profile=workflow_name if not blockers else "",
            budget_profile=budget_profile,
            resume_stage=resume_stage,
            side_effect_plan=list(side_effects),
            alternatives=[],
            blockers=blockers,
            explanation="resolved_from_intent_map"
            if not blockers
            else "missing_contract",
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="workflow_run_intent_resolved",
            module=logger.name,
            fields=asdict(resolved),
        )
    )
    return resolved


def evaluate_publish_policy(
    policy_input: PublishPolicyInput,
    *,
    ctx: RunContext,
) -> PublishPolicyDecision:
    confidences = [float(value) for value in policy_input.family_confidence.values()]
    min_confidence = min(confidences) if confidences else 0.0
    if policy_input.override:
        action = "review_required" if not policy_input.automation_enabled else "draft"
        reason = "override_requires_audit"
        override_used = True
        repair_supported = False
    elif policy_input.validation_status != "pass":
        action = "hold"
        reason = "validation_not_passed"
        override_used = False
        repair_supported = False
    elif policy_input.missing_metadata or policy_input.editorial_risk == "high":
        action = "review_required"
        reason = "metadata_or_editorial_risk"
        override_used = False
        repair_supported = False
    elif min_confidence < 0.60:
        action = "repair"
        reason = "low_family_confidence"
        override_used = False
        repair_supported = True
    elif policy_input.warnings:
        action = "draft"
        reason = "warnings_present"
        override_used = False
        repair_supported = False
    elif not policy_input.automation_enabled:
        action = "review_required"
        reason = "automation_disabled"
        override_used = False
        repair_supported = False
    else:
        action = "publish"
        reason = "policy_passed"
        override_used = False
        repair_supported = False
    decision = PublishPolicyDecision(
        schema_version="1.0",
        action=action,
        reason=reason,
        min_confidence=round(min_confidence, 6),
        repair_supported=repair_supported,
        override_used=override_used,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="workflow_publish_policy_decision",
            module=logger.name,
            fields=asdict(decision),
        )
    )
    return decision


def build_operational_memory_from_feedback(
    observations: list[WorkflowControlObservation],
) -> list[OperationalMemoryRecord]:
    return build_operational_memory(
        [
            OperationalObservation(
                schema_version="1.0",
                publisher=item.publisher,
                workflow=item.workflow,
                route=item.route,
                success=item.outcome
                in {"succeeded", "completed", "processed", "published"},
                runtime_seconds=round(max(0, int(item.latency_ms)) / 1000.0, 6),
                cost_usd=float(item.cost_usd),
                failure_signature=item.error_code,
                pdf_extractable=item.outcome not in {"unsupported", "non_report"},
                credential_required=item.outcome == "user_action_required"
                or item.error_code.endswith("credentials_missing"),
            )
            for item in observations
        ]
    )


def evaluate_pre_llm_data_quality(
    gate_input: PreLlmDataQualityInput,
    *,
    ctx: RunContext,
) -> PreLlmDataQualityDecision:
    signals: dict[str, Any] = asdict(gate_input)
    outcome: WorkflowGateOutcome
    if gate_input.duplicate_report or (
        gate_input.already_processed and not gate_input.stale_already_processed
    ):
        outcome, reason, remediation = (
            "skip_duplicate",
            "duplicate_or_already_processed",
            "reuse_existing_artifact",
        )
    elif not gate_input.supported_file_type:
        outcome, reason, remediation = (
            "hold",
            "unsupported_file_type",
            "provide_supported_pdf",
        )
    elif gate_input.known_gated_lead_form:
        outcome, reason, remediation = (
            "user_action_required",
            "known_gated_lead_form",
            "provide_credentials_or_skip",
        )
    elif gate_input.text_char_count < 1000:
        outcome, reason, remediation = (
            "repair",
            "insufficient_text",
            "run_ocr_or_source_repair",
        )
    elif not gate_input.report_like:
        outcome, reason, remediation = ("hold", "non_report_content", "review_source")
    elif not gate_input.publisher_matches:
        outcome, reason, remediation = (
            "hold",
            "publisher_mismatch",
            "review_publisher_mapping",
        )
    elif not gate_input.publication_date_evidence:
        outcome, reason, remediation = (
            "defer",
            "missing_publication_date_evidence",
            "collect_publication_date_evidence",
        )
    elif gate_input.visual_candidate_count <= 0:
        outcome, reason, remediation = (
            "defer",
            "low_value_visual_candidates",
            "run_candidate_extraction_review",
        )
    else:
        outcome, reason, remediation = (
            "proceed",
            "deterministic_gates_passed",
            "continue",
        )
    decision = PreLlmDataQualityDecision(
        schema_version="1.0",
        outcome=cast(WorkflowGateOutcome, outcome),
        expensive_work_allowed=outcome == "proceed",
        reason=reason,
        source_signals=signals,
        remediation=remediation,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="workflow_pre_llm_data_quality_decision",
            module=logger.name,
            fields=asdict(decision),
        )
    )
    return decision


def run_after_pre_llm_gate(
    decision: PreLlmDataQualityDecision,
    operation: Callable[[], _T],
) -> _T | None:
    if decision.expensive_work_allowed:
        return operation()
    if decision.outcome == "user_action_required":
        raise AppError(
            code="pre_llm_quality_gate_blocked",
            message="Pre-LLM quality gate requires user action before expensive work",
            retryable=False,
            severity="warning",
            context={
                "outcome": decision.outcome,
                "reason": decision.reason,
                "remediation": decision.remediation,
            },
        )
    return None


def resolve_all_adaptive_concurrency(
    settings: WorkflowControlSettings,
    observations: dict[str, ConcurrencyObservation],
) -> dict[str, ConcurrencyDecision]:
    decisions: dict[str, ConcurrencyDecision] = {}
    for resource, limit in sorted(settings.concurrency.items()):
        observation = observations.get(resource) or ConcurrencyObservation(
            schema_version="1.0",
            resource=resource,
            current_limit=limit.default_limit,
            retry_rate=0.0,
            p95_latency_ms=limit.low_latency_ms + 1,
            sqlite_lock_count=0,
            browser_failure_rate=0.0,
            budget_burn_rate=0.75,
        )
        decisions[resource] = resolve_adaptive_concurrency(limit, observation)
    return decisions


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
        if (
            _key(transition.from_state) not in states
            or _key(transition.to_state) not in states
        ):
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
            "candidate_screening": policy(
                "publisher_inventory.candidate_screening.v1", 1
            ),
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


def _intent_key(value: object) -> str:
    token = _key(value)
    aliases = {
        "ingest": "ingest_new_reports",
        "ingest_reports": "ingest_new_reports",
        "download_report": "acquire_missing_pdf",
        "download": "acquire_missing_pdf",
        "publish": "publish_ready_reports",
        "publish_wp": "publish_ready_reports",
        "publisher_discovery": "refresh_publisher_inventory",
        "publisher_inventory": "refresh_publisher_inventory",
        "ui_replay": "replay_ui_run",
        "replay": "replay_ui_run",
    }
    return aliases.get(token, token)


def _bounded(value: int, *, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, value))


__all__ = [
    "ConcurrencyDecision",
    "ConcurrencyLimit",
    "ConcurrencyObservation",
    "ModelCallAuditRecord",
    "ModelCallReplayBundle",
    "OperationalMemoryRecommendation",
    "OperationalMemoryRecord",
    "OperationalObservation",
    "PreLlmDataQualityDecision",
    "PreLlmDataQualityInput",
    "PreflightRemediationAction",
    "PreflightRemediationArtifact",
    "PublishPolicyDecision",
    "PublishPolicyInput",
    "ResolvedRetryPolicy",
    "ResolvedRunIntent",
    "RunIntent",
    "WorkflowContract",
    "WorkflowControlSettings",
    "WorkflowControlObservation",
    "WorkflowPreflightProfile",
    "WorkflowRetryPolicyConfig",
    "WorkflowTransition",
    "build_operational_memory_from_feedback",
    "build_operational_memory",
    "build_preflight_remediation_artifact",
    "build_workflow_preflight_request",
    "default_workflow_control_settings",
    "evaluate_pre_llm_data_quality",
    "evaluate_publish_policy",
    "is_valid_transition",
    "recommend_from_operational_memory",
    "resolve_all_adaptive_concurrency",
    "resolve_run_intent",
    "resolve_adaptive_concurrency",
    "resolve_retry_policy",
    "resolve_workflow_contract",
    "run_after_pre_llm_gate",
]
