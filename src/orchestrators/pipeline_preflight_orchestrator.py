from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from src.contracts.drive import DriveWritePreflightRequest
from src.contracts.files import (
    DeleteFileRequest,
    FileStatRequest,
    WriteBytesRequest,
)
from src.contracts.pipeline_preflight import (
    PipelinePreflightCheck,
    PipelinePreflightReport,
    PipelinePreflightRequest,
    PreflightCheckStatus,
)
from src.contracts.prompts import PromptLoadRequest
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.services import drive_service, file_service, prompt_service, wordpress_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    execution_policy_matrix,
    preflight_execution_policy_coverage,
)

logger = logging.getLogger("market_lense.pipeline_preflight_orchestrator")


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
    checks.extend(_check_local_paths(request, ctx, deps))
    checks.extend(_check_llm(request))
    checks.extend(_check_llm_policy_coverage(request))
    checks.extend(_check_prompts(request, ctx, deps))
    checks.extend(_check_drive(request, ctx, deps))
    checks.extend(_check_browser(request))
    checks.extend(_check_publish(request, ctx, deps))
    report = _build_report(request, checks)
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
