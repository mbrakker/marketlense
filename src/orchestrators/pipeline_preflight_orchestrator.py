from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, NoReturn, Protocol, cast
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserExecutableAvailabilityRequest,
    BrowserExecutableAvailabilityResponse,
    BrowserRuntimeAvailabilityResponse,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.drive import (
    DriveFolderCapabilityPreflightRequest,
    DriveWritePreflightRequest,
)
from src.contracts.files import (
    DeleteFileResponse,
    DeleteFileRequest,
    ExecutableAvailabilityResponse,
    ExecutableAvailabilityRequest,
    FileStatRequest,
    FileStatResponse,
    FileSystemUsageRequest,
    FileSystemUsageResponse,
    RepositoryRevisionReadRequest,
    WriteBytesResponse,
    WriteBytesRequest,
)
from src.contracts.pipeline_preflight import (
    CapabilityProfileName,
    CapabilityStatus,
    CapabilityPreflightCheck,
    CapabilityPreflightReport,
    CapabilityPreflightRequest,
    CapabilityExecutionReadiness,
    CapabilityReadinessProof,
    CapabilityWorkflowDecision,
    PipelinePreflightCheck,
    PipelinePreflightReport,
    PipelinePreflightRequest,
    PreflightCheckStatus,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.llm import (
    OpenAIModelPreflightRequest,
    OpenRouterModelPreflightRequest,
    OpenAIVectorStorePreflightRequest,
)
from src.contracts.mailbox_acquisition import (
    MailboxAccessPreflightResponse,
    MailboxAcquisitionSettings,
)
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId
from src.contracts.sqlite_migration import (
    SqliteCapabilityInspectionRequest,
    SqliteCapabilityInspectionResponse,
)
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.contracts.wordpress import WordPressPublishCapabilityRequirements
from src.orchestrators.workflow_queue_capabilities import (
    canonical_workflow_queue_capability_registration,
    capabilities_from_external_effects,
    preflight_profile_for_queue,
)
from src.services import (
    browser_report_download_service,
    drive_service,
    file_service,
    llm_service,
    mailbox_acquisition_service,
    prompt_service,
    sqlite_migration_service,
    wordpress_service,
)
from src.services.config_service import (
    load_browser_download_settings,
    load_mailbox_acquisition_settings,
    load_publish_settings,
    load_publisher_inventory_settings,
    load_settings,
    load_workflow_control_settings,
    load_workflow_queue_policies,
)
from src.utils.errors import AppError
from src.utils.cache_utils import sha256_json
from src.utils.clock import utc_now_iso
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    execution_policy_matrix,
    preflight_execution_policy_coverage,
)

logger = logging.getLogger("market_lense.pipeline_preflight_orchestrator")


_SECRET_IDENTITY_KEYS = frozenset(
    {
        "api_key",
        "app_password",
        "authorization",
        "bearer_token",
        "client_secret",
        "credential",
        "password",
        "secret",
        "token",
    }
)


def _python_runtime_supported(version: tuple[int, ...], executable: str) -> bool:
    return bool(str(executable or "").strip()) and version[:2] >= (3, 12)


@dataclass(frozen=True)
class CapabilityWorkflowRequirements:
    """Resolved capability inputs for one registered workflow queue."""

    workflow: str
    preflight_profile: str | None
    expected_external_effects: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    job_type: str


def derive_queue_capability_requirements(
    queue_name: str,
    policy: WorkflowQueuePolicy,
    registration: object | None,
    workflow_control: object,
) -> CapabilityWorkflowRequirements:
    """Derive a queue's capability families from its canonical registration."""

    normalized_queue = str(queue_name or "").strip()
    if normalized_queue not in WORKFLOW_QUEUE_NAMES:
        raise AppError(
            code="workflow_queue_unregistered",
            message="Enabled workflow queue is not in the canonical queue contract",
            retryable=False,
            context={"queue_name": normalized_queue},
        )
    if (
        registration is None
        or str(getattr(registration, "queue_name", "")) != normalized_queue
    ):
        raise AppError(
            code="workflow_queue_capability_mapping_missing",
            message="Enabled workflow queue has no registered capability mapping",
            retryable=False,
            context={"queue_name": normalized_queue},
        )
    if str(getattr(policy, "queue_name", "")) != normalized_queue:
        raise AppError(
            code="workflow_queue_policy_mismatch",
            message="Workflow queue policy does not match its canonical queue",
            retryable=False,
            context={"queue_name": normalized_queue},
        )
    effects = tuple(
        sorted(
            {
                str(effect).strip()
                for effect in getattr(registration, "expected_external_effects", ())
                if str(effect).strip()
            }
        )
    )
    derived = capabilities_from_external_effects(effects)
    declared = tuple(
        sorted(
            {
                str(capability).strip()
                for capability in getattr(registration, "required_capabilities", ())
                if str(capability).strip()
            }
        )
    )
    profile_name = preflight_profile_for_queue(normalized_queue)
    profile = getattr(workflow_control, "preflight_profiles", {}).get(profile_name)
    if profile_name and profile is not None:
        if bool(getattr(profile, "require_llm", False)):
            declared = tuple(sorted(set(declared) | {"llm_model"}))
        if bool(getattr(profile, "require_drive", False)):
            declared = tuple(sorted(set(declared) | {"google_drive"}))
        if bool(getattr(profile, "require_browser", False)):
            declared = tuple(sorted(set(declared) | {"browser"}))
        if bool(getattr(profile, "require_publish", False)):
            declared = tuple(sorted(set(declared) | {"wordpress"}))
    return CapabilityWorkflowRequirements(
        workflow=normalized_queue,
        preflight_profile=profile_name,
        expected_external_effects=effects,
        required_capabilities=tuple(sorted(set(derived) | set(declared))),
        job_type=str(getattr(registration, "job_type", "") or ""),
    )


def validate_capability_registry_coverage(
    queue_policies: Mapping[str, WorkflowQueuePolicy],
    workflow_control: object,
) -> dict[str, CapabilityWorkflowRequirements]:
    """Resolve every enabled canonical queue or return no partial coverage."""

    resolved: dict[str, CapabilityWorkflowRequirements] = {}
    failures: list[str] = []
    for queue_name in sorted(
        name
        for name, policy in queue_policies.items()
        if bool(getattr(policy, "enabled", False))
    ):
        policy = queue_policies[queue_name]
        registration = canonical_workflow_queue_capability_registration(queue_name)
        try:
            resolved[queue_name] = derive_queue_capability_requirements(
                queue_name, policy, registration, workflow_control
            )
        except (AppError, ValueError):
            failures.append(queue_name)
    if failures:
        raise AppError(
            code="workflow_queue_capability_mapping_missing",
            message="One or more enabled workflow queues lack capability coverage",
            retryable=False,
            context={"queue_names": sorted(failures)},
        )
    return resolved


def derive_capability_workflows(
    *,
    profile_name: str,
    supervisor_enabled: bool,
    queue_policies: Mapping[str, WorkflowQueuePolicy],
) -> tuple[str, ...]:
    """Select only the manual workflow or queues actually enabled for autonomy."""

    if profile_name == "manual":
        return ("report_generation",)
    if profile_name != "autonomous_mvp":
        raise ValueError("Unsupported capability preflight profile")
    if not supervisor_enabled:
        return ()
    return tuple(
        sorted(
            queue_name
            for queue_name, policy in queue_policies.items()
            if bool(getattr(policy, "enabled", False))
        )
    )


def build_capability_preflight_request(
    *,
    profile: CapabilityProfileName,
    ctx: RunContext,
    live: bool,
    queue_scope: tuple[str, ...] | None = None,
    workflow_scope: tuple[str, ...] | None = None,
    use_process_profile: bool = False,
    load_settings_fn: Callable = load_settings,
    load_workflow_control_settings_fn: Callable = load_workflow_control_settings,
    load_workflow_queue_policies_fn: Callable = load_workflow_queue_policies,
    load_browser_download_settings_fn: Callable = load_browser_download_settings,
    load_mailbox_acquisition_settings_fn: Callable = load_mailbox_acquisition_settings,
    load_publish_settings_fn: Callable = load_publish_settings,
    load_publisher_inventory_settings_fn: Callable = load_publisher_inventory_settings,
) -> CapabilityPreflightRequest:
    """Resolve one effective config/profile and build a shared preflight request."""

    config_request = ConfigLoadRequest(
        schema_version="1.0",
        path="",
        profile_name=(
            None
            if use_process_profile
            else ("autonomous_mvp" if profile == "autonomous_mvp" else "")
        ),
    )
    settings = load_settings_fn(config_request, ctx)
    workflow_control = load_workflow_control_settings_fn(config_request, ctx)
    queue_policies = load_workflow_queue_policies_fn(config_request, ctx)
    if queue_scope is not None:
        scope = set(queue_scope)
        queue_policies = {
            name: replace(policy, enabled=policy.enabled and name in scope)
            for name, policy in queue_policies.items()
        }
    workflows = tuple(
        sorted(
            {
                str(workflow).strip()
                for workflow in (workflow_scope or ())
                if str(workflow).strip()
            }
        )
    ) or derive_capability_workflows(
        profile_name=profile,
        supervisor_enabled=workflow_control.supervisor.enabled,
        queue_policies=queue_policies,
    )
    runtime_profiles = workflow_profiles_for_runtime(workflows)
    runtime_profiles = tuple(
        sorted(
            set(runtime_profiles)
            | {
                workflow
                for workflow in workflows
                if workflow in workflow_control.preflight_profiles
            }
        )
    )
    workflow_profiles = [
        workflow_control.preflight_profiles[name]
        for name in runtime_profiles
        if name in workflow_control.preflight_profiles
    ]
    browser_settings = None
    browser_settings_config_error = None
    if any(item.require_browser for item in workflow_profiles):
        try:
            browser_settings = load_browser_download_settings_fn(config_request, ctx)
        except AppError as exc:
            browser_settings_config_error = exc.code
        except Exception:
            browser_settings_config_error = "browser_configuration_invalid"

    mailbox_settings = None
    mailbox_settings_config_error = None
    if "mailbox_delivery" in workflows:
        try:
            mailbox_settings = load_mailbox_acquisition_settings_fn(config_request, ctx)
        except AppError as exc:
            mailbox_settings_config_error = exc.code
        except Exception:
            mailbox_settings_config_error = "mailbox_configuration_invalid"

    publish_settings = None
    publish_settings_config_error = None
    if any(item.require_publish for item in workflow_profiles):
        try:
            publish_settings = load_publish_settings_fn(config_request, ctx)
        except AppError as exc:
            publish_settings_config_error = exc.code
        except Exception:
            publish_settings_config_error = "publish_configuration_invalid"

    publisher_inventory_settings = None
    publisher_inventory_config_error = None
    if "publisher_discovery" in workflows:
        try:
            publisher_inventory_settings = load_publisher_inventory_settings_fn(
                config_request, ctx
            )
        except AppError as exc:
            publisher_inventory_config_error = exc.code
        except Exception:
            publisher_inventory_config_error = (
                "publisher_inventory_configuration_invalid"
            )

    return CapabilityPreflightRequest(
        schema_version="1.0",
        profile_name=profile,
        settings=settings,
        workflow_control=workflow_control,
        queue_policies=queue_policies,
        workflow_scope=tuple(workflow_scope or ()),
        publish_settings=publish_settings,
        publish_settings_config_error=publish_settings_config_error,
        mailbox_settings=mailbox_settings,
        mailbox_settings_config_error=mailbox_settings_config_error,
        browser_settings=browser_settings,
        browser_settings_config_error=browser_settings_config_error,
        publisher_inventory_settings=publisher_inventory_settings,
        publisher_inventory_config_error=publisher_inventory_config_error,
        live_checks=live,
    )


