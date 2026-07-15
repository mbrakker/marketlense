from __future__ import annotations

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    ConcurrencyLimit,
    RemediationReaperSettings,
    WorkflowContract,
    WorkflowControlSettings,
    WorkflowPreflightProfile,
    WorkflowRetryPolicyConfig,
    WorkflowTransition,
)
from src.services._config_service.common import (
    _load_config,
    _resolve_bootstrap_config_path,
    _to_bool,
    _to_float,
    _to_int,
    logger,
)
from src.utils.errors import AppError
from src.utils.logging import log_event


def load_workflow_control_settings(
    request: ConfigLoadRequest,
    ctx: RunContext,
) -> WorkflowControlSettings:
    config_path = _resolve_bootstrap_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_config_load_start",
            module=logger.name,
            fields={"path": str(config_path)},
        )
    )
    data = _load_config(str(config_path))
    raw_control = data.get("workflow_control", {}) or {}
    if not isinstance(raw_control, dict):
        raise AppError(
            code="workflow_control_config_invalid",
            message="workflow_control config must be a mapping",
            retryable=False,
            context={"path": str(config_path)},
        )
    settings = WorkflowControlSettings(
        schema_version=str(raw_control.get("schema_version") or "1.0"),
        preflight_profiles=_parse_preflight_profiles(
            raw_control.get("preflight_profiles")
        ),
        retry_policies=_parse_retry_policies(raw_control.get("retry_policies")),
        workflow_contracts=_parse_workflow_contracts(
            raw_control.get("workflow_contracts")
        ),
        concurrency=_parse_concurrency(raw_control.get("concurrency")),
        operational_memory_ttl_days=max(
            1,
            _to_int(
                _mapping(raw_control.get("operational_memory")).get("ttl_days"),
                30,
            ),
        ),
        operational_memory_min_observations=max(
            1,
            _to_int(
                _mapping(raw_control.get("operational_memory")).get(
                    "min_observations"
                ),
                2,
            ),
        ),
        remediation_reaper=_parse_remediation_reaper(
            raw_control.get("remediation_reaper")
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="workflow_control_config_load_complete",
            module=logger.name,
            fields={
                "path": str(config_path),
                "preflight_profile_count": len(settings.preflight_profiles),
                "retry_workflow_count": len(settings.retry_policies),
                "workflow_contract_count": len(settings.workflow_contracts),
                "concurrency_resource_count": len(settings.concurrency),
            },
        )
    )
    return settings


def _parse_preflight_profiles(raw_profiles: object) -> dict[str, WorkflowPreflightProfile]:
    profiles: dict[str, WorkflowPreflightProfile] = {}
    for name, raw_profile in _mapping(raw_profiles).items():
        profile = _mapping(raw_profile)
        workflow = _key(profile.get("workflow") or name)
        profiles[workflow] = WorkflowPreflightProfile(
            schema_version=str(profile.get("schema_version") or "1.0"),
            workflow=workflow,
            planned_side_effects=_string_list(profile.get("planned_side_effects")),
            require_llm=_to_bool(profile.get("require_llm"), False),
            require_drive=_to_bool(profile.get("require_drive"), False),
            require_publish=_to_bool(profile.get("require_publish"), False),
            require_browser=_to_bool(profile.get("require_browser"), False),
            prompt_namespaces=_string_list(profile.get("prompt_namespaces")),
        )
    return profiles


def _parse_retry_policies(
    raw_policies: object,
) -> dict[str, dict[str, WorkflowRetryPolicyConfig]]:
    policies: dict[str, dict[str, WorkflowRetryPolicyConfig]] = {}
    for workflow_name, raw_steps in _mapping(raw_policies).items():
        step_policies: dict[str, WorkflowRetryPolicyConfig] = {}
        for step_name, raw_policy in _mapping(raw_steps).items():
            policy = _mapping(raw_policy)
            workflow_key = _key(workflow_name)
            step_key = _key(step_name)
            step_policies[step_key] = WorkflowRetryPolicyConfig(
                schema_version=str(policy.get("schema_version") or "1.0"),
                policy_id=str(
                    policy.get("policy_id") or f"{workflow_key}.{step_key}.v1"
                ),
                retries=_policy_int(policy, "retries", 0, workflow_key, step_key),
                base_delay_seconds=_policy_float(
                    policy, "base_delay_seconds", 1.0, workflow_key, step_key
                ),
                backoff_step_seconds=_policy_float(
                    policy, "backoff_step_seconds", 1.0, workflow_key, step_key
                ),
                jitter_seconds=_policy_float(
                    policy, "jitter_seconds", 0.0, workflow_key, step_key
                ),
            )
        policies[_key(workflow_name)] = step_policies
    return policies


