from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, cast
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserExecutableAvailabilityRequest,
    BrowserExecutableAvailabilityResponse,
)
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
    WriteBytesResponse,
    WriteBytesRequest,
)
from src.contracts.pipeline_preflight import (
    CapabilityStatus,
    CapabilityPreflightCheck,
    CapabilityPreflightReport,
    CapabilityPreflightRequest,
    PipelinePreflightCheck,
    PipelinePreflightReport,
    PipelinePreflightRequest,
    PreflightCheckStatus,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.llm import (
    OpenAIModelPreflightRequest,
    OpenRouterModelPreflightRequest,
)
from src.contracts.mailbox_acquisition import (
    MailboxAccessPreflightResponse,
    MailboxAcquisitionSettings,
)
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import (
    SqliteCapabilityInspectionRequest,
    SqliteCapabilityInspectionResponse,
)
from src.contracts.workflow_queue import WorkflowQueuePolicy
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
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    execution_policy_matrix,
    preflight_execution_policy_coverage,
)

logger = logging.getLogger("market_lense.pipeline_preflight_orchestrator")


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


_QUEUE_PREFLIGHT_PROFILES: dict[str, str | None] = {
    "publisher_discovery": "publisher_inventory",
    "report_acquisition": "report_download",
    "mailbox_delivery": "report_download",
    "source_ingest": None,
    "report_selection": "report_generation",
    "report_analysis": "report_generation",
    "report_render": None,
    "analytics_projection": None,
    "claim_embedding": None,
    "signal_candidate": None,
    "signal_generation": None,
    "briefing_opportunity": None,
    "briefing_generation": "cross_report_analysis",
    "cover_generation": None,
    "publication_readiness": None,
    "wordpress_publish": "publishing",
    "wordpress_projection": "wordpress_sync",
    "artifact_repair": "report_generation",
    "source_revalidation": "browser_acquisition",
    "malformed_pdf_revalidation": None,
    "recategorization": "report_generation",
    "vector_retention": "report_generation",
    "wordpress_category_update": "publishing",
    "public_render_repair": "report_generation",
    "cost_reconciliation": None,
    "release_evidence_generation": None,
}

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
    load_prompt_set: _Callable2
    preflight_openai_model: Callable[[OpenAIModelPreflightRequest, RunContext], object]
    preflight_openrouter_model: Callable[
        [OpenRouterModelPreflightRequest, RunContext], object
    ]
    preflight_drive_folder_access: _Callable2
    preflight_mailbox_access: Callable[
        [MailboxAcquisitionSettings, RunContext], MailboxAccessPreflightResponse
    ]
    preflight_wordpress_publish_target: Callable[[PublishSettings, RunContext], object]


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
        load_prompt_set=prompt_service.load_prompt_set,
        preflight_openai_model=llm_service.preflight_openai_model,
        preflight_openrouter_model=llm_service.preflight_openrouter_model,
        preflight_drive_folder_access=drive_service.preflight_drive_folder_access,
        preflight_mailbox_access=mailbox_acquisition_service.preflight_mailbox_access,
        preflight_wordpress_publish_target=wordpress_service.preflight_publish_capability,
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
    workflows = derive_capability_workflows(
        profile_name=request.profile_name,
        supervisor_enabled=request.workflow_control.supervisor.enabled,
        queue_policies=request.queue_policies,
    )
    checks: list[CapabilityPreflightCheck] = []
    provider_calls = 0
    profiles: dict[str, object] = {}
    workflow_profiles: dict[str, str] = {}

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
        elif workflow in _QUEUE_PREFLIGHT_PROFILES:
            profile_name = _QUEUE_PREFLIGHT_PROFILES[workflow]
            if profile_name is None:
                workflow_profiles[workflow] = "local_runtime"
                continue
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

    llm_workflows = _profile_workflows(profiles, workflow_profiles, "require_llm")
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
        workflow for workflow in workflows if workflow == "claim_embedding"
    )
    openai_workflows = tuple(sorted(set(llm_workflows) | set(embedding_workflows)))
    drive_workflows = _profile_workflows(profiles, workflow_profiles, "require_drive")
    if request.browser_settings is not None and not (
        request.browser_settings.drive_upload_enabled
        and request.browser_settings.drive_upload_required
    ):
        drive_workflows = tuple(
            workflow
            for workflow in drive_workflows
            if workflow not in {"report_acquisition", "mailbox_delivery"}
        )
    browser_workflows = _profile_workflows(
        profiles, workflow_profiles, "require_browser"
    )
    wordpress_workflows = _profile_workflows(
        profiles, workflow_profiles, "require_publish"
    )
    mailbox_workflows = tuple(
        workflow for workflow in workflows if workflow == "mailbox_delivery"
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
        _check_capability_configuration(request, workflows, workflow_profiles)
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
            provider_calls += 1
            try:
                deps.preflight_openai_model(
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

    publisher_checks, calls = _check_publisher_inventory_model(
        request,
        tuple(workflow for workflow in workflows if workflow == "publisher_discovery"),
        deps,
        ctx,
    )
    checks.extend(publisher_checks)
    provider_calls += calls

    if drive_workflows:
        drive_check, calls = _check_drive_capability(
            request, drive_workflows, deps, ctx
        )
        checks.append(drive_check)
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
            request, browser_workflows, deps, ctx
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
        elif any(status in {"degraded", "not_checked"} for status in relevant):
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
    elif any(
        status in {"degraded", "not_checked"} for status in global_required_statuses
    ) or any(status != "ready" for status in workflow_statuses.values()):
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
                else "Check OPENAI_API_KEY and the configured embedding model",
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
                "Check OPENAI_API_KEY and the configured embedding model",
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
            if workflow not in _QUEUE_PREFLIGHT_PROFILES
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
    python_ok = bool(sys.executable) and sys.version_info >= (3, 11)
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
    if browser_workflows:
        dependency_groups.append(
            ("browser_dependencies", browser_workflows, ("browser_use", "playwright"))
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
    ocr_workflows = tuple(
        workflow for workflow in workflows if workflow in _OCR_WORKFLOWS
    )
    if ocr_workflows and bool(getattr(settings, "pdf_text_ocr_enabled", False)):
        tesseract_available = deps.inspect_executable(
            ExecutableAvailabilityRequest(
                schema_version="1.0", executable_name="tesseract"
            ),
            ctx,
        ).available
        checks.append(
            _capability_check(
                "ocr_executable",
                ocr_workflows,
                "ready" if tesseract_available else "blocked",
                "tesseract_available" if tesseract_available else "tesseract_missing",
                False,
                "Install Tesseract or disable the OCR fallback if the workflow does not use it",
                required=True,
            )
        )
    else:
        checks.append(
            _capability_check(
                "ocr_executable",
                (),
                "not_required",
                "ocr_not_required",
                False,
                "OCR fallback is disabled",
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
                else _QUEUE_PREFLIGHT_PROFILES.get(workflow) or "local_runtime"
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
            else _QUEUE_PREFLIGHT_PROFILES.get(workflow) or "local_runtime"
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
        lock_path = str(request.settings.ingest_lock_path or "").strip()
        add_path(
            str(Path(lock_path).expanduser().parent) if lock_path else "",
            report_workflows,
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
        deps.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=probe_path,
                content=b"capability-preflight",
                make_parents=False,
            ),
            ctx,
        )
        deps.delete_file(
            DeleteFileRequest(schema_version="1.0", path=probe_path, missing_ok=True),
            ctx,
        )
    except AppError as exc:
        return False, _safe_reason_code(exc.code, "storage_not_writable")
    return True, "storage_writable"


def _check_capability_databases(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    report_workflows: tuple[str, ...],
    llm_workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    checks: list[CapabilityPreflightCheck],
    ctx: RunContext,
) -> int:
    del llm_workflows
    if not workflows:
        return 0
    stores: list[tuple[str, str, tuple[str, ...]]] = [
        ("state_db", request.settings.state_db, workflows)
    ]
    if report_workflows:
        stores.append(("reports_db", request.settings.reports_db, report_workflows))
    if any(request.queue_policies.get(workflow) for workflow in workflows):
        stores.append(("llm_usage_db", request.settings.usage_db_path, workflows))
    provider_calls = 0
    for database_key, path, affected_workflows in stores:
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
                f"{database_key}",
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


def _check_drive_capability(
    request: CapabilityPreflightRequest,
    workflows: tuple[str, ...],
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.settings
    if not str(settings.gdrive_folder_id or "").strip():
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_folder_id_missing",
                False,
                "Set ingest.gdrive_folder_id for the configured Drive source",
                required=True,
            ),
            0,
        )
    if settings.drive_auth_mode not in {"service_account", "oauth_user"}:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_auth_mode_invalid",
                False,
                "Set drive_auth_mode to service_account or oauth_user",
                required=True,
            ),
            0,
        )
    credential_path = (
        settings.google_sa_path
        if settings.drive_auth_mode == "service_account"
        else str(settings.google_oauth_token_path or "")
    )
    if not credential_path:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "blocked",
                "drive_credentials_missing",
                False,
                "Configure the credential file for the selected Drive auth mode",
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
            if settings.drive_auth_mode == "service_account"
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
                "Rerun with --live to verify read access to the configured Drive folder",
                required=True,
            ),
            0,
        )
    if importlib.util.find_spec("googleapiclient") is None:
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
    try:
        result = deps.preflight_drive_folder_access(
            DriveFolderCapabilityPreflightRequest(
                schema_version="1.0",
                folder_id=settings.gdrive_folder_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_token_path=settings.google_oauth_token_path,
                supports_all_drives=settings.drive_supports_all_drives,
                include_items_from_all_drives=settings.drive_include_items_from_all_drives,
                drive_id=settings.drive_id,
                timeout_seconds=5.0,
            ),
            ctx,
        )
        if not result.accessible:
            return (
                _capability_check(
                    "google_drive",
                    workflows,
                    "blocked",
                    "drive_folder_unavailable",
                    False,
                    "Verify the configured account has read access to the Drive folder",
                    required=True,
                ),
                max(0, int(result.provider_calls)),
            )
        return (
            _capability_check(
                "google_drive",
                workflows,
                "ready",
                "drive_folder_accessible",
                False,
                "continue",
                required=True,
            ),
            max(0, int(result.provider_calls)),
        )
    except AppError as exc:
        return (
            _capability_check(
                "google_drive",
                workflows,
                "degraded" if exc.retryable else "blocked",
                _safe_reason_code(exc.code, "drive_preflight_failed"),
                bool(exc.retryable),
                "Rerun the preflight"
                if exc.retryable
                else "Check Drive credentials, scopes and folder access",
                required=True,
            ),
            1,
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
            max(1, int(exc.context.get("provider_calls", 0) or 0)),
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
    deps: CapabilityPreflightDependencies,
    ctx: RunContext,
) -> tuple[CapabilityPreflightCheck, int]:
    settings = request.browser_settings
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
    if (
        importlib.util.find_spec("browser_use") is None
        or importlib.util.find_spec("playwright") is None
    ):
        return (
            _capability_check(
                "browser",
                workflows,
                "blocked",
                "browser_runtime_dependency_missing",
                False,
                "Install the locked browser-use and Playwright dependencies",
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
        result = deps.preflight_wordpress_publish_target(settings, ctx)
        required_capabilities = {"create_posts"}
        if str(wp.post_status or "").strip().lower() == "publish":
            required_capabilities.add("publish_posts")
        verified = set(getattr(result, "verified_capabilities", ()))
        if not bool(
            getattr(result, "authenticated", False)
        ) or not required_capabilities.issubset(verified):
            return (
                _capability_check(
                    "wordpress",
                    workflows,
                    "blocked",
                    "wordpress_capability_unverified",
                    False,
                    "Verify the configured identity can create the selected post type and status",
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


def default_dependencies() -> PipelinePreflightDependencies:
    return PipelinePreflightDependencies(
        file_stat=file_service.file_stat,
        write_bytes=file_service.write_bytes,
        delete_file=file_service.delete_file,
        load_prompt_set=prompt_service.load_prompt_set,
        preflight_drive_write_access=drive_service.preflight_drive_write_access,
        preflight_wordpress_publish_target=wordpress_service.preflight_publish_target,
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
    probe_path = probe_dir / f".marketlense-preflight-{label}.tmp"
    try:
        existed_before = deps.file_stat(
            FileStatRequest(schema_version="1.0", path=str(probe_dir)),
            ctx,
        ).exists
        deps.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(probe_path),
                content=b"preflight",
                make_parents=True,
            ),
            ctx,
        )
        deps.delete_file(
            DeleteFileRequest(schema_version="1.0", path=str(probe_path)),
            ctx,
        )
    except AppError as exc:
        return _check(
            f"path_writable:{label}",
            "blocker",
            exc.code,
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