def _redacted_identity_value(value: object, *, key: str = "") -> object:
    """Normalize identity material without retaining secret values.

    Credential fields retain only a one-way identity hash so rotating a provider
    credential invalidates an old proof without persisting credential contents.
    """

    normalized_key = str(key or "").strip().lower()
    if any(token in normalized_key for token in _SECRET_IDENTITY_KEYS):
        if value in (None, "", [], {}, ()):
            return "<absent>"
        return f"redacted_sha256:{sha256_json(str(value))}"
    if isinstance(value, dict):
        return {
            str(item_key): _redacted_identity_value(item_value, key=str(item_key))
            for item_key, item_value in sorted(
                value.items(), key=lambda item: str(item[0])
            )
        }
    if isinstance(value, (list, tuple)):
        return [_redacted_identity_value(item, key=normalized_key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _proof_timestamp(value: str, *, fallback_now: str) -> str:
    token = str(value or "").strip()
    return token or fallback_now


def _proof_expiry(generated_at_utc: str, ttl_seconds: int) -> str:
    try:
        current = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    except ValueError:
        current = datetime.now(timezone.utc)
    return (
        (current + timedelta(seconds=max(1, int(ttl_seconds or 900))))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _proof_identity_hash(
    check_identity: list[dict[str, object]],
    *,
    family: str,
) -> str:
    """Hash only the normalized evidence relevant to one proof identity family."""

    dependency_capabilities = {
        "core_dependencies",
        "pdf_dependencies",
        "python_dependencies",
        "python_runtime",
        "openai_dependencies",
        "google_dependencies",
        "wordpress_dependencies",
        "browser_dependencies",
    }
    provider_capabilities = {
        "browser",
        "google_drive",
        "llm_model",
        "mailbox",
        "openai_embedding_model",
        "ocr_model",
        "openrouter_model",
        "vector_store",
        "wordpress",
    }
    sqlite_capabilities = {
        "llm_usage_db",
        "reports_db",
        "signal_store_db",
        "state_db",
    }
    tool_capabilities = {
        "browser_dependencies",
        "free_space",
        "ocr_executable",
        "writable_storage",
    }

    def belongs(capability: str) -> bool:
        if family == "dependency":
            return capability in dependency_capabilities or capability.endswith(
                "_dependencies"
            )
        if family == "asset":
            return capability.startswith("asset_") or capability == "prompt_assets"
        if family == "sqlite":
            return capability in sqlite_capabilities or capability.endswith("_db")
        if family == "provider":
            return capability in provider_capabilities
        if family == "tool":
            return capability in tool_capabilities
        raise ValueError(f"Unsupported proof identity family: {family}")

    def workflow_key(item: dict[str, object]) -> tuple[str, ...]:
        raw_workflows = item.get("workflows", ())
        if not isinstance(raw_workflows, (list, tuple)):
            return ()
        return tuple(str(workflow) for workflow in raw_workflows)

    selected = sorted(
        (item for item in check_identity if belongs(str(item.get("capability", "")))),
        key=lambda item: (
            str(item.get("capability", "")),
            workflow_key(item),
            str(item.get("status", "")),
            str(item.get("reason_code", "")),
            bool(item.get("required", False)),
        ),
    )
    return sha256_json(selected)


def _current_build_identity(ctx: RunContext | None) -> str:
    configured = str(getattr(ctx, "producer_commit_sha", "") or "").strip().lower()
    if configured:
        return configured
    try:
        revision = file_service.read_repository_revision(
            RepositoryRevisionReadRequest(schema_version="1.0"),
            ctx
            or RunContext(
                schema_version="1.0",
                run_id=RunId("preflight-build-identity"),
                task_id=TaskId("preflight-build-identity"),
                span_id="preflight-build-identity",
            ),
        )
    except Exception:
        return "unknown"
    return str(getattr(revision, "commit_sha", "") or "unknown")


def build_execution_readiness(
    report: CapabilityPreflightReport,
    request: CapabilityPreflightRequest | None = None,
    ctx: RunContext | None = None,
    *,
    generated_at_utc: str = "",
    expires_at_utc: str = "",
    proof_reference: str = "",
) -> CapabilityExecutionReadiness:
    """Derive the fail-closed execution decision from one capability report.

    Diagnostic summaries intentionally remain separate from execution policy:
    a degraded or skipped required check is retained as-is and is not silently
    promoted to runnable.
    """

    workflow_scope = sorted(
        {
            str(workflow).strip()
            for workflow in report.workflow_names
            if str(workflow).strip()
        }
    )
    allow_degraded = {
        str(workflow).strip()
        for workflow in getattr(request, "allow_degraded_workflows", ())
        if str(workflow).strip()
    }
    decisions: list[CapabilityWorkflowDecision] = []
    blocked: dict[str, list[str]] = {}
    deferred: dict[str, list[str]] = {}
    for workflow in workflow_scope:
        relevant = [
            check
            for check in report.checks
            if check.required
            and (not check.affected_workflows or workflow in check.affected_workflows)
        ]
        statuses = {check.status for check in relevant}
        if "blocked" in statuses:
            status: CapabilityStatus = "blocked"
        elif "not_checked" in statuses:
            status = "not_checked"
        elif "degraded" in statuses:
            status = "degraded"
        elif relevant and all(check.status == "not_required" for check in relevant):
            status = "not_required"
        else:
            status = cast(
                CapabilityStatus, report.workflow_statuses.get(workflow, "ready")
            )
        reason_codes = sorted(
            {
                str(check.reason_code).strip()
                for check in relevant
                if str(check.reason_code).strip()
                and check.status not in {"ready", "not_required"}
            }
        )
        remediations = sorted(
            {
                str(check.remediation).strip()
                for check in relevant
                if str(check.remediation).strip()
                and check.status not in {"ready", "not_required"}
            }
        )
        executable = status == "ready" or (
            status == "degraded" and workflow in allow_degraded
        )
        decision = CapabilityWorkflowDecision(
            schema_version="2.0",
            workflow=workflow,
            status=status,
            executable=executable,
            reason_codes=reason_codes,
            remediations=remediations,
            required_capabilities=sorted(
                {str(check.capability) for check in relevant if check.required}
            ),
        )
        decisions.append(decision)
        if not executable:
            reasons = reason_codes or [f"workflow_{status}"]
            if status in {"blocked", "not_checked"}:
                blocked[workflow] = reasons
            else:
                deferred[workflow] = reasons

    settings_identity = _redacted_identity_value(
        asdict(request.settings) if request is not None else {}
    )
    configuration_fingerprint = sha256_json(
        {"profile": report.profile_name, "settings": settings_identity}
    )
    execution_policy_fingerprint = sha256_json(
        {
            "queue_policies": _redacted_identity_value(
                {
                    name: asdict(policy)
                    for name, policy in sorted(
                        (request.queue_policies.items() if request is not None else []),
                        key=lambda item: item[0],
                    )
                }
            ),
            "workflow_control": _redacted_identity_value(
                asdict(request.workflow_control) if request is not None else {}
            ),
            "allow_degraded_workflows": sorted(allow_degraded),
        }
    )
    check_identity = [
        {
            "capability": check.capability,
            "workflows": sorted(check.affected_workflows),
            "status": check.status,
            "reason_code": check.reason_code,
            "required": check.required,
        }
        for check in report.checks
    ]
    check_identity.sort(
        key=lambda item: (
            str(item["capability"]),
            tuple(str(workflow) for workflow in item["workflows"])
            if isinstance(item["workflows"], (list, tuple))
            else (),
            str(item["status"]),
            str(item["reason_code"]),
            bool(item["required"]),
        )
    )
    check_hash = sha256_json(check_identity)
    identity_hashes = {
        family: _proof_identity_hash(check_identity, family=family)
        for family in ("dependency", "asset", "sqlite", "provider", "tool")
    }
    generated = _proof_timestamp(generated_at_utc, fallback_now=utc_now_iso())
    expires = str(expires_at_utc or "").strip() or _proof_expiry(
        generated, getattr(request, "proof_ttl_seconds", 900)
    )
    verification_mode = (
        "live" if bool(getattr(request, "live_checks", False)) else "offline"
    )
    reason_codes = sorted(
        {code for decision in decisions for code in decision.reason_codes}
    )
    remediation = sorted(
        {item for decision in decisions for item in decision.remediations}
    )
    proof_material = {
        "schema_version": "2.0",
        "profile_name": report.profile_name,
        "workflow_scope": workflow_scope,
        "configuration_fingerprint": configuration_fingerprint,
        "execution_policy_fingerprint": execution_policy_fingerprint,
        "build_identity": _current_build_identity(ctx),
        "check_identity": check_hash,
        "identity_hashes": identity_hashes,
        "verification_mode": verification_mode,
        "decisions": [asdict(decision) for decision in decisions],
    }
    proof_id = sha256_json(proof_material)
    proof = CapabilityReadinessProof(
        schema_version="2.0",
        proof_id=proof_id,
        profile_name=report.profile_name,
        workflow_scope=workflow_scope,
        configuration_fingerprint=configuration_fingerprint,
        execution_policy_fingerprint=execution_policy_fingerprint,
        build_identity=str(proof_material["build_identity"]),
        dependency_identity=identity_hashes["dependency"],
        asset_identity=identity_hashes["asset"],
        sqlite_identity=identity_hashes["sqlite"],
        provider_identity=identity_hashes["provider"],
        tool_identity=identity_hashes["tool"],
        generated_at_utc=generated,
        expires_at_utc=expires,
        verification_mode=verification_mode,
        reason_codes=reason_codes,
        remediation=remediation,
        artifact_reference=str(proof_reference or ""),
        valid=True,
    )
    return CapabilityExecutionReadiness(
        schema_version="2.0",
        profile_name=report.profile_name,
        workflow_scope=workflow_scope,
        executable_workflows=[
            decision.workflow for decision in decisions if decision.executable
        ],
        blocked_workflows=blocked,
        deferred_workflows=deferred,
        decisions=decisions,
        proof=proof,
    )


def validate_execution_readiness(
    readiness: CapabilityExecutionReadiness,
    *,
    expected_workflow: str,
    expected_profile_name: str = "",
    expected_workflow_scope: tuple[str, ...] | list[str] = (),
    expected_configuration_fingerprint: str = "",
    expected_execution_policy_fingerprint: str = "",
    now_utc: str = "",
) -> None:
    """Reject missing, expired, mismatched, or non-executable proof material."""

    def reject_incomplete(detail: str) -> NoReturn:
        raise AppError(
            code="capability_readiness_incomplete",
            message="Capability readiness proof is incomplete",
            retryable=False,
            context={"detail": detail},
        )

    proof = getattr(readiness, "proof", None)
    if proof is None:
        reject_incomplete("proof_missing")
    if getattr(readiness, "schema_version", "") != "2.0":
        reject_incomplete("readiness_schema_unsupported")
    if getattr(proof, "schema_version", "") != "2.0":
        reject_incomplete("proof_schema_unsupported")

    scope = [str(item).strip() for item in getattr(readiness, "workflow_scope", [])]
    normalized_scope = sorted({item for item in scope if item})
    if scope != normalized_scope:
        reject_incomplete("workflow_scope_not_normalized")
    proof_scope = [str(item).strip() for item in getattr(proof, "workflow_scope", [])]
    if proof_scope != normalized_scope or proof_scope != scope:
        reject_incomplete("proof_scope_mismatch")
    if str(getattr(proof, "profile_name", "")) != str(
        getattr(readiness, "profile_name", "")
    ):
        reject_incomplete("proof_profile_missing_or_mismatched")

    decisions = list(getattr(readiness, "decisions", []))
    decision_workflows = [str(item.workflow).strip() for item in decisions]
    if decision_workflows != scope or len(set(decision_workflows)) != len(
        decision_workflows
    ):
        reject_incomplete("workflow_decisions_incomplete")
    allowed_statuses = {"ready", "degraded", "blocked", "not_required", "not_checked"}
    for decision in decisions:
        if decision.status not in allowed_statuses:
            reject_incomplete("workflow_decision_status_invalid")
        if decision.executable and decision.status not in {"ready", "degraded"}:
            reject_incomplete("blocked_workflow_marked_executable")
        if decision.required_capabilities != sorted(
            set(
                str(item).strip()
                for item in decision.required_capabilities
                if str(item).strip()
            )
        ):
            reject_incomplete("required_capabilities_not_normalized")

    executable = [
        str(item).strip() for item in getattr(readiness, "executable_workflows", [])
    ]
    expected_executable = [item.workflow for item in decisions if item.executable]
    if executable != sorted(set(executable)) or executable != expected_executable:
        reject_incomplete("executable_workflows_mismatch")
    blocked = set(getattr(readiness, "blocked_workflows", {}))
    deferred = set(getattr(readiness, "deferred_workflows", {}))
    if blocked & deferred or not (blocked | deferred | set(executable)).issubset(
        set(scope)
    ):
        reject_incomplete("workflow_outcome_partition_invalid")

    def is_sha256(value: object) -> bool:
        token = str(value or "")
        return len(token) == 64 and all(
            character in "0123456789abcdef" for character in token
        )

    for identity_field in (
        "proof_id",
        "configuration_fingerprint",
        "execution_policy_fingerprint",
        "dependency_identity",
        "asset_identity",
        "sqlite_identity",
        "provider_identity",
        "tool_identity",
    ):
        if not is_sha256(getattr(proof, identity_field, "")):
            reject_incomplete(f"{identity_field}_missing_or_invalid")
    if (
        not str(getattr(proof, "build_identity", "")).strip()
        or str(getattr(proof, "build_identity", "")).strip().lower() == "unknown"
    ):
        reject_incomplete("build_identity_missing")
    if getattr(proof, "verification_mode", "") not in {"offline", "live"}:
        reject_incomplete("verification_mode_invalid")
    try:
        generated_at = datetime.fromisoformat(
            str(proof.generated_at_utc).replace("Z", "+00:00")
        )
        expiry_at = datetime.fromisoformat(
            str(proof.expires_at_utc).replace("Z", "+00:00")
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise AppError(
            code="capability_readiness_expiry_invalid",
            message="Capability readiness proof timestamps are invalid",
            retryable=False,
            cause=exc,
        ) from exc
    if expiry_at <= generated_at:
        reject_incomplete("proof_expiry_not_after_generation")

    workflow = str(expected_workflow or "").strip()
    if not proof.valid:
        raise AppError(
            code="capability_readiness_invalid",
            message="Capability readiness proof is invalid",
            retryable=False,
        )
    if expected_profile_name and readiness.profile_name != expected_profile_name:
        raise AppError(
            code="capability_readiness_profile_mismatch",
            message="Capability readiness profile does not match execution",
            retryable=False,
        )
    expected_scope = sorted(
        {str(item).strip() for item in expected_workflow_scope if str(item).strip()}
    )
    if expected_scope and readiness.workflow_scope != expected_scope:
        raise AppError(
            code="capability_readiness_scope_mismatch",
            message="Capability readiness workflow scope does not match execution",
            retryable=False,
        )
    if expected_configuration_fingerprint and (
        proof.configuration_fingerprint != expected_configuration_fingerprint
    ):
        raise AppError(
            code="capability_readiness_configuration_mismatch",
            message="Capability readiness configuration identity is stale",
            retryable=False,
        )
    if expected_execution_policy_fingerprint and (
        proof.execution_policy_fingerprint != expected_execution_policy_fingerprint
    ):
        raise AppError(
            code="capability_readiness_policy_mismatch",
            message="Capability readiness execution-policy identity is stale",
            retryable=False,
        )
    if workflow and workflow not in readiness.workflow_scope:
        raise AppError(
            code="capability_readiness_workflow_unscoped",
            message="Workflow is not included in the capability readiness scope",
            retryable=False,
        )
    try:
        current = datetime.fromisoformat(
            (_proof_timestamp(now_utc, fallback_now=utc_now_iso())).replace(
                "Z", "+00:00"
            )
        )
        expiry = datetime.fromisoformat(proof.expires_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(
            code="capability_readiness_expiry_invalid",
            message="Capability readiness proof expiry is invalid",
            retryable=False,
            cause=exc,
        ) from exc
    if expiry <= current:
        raise AppError(
            code="capability_readiness_expired",
            message="Capability readiness proof has expired",
            retryable=False,
        )
    if workflow and not readiness.is_workflow_executable(workflow):
        raise AppError(
            code="capability_readiness_workflow_blocked",
            message="Required capability readiness is not executable for this workflow",
            retryable=False,
            severity="warning",
            context={
                "workflow": workflow,
                "reason_codes": readiness.blocked_workflows.get(workflow)
                or readiness.deferred_workflows.get(workflow)
                or [],
            },
        )


def retain_capability_proof(
    readiness: CapabilityExecutionReadiness,
    request: CapabilityPreflightRequest,
    ctx: RunContext,
    deps: CapabilityPreflightDependencies,
    *,
    report: CapabilityPreflightReport | None = None,
) -> CapabilityExecutionReadiness:
    """Retain one redacted proof/report through the canonical file service."""

    output_dir = str(getattr(request.settings, "output_dir", "") or "").strip()
    if not output_dir:
        raise AppError(
            code="capability_proof_path_missing",
            message="Capability proof output path is not configured",
            retryable=False,
        )
    proof_path = (
        Path(output_dir)
        / "preflight"
        / f"capability-{readiness.proof.proof_id[:32]}-{uuid.uuid4().hex[:8]}.json"
    )
    proof = replace(readiness.proof, artifact_reference=str(proof_path))
    retained = replace(readiness, proof=proof)
    artifact_value: object = (
        asdict(replace(report, execution_readiness=retained))
        if report is not None
        else asdict(retained)
    )
    payload = json.dumps(
        artifact_value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    try:
        deps.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(proof_path),
                content=payload,
                make_parents=True,
            ),
            ctx,
        )
    except AppError as exc:
        raise AppError(
            code="capability_proof_persist_failed",
            message="Redacted capability proof could not be retained",
            cause=exc,
            retryable=False,
            context={"path": str(proof_path)},
        ) from exc
    return retained


_REPORTS_DB_WORKFLOWS = frozenset(
    {
        "publisher_discovery",
        "report_acquisition",
        "source_ingest",
        "report_selection",
        "report_analysis",
        "report_render",
        "analytics_projection",
        "claim_embedding",
        "signal_candidate",
        "signal_generation",
        "briefing_opportunity",
        "briefing_generation",
        "cover_generation",
        "publication_readiness",
        "wordpress_publish",
        "wordpress_projection",
        "artifact_repair",
        "source_revalidation",
        "malformed_pdf_revalidation",
        "recategorization",
        "vector_retention",
        "wordpress_category_update",
        "public_render_repair",
    }
)
_SIGNAL_STORE_WORKFLOWS = frozenset({"signal_candidate", "signal_generation"})
_REPORT_ARTIFACT_WORKFLOWS = frozenset(
    {
        "report_generation",
        "publisher_discovery",
        "report_acquisition",
        "source_ingest",
        "report_selection",
        "report_analysis",
        "report_render",
        "signal_generation",
        "briefing_generation",
        "cover_generation",
        "wordpress_publish",
        "artifact_repair",
        "source_revalidation",
        "malformed_pdf_revalidation",
        "public_render_repair",
    }
)
_PDF_WORKFLOWS = frozenset(
    {
        "report_generation",
        "report_acquisition",
        "source_ingest",
        "report_selection",
        "malformed_pdf_revalidation",
    }
)
_OCR_WORKFLOWS = frozenset(
    {
        "report_generation",
        "source_ingest",
        "report_selection",
        "malformed_pdf_revalidation",
    }
)
_CATEGORY_MAPPING_WORKFLOWS = frozenset(
    {
        "report_generation",
        "source_ingest",
        "report_selection",
        "report_analysis",
        "report_render",
        "recategorization",
        "wordpress_publish",
        "wordpress_category_update",
    }
)
_CLAIM_EMBEDDING_MODEL = "text-embedding-3-large"


@dataclass(frozen=True)
class CapabilityPreflightDependencies:
    inspect_sqlite: Callable[
        [SqliteCapabilityInspectionRequest, RunContext],
        SqliteCapabilityInspectionResponse,
    ]
    file_stat: Callable[[FileStatRequest, RunContext], FileStatResponse]
    write_bytes: Callable[[WriteBytesRequest, RunContext], WriteBytesResponse]
    delete_file: Callable[[DeleteFileRequest, RunContext], DeleteFileResponse]
    inspect_executable: Callable[
        [ExecutableAvailabilityRequest, RunContext], ExecutableAvailabilityResponse
    ]
    preflight_browser_executable: Callable[
        [BrowserExecutableAvailabilityRequest, RunContext],
        BrowserExecutableAvailabilityResponse,
    ]
    preflight_browser_runtime: Callable[
        [RunContext], BrowserRuntimeAvailabilityResponse
    ]
    load_prompt_set: _Callable2
    preflight_openai_model: Callable[[OpenAIModelPreflightRequest, RunContext], object]
    preflight_openrouter_model: Callable[
        [OpenRouterModelPreflightRequest, RunContext], object
    ]
    preflight_drive_folder_access: _Callable2
    preflight_mailbox_access: Callable[
        [MailboxAcquisitionSettings, RunContext], MailboxAccessPreflightResponse
    ]
    preflight_wordpress_publish_target: Callable[
        [PublishSettings, RunContext, WordPressPublishCapabilityRequirements], object
    ]
    inspect_filesystem_usage: (
        Callable[[FileSystemUsageRequest, RunContext], FileSystemUsageResponse] | None
    ) = None
    preflight_vector_store: (
        Callable[[OpenAIVectorStorePreflightRequest, RunContext], object] | None
    ) = None
    write_exclusive_bytes: _Callable2 | None = None


def default_capability_preflight_dependencies() -> CapabilityPreflightDependencies:
    return CapabilityPreflightDependencies(
        inspect_sqlite=sqlite_migration_service.inspect_sqlite_capability,
        file_stat=file_service.file_stat,
        write_bytes=file_service.write_bytes,
        delete_file=file_service.delete_file,
        inspect_executable=file_service.inspect_executable,
        preflight_browser_executable=(
            browser_report_download_service.preflight_browser_executable
        ),
        preflight_browser_runtime=(
            browser_report_download_service.preflight_browser_runtime
        ),
        load_prompt_set=prompt_service.load_prompt_set,
        preflight_openai_model=llm_service.preflight_openai_model,
        preflight_openrouter_model=llm_service.preflight_openrouter_model,
        preflight_drive_folder_access=drive_service.preflight_drive_folder_access,
        preflight_mailbox_access=mailbox_acquisition_service.preflight_mailbox_access,
        preflight_wordpress_publish_target=(
            lambda settings, ctx, requirements: (
                wordpress_service.preflight_publish_capability(
                    settings, ctx, requirements
                )
            )
        ),
        inspect_filesystem_usage=file_service.inspect_filesystem_usage,
        preflight_vector_store=llm_service.preflight_openai_vector_store,
        write_exclusive_bytes=lambda request, ctx: file_service.write_bytes(
            request, ctx, require_absent=True
        ),
    )


def run_capability_preflight(
    request: CapabilityPreflightRequest,
    ctx: RunContext,
    *,
    dependencies: CapabilityPreflightDependencies | None = None,
) -> CapabilityPreflightReport:
    """Produce a profile-derived readiness proof without workflow side effects."""

    started = time.perf_counter()
    deps = dependencies or default_capability_preflight_dependencies()
    workflows = tuple(
        sorted(
            {
                str(workflow).strip()
                for workflow in request.workflow_scope
                if str(workflow).strip()
            }
        )
    ) or derive_capability_workflows(
        profile_name=request.profile_name,
        supervisor_enabled=request.workflow_control.supervisor.enabled,
        queue_policies=request.queue_policies,
    )
    ocr_workflows: tuple[str, ...] = ()
    checks: list[CapabilityPreflightCheck] = []
    provider_calls = 0
    profiles: dict[str, object] = {}
    workflow_profiles: dict[str, str] = {}
    queue_requirements: dict[str, CapabilityWorkflowRequirements] = {}
    if workflows and (
        request.profile_name == "autonomous_mvp"
        or any(
            canonical_workflow_queue_capability_registration(workflow) is not None
            for workflow in workflows
        )
    ):
        try:
            queue_requirements = validate_capability_registry_coverage(
                request.queue_policies, request.workflow_control
            )
        except AppError:
            # Keep the report complete for unaffected diagnostics, but the
            # configuration check below will fail closed for every uncovered queue.
            queue_requirements = {}

    if (
        request.profile_name == "autonomous_mvp"
        and not request.workflow_control.supervisor.enabled
    ):
        checks.append(
            _capability_check(
                "autonomous_supervisor",
                (),
                "blocked",
                "autonomous_supervisor_disabled",
                False,
                "Enable workflow_control.supervisor.enabled in app.autonomous_mvp.yaml",
                required=True,
            )
        )
    elif workflows:
        checks.append(
            _capability_check(
                "autonomous_supervisor"
                if request.profile_name == "autonomous_mvp"
                else "manual_workflow",
                workflows,
                "ready",
                "workflow_scope_resolved",
                False,
                "continue",
                required=True,
            )
        )
    else:
        checks.append(
            _capability_check(
                "workflow_scope",
                (),
                "not_required",
                "no_workflows_enabled",
                False,
                "Enable a supported workflow queue to run autonomous work",
                required=False,
            )
        )

    for workflow in workflows:
        profile_name: str | None = None
        if workflow == "report_generation":
            profile_name = "report_generation"
        elif workflow in queue_requirements:
            profile_name = queue_requirements[workflow].preflight_profile
            if profile_name is None:
                workflow_profiles[workflow] = "local_runtime"
                continue
        elif canonical_workflow_queue_capability_registration(workflow) is not None:
            profile_name = preflight_profile_for_queue(workflow)
            if profile_name is None:
                workflow_profiles[workflow] = "local_runtime"
                continue
        elif workflow in request.workflow_control.preflight_profiles:
            profile_name = workflow
        else:
            profile_name = None
        if not profile_name:
            checks.append(
                _capability_check(
                    "workflow_profile",
                    (workflow,),
                    "blocked",
                    "workflow_capability_profile_missing",
                    False,
                    "Add the workflow to workflow_control.preflight_profiles",
                    required=True,
                )
            )
            continue
        profile = request.workflow_control.preflight_profiles.get(profile_name)
        if profile is None:
            checks.append(
                _capability_check(
                    "workflow_profile",
                    (workflow,),
                    "blocked",
                    "workflow_capability_profile_missing",
                    False,
                    f"Add workflow_control.preflight_profiles.{profile_name}",
                    required=True,
                )
            )
            continue
        workflow_profiles[workflow] = profile_name
        profiles.setdefault(profile_name, profile)

    ocr_workflows = tuple(
        sorted(
            workflow
            for workflow in workflows
            if bool(getattr(request.settings, "pdf_text_ocr_enabled", False))
            and (
                workflow == "report_generation"
                or "ocr_model"
                in queue_requirements.get(
                    workflow,
                    CapabilityWorkflowRequirements(
                        workflow=workflow,
                        preflight_profile=None,
                        expected_external_effects=(),
                        required_capabilities=(),
                        job_type="",
                    ),
                ).required_capabilities
            )
        )
    )
    requirement_workflows = {
        capability: tuple(
            sorted(
                workflow
                for workflow, requirements in queue_requirements.items()
                if workflow in workflows
                and capability in requirements.required_capabilities
            )
        )
        for capability in (
            "llm_model",
            "openai_embedding_model",
            "google_drive",
            "browser",
            "wordpress",
            "mailbox",
        )
    }
    llm_workflows = tuple(
        sorted(
            set(_profile_workflows(profiles, workflow_profiles, "require_llm"))
            | set(requirement_workflows["llm_model"])
        )
    )
    inventory_settings = request.publisher_inventory_settings
    if "publisher_discovery" in llm_workflows and not (
        inventory_settings is not None
        and inventory_settings.candidate_screening_enabled
    ):
        # Publisher discovery's route model is OpenRouter and is checked below.
        # Its OpenAI dependency is conditional on candidate screening.
        llm_workflows = tuple(
            workflow for workflow in llm_workflows if workflow != "publisher_discovery"
        )
    embedding_workflows = tuple(
        sorted(
            set(workflow for workflow in workflows if workflow == "claim_embedding")
            | set(requirement_workflows["openai_embedding_model"])
        )
    )
    vector_workflows = tuple(
        sorted(
            workflow
            for workflow, requirements in queue_requirements.items()
            if workflow in workflows
            and "vector_store" in requirements.required_capabilities
        )
    )
    openai_workflows = tuple(
        sorted(
            set(llm_workflows)
            | set(embedding_workflows)
            | set(ocr_workflows)
            | set(vector_workflows)
        )
    )
    drive_workflows = tuple(
        sorted(
            set(_profile_workflows(profiles, workflow_profiles, "require_drive"))
            | set(requirement_workflows["google_drive"])
        )
    )
    if request.browser_settings is not None and not (
        request.browser_settings.drive_upload_enabled
        and request.browser_settings.drive_upload_required
    ):
        drive_workflows = tuple(
            workflow
            for workflow in drive_workflows
            if workflow not in {"report_acquisition", "mailbox_delivery"}
        )
    browser_workflows = tuple(
        sorted(
            set(_profile_workflows(profiles, workflow_profiles, "require_browser"))
            | set(requirement_workflows["browser"])
        )
    )
    wordpress_workflows = tuple(
        sorted(
            set(_profile_workflows(profiles, workflow_profiles, "require_publish"))
            | set(requirement_workflows["wordpress"])
        )
    )
    mailbox_workflows = tuple(
        sorted(
            set(workflow for workflow in workflows if workflow == "mailbox_delivery")
            | set(requirement_workflows["mailbox"])
        )
    )
    report_db_workflows = tuple(
        workflow
        for workflow in workflows
        if workflow == "report_generation" or workflow in _REPORTS_DB_WORKFLOWS
    )
    report_artifact_workflows = tuple(
        workflow for workflow in workflows if workflow in _REPORT_ARTIFACT_WORKFLOWS
    )

    checks.extend(
        _check_capability_configuration(
            request,
            workflows,
            workflow_profiles,
            registry_requirements=queue_requirements,
        )
    )
    checks.extend(
        _check_capability_dependencies(
            request,
            workflows,
            openai_workflows,
            drive_workflows,
            mailbox_workflows,
            wordpress_workflows,
            browser_workflows,
            deps,
            ctx,
        )
    )
    checks.extend(_check_capability_assets(request, workflows, deps, ctx))
    checks.extend(
        _check_capability_storage(
            request,
            workflows,
            report_artifact_workflows,
            browser_workflows,
            mailbox_workflows,
            wordpress_workflows,
            deps,
            ctx,
        )
    )
    provider_calls += _check_capability_databases(
        request,
        workflows,
        report_db_workflows,
        llm_workflows,
        deps,
        checks,
        ctx,
    )
    checks.extend(_check_queue_operational_settings(request, workflows))

    if llm_workflows:
        settings = request.settings
        if not str(settings.openai_api_key or "").strip():
            checks.append(
                _capability_check(
                    "llm_model",
                    llm_workflows,
                    "blocked",
                    "openai_missing_api_key",
                    False,
                    "Set OPENAI_API_KEY",
                    required=True,
                )
            )
        elif not str(settings.openai_model or "").strip():
            checks.append(
                _capability_check(
                    "llm_model",
                    llm_workflows,
                    "blocked",
                    "openai_model_missing",
                    False,
                    "Set ingest.openai_model",
                    required=True,
                )
            )
        elif _dependency_blocked(checks, "openai_dependencies", llm_workflows):
            checks.append(
                _capability_check(
                    "llm_model",
                    llm_workflows,
                    "blocked",
                    "openai_dependency_missing",
                    False,
                    "Install the locked OpenAI client dependency",
                    required=True,
                )
            )
        elif not request.live_checks:
            checks.append(
                _capability_check(
                    "llm_model",
                    llm_workflows,
                    "not_checked",
                    "llm_live_probe_skipped",
                    False,
                    "Rerun with --live to verify OpenAI model access",
                    required=True,
                )
            )
        else:
            try:
                result = deps.preflight_openai_model(
                    OpenAIModelPreflightRequest(
                        schema_version="1.0",
                        api_key=settings.openai_api_key,
                        model=settings.openai_model,
                        timeout_seconds=min(
                            float(
                                getattr(settings, "openai_timeout_seconds", 5.0) or 5.0
                            ),
                            10.0,
                        ),
                    ),
                    ctx,
                )
                provider_calls += max(1, int(getattr(result, "provider_calls", 1) or 0))
                if not bool(getattr(result, "accessible", False)):
                    checks.append(
                        _capability_check(
                            "llm_model",
                            llm_workflows,
                            "blocked",
                            "openai_model_unavailable",
                            False,
                            "Check OPENAI_API_KEY and the configured model",
                            required=True,
                        )
                    )
                else:
                    checks.append(
                        _capability_check(
                            "llm_model",
                            llm_workflows,
                            "ready",
                            "openai_model_accessible",
                            False,
                            "continue",
                            required=True,
                        )
                    )
            except AppError as exc:
                provider_calls += max(1, int(exc.context.get("provider_calls", 1) or 0))
                checks.append(
                    _capability_check(
                        "llm_model",
                        llm_workflows,
                        "degraded" if exc.retryable else "blocked",
                        _safe_reason_code(exc.code, "openai_provider_unavailable"),
                        exc.retryable,
                        "Rerun the capability preflight"
                        if exc.retryable
                        else "Check OPENAI_API_KEY and the configured model",
                        required=True,
                    )
                )
            except Exception:
                provider_calls += 1
                checks.append(
                    _capability_check(
                        "llm_model",
                        llm_workflows,
                        "degraded",
                        "openai_provider_unavailable",
                        True,
                        "Rerun the capability preflight",
                        required=True,
                    )
                )
    else:
        checks.append(
            _capability_check(
                "llm_model",
                (),
                "not_required",
                "llm_not_required",
                False,
                "No enabled workflow requires model access",
                required=False,
            )
        )

    if ocr_workflows:
        settings = request.settings
        llm_model_check = next(
            (check for check in checks if check.capability == "llm_model"), None
        )
        if (
            str(settings.pdf_text_ocr_model or "").strip()
            == str(settings.openai_model or "").strip()
            and set(ocr_workflows).issubset(llm_workflows)
            and llm_model_check is not None
        ):
            checks.append(
                _capability_check(
                    "ocr_model",
                    ocr_workflows,
                    llm_model_check.status,
                    llm_model_check.reason_code,
                    llm_model_check.retryable,
                    llm_model_check.remediation,
                    required=True,
                )
            )
        else:
            ocr_model_check, calls = _check_openai_model_capability(
                request,
                ocr_workflows,
                str(settings.pdf_text_ocr_model or "").strip(),
                capability="ocr_model",
                missing_dependency_checks=checks,
                deps=deps,
                ctx=ctx,
            )
            checks.append(ocr_model_check)
            provider_calls += calls

    if embedding_workflows:
        embedding_check, calls = _check_openai_model_capability(
            request,
            embedding_workflows,
            _CLAIM_EMBEDDING_MODEL,
            capability="openai_embedding_model",
            missing_dependency_checks=checks,
            deps=deps,
            ctx=ctx,
        )
        checks.append(embedding_check)
        provider_calls += calls
    else:
        checks.append(
            _capability_check(
                "openai_embedding_model",
                (),
                "not_required",
                "openai_embedding_not_required",
                False,
                "No enabled workflow requires claim embeddings",
                required=False,
            )
        )

    vector_check, vector_calls = _check_vector_store_capability(
        request, vector_workflows, checks, deps, ctx
    )
    checks.append(vector_check)
    provider_calls += vector_calls

    publisher_checks, calls = _check_publisher_inventory_model(
        request,
        tuple(workflow for workflow in workflows if workflow == "publisher_discovery"),
        deps,
        ctx,
    )
    checks.extend(publisher_checks)
    provider_calls += calls

    if drive_workflows:
        drive_checks, calls = _check_drive_capability(
            request, drive_workflows, deps, ctx
        )
        checks.extend(drive_checks)
        provider_calls += calls
    else:
        checks.append(
            _capability_check(
                "google_drive",
                (),
                "not_required",
                "drive_not_required",
                False,
                "No enabled workflow requires Drive access",
                required=False,
            )
        )

    if mailbox_workflows:
        mailbox_check, calls = _check_mailbox_capability(
            request, mailbox_workflows, deps, ctx
        )
        provider_calls += calls
        checks.append(mailbox_check)
    else:
        checks.append(
            _capability_check(
                "mailbox",
                (),
                "not_required",
                "mailbox_not_required",
                False,
                "No enabled workflow requires mailbox access",
                required=False,
            )
        )

    if browser_workflows:
        browser_check, calls = _check_browser_capability(
            request, browser_workflows, checks, deps, ctx
        )
        checks.append(browser_check)
        provider_calls += calls
    else:
        checks.append(
            _capability_check(
                "browser",
                (),
                "not_required",
                "browser_not_required",
                False,
                "No enabled workflow requires browser acquisition",
                required=False,
            )
        )

    if wordpress_workflows:
        wordpress_check, calls = _check_wordpress_capability(
            request, wordpress_workflows, deps, ctx
        )
        provider_calls += calls
        checks.append(wordpress_check)
    else:
        checks.append(
            _capability_check(
                "wordpress",
                (),
                "not_required",
                "wordpress_not_required",
                False,
                "No enabled workflow requires WordPress access",
                required=False,
            )
        )

    workflow_statuses: dict[str, CapabilityStatus] = {}
    for workflow in workflows:
        relevant = [
            check.status
            for check in checks
            if check.required and workflow in check.affected_workflows
        ]
        if any(status == "blocked" for status in relevant):
            workflow_statuses[workflow] = "blocked"
        elif any(status == "not_checked" for status in relevant):
            workflow_statuses[workflow] = "not_checked"
        elif any(status == "degraded" for status in relevant):
            workflow_statuses[workflow] = "degraded"
        else:
            workflow_statuses[workflow] = "ready"
    global_required_statuses = [
        check.status
        for check in checks
        if check.required and not check.affected_workflows
    ]
    has_global_blocker = "blocked" in global_required_statuses
    if has_global_blocker or (
        workflow_statuses
        and all(status == "blocked" for status in workflow_statuses.values())
    ):
        overall_status: CapabilityStatus = "blocked"
    elif any(status == "not_checked" for status in global_required_statuses) or any(
        status == "not_checked" for status in workflow_statuses.values()
    ):
        overall_status = "not_checked"
    elif any(status == "degraded" for status in global_required_statuses) or any(
        status != "ready" for status in workflow_statuses.values()
    ):
        overall_status = "degraded"
    elif workflow_statuses:
        overall_status = "ready"
    else:
        overall_status = "not_required"
    report = CapabilityPreflightReport(
        schema_version="1.0",
        profile_name=request.profile_name,
        status=overall_status,
        workflow_names=list(workflows),
        workflow_statuses=workflow_statuses,
        checks=checks,
        elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
        provider_calls=provider_calls,
        external_writes=0,
        blocking_count=sum(
            check.required and check.status != "ready" for check in checks
        ),
    )
    report = replace(
        report,
        execution_readiness=build_execution_readiness(report, request, ctx),
    )
    try:
        assert report.execution_readiness is not None
        retained_readiness = retain_capability_proof(
            report.execution_readiness,
            request,
            ctx,
            deps,
            report=report,
        )
        report = replace(
            report,
            execution_readiness=retained_readiness,
            proof_reference=retained_readiness.proof.artifact_reference,
        )
    except AppError as exc:
        proof_failure = _capability_check(
            "capability_proof",
            workflows,
            "blocked",
            _safe_reason_code(exc.code, "capability_proof_persist_failed"),
            False,
            "Restore the configured proof output path and rerun capability preflight",
            required=bool(workflows),
        )
        failed_checks = [*report.checks, proof_failure]
        failed_workflow_statuses: dict[str, CapabilityStatus] = {
            workflow: "blocked" for workflow in workflows
        }
        failed_report = replace(
            report,
            status="blocked" if workflows else report.status,
            workflow_statuses=failed_workflow_statuses or report.workflow_statuses,
            checks=failed_checks,
            blocking_count=report.blocking_count + int(bool(workflows)),
        )
        report = replace(
            failed_report,
            execution_readiness=build_execution_readiness(failed_report, request, ctx),
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="capability_preflight_complete",
            module=logger.name,
            fields={
                "profile": request.profile_name,
                "status": report.status,
                "workflow_count": len(report.workflow_names),
                "check_count": len(report.checks),
                "blocking_count": report.blocking_count,
                "provider_calls": report.provider_calls,
                "external_writes": report.external_writes,
                "elapsed_ms": report.elapsed_ms,
            },
        )
    )
    return report


def _capability_check(
    capability: str,
    workflows: tuple[str, ...],
    status: str,
    reason_code: str,
    retryable: bool,
    remediation: str,
    *,
    required: bool,
) -> CapabilityPreflightCheck:
    return CapabilityPreflightCheck(
        schema_version="1.0",
        capability=capability,
        affected_workflows=list(workflows),
        status=cast(CapabilityStatus, status),
        reason_code=reason_code,
        retryable=retryable,
        remediation=remediation,
        required=required,
    )


def _profile_workflows(
    profiles: dict[str, object],
    workflow_profiles: dict[str, str],
    requirement: str,
) -> tuple[str, ...]:
    required_profiles = {
        profile_name
        for profile_name, profile in profiles.items()
        if bool(getattr(profile, requirement, False))
    }
    return tuple(
        sorted(
            workflow
            for workflow, profile_name in workflow_profiles.items()
            if profile_name in required_profiles
        )
    )


def _check_openai_model_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    model: str,
    *,
    capability: str,
    missing_dependency_checks: list[CapabilityPreflightCheck],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.settings
    if not str(settings.openai_api_key or "").strip():
        return (
            _capability_check(
                capability,
                workflows,
                "blocked",
                "openai_missing_api_key",
                False,
                "Set OPENAI_API_KEY",
                required=True,
            ),
            0,
        )
    if not str(model or "").strip():
        return (
            _capability_check(
                capability,
                workflows,
                "blocked",
                "openai_model_missing",
                False,
                "Set the configured OpenAI model for this workflow",
                required=True,
            ),
            0,
        )
    if _dependency_blocked(missing_dependency_checks, "openai_dependencies", workflows):
        return (
            _capability_check(
                capability,
                workflows,
                "blocked",
                "openai_dependency_missing",
                False,
                "Install the locked OpenAI client dependency",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                capability,
                workflows,
                "not_checked",
                "openai_model_live_probe_skipped",
                False,
                "Rerun with --live to verify OpenAI model access",
                required=True,
            ),
            0,
        )
    try:
        result = deps.preflight_openai_model(
            OpenAIModelPreflightRequest(
                schema_version="1.0",
                api_key=settings.openai_api_key,
                model=model,
                timeout_seconds=min(
                    float(getattr(settings, "openai_timeout_seconds", 5.0) or 5.0),
                    10.0,
                ),
            ),
            ctx,
        )
    except AppError as exc:
        return (
            _capability_check(
                capability,
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "openai_provider_unavailable"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check OPENAI_API_KEY and the configured OpenAI model",
                required=True,
            ),
            1,
        )
    except Exception:
        return (
            _capability_check(
                capability,
                workflows,
                "degraded",
                "openai_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            ),
            1,
        )
    if not bool(getattr(result, "accessible", False)):
        return (
            _capability_check(
                capability,
                workflows,
                "blocked",
                "openai_model_unavailable",
                False,
                "Check OPENAI_API_KEY and the configured OpenAI model",
                required=True,
            ),
            1,
        )
    return (
        _capability_check(
            capability,
            workflows,
            "ready",
            "openai_model_accessible",
            False,
            "continue",
            required=True,
        ),
        1,
    )


def _check_vector_store_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    checks: list[CapabilityPreflightCheck],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    if not workflows:
        return (
            _capability_check(
                "vector_store",
                (),
                "not_required",
                "vector_store_not_required",
                False,
                "No enabled workflow requires vector-store access",
                required=False,
            ),
            0,
        )
    settings = request.settings
    if not str(settings.openai_api_key or "").strip():
        return (
            _capability_check(
                "vector_store",
                workflows,
                "blocked",
                "vector_store_missing_api_key",
                False,
                "Set OPENAI_API_KEY before vector-store work",
                required=True,
            ),
            0,
        )
    if _dependency_blocked(checks, "openai_dependencies", workflows):
        return (
            _capability_check(
                "vector_store",
                workflows,
                "blocked",
                "vector_store_dependency_missing",
                False,
                "Install the locked OpenAI client dependency",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                "vector_store",
                workflows,
                "not_checked",
                "vector_store_live_probe_skipped",
                False,
                "Rerun with --live to verify vector-store authorization",
                required=True,
            ),
            0,
        )
    if deps.preflight_vector_store is None:
        return (
            _capability_check(
                "vector_store",
                workflows,
                "not_checked",
                "vector_store_probe_unavailable",
                False,
                "Use the supported vector-store preflight implementation",
                required=True,
            ),
            0,
        )
    try:
        result = deps.preflight_vector_store(
            OpenAIVectorStorePreflightRequest(
                schema_version="1.0",
                api_key=settings.openai_api_key,
                timeout_seconds=min(
                    float(getattr(settings, "openai_timeout_seconds", 5.0) or 5.0),
                    10.0,
                ),
            ),
            ctx,
        )
        calls = max(1, int(getattr(result, "provider_calls", 1) or 0))
        if not bool(getattr(result, "accessible", False)):
            return (
                _capability_check(
                    "vector_store",
                    workflows,
                    "blocked",
                    "vector_store_unavailable",
                    False,
                    "Check vector-store authorization for the configured provider",
                    required=True,
                ),
                calls,
            )
        return (
            _capability_check(
                "vector_store",
                workflows,
                "ready",
                "vector_store_accessible",
                False,
                "continue",
                required=True,
            ),
            calls,
        )
    except AppError as exc:
        return (
            _capability_check(
                "vector_store",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "vector_store_provider_unavailable"),
                bool(exc.retryable),
                "Rerun the capability preflight"
                if exc.retryable
                else "Check vector-store authorization for the configured provider",
                required=True,
            ),
            max(1, int(exc.context.get("provider_calls", 1) or 0)),
        )
    except Exception:
        return (
            _capability_check(
                "vector_store",
                workflows,
                "degraded",
                "vector_store_provider_unavailable",
                True,
                "Rerun the capability preflight",
                required=True,
            ),
            1,
        )


def _check_publisher_inventory_model(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[list[CapabilityPreflightCheck], int]:
    if not workflows:
        return (
            [
                _capability_check(
                    "openrouter_model",
                    (),
                    "not_required",
                    "publisher_discovery_not_required",
                    False,
                    "No enabled workflow requires publisher discovery",
                    required=False,
                )
            ],
            0,
        )

    checks: list[CapabilityPreflightCheck] = []
    inventory = request.publisher_inventory_settings
    config_error = str(request.publisher_inventory_config_error or "").strip()
    if config_error:
        reason_code = _safe_reason_code(
            config_error, "publisher_inventory_configuration_incomplete"
        )
        remediation = {
            "publisher_inventory_openrouter_api_key_missing": "Set OPENROUTER_API_KEY",
            "publisher_inventory_openai_api_key_missing": "Set OPENAI_API_KEY or disable publisher candidate screening",
        }.get(
            reason_code,
            "Correct the publisher discovery configuration and rerun capability preflight",
        )
        checks.append(
            _capability_check(
                "publisher_inventory_configuration",
                workflows,
                "blocked",
                reason_code,
                False,
                remediation,
                required=True,
            )
        )
    elif inventory is None:
        checks.append(
            _capability_check(
                "publisher_inventory_configuration",
                workflows,
                "blocked",
                "publisher_inventory_settings_missing",
                False,
                "Load publisher discovery settings for the selected profile",
                required=True,
            )
        )

    if inventory is None:
        return (
            checks
            + [
                _capability_check(
                    "openrouter_model",
                    workflows,
                    "not_checked",
                    "publisher_inventory_settings_unavailable",
                    False,
                    "Resolve publisher discovery settings before verifying its OpenRouter model",
                    required=True,
                )
            ],
            0,
        )
    if not str(inventory.openrouter_api_key or "").strip():
        checks.append(
            _capability_check(
                "publisher_inventory_configuration",
                workflows,
                "blocked",
                "openrouter_missing_api_key",
                False,
                "Set OPENROUTER_API_KEY",
                required=True,
            )
        )
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "blocked",
                "openrouter_missing_api_key",
                False,
                "Set OPENROUTER_API_KEY",
                required=True,
            )
        )
        return checks, 0
    model = str(inventory.model or "").strip()
    if not model:
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "blocked",
                "openrouter_model_missing",
                False,
                "Set publisher_discovery.model to an OpenRouter author/model slug",
                required=True,
            )
        )
        return checks, 0

    if config_error:
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "not_checked",
                "publisher_inventory_configuration_incomplete",
                False,
                "Resolve publisher discovery configuration before checking the OpenRouter model",
                required=True,
            )
        )
        return checks, 0
    checks.append(
        _capability_check(
            "publisher_inventory_configuration",
            workflows,
            "ready",
            "publisher_inventory_configuration_resolved",
            False,
            "continue",
            required=True,
        )
    )
    if not request.live_checks:
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "not_checked",
                "openrouter_model_live_probe_skipped",
                False,
                "Rerun with --live to verify OpenRouter model metadata access",
                required=True,
            )
        )
        return checks, 0

    try:
        result = deps.preflight_openrouter_model(
            OpenRouterModelPreflightRequest(
                schema_version="1.0",
                api_key=inventory.openrouter_api_key,
                model=model,
                timeout_seconds=min(float(inventory.timeout_seconds or 5.0), 10.0),
            ),
            ctx,
        )
    except AppError as exc:
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "openrouter_provider_unavailable"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check OPENROUTER_API_KEY and publisher_discovery.model",
                required=True,
            )
        )
        return checks, max(1, int(exc.context.get("provider_calls", 0) or 0))
    except Exception:
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "degraded",
                "openrouter_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            )
        )
        return checks, 1

    if not bool(getattr(result, "accessible", False)):
        checks.append(
            _capability_check(
                "openrouter_model",
                workflows,
                "blocked",
                "openrouter_model_unavailable",
                False,
                "Check OPENROUTER_API_KEY and publisher_discovery.model",
                required=True,
            )
        )
        return checks, max(1, int(getattr(result, "provider_calls", 1) or 0))
    checks.append(
        _capability_check(
            "openrouter_model",
            workflows,
            "ready",
            "openrouter_model_metadata_accessible",
            False,
            "continue",
            required=True,
        )
    )
    return checks, max(1, int(getattr(result, "provider_calls", 1) or 0))