def _parse_workflow_contracts(raw_contracts: object) -> dict[str, WorkflowContract]:
    contracts: dict[str, WorkflowContract] = {}
    for workflow_name, raw_contract in _mapping(raw_contracts).items():
        contract = _mapping(raw_contract)
        workflow_key = _key(contract.get("workflow") or workflow_name)
        contracts[workflow_key] = WorkflowContract(
            schema_version=str(contract.get("schema_version") or "1.0"),
            workflow=workflow_key,
            version=str(contract.get("version") or "1.0"),
            states=_string_list(contract.get("states")),
            initial_state=str(contract.get("initial_state") or "pending"),
            transitions=_parse_transitions(contract.get("transitions")),
            prerequisites={
                _key(key): _string_list(value)
                for key, value in _mapping(contract.get("prerequisites")).items()
            },
            checkpoint_outputs=_string_list(contract.get("checkpoint_outputs")),
            validation_gates=_string_list(contract.get("validation_gates")),
            terminal_outcomes=_string_list(contract.get("terminal_outcomes")),
        )
    return contracts


def _parse_transitions(raw_transitions: object) -> list[WorkflowTransition]:
    transitions: list[WorkflowTransition] = []
    for raw_transition in raw_transitions if isinstance(raw_transitions, list) else []:
        transition = _mapping(raw_transition)
        transitions.append(
            WorkflowTransition(
                schema_version=str(transition.get("schema_version") or "1.0"),
                from_state=_key(transition.get("from_state")),
                to_state=_key(transition.get("to_state")),
                step_name=_key(transition.get("step_name")),
                retry_policy_ref=str(transition.get("retry_policy_ref") or ""),
                side_effects=_string_list(transition.get("side_effects")),
            )
        )
    return transitions


def _parse_concurrency(raw_concurrency: object) -> dict[str, ConcurrencyLimit]:
    limits: dict[str, ConcurrencyLimit] = {}
    for resource_name, raw_limit in _mapping(raw_concurrency).items():
        limit = _mapping(raw_limit)
        resource = _key(limit.get("resource") or resource_name)
        min_limit = max(1, _to_int(limit.get("min_limit"), 1))
        max_limit = max(min_limit, _to_int(limit.get("max_limit"), min_limit))
        limits[resource] = ConcurrencyLimit(
            schema_version=str(limit.get("schema_version") or "1.0"),
            resource=resource,
            min_limit=min_limit,
            max_limit=max_limit,
            default_limit=min(
                max_limit,
                max(min_limit, _to_int(limit.get("default_limit"), min_limit)),
            ),
            high_retry_rate=max(0.0, _to_float(limit.get("high_retry_rate"), 0.25)),
            high_latency_ms=max(0, _to_int(limit.get("high_latency_ms"), 5000)),
            low_retry_rate=max(0.0, _to_float(limit.get("low_retry_rate"), 0.05)),
            low_latency_ms=max(0, _to_int(limit.get("low_latency_ms"), 1500)),
        )
    return limits


def _parse_remediation_reaper(raw_reaper: object) -> RemediationReaperSettings:
    reaper = _mapping(raw_reaper)
    return RemediationReaperSettings(
        schema_version=str(reaper.get("schema_version") or "1.0"),
        execution_enabled=_to_bool(reaper.get("execution_enabled"), False),
        max_records_per_run=max(1, _to_int(reaper.get("max_records_per_run"), 10)),
        lease_seconds=max(1, _to_int(reaper.get("lease_seconds"), 60)),
    )


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _policy_int(
    policy: dict,
    name: str,
    default: int,
    workflow: str,
    step: str,
) -> int:
    raw_value = policy.get(name, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise _invalid_policy(name, raw_value, workflow, step) from exc
    if value < 0:
        raise _invalid_policy(name, raw_value, workflow, step)
    return value


def _policy_float(
    policy: dict,
    name: str,
    default: float,
    workflow: str,
    step: str,
) -> float:
    raw_value = policy.get(name, default)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise _invalid_policy(name, raw_value, workflow, step) from exc
    if value < 0.0:
        raise _invalid_policy(name, raw_value, workflow, step)
    return value


def _invalid_policy(name: str, value: object, workflow: str, step: str) -> AppError:
    return AppError(
        code="workflow_retry_policy_invalid",
        message="Workflow retry policy values must be non-negative numbers",
        retryable=False,
        context={
            "workflow": workflow,
            "step": step,
            "field": name,
            "value": str(value),
        },
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _key(value: object) -> str:
    return " ".join(str(value or "").strip().split()).lower().replace("-", "_").replace(
        " ", "_"
    )


__all__ = ["load_workflow_control_settings"]