def _check_capability_configuration(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    workflow_profiles: dict[str, str],
    *,
    registry_requirements: Mapping[str, CapabilityWorkflowRequirements] | None = None,
) -> list[CapabilityPreflightCheck]:
    checks = [
        _capability_check(
            "resolved_configuration",
            workflows,
            "ready" if workflows else "not_required",
            "configuration_resolved" if workflows else "no_workflows_enabled",
            False,
            "continue" if workflows else "Enable a supported workflow queue",
            required=bool(workflows),
        )
    ]
    if request.profile_name == "autonomous_mvp" and workflows:
        supervisor = request.workflow_control.supervisor
        recovery_ready = (
            supervisor.deferred_work_enabled
            and supervisor.remediation_enabled
            and request.workflow_control.remediation_reaper.execution_enabled
            and request.workflow_control.deferred_work_reaper.execution_enabled
        )
        checks.append(
            _capability_check(
                "autonomous_recovery",
                workflows,
                "ready" if recovery_ready else "blocked",
                "autonomous_recovery_enabled"
                if recovery_ready
                else "autonomous_recovery_disabled",
                False,
                "continue"
                if recovery_ready
                else "Enable deferred-work and remediation recovery in app.autonomous_mvp.yaml",
                required=True,
            )
        )
        dispatch_enabled = bool(supervisor.worker_batches_enabled)
        checks.append(
            _capability_check(
                "autonomous_dispatch",
                workflows,
                "ready" if dispatch_enabled else "blocked",
                "autonomous_worker_dispatch_enabled"
                if dispatch_enabled
                else "autonomous_worker_dispatch_disabled",
                False,
                "continue"
                if dispatch_enabled
                else "Enable workflow_control.supervisor.worker_batches_enabled in app.autonomous_mvp.yaml",
                required=True,
            )
        )
        unknown_queues = sorted(
            workflow
            for workflow in workflows
            if (
                workflow not in registry_requirements
                if registry_requirements is not None
                else canonical_workflow_queue_capability_registration(workflow) is None
            )
        )
        checks.append(
            _capability_check(
                "workflow_queue_registry",
                tuple(unknown_queues or workflows),
                "blocked" if unknown_queues else "ready",
                "workflow_queue_capability_mapping_missing"
                if unknown_queues
                else "workflow_queue_capability_mapping_complete",
                False,
                "Add each enabled queue to the capability preflight mapping",
                required=True,
            )
        )
        active_queues = [
            request.queue_policies[name]
            for name in workflows
            if name in request.queue_policies
        ]
        available_profiles = set(request.workflow_control.available_budget_profile_refs)
        invalid_budget_queues = sorted(
            policy.queue_name
            for policy in active_queues
            if policy.budget_profile not in available_profiles
        )
        checks.append(
            _capability_check(
                "queue_budget_profiles",
                tuple(invalid_budget_queues or workflows),
                "blocked" if invalid_budget_queues else "ready",
                "workflow_queue_budget_profile_missing"
                if invalid_budget_queues
                else "workflow_queue_budget_profiles_resolved",
                False,
                "Configure a budget profile for each enabled queue",
                required=True,
            )
        )
        if "wordpress_publish" in workflows:
            publication_enabled = (
                request.workflow_control.autonomous_publication_policy.enabled
            )
            if not publication_enabled:
                checks.append(
                    _capability_check(
                        "autonomous_publication_policy",
                        ("wordpress_publish",),
                        "degraded",
                        "autonomous_publication_policy_disabled",
                        False,
                        "Enable the existing policy-gated autonomous publication overlay if automatic approval is intended",
                        required=True,
                    )
                )
    return checks


def _check_capability_dependencies(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    llm_workflows: tuple[str, ...],
    drive_workflows: tuple[str, ...],
    mailbox_workflows: tuple[str, ...],
    wordpress_workflows: tuple[str, ...],
    browser_workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> list[CapabilityPreflightCheck]:
    if not workflows:
        return [
            _capability_check(
                "python_runtime",
                (),
                "not_required",
                "runtime_not_required",
                False,
                "No workflow is enabled",
                required=False,
            ),
            _capability_check(
                "python_dependencies",
                (),
                "not_required",
                "dependencies_not_required",
                False,
                "No workflow is enabled",
                required=False,
            ),
        ]

    settings = request.settings
    python_ok = _python_runtime_supported(tuple(sys.version_info[:2]), sys.executable)
    checks = [
        _capability_check(
            "python_runtime",
            workflows,
            "ready" if python_ok else "blocked",
            "python_runtime_ready" if python_ok else "python_runtime_unsupported",
            False,
            "Use the supported Python interpreter from the locked environment",
            required=True,
        )
    ]
    dependency_groups: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        ("core_dependencies", workflows, ("yaml",))
    ]
    pdf_workflows = tuple(
        workflow for workflow in workflows if workflow in _PDF_WORKFLOWS
    )
    if pdf_workflows:
        dependency_groups.append(
            ("pdf_dependencies", pdf_workflows, ("pypdf", "fitz", "PIL"))
        )
    if llm_workflows:
        dependency_groups.append(("openai_dependencies", llm_workflows, ("openai",)))
    google_workflows = set(drive_workflows)
    if request.mailbox_settings is not None:
        mailbox_provider = str(request.mailbox_settings.provider or "").strip().lower()
        if mailbox_provider == "gmail":
            google_workflows.update(mailbox_workflows)
        elif mailbox_provider == "auto":
            token_path = str(
                request.mailbox_settings.gmail_oauth_token_path or ""
            ).strip()
            try:
                gmail_configured = bool(
                    token_path
                    and deps.file_stat(
                        FileStatRequest(
                            schema_version="1.0",
                            path=str(Path(token_path).expanduser()),
                        ),
                        ctx,
                    ).is_file
                )
            except AppError:
                gmail_configured = False
            imap_configured = bool(
                request.mailbox_settings.imap_host
                and request.mailbox_settings.imap_user
                and request.mailbox_settings.imap_password
            )
            if gmail_configured and not imap_configured:
                google_workflows.update(mailbox_workflows)
    if google_workflows:
        dependency_groups.append(
            (
                "google_dependencies",
                tuple(sorted(google_workflows)),
                ("googleapiclient", "google_auth_httplib2"),
            )
        )
    if wordpress_workflows:
        dependency_groups.append(
            ("wordpress_dependencies", wordpress_workflows, ("requests",))
        )
    for capability, affected_workflows, packages in dependency_groups:
        missing_packages = sorted(
            package for package in packages if importlib.util.find_spec(package) is None
        )
        checks.append(
            _capability_check(
                capability,
                affected_workflows,
                "blocked" if missing_packages else "ready",
                "required_dependency_missing"
                if missing_packages
                else "required_dependencies_available",
                False,
                "Install the locked dependencies with the repository setup procedure"
                if missing_packages
                else "continue",
                required=True,
            )
        )
    if browser_workflows:
        browser_runtime = deps.preflight_browser_runtime(ctx)
        checks.append(
            _capability_check(
                "browser_dependencies",
                browser_workflows,
                "ready" if browser_runtime.available else "blocked",
                browser_runtime.reason_code,
                False,
                "continue"
                if browser_runtime.available
                else "Install or restore the supported browser-use runtime using the local setup procedure",
                required=True,
            )
        )
    ocr_enabled = bool(getattr(settings, "pdf_text_ocr_enabled", False))
    checks.append(
        _capability_check(
            "ocr_executable",
            (),
            "not_required",
            "ocr_provider_backed"
            if ocr_enabled and any(workflow in _OCR_WORKFLOWS for workflow in workflows)
            else "ocr_not_required",
            False,
            "OCR uses the configured LLM provider; no local OCR executable is required"
            if ocr_enabled and any(workflow in _OCR_WORKFLOWS for workflow in workflows)
            else "OCR is disabled or no enabled workflow uses OCR",
            required=False,
        )
    )
    return checks


def workflow_profiles_for_runtime(workflows: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "report_generation"
                if workflow == "report_generation"
                else preflight_profile_for_queue(workflow) or "local_runtime"
                for workflow in workflows
            }
        )
    )


def _check_capability_assets(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> list[CapabilityPreflightCheck]:
    checks: list[CapabilityPreflightCheck] = []
    ocr_workflows = tuple(
        workflow
        for workflow in workflows
        if workflow in _OCR_WORKFLOWS
        and bool(getattr(request.settings, "pdf_text_ocr_enabled", False))
    )
    category_workflows = tuple(
        workflow for workflow in workflows if workflow in _CATEGORY_MAPPING_WORKFLOWS
    )
    required_files: list[tuple[str, tuple[str, ...], str]] = []
    if category_workflows:
        required_files.append(
            (
                request.settings.category_mapping_path,
                category_workflows,
                "category_mapping",
            )
        )
    cover_workflows = tuple(
        workflow
        for workflow in workflows
        if workflow in {"report_generation", "cover_generation"}
    )
    if cover_workflows:
        required_files.append(
            (
                request.settings.cover_style_path,
                cover_workflows,
                "cover_style",
            )
        )
    if "publisher_discovery" in workflows:
        required_files.append(
            (
                request.settings.publisher_profiles_path,
                ("publisher_discovery",),
                "publisher_profiles",
            )
        )
    for path, affected_workflows, asset_name in required_files:
        available = False
        reason_code = f"{asset_name}_missing"
        retryable = False
        if str(path or "").strip():
            try:
                available = deps.file_stat(
                    FileStatRequest(
                        schema_version="1.0", path=str(Path(path).expanduser())
                    ),
                    ctx,
                ).is_file
            except AppError as exc:
                reason_code = _safe_reason_code(exc.code, f"{asset_name}_unavailable")
                retryable = bool(exc.retryable)
        checks.append(
            _capability_check(
                f"asset_{asset_name}",
                affected_workflows,
                "ready" if available else "degraded" if retryable else "blocked",
                f"{asset_name}_available" if available else reason_code,
                retryable,
                "continue"
                if available
                else "Restore the configured application asset file",
                required=True,
            )
        )

    workflow_profiles = {
        workflow: (
            "report_generation"
            if workflow == "report_generation"
            else preflight_profile_for_queue(workflow)
            or (
                workflow
                if workflow in request.workflow_control.preflight_profiles
                else "local_runtime"
            )
        )
        for workflow in workflows
    }
    prompt_workflows: dict[str, set[str]] = {}
    for workflow, profile_name in workflow_profiles.items():
        profile = request.workflow_control.preflight_profiles.get(profile_name)
        namespaces = {
            str(value).strip()
            for value in (profile.prompt_namespaces if profile else ())
            if str(value).strip()
        }
        if profile_name == "report_generation":
            namespaces.update(report_pipeline_prompt_namespaces(request.settings))
        if workflow in ocr_workflows:
            ocr_namespace = str(
                getattr(request.settings, "pdf_text_ocr_prompt_namespace", "") or ""
            ).strip()
            if ocr_namespace:
                namespaces.add(ocr_namespace)
        for namespace in namespaces:
            prompt_workflows.setdefault(namespace, set()).add(workflow)
    prompt_namespaces = tuple(sorted(prompt_workflows))
    if not prompt_namespaces:
        checks.append(
            _capability_check(
                "prompt_assets",
                workflows,
                "not_required",
                "no_prompts_required",
                False,
                "No enabled workflow declares prompt assets",
                required=False,
            )
        )
    for namespace in prompt_namespaces:
        affected = tuple(sorted(prompt_workflows[namespace]))
        try:
            deps.load_prompt_set(
                PromptLoadRequest(schema_version="1.0", namespace=namespace),
                ctx,
            )
        except AppError as exc:
            checks.append(
                _capability_check(
                    "prompt_assets",
                    affected,
                    "degraded" if exc.retryable else "blocked",
                    _safe_reason_code(exc.code, "prompt_asset_unavailable"),
                    bool(exc.retryable),
                    "Rerun the preflight"
                    if exc.retryable
                    else "Restore the configured prompt files under src/prompts",
                    required=True,
                )
            )
        except Exception:
            checks.append(
                _capability_check(
                    "prompt_assets",
                    affected,
                    "blocked",
                    "prompt_asset_unavailable",
                    False,
                    "Restore the configured prompt files under src/prompts",
                    required=True,
                )
            )
        else:
            checks.append(
                _capability_check(
                    "prompt_assets",
                    affected,
                    "ready",
                    "prompt_asset_available",
                    False,
                    "continue",
                    required=True,
                )
            )
    return checks


def _check_capability_storage(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    report_workflows: tuple[str, ...],
    browser_workflows: tuple[str, ...],
    mailbox_workflows: tuple[str, ...],
    wordpress_workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> list[CapabilityPreflightCheck]:
    paths: dict[str, tuple[str, ...]] = {}

    def add_path(path: str, affected_workflows: tuple[str, ...]) -> None:
        paths[path] = tuple(sorted(set(paths.get(path, ())) | set(affected_workflows)))

    if report_workflows:
        add_path(request.settings.output_dir, report_workflows)
        add_path(request.settings.cache_dir, report_workflows)
        add_path(
            str(Path(request.settings.reports_db).expanduser().parent), report_workflows
        )
        lock_path = str(request.settings.ingest_lock_path or "").strip()
        add_path(
            str(Path(lock_path).expanduser().parent) if lock_path else "",
            report_workflows,
        )
    if workflows:
        add_path(str(Path(request.settings.state_db).expanduser().parent), workflows)
        add_path(
            str(Path(request.settings.usage_db_path).expanduser().parent), workflows
        )
    signal_workflows = tuple(
        workflow for workflow in workflows if workflow in _SIGNAL_STORE_WORKFLOWS
    )
    if signal_workflows:
        add_path(
            str(
                Path(request.settings.signal_store_db or request.settings.reports_db)
                .expanduser()
                .parent
            ),
            signal_workflows,
        )
    if request.browser_settings is not None:
        if browser_workflows:
            add_path(request.browser_settings.output_dir, browser_workflows)
    if request.mailbox_settings is not None and mailbox_workflows:
        add_path(request.mailbox_settings.output_dir, mailbox_workflows)
    if request.publish_settings is not None and wordpress_workflows:
        add_path(request.publish_settings.output_dir, wordpress_workflows)

    checks: list[CapabilityPreflightCheck] = []
    for path, affected_workflows in sorted(paths.items()):
        writable, reason_code = _probe_storage_path(path, deps, ctx)
        checks.append(
            _capability_check(
                "writable_storage",
                affected_workflows,
                "ready" if writable else "blocked",
                reason_code,
                False,
                "continue"
                if writable
                else "Restore write access to the configured storage directory",
                required=True,
            )
        )
    minimum_free_space = max(
        0, int(getattr(request.settings, "preflight_min_free_space_bytes", 0) or 0)
    )
    if minimum_free_space > 0:
        usage_probe = (
            deps.inspect_filesystem_usage or file_service.inspect_filesystem_usage
        )
        for path, affected_workflows in sorted(paths.items()):
            try:
                usage = usage_probe(
                    FileSystemUsageRequest(schema_version="1.0", path=str(path)),
                    ctx,
                )
                available = int(
                    getattr(usage, "available_bytes", getattr(usage, "free_bytes", -1))
                )
                status = "ready" if available >= minimum_free_space else "blocked"
                reason_code = (
                    "filesystem_free_space_ready"
                    if status == "ready"
                    else "insufficient_free_space"
                )
                retryable = False
            except AppError as exc:
                status = "degraded" if exc.retryable else "blocked"
                reason_code = _safe_reason_code(
                    exc.code, "filesystem_usage_unavailable"
                )
                retryable = bool(exc.retryable)
            checks.append(
                _capability_check(
                    "free_space",
                    affected_workflows,
                    status,
                    reason_code,
                    retryable,
                    "Free space on the filesystem or lower the configured preflight floor"
                    if status != "ready"
                    else "continue",
                    required=True,
                )
            )
    if not paths:
        checks.append(
            _capability_check(
                "writable_storage",
                (),
                "not_required",
                "storage_not_required",
                False,
                "No enabled workflow requires local artifact storage",
                required=False,
            )
        )
    return checks


def _probe_storage_path(
    raw_path: str,
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[bool, str]:
    path = Path(str(raw_path or "")).expanduser()
    if not str(raw_path or "").strip():
        return False, "storage_path_missing"
    try:
        path_stat = deps.file_stat(
            FileStatRequest(schema_version="1.0", path=str(path)), ctx
        )
    except AppError as exc:
        return False, _safe_reason_code(exc.code, "storage_path_unavailable")
    if path_stat.exists and not path_stat.is_dir:
        return False, "storage_path_not_directory"
    probe_dir = path if path_stat.is_dir else path.parent
    while True:
        try:
            parent_stat = deps.file_stat(
                FileStatRequest(schema_version="1.0", path=str(probe_dir)), ctx
            )
        except AppError as exc:
            return False, _safe_reason_code(exc.code, "storage_parent_unavailable")
        if parent_stat.exists:
            if not parent_stat.is_dir:
                return False, "storage_parent_unavailable"
            break
        if probe_dir == probe_dir.parent:
            return False, "storage_parent_unavailable"
        probe_dir = probe_dir.parent
    probe_path = str(probe_dir / f".marketlense-preflight-{uuid.uuid4().hex}.tmp")
    try:
        if deps.file_stat(
            FileStatRequest(schema_version="1.0", path=probe_path), ctx
        ).exists:
            return False, "storage_probe_path_collision"
    except AppError as exc:
        return False, _safe_reason_code(exc.code, "storage_probe_unavailable")

    write_reason = "storage_writable"
    cleanup_reason = ""
    owned = True
    try:
        write_probe = getattr(deps, "write_exclusive_bytes", None)
        if not callable(write_probe):
            write_probe = deps.write_bytes
        write_probe(
            WriteBytesRequest(
                schema_version="1.0",
                path=probe_path,
                content=b"capability-preflight",
                make_parents=False,
            ),
            ctx,
        )
    except AppError as exc:
        if exc.code == "file_write_conflict":
            owned = False
        write_reason = _safe_reason_code(exc.code, "storage_not_writable")
    finally:
        if owned:
            try:
                deleted = deps.delete_file(
                    DeleteFileRequest(
                        schema_version="1.0", path=probe_path, missing_ok=True
                    ),
                    ctx,
                )
                if write_reason == "storage_writable" and not deleted.deleted:
                    cleanup_reason = "storage_probe_cleanup_failed"
            except AppError:
                cleanup_reason = "storage_probe_cleanup_failed"
    if cleanup_reason:
        return False, cleanup_reason
    if write_reason != "storage_writable":
        return False, write_reason
    return True, write_reason


def _check_capability_databases(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    report_workflows: tuple[str, ...],
    llm_workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    checks: list[CapabilityPreflightCheck],
    ctx: RunContext,
) -> int:
    if not workflows:
        return 0
    stores: list[tuple[str, str, str, tuple[str, ...]]] = [
        ("state_db", "state_db", request.settings.state_db, workflows)
    ]
    signal_workflows = tuple(
        workflow for workflow in workflows if workflow in _SIGNAL_STORE_WORKFLOWS
    )
    if signal_workflows:
        # The dedicated Signal file uses the reports migration registry while
        # retaining a separate configured path and readiness result.
        stores.append(
            (
                "signal_store_db",
                "reports_db",
                request.settings.signal_store_db or request.settings.reports_db,
                signal_workflows,
            )
        )
    if report_workflows:
        stores.append(
            ("reports_db", "reports_db", request.settings.reports_db, report_workflows)
        )
    if llm_workflows or any(
        request.queue_policies.get(workflow) for workflow in workflows
    ):
        stores.append(
            ("llm_usage_db", "llm_usage_db", request.settings.usage_db_path, workflows)
        )
    provider_calls = 0
    for capability_key, database_key, path, affected_workflows in stores:
        if not str(path or "").strip():
            status = "blocked"
            reason_code = "sqlite_database_path_missing"
            retryable = False
        else:
            try:
                inspection = deps.inspect_sqlite(
                    SqliteCapabilityInspectionRequest(
                        schema_version="1.0",
                        database_key=database_key,
                        db_path=path,
                        lock_timeout_seconds=0.1,
                    ),
                    ctx,
                )
                status = inspection.status
                reason_code = inspection.reason_code
                retryable = inspection.retryable
            except AppError as exc:
                status = "degraded" if exc.retryable else "blocked"
                reason_code = _safe_reason_code(exc.code, "sqlite_inspection_failed")
                retryable = bool(exc.retryable)
            except Exception:
                status = "blocked"
                reason_code = "sqlite_inspection_failed"
                retryable = False
        if status not in {"ready", "degraded", "blocked"}:
            status = "blocked"
            reason_code = "sqlite_inspection_response_invalid"
            retryable = False
        checks.append(
            _capability_check(
                capability_key,
                affected_workflows,
                status,
                _safe_reason_code(reason_code, "sqlite_inspection_failed"),
                retryable,
                "continue"
                if status == "ready"
                else "Rerun the canonical SQLite migrations or resolve database integrity and lock contention",
                required=True,
            )
        )
    return provider_calls


def _check_queue_operational_settings(
    request: CapabilityPreflightRequest, workflows: tuple[str, ...]
) -> list[CapabilityPreflightCheck]:
    if not workflows:
        return [
            _capability_check(
                "queue_operations",
                (),
                "not_required",
                "no_queues_enabled",
                False,
                "Enable a supported workflow queue",
                required=False,
            )
        ]
    if request.profile_name == "manual":
        invalid = any(
            int(value) <= 0
            for value in (
                request.settings.batch_limit,
                request.settings.ingest_worker_limit,
                request.settings.report_worker_limit,
            )
        )
        return [
            _capability_check(
                "queue_operations",
                workflows,
                "blocked" if invalid else "ready",
                "manual_operational_setting_invalid"
                if invalid
                else "manual_operational_settings_ready",
                False,
                "Correct the configured batch and worker limits",
                required=True,
            )
        ]
    available_budgets = set(request.workflow_control.available_budget_profile_refs)
    bad: list[str] = []
    for workflow in workflows:
        policy = request.queue_policies.get(workflow)
        if policy is None or policy.queue_name != workflow:
            bad.append(workflow)
            continue
        positive_values = (
            policy.max_workers,
            policy.max_attempts,
            policy.lease_seconds,
            policy.maximum_pending,
            policy.maximum_fanout,
            policy.retry_delay_seconds,
        )
        if any(int(value) <= 0 for value in positive_values):
            bad.append(workflow)
        if (
            not str(policy.budget_profile or "").strip()
            or policy.budget_profile not in available_budgets
        ):
            bad.append(workflow)
    supervisor = request.workflow_control.supervisor
    invalid_supervisor = supervisor.enabled and any(
        int(value) <= 0
        for value in (
            supervisor.max_parallel_workers,
            supervisor.max_jobs_per_queue,
            supervisor.max_total_jobs,
            supervisor.max_runtime_seconds,
            supervisor.lease_seconds,
        )
    )
    if invalid_supervisor:
        bad.extend(workflows)
    bad_workflows = tuple(sorted(set(bad)))
    return [
        _capability_check(
            "queue_operations",
            bad_workflows or workflows,
            "blocked" if bad_workflows else "ready",
            "queue_operational_setting_invalid"
            if bad_workflows
            else "queue_operational_settings_ready",
            False,
            "Correct enabled queue worker, retry, lease, fanout and budget settings",
            required=True,
        )
    ]


def _safe_reason_code(value: str, fallback: str) -> str:
    rendered = str(value or "").strip().lower()
    if (
        rendered
        and len(rendered) <= 80
        and all(char.isalnum() or char == "_" for char in rendered)
    ):
        return rendered
    return fallback


def _dependency_blocked(
    checks: list[CapabilityPreflightCheck],
    capability: str,
    workflows: tuple[str, ...],
) -> bool:
    return any(
        check.capability == capability
        and check.status == "blocked"
        and bool(set(check.affected_workflows) & set(workflows))
        for check in checks
    )


@dataclass(frozen=True)
class _DrivePreflightTarget:
    folder_id: str
    service_account_path: str
    auth_mode: str
    oauth_token_path: str | None
    supports_all_drives: bool
    requires_child_write: bool


def _check_drive_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[list[CapabilityPreflightCheck], int]:
    settings = request.settings
    targets: dict[_DrivePreflightTarget, list[str]] = {}
    checks: list[CapabilityPreflightCheck] = []

    for workflow in workflows:
        if workflow == "publisher_discovery":
            inventory = request.publisher_inventory_settings
            if inventory is None:
                checks.append(
                    _capability_check(
                        "google_drive",
                        (workflow,),
                        "blocked",
                        _safe_reason_code(
                            request.publisher_inventory_config_error or "",
                            "publisher_inventory_configuration_missing",
                        ),
                        False,
                        "Resolve publisher discovery Drive settings",
                        required=True,
                    )
                )
                continue
            target = _DrivePreflightTarget(
                folder_id=inventory.drive_parent_folder_id,
                service_account_path=inventory.google_sa_path,
                auth_mode=inventory.drive_auth_mode,
                oauth_token_path=inventory.google_oauth_token_path,
                supports_all_drives=True,
                requires_child_write=True,
            )
        elif workflow in {"report_acquisition", "mailbox_delivery"}:
            browser = request.browser_settings
            if browser is None:
                checks.append(
                    _capability_check(
                        "google_drive",
                        (workflow,),
                        "blocked",
                        _safe_reason_code(
                            request.browser_settings_config_error or "",
                            "drive_upload_configuration_missing",
                        ),
                        False,
                        "Resolve the workflow's Drive archive settings",
                        required=True,
                    )
                )
                continue
            target = _DrivePreflightTarget(
                folder_id=browser.drive_upload_parent_folder_id,
                service_account_path=browser.drive_upload_google_sa_path,
                auth_mode=browser.drive_upload_auth_mode,
                oauth_token_path=browser.drive_upload_oauth_token_path,
                supports_all_drives=browser.drive_upload_supports_all_drives,
                requires_child_write=True,
            )
        else:
            target = _DrivePreflightTarget(
                folder_id=settings.gdrive_folder_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_token_path=settings.google_oauth_token_path,
                supports_all_drives=settings.drive_supports_all_drives,
                requires_child_write=False,
            )
        targets.setdefault(target, []).append(workflow)

    provider_calls = 0
    for target, target_workflows in targets.items():
        check, calls = _check_drive_target(
            request, target, tuple(target_workflows), deps, ctx
        )
        checks.append(check)
        provider_calls += calls
    return checks, provider_calls


def _check_drive_target(
    request: CapabilityPreflightRequest,
    target: _DrivePreflightTarget,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    if not str(target.folder_id or "").strip():
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_folder_id_missing",
                False,
                "Set the folder used by this workflow's Drive integration",
                required=True,
            ),
            0,
        )
    if target.auth_mode not in {"service_account", "oauth_user"}:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_auth_mode_invalid",
                False,
                "Set Drive auth mode to service_account or oauth_user",
                required=True,
            ),
            0,
        )
    credential_path = (
        target.service_account_path
        if target.auth_mode == "service_account"
        else str(target.oauth_token_path or "")
    )
    if not credential_path:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_credentials_missing",
                False,
                "Configure credentials for this workflow's selected Drive auth mode",
                required=True,
            ),
            0,
        )
    try:
        credential_available = deps.file_stat(
            FileStatRequest(
                schema_version="1.0",
                path=str(Path(credential_path).expanduser()),
            ),
            ctx,
        ).is_file
    except AppError as exc:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "drive_credentials_unavailable"),
                bool(exc.retryable),
                "Restore access to the configured Drive credential file",
                required=True,
            ),
            0,
        )
    if not credential_available:
        reason = (
            "drive_service_account_missing"
            if target.auth_mode == "service_account"
            else "drive_oauth_token_missing"
        )
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                reason,
                False,
                "Restore the configured Drive credential file",
                required=True,
            ),
            0,
        )
    if any(
        importlib.util.find_spec(package) is None
        for package in ("googleapiclient", "google_auth_httplib2")
    ):
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_dependency_missing",
                False,
                "Install the locked Google API dependencies",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "not_checked",
                "drive_live_probe_skipped",
                False,
                "Rerun with --live to verify the configured Drive folder",
                required=True,
            ),
            0,
        )
    try:
        result = deps.preflight_drive_folder_access(
            DriveFolderCapabilityPreflightRequest(
                schema_version="1.0",
                folder_id=target.folder_id,
                service_account_path=target.service_account_path,
                auth_mode=target.auth_mode,
                oauth_token_path=target.oauth_token_path,
                supports_all_drives=target.supports_all_drives,
                require_write_scope=target.requires_child_write,
                timeout_seconds=5.0,
            ),
            ctx,
        )
        calls = max(0, int(result.provider_calls))
        if not result.accessible:
            return (
                _capability_check(
                    "google_drive",
                    workflows,
                    "blocked",
                    "drive_folder_unavailable",
                    False,
                    "Verify the configured account has access to the Drive folder",
                    required=True,
                ),
                calls,
            )
        if result.is_folder is False:
            return (
                _capability_check(
                    "google_drive",
                    workflows,
                    "blocked",
                    "drive_target_not_folder",
                    False,
                    "Configure a Drive folder for this workflow",
                    required=True,
                ),
                calls,
            )
        if result.is_folder is None:
            return (
                _capability_check(
                    "google_drive",
                    workflows,
                    "not_checked",
                    "drive_target_type_unverified",
                    False,
                    "Rerun with a Drive preflight service that reports the target type",
                    required=True,
                ),
                calls,
            )
        if target.requires_child_write and result.can_add_children is not True:
            status: CapabilityStatus = (
                "blocked" if result.can_add_children is False else "not_checked"
            )
            return (
                _capability_check(
                    "google_drive",
                    workflows,
                    status,
                    "drive_folder_write_unavailable"
                    if result.can_add_children is False
                    else "drive_folder_write_capability_unverified",
                    False,
                    "Grant child creation access or verify the Drive capability",
                    required=True,
                ),
                calls,
            )
        reason_code = (
            "drive_folder_write_ready"
            if target.requires_child_write
            else "drive_folder_accessible"
        )
        return (
            _capability_check(
                "google_drive",
                workflows,
                "ready",
                reason_code,
                False,
                "continue",
                required=True,
            ),
            calls,
        )
    except AppError as exc:
        reported_calls = exc.context.get("provider_calls")
        calls = max(0, int(reported_calls)) if reported_calls is not None else 1
        scope_unverified = exc.code == "drive_preflight_scope_unverified"
        return (
            _capability_check(
                "google_drive",
                workflows,
                "not_checked"
                if scope_unverified
                else "degraded"
                if exc.retryable
                else "blocked",
                _safe_reason_code(exc.code, "drive_preflight_failed"),
                bool(exc.retryable),
                "Reauthorize Drive and rerun the preflight"
                if scope_unverified
                else "Rerun the preflight"
                if exc.retryable
                else "Check Drive credentials, scopes and folder access",
                required=True,
            ),
            calls,
        )
    except Exception:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "degraded",
                "drive_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            ),
            1,
        )


def _check_mailbox_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.mailbox_settings
    config_error = str(request.mailbox_settings_config_error or "").strip()
    if config_error:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "blocked",
                _safe_reason_code(config_error, "mailbox_configuration_invalid"),
                False,
                "Correct mailbox acquisition settings for the enabled mailbox workflow",
                required=True,
            ),
            0,
        )
    if settings is None:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "blocked",
                "mailbox_configuration_missing",
                False,
                "Load mailbox acquisition settings for the enabled mailbox queue",
                required=True,
            ),
            0,
        )
    provider = str(settings.provider or "").strip().lower()
    gmail_token_path = str(settings.gmail_oauth_token_path or "").strip()
    try:
        has_gmail = bool(
            gmail_token_path
            and deps.file_stat(
                FileStatRequest(
                    schema_version="1.0",
                    path=str(Path(gmail_token_path).expanduser()),
                ),
                ctx,
            ).is_file
        )
    except AppError:
        has_gmail = False
    has_imap = bool(
        settings.imap_host and settings.imap_user and settings.imap_password
    )
    configured_provider = (
        has_gmail
        if provider == "gmail"
        else has_imap
        if provider == "imap"
        else has_gmail or has_imap
    )
    if provider not in {"gmail", "imap", "auto"}:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "blocked",
                "mailbox_provider_invalid",
                False,
                "Set mailbox_acquisition.provider to gmail, imap or auto",
                required=True,
            ),
            0,
        )
    if not configured_provider:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "blocked",
                "mailbox_credentials_missing",
                False,
                "Configure credentials for the selected Gmail or IMAP mailbox provider",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "not_checked",
                "mailbox_live_probe_skipped",
                False,
                "Rerun with --live to verify mailbox authentication without reading messages",
                required=True,
            ),
            0,
        )
    if (
        provider == "gmail" or (provider == "auto" and has_gmail and not has_imap)
    ) and any(
        importlib.util.find_spec(package) is None
        for package in ("googleapiclient", "google_auth_httplib2")
    ):
        return (
            _capability_check(
                "mailbox",
                workflows,
                "blocked",
                "mailbox_dependency_missing",
                False,
                "Install the locked Google authentication dependencies",
                required=True,
            ),
            0,
        )
    try:
        result = deps.preflight_mailbox_access(settings, ctx)
        if not result.accessible:
            return (
                _capability_check(
                    "mailbox",
                    workflows,
                    "blocked",
                    "mailbox_access_denied",
                    False,
                    "Verify mailbox credentials and read-only mailbox access",
                    required=True,
                ),
                max(0, int(result.provider_calls)),
            )
        return (
            _capability_check(
                "mailbox",
                workflows,
                "ready",
                "mailbox_accessible",
                False,
                "continue",
                required=True,
            ),
            max(0, int(result.provider_calls)),
        )
    except AppError as exc:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "mailbox_preflight_failed"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check mailbox credentials and provider settings",
                required=True,
            ),
            max(0, int(exc.context.get("provider_calls", 0) or 0)),
        )
    except Exception:
        return (
            _capability_check(
                "mailbox",
                workflows,
                "degraded",
                "mailbox_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            ),
            1,
        )


def _check_browser_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    checks: list[CapabilityPreflightCheck],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.browser_settings
    config_error = str(request.browser_settings_config_error or "").strip()
    if config_error:
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                _safe_reason_code(config_error, "browser_configuration_invalid"),
                False,
                "Correct browser acquisition settings for the enabled workflow",
                required=True,
            ),
            0,
        )
    if settings is None:
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                "browser_configuration_missing",
                False,
                "Load browser acquisition settings for the enabled workflow",
                required=True,
            ),
            0,
        )
    runtime_check = next(
        (
            check
            for check in checks
            if check.capability == "browser_dependencies" and check.status == "blocked"
        ),
        None,
    )
    if runtime_check is not None:
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                runtime_check.reason_code,
                False,
                runtime_check.remediation,
                required=True,
            ),
            0,
        )
    try:
        browser_executable = deps.preflight_browser_executable(
            BrowserExecutableAvailabilityRequest(schema_version="1.0"), ctx
        )
    except AppError as exc:
        return (
            _capability_check(
                "browser",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "browser_executable_check_failed"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check the installed Chromium browser assets",
                required=True,
            ),
            0,
        )
    except Exception:
        return (
            _capability_check(
                "browser",
                workflows,
                "degraded",
                "browser_executable_check_failed",
                True,
                "Rerun the preflight",
                required=True,
            ),
            0,
        )
    if not browser_executable.available:
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                "browser_executable_missing",
                False,
                "Install the configured Chromium browser assets; this check does not launch a browser",
                required=True,
            ),
            0,
        )
    if not str(settings.model or "").strip() or not (
        str(settings.openai_api_key or "").strip()
        or str(settings.openrouter_api_key or "").strip()
    ):
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                "browser_llm_credentials_missing",
                False,
                "Configure a browser-use model and its provider credential",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                "browser",
                workflows,
                "not_checked",
                "browser_provider_probe_skipped",
                False,
                "Rerun with --live to verify the browser-use model provider; the browser is not launched",
                required=True,
            ),
            0,
        )
    if not str(settings.openai_api_key or "").strip():
        return (
            _capability_check(
                "browser",
                workflows,
                "not_checked",
                "browser_provider_probe_unsupported",
                False,
                "Configure the OpenAI browser-use provider for metadata-only live verification; OpenRouter fallback is not probed",
                required=True,
            ),
            0,
        )
    try:
        result = deps.preflight_openai_model(
            OpenAIModelPreflightRequest(
                schema_version="1.0",
                api_key=settings.openai_api_key,
                model=settings.model,
                timeout_seconds=min(float(settings.timeout_seconds or 5.0), 10.0),
            ),
            ctx,
        )
    except AppError as exc:
        return (
            _capability_check(
                "browser",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "browser_provider_unavailable"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check the browser-use OpenAI credential and configured model",
                required=True,
            ),
            1,
        )
    except Exception:
        return (
            _capability_check(
                "browser",
                workflows,
                "degraded",
                "browser_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            ),
            1,
        )
    if not bool(getattr(result, "accessible", False)):
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                "browser_model_unavailable",
                False,
                "Check the browser-use OpenAI credential and configured model",
                required=True,
            ),
            1,
        )
    return (
        _capability_check(
            "browser",
            workflows,
            "ready",
            "browser_runtime_and_model_available",
            False,
            "continue; local browser assets were checked without launching a browser",
            required=True,
        ),
        1,
    )


def _check_wordpress_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.publish_settings
    config_error = str(request.publish_settings_config_error or "").strip()
    if config_error:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "blocked",
                _safe_reason_code(config_error, "publish_configuration_invalid"),
                False,
                "Correct WordPress publication settings for the enabled workflow",
                required=True,
            ),
            0,
        )
    if settings is None:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "blocked",
                "wordpress_configuration_missing",
                False,
                "Load publication settings for the enabled WordPress workflow",
                required=True,
            ),
            0,
        )
    wp = settings.wp
    parsed_url = urlsplit(str(wp.site_url or "").strip())
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or not str(wp.post_type or "").strip()
    ):
        return (
            _capability_check(
                "wordpress",
                workflows,
                "blocked",
                "wordpress_configuration_invalid",
                False,
                "Set a valid WordPress REST site URL and post type",
                required=True,
            ),
            0,
        )
    if not ((wp.username and wp.app_password) or wp.bearer_token):
        return (
            _capability_check(
                "wordpress",
                workflows,
                "blocked",
                "wordpress_credentials_missing",
                False,
                "Configure a WordPress application password or bearer token",
                required=True,
            ),
            0,
        )
    if not request.live_checks:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "not_checked",
                "wordpress_live_probe_skipped",
                False,
                "Rerun with --live to verify authentication, post type, metadata and create permission",
                required=True,
            ),
            0,
        )
    if importlib.util.find_spec("requests") is None:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "blocked",
                "wordpress_dependency_missing",
                False,
                "Install the locked HTTP client dependency",
                required=True,
            ),
            0,
        )
    try:
        publisher_enabled = "wordpress_publish" in workflows
        category_update_enabled = "wordpress_category_update" in workflows
        projection_enabled = "wordpress_projection" in workflows
        required_post_types = (
            ("ml_report", "ml_briefing", "ml_signal")
            if publisher_enabled
            else ((str(wp.post_type),) if category_update_enabled else ())
        )
        required_post_type_capabilities: set[str] = set()
        if publisher_enabled:
            required_post_type_capabilities.add("create_posts")
            if str(wp.post_status or "").strip().lower() == "publish":
                required_post_type_capabilities.add("publish_posts")
        if category_update_enabled:
            required_post_type_capabilities.add("edit_posts")
        requirements = WordPressPublishCapabilityRequirements(
            schema_version="1.0",
            post_types=required_post_types,
            post_type_capabilities=tuple(sorted(required_post_type_capabilities)),
            user_capabilities=("manage_options",) if projection_enabled else (),
            rest_routes=(
                ("marketlense/v1/intelligence-projection",)
                if projection_enabled
                else ()
            ),
        )
        if not required_post_types and not projection_enabled:
            # Preserve the legacy check for any future publish profile until its
            # concrete target requirements are declared above.
            required_post_types = (str(wp.post_type),)
            required_post_type_capabilities.update({"create_posts"})
            if str(wp.post_status or "").strip().lower() == "publish":
                required_post_type_capabilities.add("publish_posts")
            requirements = WordPressPublishCapabilityRequirements(
                schema_version="1.0",
                post_types=required_post_types,
                post_type_capabilities=tuple(sorted(required_post_type_capabilities)),
            )
        result = deps.preflight_wordpress_publish_target(settings, ctx, requirements)
        required_capabilities = set(requirements.post_type_capabilities)
        verified = set(getattr(result, "verified_capabilities", ()))
        verified_post_types = set(getattr(result, "verified_post_types", ()))
        verified_user_capabilities = set(
            getattr(result, "verified_user_capabilities", ())
        )
        verified_rest_routes = set(getattr(result, "verified_rest_routes", ()))
        requirements_verified = (
            required_capabilities.issubset(verified)
            and set(requirements.post_types).issubset(verified_post_types)
            and set(requirements.user_capabilities).issubset(verified_user_capabilities)
            and set(requirements.rest_routes).issubset(verified_rest_routes)
        )
        if (
            not bool(getattr(result, "authenticated", False))
            or not requirements_verified
        ):
            return (
                _capability_check(
                    "wordpress",
                    workflows,
                    "blocked",
                    "wordpress_capability_unverified",
                    False,
                    "Verify WordPress route registration, required capabilities, and writable metadata for every enabled target",
                    required=True,
                ),
                max(0, int(getattr(result, "provider_calls", 1) or 0)),
            )
        return (
            _capability_check(
                "wordpress",
                workflows,
                "ready",
                "wordpress_publish_capability_ready",
                False,
                "continue",
                required=True,
            ),
            max(0, int(getattr(result, "provider_calls", 1) or 0)),
        )
    except AppError as exc:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "wordpress_preflight_failed"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check WordPress authentication, REST registration, metadata and permissions",
                required=True,
            ),
            max(1, int(exc.context.get("provider_calls", 0) or 0)),
        )
    except Exception:
        return (
            _capability_check(
                "wordpress",
                workflows,
                "degraded",
                "wordpress_provider_unavailable",
                True,
                "Rerun the preflight",
                required=True,
            ),
            1,
        )


class _Callable2(Protocol):
    def __call__(self, request, ctx: RunContext): ...


@dataclass(frozen=True)
class PipelinePreflightDependencies:
    file_stat: _Callable2
    write_bytes: _Callable2
    delete_file: _Callable2
    load_prompt_set: _Callable2
    preflight_drive_write_access: _Callable2
    preflight_wordpress_publish_target: Callable[[PublishSettings, RunContext], object]
    write_exclusive_bytes: _Callable2 | None = None


def default_dependencies() -> PipelinePreflightDependencies:
    return PipelinePreflightDependencies(
        file_stat=file_service.file_stat,
        write_bytes=file_service.write_bytes,
        delete_file=file_service.delete_file,
        load_prompt_set=prompt_service.load_prompt_set,
        preflight_drive_write_access=drive_service.preflight_drive_write_access,
        preflight_wordpress_publish_target=wordpress_service.preflight_publish_target,
        write_exclusive_bytes=lambda request, ctx: file_service.write_bytes(
            request, ctx, require_absent=True
        ),
    )


def report_pipeline_prompt_namespaces(settings) -> list[str]:
    namespaces = {
        "report_vs/taxonomy",
        "report_vs/taxonomy_repair",
        "report_vs/context_category_fit",
        "report_vs/context_category_fit_repair",
        "report_vs/artifacts/cover_semantics",
        "report_vs/artifacts/cover_semantics_repair",
        "rank_candidates",
    }
    registry = list(getattr(settings, "evidence_pack_registry", []) or [])
    for pack_name in registry:
        suffix = str(pack_name or "").strip()
        if not suffix:
            continue
        if suffix == "doc_map":
            namespaces.add("report_vs/doc_map")
        else:
            namespaces.add(f"report_vs/evidence_packs/{suffix}")
    if bool(getattr(settings, "crop_refine_enabled", False)):
        namespaces.add("rank_candidates/crop_refine")
    if bool(getattr(settings, "pdf_text_ocr_enabled", False)):
        namespaces.add(str(getattr(settings, "pdf_text_ocr_prompt_namespace", "")))
    if bool(getattr(settings, "figure_caption_enabled", False)):
        namespaces.add(str(getattr(settings, "figure_caption_prompt_namespace", "")))
    return sorted(namespace for namespace in namespaces if namespace)


def preflight_report_pipeline(
    settings,
    ctx: RunContext,
    *,
    planned_side_effects: list[str] | None = None,
    require_live_endpoints: bool = False,
    dependencies: PipelinePreflightDependencies | None = None,
) -> PipelinePreflightReport:
    return run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=planned_side_effects or ["pdf", "model"],
            settings=settings,
            prompt_namespaces=report_pipeline_prompt_namespaces(settings),
            require_llm=True,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=require_live_endpoints,
        ),
        ctx,
        dependencies=dependencies,
    )


def run_pipeline_preflight(
    request: PipelinePreflightRequest,
    ctx: RunContext,
    *,
    dependencies: PipelinePreflightDependencies | None = None,
) -> PipelinePreflightReport:
    deps = dependencies or default_dependencies()
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="pipeline_preflight_start",
            module=logger.name,
            fields={
                "workflow": request.workflow,
                "planned_side_effects": list(request.planned_side_effects),
                "prompt_namespace_count": len(request.prompt_namespaces),
                "require_live_endpoints": request.require_live_endpoints,
            },
        )
    )
    checks: list[PipelinePreflightCheck] = []
    checks.extend(_check_canary_mutable_state_root(request))
    if not any(check.status == "blocker" for check in checks):
        checks.extend(_check_local_paths(request, ctx, deps))
        checks.extend(_check_llm(request))
        checks.extend(_check_llm_policy_coverage(request))
        checks.extend(_check_prompts(request, ctx, deps))
        checks.extend(_check_drive(request, ctx, deps))
        checks.extend(_check_browser(request))
        checks.extend(_check_publish(request, ctx, deps))
    report = _build_report(request, checks)
    if report.expensive_side_effects_allowed:
        _persist_resolved_policy_matrix(report, request, ctx, deps)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="pipeline_preflight_complete",
            module=logger.name,
            fields={
                "workflow": report.workflow,
                "passed": report.passed,
                "blocker_count": report.blocker_count,
                "warning_count": report.warning_count,
                "auto_fixed_count": report.auto_fixed_count,
                "expensive_side_effects_allowed": report.expensive_side_effects_allowed,
                "next_actions": list(report.next_actions),
            },
        )
    )
    return report


def _check_canary_mutable_state_root(
    request: PipelinePreflightRequest,
) -> list[PipelinePreflightCheck]:
    """Reject canary accounting or runtime state that escapes its declared root."""

    raw_root = str(getattr(request.settings, "canary_state_root", "") or "").strip()
    if not raw_root:
        return []
    root = Path(raw_root).resolve()
    mutable_paths = (
        ("output_dir", request.settings.output_dir),
        ("cache_dir", request.settings.cache_dir),
        ("state_db", request.settings.state_db),
        ("reports_db", request.settings.reports_db),
        ("signal_store_db", request.settings.signal_store_db),
        ("ingest_lock_path", request.settings.ingest_lock_path),
        ("usage_db_path", request.settings.usage_db_path),
        ("cost_ledger_path", request.settings.cost_ledger_path),
        ("cost_daily_path", request.settings.cost_daily_path),
    )
    for name, raw_path in mutable_paths:
        resolved_path = Path(str(raw_path)).resolve()
        try:
            resolved_path.relative_to(root)
        except ValueError:
            return [
                _check(
                    f"canary_mutable_state:{name}",
                    "blocker",
                    "canary_mutable_state_outside_root",
                    "Canary mutable state path is outside its isolated state root",
                    f"set_canary_mutable_path:{name}",
                    metadata={
                        "canary_state_root": str(root),
                        "path": str(resolved_path),
                    },
                )
            ]
    return [
        _check(
            "canary_mutable_state_root",
            "pass",
            "canary_mutable_state_isolated",
            "Every mutable canary state path is under the isolated state root",
            "continue",
            metadata={"canary_state_root": str(root)},
        )
    ]


def assert_expensive_side_effects_allowed(
    report: PipelinePreflightReport,
    ctx: RunContext,
) -> None:
    if report.expensive_side_effects_allowed:
        return
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="pipeline_preflight_blocked",
            module=logger.name,
            fields={
                "workflow": report.workflow,
                "blocker_count": report.blocker_count,
                "next_actions": list(report.next_actions),
                "blocker_codes": [check.code for check in report.blockers],
            },
        )
    )
    raise AppError(
        code="pipeline_preflight_blocked",
        message="Pipeline preflight blocked expensive side effects",
        retryable=False,
        severity="error",
        context={
            "workflow": report.workflow,
            "blocker_count": report.blocker_count,
            "next_actions": list(report.next_actions),
            "blocker_codes": [check.code for check in report.blockers],
        },
    )


def _check_local_paths(
    request: PipelinePreflightRequest,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> list[PipelinePreflightCheck]:
    settings = request.settings
    checks: list[PipelinePreflightCheck] = []
    paths = [
        ("output_dir", settings.output_dir),
        ("cache_dir", settings.cache_dir),
        ("state_db", settings.state_db),
        ("reports_db", settings.reports_db),
    ]
    usage_db_path = str(getattr(settings, "usage_db_path", "") or "").strip()
    if usage_db_path:
        paths.append(("usage_db", usage_db_path))
    for label, raw_path in paths:
        checks.append(_probe_writable_path(label, raw_path, ctx, deps))
    return checks


def _probe_writable_path(
    label: str,
    raw_path: str,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> PipelinePreflightCheck:
    path = Path(raw_path)
    is_directory_target = label in {"output_dir", "cache_dir"}
    probe_dir = path if is_directory_target else path.parent
    probe_path = probe_dir / f".marketlense-preflight-{label}-{uuid.uuid4().hex}.tmp"
    existed_before = False
    write_reason = ""
    cleanup_reason = ""
    owned = False
    try:
        existed_before = deps.file_stat(
            FileStatRequest(schema_version="1.0", path=str(probe_dir)),
            ctx,
        ).exists
        if deps.file_stat(
            FileStatRequest(schema_version="1.0", path=str(probe_path)),
            ctx,
        ).exists:
            return _check(
                f"path_writable:{label}",
                "blocker",
                "probe_path_collision",
                f"Probe path collided for {label}",
                f"fix_path_permissions:{label}",
                metadata={"path": str(raw_path)},
            )
        owned = True
        write_probe = getattr(deps, "write_exclusive_bytes", None)
        if not callable(write_probe):
            write_probe = deps.write_bytes
        write_probe(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(probe_path),
                content=b"preflight",
                make_parents=True,
            ),
            ctx,
        )
    except AppError as exc:
        if exc.code == "file_write_conflict":
            owned = False
        write_reason = exc.code
    finally:
        if owned:
            try:
                deleted = deps.delete_file(
                    DeleteFileRequest(
                        schema_version="1.0", path=str(probe_path), missing_ok=True
                    ),
                    ctx,
                )
                if not deleted.deleted:
                    cleanup_reason = "probe_cleanup_failed"
            except AppError:
                cleanup_reason = "probe_cleanup_failed"
    if write_reason or cleanup_reason:
        reason = cleanup_reason or write_reason or "path_probe_failed"
        return _check(
            f"path_writable:{label}",
            "blocker",
            reason,
            f"Path is not writable for {label}",
            f"fix_path_permissions:{label}",
            metadata={"path": str(raw_path)},
        )
    return _check(
        f"path_writable:{label}",
        "pass" if existed_before else "auto_fixed",
        f"{label}_writable" if existed_before else f"{label}_created",
        f"Path is writable for {label}",
        "continue",
        auto_fix_applied=not existed_before,
        metadata={"path": str(raw_path)},
    )


def _check_llm(request: PipelinePreflightRequest) -> list[PipelinePreflightCheck]:
    if not request.require_llm:
        return []
    settings = request.settings
    if not str(settings.openai_api_key or "").strip():
        return [
            _check(
                "openai_api_key",
                "blocker",
                "openai_missing_api_key",
                "OpenAI API key is missing",
                "set_OPENAI_API_KEY",
            )
        ]
    if not str(settings.openai_model or "").strip():
        return [
            _check(
                "openai_model",
                "blocker",
                "openai_model_missing",
                "OpenAI model setting is missing",
                "set_openai_model",
            )
        ]
    return [
        _check(
            "openai_settings",
            "pass",
            "openai_settings_present",
            "OpenAI settings are present",
            "continue",
            metadata={"model": str(settings.openai_model)},
        )
    ]


def _check_llm_policy_coverage(
    request: PipelinePreflightRequest,
) -> list[PipelinePreflightCheck]:
    """Resolve every reachable provider policy before any model boundary is used."""
    if not request.require_llm:
        return []
    settings = request.settings
    raw_policies = getattr(settings, "llm_execution_policies", {})
    if not isinstance(raw_policies, dict) or not raw_policies:
        # Isolated unit/in-process callers can still use the historical injected
        # compatibility seam. Live configuration carries an explicit policy map
        # and therefore always takes the fail-closed branch below.
        return []
    try:
        policies = execution_policies_from_config(
            raw_policies,
            model_overrides=getattr(settings, "openai_models", {}),
            legacy_routing=getattr(settings, "llm_routing", {}),
            default_model=str(settings.openai_model),
            default_temperature=float(settings.temperature),
            default_seed=getattr(settings, "openai_seed", None),
            default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
        )
        decisions = preflight_execution_policy_coverage(
            policies,
            default_model=str(settings.openai_model),
            default_temperature=float(settings.temperature),
            default_seed=getattr(settings, "openai_seed", None),
            default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
        )
    except AppError as exc:
        return [
            _check(
                "llm_execution_policy_matrix",
                "blocker",
                exc.code,
                "LLM execution-policy coverage is incomplete",
                "repair_llm_execution_policy_coverage",
                metadata={},
            )
        ]
    return [
        _check(
            "llm_execution_policy_matrix",
            "pass",
            "llm_execution_policy_coverage_complete",
            "Every registered production LLM namespace resolved before provider I/O",
            "continue",
            metadata={
                "namespace_count": len(decisions),
                "policy_hashes": sorted(
                    {decision.policy_hash for decision in decisions}
                ),
                "resolved_matrix": execution_policy_matrix(decisions),
            },
        )
    ]


def _persist_resolved_policy_matrix(
    report: PipelinePreflightReport,
    request: PipelinePreflightRequest,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> None:
    """Retain the exact non-sensitive policy resolution used before provider I/O."""

    matrix_check = next(
        (
            check
            for check in report.checks
            if check.check_name == "llm_execution_policy_matrix"
        ),
        None,
    )
    if matrix_check is None or matrix_check.status != "pass":
        return
    matrix = matrix_check.metadata.get("resolved_matrix")
    if not isinstance(matrix, list):
        return
    path = (
        Path(str(request.settings.output_dir))
        / "preflight"
        / f"{ctx.run_id}.llm_policy_matrix.json"
    )
    payload = {
        "schema_version": "1.0",
        "run_id": str(ctx.run_id),
        "workflow": request.workflow,
        "configuration_hash": str(getattr(ctx, "configuration_hash", "") or ""),
        "policy_hash": str(getattr(ctx, "policy_hash", "") or ""),
        "producer_build_identity": str(getattr(ctx, "producer_commit_sha", "") or ""),
        "resolved_matrix": matrix,
    }
    try:
        deps.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(path),
                content=json.dumps(
                    payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                make_parents=True,
            ),
            ctx,
        )
    except AppError as exc:
        raise AppError(
            code="llm_execution_policy_matrix_persist_failed",
            message="Resolved LLM execution-policy matrix could not be retained",
            retryable=False,
            cause=exc,
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="llm_execution_policy_matrix_persisted",
            module=logger.name,
            fields={
                "path": str(path),
                "namespace_count": len(matrix),
                "policy_hash_count": len(
                    {
                        str(item.get("policy_hash") or "")
                        for item in matrix
                        if isinstance(item, dict)
                    }
                ),
            },
        )
    )


def _check_prompts(
    request: PipelinePreflightRequest,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> list[PipelinePreflightCheck]:
    checks: list[PipelinePreflightCheck] = []
    seen: set[str] = set()
    for namespace in request.prompt_namespaces:
        normalized = str(namespace or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            prompt_set = deps.load_prompt_set(
                PromptLoadRequest(
                    schema_version="1.0",
                    namespace=normalized,
                    reload_if_changed=True,
                    force_reload=False,
                ),
                ctx,
            )
        except AppError as exc:
            checks.append(
                _check(
                    f"prompt_namespace:{normalized}",
                    "blocker",
                    exc.code,
                    f"Prompt namespace is not usable: {normalized}",
                    f"fix_prompt_namespace:{normalized}",
                    metadata={"namespace": normalized},
                )
            )
        else:
            checks.append(
                _check(
                    f"prompt_namespace:{normalized}",
                    "pass",
                    "prompt_namespace_ready",
                    f"Prompt namespace is usable: {normalized}",
                    "continue",
                    metadata={
                        "namespace": normalized,
                        "system_path": prompt_set.system.path,
                        "user_path": prompt_set.user.path,
                    },
                )
            )
    return checks


def _check_drive(
    request: PipelinePreflightRequest,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> list[PipelinePreflightCheck]:
    if not request.require_drive:
        return []
    settings = request.settings
    if not str(settings.gdrive_folder_id or "").strip():
        return [
            _check(
                "drive_folder",
                "blocker",
                "drive_folder_missing",
                "Drive folder ID is missing",
                "set_GDRIVE_FOLDER_ID",
            )
        ]
    if not request.require_live_endpoints:
        return [
            _check(
                "drive_live_preflight",
                "warning",
                "drive_live_preflight_skipped",
                "Drive live endpoint preflight was skipped",
                "run_live_preflight_before_drive_side_effects",
            )
        ]
    try:
        response = deps.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id=settings.gdrive_folder_id,
                service_account_path=settings.google_sa_path,
                supports_all_drives=settings.drive_supports_all_drives,
                include_items_from_all_drives=settings.drive_include_items_from_all_drives,
                drive_id=settings.drive_id,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
            ),
            ctx,
        )
    except AppError as exc:
        return [
            _check(
                "drive_write_preflight",
                "blocker",
                exc.code,
                "Drive write preflight failed",
                "repair_drive_credentials_or_folder",
                metadata={"folder_id": settings.gdrive_folder_id},
            )
        ]
    if bool(response.credentials_refreshed):
        return [
            _check(
                "drive_write_preflight",
                "auto_fixed",
                "drive_oauth_credentials_refreshed",
                "Drive OAuth credentials were refreshed",
                "continue",
                auto_fix_applied=True,
                metadata={"folder_id": settings.gdrive_folder_id},
            )
        ]
    return [
        _check(
            "drive_write_preflight",
            "pass",
            "drive_write_preflight_passed",
            "Drive write preflight passed",
            "continue",
            metadata={"folder_id": settings.gdrive_folder_id},
        )
    ]


def _check_browser(request: PipelinePreflightRequest) -> list[PipelinePreflightCheck]:
    if not request.require_browser:
        return []
    if request.require_live_endpoints:
        return [
            _check(
                "browser_dependency",
                "pass",
                "browser_dependency_live_check_ready",
                "Browser dependency live check is delegated to browser service preflight",
                "continue",
            )
        ]
    return [
        _check(
            "browser_dependency",
            "warning",
            "browser_dependency_live_check_skipped",
            "Browser dependency live check was skipped",
            "run_browser_preflight_before_browser_agent",
        )
    ]


def _check_publish(
    request: PipelinePreflightRequest,
    ctx: RunContext,
    deps: PipelinePreflightDependencies,
) -> list[PipelinePreflightCheck]:
    if not request.require_publish:
        return []
    settings = request.publish_settings
    if settings is None:
        return [
            _check(
                "wordpress_publish_settings",
                "blocker",
                "wordpress_publish_settings_missing",
                "Publish settings are required for publish preflight",
                "load_publish_settings",
            )
        ]
    wp = settings.wp
    has_auth = bool(str(wp.bearer_token or "").strip()) or (
        bool(str(wp.username or "").strip())
        and bool(str(wp.app_password or "").strip())
    )
    if not str(wp.site_url or "").strip() or not has_auth:
        return [
            _check(
                "wordpress_credentials",
                "blocker",
                "wordpress_credentials_missing",
                "WordPress site or credentials are missing",
                "set_wordpress_credentials",
            )
        ]
    if not request.require_live_endpoints:
        return [
            _check(
                "wordpress_publish_target",
                "warning",
                "wordpress_live_preflight_skipped",
                "WordPress live publish-target check was skipped",
                "run_live_preflight_before_publish",
            )
        ]
    try:
        deps.preflight_wordpress_publish_target(settings, ctx)
    except AppError as exc:
        return [
            _check(
                "wordpress_publish_target",
                "blocker",
                exc.code,
                "WordPress publish target preflight failed",
                "repair_wordpress_publish_target",
            )
        ]
    return [
        _check(
            "wordpress_publish_target",
            "pass",
            "wordpress_publish_target_ready",
            "WordPress publish target is reachable",
            "continue",
        )
    ]


def _build_report(
    request: PipelinePreflightRequest,
    checks: list[PipelinePreflightCheck],
) -> PipelinePreflightReport:
    blockers = [check for check in checks if check.status == "blocker"]
    warnings = [check for check in checks if check.status == "warning"]
    auto_fixed = [check for check in checks if check.status == "auto_fixed"]
    next_actions = []
    for check in (*blockers, *warnings, *auto_fixed):
        if check.next_action and check.next_action not in {"continue"}:
            next_actions.append(check.next_action)
    if blockers:
        next_actions.append("rerun_preflight")
    else:
        next_actions.append("continue_pipeline")
    deduped_actions = list(dict.fromkeys(next_actions))
    passed = not blockers
    return PipelinePreflightReport(
        schema_version="1.0",
        workflow=request.workflow,
        planned_side_effects=list(request.planned_side_effects),
        passed=passed,
        expensive_side_effects_allowed=passed,
        blocker_count=len(blockers),
        warning_count=len(warnings),
        auto_fixed_count=len(auto_fixed),
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        auto_fixable_issues=auto_fixed,
        next_actions=deduped_actions,
    )


def _check(
    check_name: str,
    status: PreflightCheckStatus,
    code: str,
    message: str,
    next_action: str,
    *,
    auto_fix_applied: bool = False,
    metadata: dict[str, object] | None = None,
) -> PipelinePreflightCheck:
    return PipelinePreflightCheck(
        schema_version="1.0",
        check_name=check_name,
        status=status,
        code=code,
        message=message,
        next_action=next_action,
        auto_fix_applied=auto_fix_applied,
        metadata=dict(metadata or {}),
    )
