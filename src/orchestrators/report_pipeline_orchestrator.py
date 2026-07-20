from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import asdict, replace
from inspect import Parameter, signature
from pathlib import Path
from typing import Callable, Optional, cast

from src.contracts.deferred_work import (
    DeferredWorkItem,
    DeferredWorkResumePlan,
)
from src.contracts.drive import DriveFile
from src.contracts.files import FileStatRequest
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionPlanRecordRequest,
    ExecutionPlanResultRequest,
    MinimalExecutionPlan,
    MinimalExecutionPlanBuildRequest,
    MinimalExecutionPlanInput,
    RetainedArtifactGraph,
)
from src.contracts.pipeline_preflight import PipelinePreflightReport
from src.contracts.regeneration import (
    LineageRegenerationPlan,
    LineageRegenerationQualityReport,
)
from src.contracts.report_generation import ReportGenerationClientBundle
from src.contracts.run_budget import (
    BudgetOverrideContext,
    BudgetRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudget,
    RunBudgetUsage,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.workflow_control import WorkflowControlSettings
from src.orchestrators.pipeline_preflight_orchestrator import (
    assert_expensive_side_effects_allowed,
    preflight_report_pipeline,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.orchestrators.report_generation_orchestrator import (
    run_report_generation as generate_report_orchestrator,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.orchestrators.workflow_control_orchestrator import resolve_retry_policy
from src.services import file_service, llm_service, lock_service
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_budget_side_effect,
)
from src.services.report_store_service import (
    build_current_report_execution_compatibility,
    build_minimal_execution_plan,
    record_minimal_execution_plan,
    record_minimal_execution_plan_result,
)
from src.utils.coercion import coerce_int
from src.utils.errors import AppError
from src.utils.lineage_regeneration import (
    build_lineage_regeneration_quality_report,
    plan_lineage_regeneration,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_pipeline_orchestrator")

_ENFORCED_RESUME_STAGES = {
    ("render_complete",): "analysis_complete",
    ("selection_complete", "render_complete"): "source_prepared",
    ("analysis_complete", "render_complete"): "selection_complete",
    (
        "selection_complete",
        "analysis_complete",
        "render_complete",
    ): "source_prepared",
    (
        "source_prepared",
        "selection_complete",
        "analysis_complete",
        "render_complete",
    ): None,
}


def _enforced_resume_stage(plan: MinimalExecutionPlan) -> str | None:
    """Map the pure planner's approved shape to an existing checkpoint entrypoint."""
    if plan.missing_lineage_blockers:
        raise AppError(
            code="minimal_execution_plan_lineage_incomplete",
            message="Enforce-mode execution requires complete retained lineage",
            retryable=False,
            context={
                "plan_hash": plan.plan_hash,
                "blockers": [item.reason for item in plan.missing_lineage_blockers],
            },
        )
    stages = tuple(plan.required_stages)
    if stages not in _ENFORCED_RESUME_STAGES:
        raise AppError(
            code="minimal_execution_plan_enforcement_unavailable",
            message=(
                "The planned stages are not supported by the report-generation "
                "entrypoint"
            ),
            retryable=False,
            context={"plan_hash": plan.plan_hash, "required_stages": list(stages)},
        )
    return _ENFORCED_RESUME_STAGES[stages]


def _acquire_execution_lease(
    settings: IngestSettings,
    plan: MinimalExecutionPlan,
    ctx: RunContext,
) -> tuple[str, str]:
    """Serialize writes for one retained plan without widening the ingest lock."""
    key = hashlib.sha256(
        f"{plan.report_id}:{plan.plan_hash}".encode("utf-8")
    ).hexdigest()
    lock_path = str(
        Path(settings.output_dir) / ".minimal_execution_leases" / f"{key}.lock"
    )
    owner_id = f"{ctx.run_id}:{plan.plan_hash}"
    response = lock_service.acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=lock_path,
            owner_id=owner_id,
            pid=os.getpid(),
            ttl_seconds=300.0,
        ),
        ctx,
    )
    if response.acquired:
        return lock_path, owner_id
    raise AppError(
        code="minimal_execution_plan_lease_conflict",
        message="Another run already owns the retained-artifact execution lease",
        retryable=False,
        context={
            "plan_hash": plan.plan_hash,
            "report_id": plan.report_id,
            "lock_path": lock_path,
            "owner_id": response.conflict.owner_id if response.conflict else "",
        },
    )


def _release_execution_lease(lock_path: str, owner_id: str, ctx: RunContext) -> None:
    if not lock_path:
        return
    lock_service.release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=lock_path,
            owner_id=owner_id,
            pid=os.getpid(),
        ),
        ctx,
    )


def _doc_map_reason(outcome: IngestOutcome) -> str:
    summary = (
        outcome.doc_map_summary if isinstance(outcome.doc_map_summary, dict) else {}
    )
    reason = str(summary.get("not_found_reason") or "").strip()
    if reason:
        return reason
    error_text = str(outcome.error or "")
    prefix = "doc_map_empty:"
    if error_text.startswith(prefix):
        return error_text[len(prefix) :].strip()
    return ""


def _is_retryable_doc_map_reason(reason: str) -> bool:
    normalized = reason.strip()
    if not normalized:
        return False
    if normalized == "model_returned_no_json":
        return True
    if normalized.startswith("schema_validation_failed:"):
        return True
    return normalized.startswith("retryable_error:")


def _is_retryable_doc_map_outcome(outcome: IngestOutcome, reason: str) -> bool:
    if _is_retryable_doc_map_reason(reason):
        return True
    text_validation_status = str(outcome.text_validation_status or "").strip().lower()
    return reason.strip() == "no_content" and text_validation_status == "pass"


def _invoke_report_fn(
    report_fn: Callable[..., IngestOutcome],
    *,
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    client_bundle: ReportGenerationClientBundle | None,
    resume_from_stage: Optional[str] = None,
    require_artifact_lineage: bool = False,
    execution_compatibility: dict[str, object] | None = None,
    minimal_execution_plan: MinimalExecutionPlan | None = None,
    enforce_minimal_execution: bool = False,
    stop_after_stage: str | None = None,
    projection_only: bool = False,
    budget_override: BudgetOverrideContext | None = None,
) -> IngestOutcome:
    arguments: dict[str, object] = {"resume_from_stage": resume_from_stage}
    if client_bundle is not None:
        arguments["client_bundle"] = client_bundle.validate()
    parameters = signature(report_fn).parameters.values()
    supports_lineage_requirement = any(
        parameter.kind == Parameter.VAR_KEYWORD
        or parameter.name == "require_artifact_lineage"
        for parameter in parameters
    )
    if supports_lineage_requirement:
        arguments["require_artifact_lineage"] = require_artifact_lineage
    supports_compatibility = any(
        parameter.kind == Parameter.VAR_KEYWORD
        or parameter.name == "execution_compatibility"
        for parameter in parameters
    )
    if supports_compatibility:
        arguments["execution_compatibility"] = execution_compatibility
    supports_minimal_plan = any(
        parameter.kind == Parameter.VAR_KEYWORD
        or parameter.name == "minimal_execution_plan"
        for parameter in parameters
    )
    if supports_minimal_plan:
        arguments["minimal_execution_plan"] = minimal_execution_plan
    supports_enforcement = any(
        parameter.kind == Parameter.VAR_KEYWORD
        or parameter.name == "enforce_minimal_execution"
        for parameter in parameters
    )
    if supports_enforcement:
        arguments["enforce_minimal_execution"] = enforce_minimal_execution
    supports_stop_boundary = any(
        parameter.kind == Parameter.VAR_KEYWORD or parameter.name == "stop_after_stage"
        for parameter in parameters
    )
    if supports_stop_boundary:
        arguments["stop_after_stage"] = stop_after_stage
    supports_projection_only = any(
        parameter.kind == Parameter.VAR_KEYWORD or parameter.name == "projection_only"
        for parameter in parameters
    )
    if supports_projection_only:
        arguments["projection_only"] = projection_only
    return report_fn(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        **arguments,
    )


def _deferred_local_pdf(item: DeferredWorkItem) -> str:
    for artifact in item.reusable_artifacts:
        if artifact.kind == "local_pdf" and artifact.reference:
            return artifact.reference
    raise AppError(
        code="deferred_work_required_artifact_missing",
        message="Deferred report work is missing its retained local PDF reference",
        retryable=False,
        context={"work_key": item.work_key, "report_id": item.report_id},
    )


def build_report_pipeline_deferred_work_plan(
    item: DeferredWorkItem,
    settings: IngestSettings,
    ctx: RunContext,
) -> DeferredWorkResumePlan:
    """Rebuild and validate the minimum plan before resuming report work."""

    local_pdf_path = _deferred_local_pdf(item)
    stat = file_service.file_stat(
        FileStatRequest(schema_version="1.0", path=local_pdf_path), ctx
    )
    if not stat.exists:
        raise AppError(
            code="deferred_work_required_artifact_missing",
            message="Deferred report work cannot reuse its missing local PDF",
            retryable=False,
            context={"work_key": item.work_key, "report_id": item.report_id},
        )
    current_compatibility = build_current_report_execution_compatibility(settings, ctx)
    response = build_minimal_execution_plan(
        MinimalExecutionPlanBuildRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=settings.reports_db,
            source_path=local_pdf_path,
            execution_input=MinimalExecutionPlanInput(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                execution_intent="report_generation",
                report_id=item.report_id,
                source_id=item.source_id,
                current_source_content_hashes={},
                retained_graph=RetainedArtifactGraph(),
                requested_output_families=["rendered_html"],
                current_compatibility=current_compatibility,
            ),
        ),
        ctx,
    )
    _enforced_resume_stage(response.plan)
    record_minimal_execution_plan(
        ExecutionPlanRecordRequest(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            db_path=settings.reports_db,
            plan=response.plan,
            execution_mode="enforce",
        ),
        ctx,
    )
    return DeferredWorkResumePlan(
        schema_version="1.0",
        plan_hash=response.plan.plan_hash,
        resume_stage="latest_safe",
        reusable_artifacts=list(item.reusable_artifacts),
    )


def resume_deferred_report_pipeline(
    item: DeferredWorkItem,
    plan: DeferredWorkResumePlan,
    settings: IngestSettings,
    ctx: RunContext,
    *,
    generate_report_fn: Callable[..., IngestOutcome] | None = None,
    preflight_fn: Callable[..., PipelinePreflightReport] | None = None,
    workflow_control_settings: WorkflowControlSettings | None = None,
) -> str:
    """Resume one validated report plan using its original budget run identity."""

    local_pdf_path = _deferred_local_pdf(item)
    file = DriveFile(
        schema_version="1.0",
        file_id=item.report_id,
        name=Path(local_pdf_path).name,
        modified_time=None,
        md5_checksum=item.source_id or None,
        mime_type="application/pdf",
    )
    resume_ctx = replace(ctx, run_id=cast(RunId, item.run_id))
    outcome = run_report_pipeline(
        file,
        local_pdf_path,
        settings,
        item.source_id or None,
        resume_ctx,
        retries=0,
        generate_report_fn=generate_report_fn,
        resume_from_stage=plan.resume_stage,
        preflight_fn=preflight_fn,
        workflow_control_settings=workflow_control_settings,
        auto_resume_from_latest_safe=True,
        execution_plan_mode="enforce",
    )
    if outcome.status == "error":
        raise AppError(
            code="deferred_work_report_pipeline_error",
            message=outcome.error
            or "Deferred report pipeline returned an error outcome",
            retryable=False,
        )
    return "completed"


def run_report_pipeline(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    retries: int = 2,
    generate_report_fn: Optional[Callable[..., IngestOutcome]] = None,
    openai_client_override=None,
    resume_from_stage: Optional[str] = None,
    preflight_fn: Optional[Callable[..., PipelinePreflightReport]] = None,
    workflow_control_settings: WorkflowControlSettings | None = None,
    auto_resume_from_latest_safe: bool = False,
    lineage_change_kind: str = "",
    lineage_available: bool = False,
    execution_plan_mode: str = "shadow",
    stop_after_stage: str | None = None,
    projection_only: bool = False,
    budget_override: BudgetOverrideContext | None = None,
) -> IngestOutcome:
    report_fn = generate_report_fn or generate_report_orchestrator
    preflight_report = (
        preflight_fn(settings, ctx)
        if preflight_fn is not None
        else preflight_report_pipeline(settings, ctx)
    )
    assert_expensive_side_effects_allowed(preflight_report, ctx)
    evidence_max_in_flight = coerce_int(
        getattr(settings, "evidence_pack_global_max_in_flight", 2), 2, min_value=1
    )
    evidence_min_interval_ms = coerce_int(
        getattr(settings, "evidence_pack_global_min_interval_ms", 250), 250, min_value=0
    )
    artifact_max_in_flight = coerce_int(
        getattr(settings, "artifact_global_max_in_flight", 2), 2, min_value=1
    )
    artifact_min_interval_ms = coerce_int(
        getattr(settings, "artifact_global_min_interval_ms", 250), 250, min_value=0
    )
    doc_map_max_attempts = coerce_int(
        getattr(settings, "evidence_pack_doc_map_max_attempts", 3), 3, min_value=1
    )
    doc_map_retry_delay_ms = coerce_int(
        getattr(settings, "evidence_pack_doc_map_retry_delay_ms", 500), 500, min_value=0
    )
    configured_retries = max(0, int(retries))
    retry_policy_id = "report_generation.report_pipeline.legacy_args"
    retry_policy = RetryPolicy(
        retries=configured_retries,
        base_delay_seconds=1.0,
        backoff_step_seconds=1.0,
        jitter_seconds=0.25,
    )
    if workflow_control_settings is not None:
        resolved_policy = resolve_retry_policy(
            workflow_control_settings,
            workflow_name="report_generation",
            step_name="report_pipeline",
            ctx=ctx,
        )
        retry_policy = resolved_policy.policy
        retry_policy_id = resolved_policy.policy_id
        configured_retries = retry_policy.retries
    pipeline_budget = RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="",
        usage_db_path=settings.usage_db_path,
        max_spend_usd=getattr(settings, "run_budget_max_spend_usd", None),
        max_pdfs=getattr(settings, "run_budget_max_pdfs", None),
        max_retries=getattr(settings, "run_budget_max_retries", None),
        max_runtime_seconds=getattr(settings, "run_budget_max_runtime_seconds", None),
        limit_decision=getattr(settings, "run_budget_limit_decision", "stop"),
        enabled_effect_kinds=getattr(settings, "run_budget_enabled_effect_kinds", ()),
    )
    retry_policy = replace(
        retry_policy,
        budget=pipeline_budget,
        budget_workflow_id="report_generation",
        budget_report_id=file.file_id,
    )
    normalized_plan_mode = str(execution_plan_mode or "shadow").strip().lower()
    if normalized_plan_mode not in {"shadow", "enforce", "disabled"}:
        raise AppError(
            code="minimal_execution_plan_mode_invalid",
            message="Execution planning mode must be shadow, enforce, or disabled",
            retryable=False,
        )
    if lineage_change_kind and not lineage_available:
        plan_lineage_regeneration(
            change_kind=lineage_change_kind,
            lineage_available=False,
        )
    minimal_plan = None
    execution_compatibility: dict[str, object] | None = None
    if normalized_plan_mode != "disabled":
        current_compatibility = build_current_report_execution_compatibility(
            settings, ctx
        )
        intent_by_change = {
            "template": "render_repair",
            "crop": "crop_repair",
            "publication": "publication_repair",
            "prompt": "targeted_repair",
            "model": "targeted_repair",
            "validator": "targeted_repair",
        }
        plan_response = build_minimal_execution_plan(
            MinimalExecutionPlanBuildRequest(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                db_path=settings.reports_db,
                source_path=local_pdf_path,
                execution_input=MinimalExecutionPlanInput(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    execution_intent=intent_by_change.get(
                        str(lineage_change_kind).strip().lower(),
                        "report_generation",
                    ),
                    report_id=file.file_id,
                    source_id=str(md5 or "").strip().lower(),
                    current_source_content_hashes={},
                    retained_graph=RetainedArtifactGraph(),
                    requested_output_families=["rendered_html"],
                    current_compatibility=current_compatibility,
                ),
            ),
            ctx,
        )
        minimal_plan = plan_response.plan
        execution_compatibility = asdict(current_compatibility)
        record_minimal_execution_plan(
            ExecutionPlanRecordRequest(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                db_path=settings.reports_db,
                plan=minimal_plan,
                execution_mode=normalized_plan_mode,
            ),
            ctx,
        )
    lineage_plan: LineageRegenerationPlan | None = None
    lineage_quality: LineageRegenerationQualityReport | None = None
    if lineage_change_kind:
        lineage_plan = plan_lineage_regeneration(
            change_kind=lineage_change_kind,
            lineage_available=lineage_available,
        )
        lineage_quality = build_lineage_regeneration_quality_report(lineage_plan)
    enforced_resume_stage = None
    if normalized_plan_mode == "enforce" and minimal_plan is not None:
        try:
            enforced_resume_stage = _enforced_resume_stage(minimal_plan)
        except AppError:
            record_minimal_execution_plan_result(
                ExecutionPlanResultRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    plan_hash=minimal_plan.plan_hash,
                    report_id=file.file_id,
                    execution_intent=minimal_plan.execution_intent,
                    actual_stages=[],
                    actual_external_calls=[],
                    actual_side_effects=[],
                    reusable_artifact_ids=minimal_plan.reusable_artifacts,
                    execution_status="enforcement_deferred",
                ),
                ctx,
            )
            raise
        if resume_from_stage is not None and resume_from_stage != enforced_resume_stage:
            raise AppError(
                code="minimal_execution_plan_resume_mismatch",
                message="Caller-provided resume stage differs from the enforced plan",
                retryable=False,
                context={
                    "plan_hash": minimal_plan.plan_hash,
                    "requested_resume_stage": resume_from_stage,
                    "planned_resume_stage": enforced_resume_stage or "fresh",
                },
            )
    effective_resume_from_stage = (
        resume_from_stage
        if resume_from_stage
        else (
            enforced_resume_stage
            if normalized_plan_mode == "enforce" and minimal_plan is not None
            else ("latest_safe" if auto_resume_from_latest_safe else None)
        )
    )
    client_bundle: ReportGenerationClientBundle | None = None
    client_free_enforced_plan = (
        normalized_plan_mode == "enforce"
        and minimal_plan is not None
        and not minimal_plan.missing_lineage_blockers
        and minimal_plan.required_stages
        in (
            ["render_complete"],
            ["selection_complete", "render_complete"],
        )
    )
    if not client_free_enforced_plan:
        evidence_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="evidence_pack",
            rate_limit_max_in_flight=evidence_max_in_flight,
            rate_limit_min_interval_ms=evidence_min_interval_ms,
            base_client=openai_client_override,
            sleep_fn=time.sleep,
            monotonic_fn=time.monotonic,
        )
        artifact_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="artifact",
            rate_limit_max_in_flight=artifact_max_in_flight,
            rate_limit_min_interval_ms=artifact_min_interval_ms,
            base_client=openai_client_override,
            sleep_fn=time.sleep,
            monotonic_fn=time.monotonic,
        )
        source_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="pdf_text_ocr",
            base_client=openai_client_override,
        )
        taxonomy_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="taxonomy",
            base_client=openai_client_override,
        )
        category_fit_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="context_category_fit",
            base_client=openai_client_override,
        )
        validation_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="validation",
            base_client=openai_client_override,
        )
        regeneration_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="artifact_regeneration",
            base_client=openai_client_override,
        )
        figure_caption_openai_client = llm_service.build_client_for_settings(
            settings,
            scope="figure_caption",
            base_client=openai_client_override,
        )
        client_bundle = ReportGenerationClientBundle(
            schema_version="1.0",
            source_ocr_client=source_openai_client,
            taxonomy_client=taxonomy_openai_client,
            category_fit_client=category_fit_openai_client,
            evidence_pack_client=evidence_openai_client,
            artifact_client=artifact_openai_client,
            validation_client=validation_openai_client,
            regeneration_client=regeneration_openai_client,
            figure_caption_client=figure_caption_openai_client,
        ).validate()
    else:
        assert minimal_plan is not None
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_pipeline_model_clients_avoided",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "plan_hash": minimal_plan.plan_hash,
                    "required_stages": list(minimal_plan.required_stages),
                },
            )
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_pipeline_start",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "md5": md5 or "",
                "local_pdf_path": local_pdf_path,
                "retries": retries,
                "effective_retries": configured_retries,
                "doc_map_max_attempts": doc_map_max_attempts,
                "retry_delay_ms": doc_map_retry_delay_ms,
                "retry_policy_id": retry_policy_id,
                "retry_jitter_seconds": retry_policy.jitter_seconds,
                "evidence_pack_global_max_in_flight": evidence_max_in_flight,
                "evidence_pack_global_min_interval_ms": evidence_min_interval_ms,
                "artifact_global_max_in_flight": artifact_max_in_flight,
                "artifact_global_min_interval_ms": artifact_min_interval_ms,
                "resume_from_stage": effective_resume_from_stage or "",
                "auto_resume_from_latest_safe": bool(auto_resume_from_latest_safe),
                "lineage_regeneration_plan": (
                    {
                        "change_kind": lineage_plan.change_kind,
                        "full_regeneration_required": (
                            lineage_plan.full_regeneration_required
                        ),
                        "reused_stages": lineage_plan.reused_stages,
                        "regenerated_stages": lineage_plan.regenerated_stages,
                        "avoided_work": lineage_plan.avoided_work,
                    }
                    if lineage_plan is not None
                    else {}
                ),
                "lineage_quality": (
                    {
                        "fan_out": lineage_quality.fan_out,
                        "reused_stage_count": lineage_quality.reused_stage_count,
                        "regenerated_stage_count": (
                            lineage_quality.regenerated_stage_count
                        ),
                        "avoided_work": lineage_quality.avoided_work,
                        "avoided_work_count": len(lineage_quality.avoided_work),
                        "estimated_avoided_cost_usd": (
                            lineage_quality.estimated_avoided_cost_usd
                        ),
                        "cost_status": lineage_quality.cost_status,
                    }
                    if lineage_quality is not None
                    else {}
                ),
                "minimal_execution_plan": (
                    {
                        "plan_hash": minimal_plan.plan_hash,
                        "intent": minimal_plan.execution_intent,
                        "required_stages": minimal_plan.required_stages,
                        "skipped_stages": minimal_plan.skipped_stages,
                        "blocker_count": len(minimal_plan.missing_lineage_blockers),
                        "mode": normalized_plan_mode,
                    }
                    if minimal_plan is not None
                    else {}
                ),
            },
        )
    )

    attempt_state = {"value": 0}

    def _report_attempt() -> IngestOutcome:
        current_attempt = attempt_state["value"]
        attempt_state["value"] += 1
        try:
            outcome = _invoke_report_fn(
                report_fn,
                file=file,
                local_pdf_path=local_pdf_path,
                settings=settings,
                md5=md5,
                ctx=ctx,
                client_bundle=client_bundle,
                resume_from_stage=effective_resume_from_stage,
                require_artifact_lineage=(
                    bool(lineage_change_kind) or normalized_plan_mode == "enforce"
                ),
                execution_compatibility=execution_compatibility,
                minimal_execution_plan=minimal_plan,
                enforce_minimal_execution=normalized_plan_mode == "enforce",
                stop_after_stage=stop_after_stage,
                projection_only=projection_only,
            )
        except AppError as exc:
            if (
                auto_resume_from_latest_safe
                and effective_resume_from_stage == "latest_safe"
                and exc.code == "report_pipeline_checkpoint_missing"
            ):
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="report_pipeline_latest_safe_fresh_fallback",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "error_code": exc.code,
                        },
                    )
                )
                outcome = _invoke_report_fn(
                    report_fn,
                    file=file,
                    local_pdf_path=local_pdf_path,
                    settings=settings,
                    md5=md5,
                    ctx=ctx,
                    client_bundle=client_bundle,
                    resume_from_stage=None,
                    require_artifact_lineage=False,
                    execution_compatibility=execution_compatibility,
                    minimal_execution_plan=minimal_plan,
                    enforce_minimal_execution=False,
                    stop_after_stage=stop_after_stage,
                    projection_only=projection_only,
                )
            else:
                raise
        doc_map_reason = _doc_map_reason(outcome)
        should_retry_doc_map = (
            outcome.status == "error"
            and _is_retryable_doc_map_outcome(outcome, doc_map_reason)
            and current_attempt < doc_map_max_attempts - 1
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_pipeline_complete",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "status": outcome.status,
                    "html_path": outcome.html_path or "",
                    "error": outcome.error or "",
                    "attempt": current_attempt,
                    "doc_map_reason": doc_map_reason,
                    "retry_transition": should_retry_doc_map,
                },
            )
        )
        if should_retry_doc_map:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="report_pipeline_doc_map_retry_transition",
                    module=logger.name,
                    fields={
                        "file_id": file.file_id,
                        "attempt": current_attempt + 1,
                        "max_attempts": doc_map_max_attempts,
                        "reason": doc_map_reason,
                    },
                )
            )
            raise AppError(
                code="doc_map_generation_retry",
                message=(
                    f"Retrying report pipeline for doc_map reason: {doc_map_reason}"
                ),
                retryable=True,
                context={
                    "file_id": file.file_id,
                    "attempt": current_attempt + 1,
                    "max_attempts": doc_map_max_attempts,
                    "reason": doc_map_reason,
                },
            )
        return outcome

    needs_source_processing = (
        minimal_plan is None or "source_prepared" in minimal_plan.required_stages
    )
    pdf_decision = None
    if needs_source_processing:
        pdf_decision = evaluate_budget_request(
            BudgetRequest(
                schema_version="1.0",
                budget=pipeline_budget,
                run_id=ctx.run_id,
                workflow_id="report_generation",
                report_id=file.file_id,
                source_id=str(md5 or "").strip(),
                stage="source_prepared",
                plan_hash=minimal_plan.plan_hash if minimal_plan is not None else "",
                reusable_artifact_references=(
                    (
                        "local_pdf",
                        local_pdf_path,
                        str(md5 or "").strip(),
                    ),
                ),
                resource_type="pdf_process",
                operation="process_pdf",
                estimated_pdfs=1,
                idempotency_key=f"pdf-process:{ctx.run_id}:{file.file_id}:{md5 or ''}",
                requested_override=budget_override,
                reserve_in_flight=True,
            ),
            ctx,
        )
        if pdf_decision.decision in {"defer", "pause", "stop"}:
            raise AppError(
                code=f"report_pipeline_pdf_budget_{pdf_decision.decision}",
                message="PDF processing was blocked by the canonical budget authority",
                retryable=False,
                context={
                    "reason_code": pdf_decision.reason_code,
                    "affected_limit": pdf_decision.affected_limit,
                    "retry_decision": "defer"
                    if pdf_decision.decision == "defer"
                    else "abort",
                    "next_action": pdf_decision.next_action,
                },
            )
    lease_path = ""
    lease_owner_id = ""
    if normalized_plan_mode == "enforce" and minimal_plan is not None:
        try:
            lease_path, lease_owner_id = _acquire_execution_lease(
                settings, minimal_plan, ctx
            )
        except AppError:
            record_minimal_execution_plan_result(
                ExecutionPlanResultRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    plan_hash=minimal_plan.plan_hash,
                    report_id=file.file_id,
                    execution_intent=minimal_plan.execution_intent,
                    actual_stages=[],
                    actual_external_calls=[],
                    actual_side_effects=[],
                    reusable_artifact_ids=list(minimal_plan.reusable_artifacts),
                    execution_status="lease_conflict",
                ),
                ctx,
            )
            raise
    execution_started_at = time.perf_counter()
    pdf_started = False
    try:
        pdf_started = True
        outcome = run_with_retry(
            step_name="report_pipeline",
            operation=_report_attempt,
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=retry_policy,
            retry_event="report_pipeline_retry",
            retry_fields_builder=lambda exc, attempt: {
                "file_id": file.file_id,
                "attempt": attempt + 1,
                "code": exc.code if isinstance(exc, AppError) else "",
            },
            failure_event="report_pipeline_failed",
            failure_fields_builder=lambda exc, attempt, retryable: {
                "file_id": file.file_id,
                "code": exc.code if isinstance(exc, AppError) else "",
                "error": exc.message if isinstance(exc, AppError) else str(exc),
                "attempt": attempt,
                "retryable": retryable,
            },
            on_terminal_failure=lambda exc, decision: record_workflow_failure(
                state_db=settings.state_db,
                workflow="report_generation",
                stage="report_pipeline",
                operation="generate_report",
                error=exc,
                ctx=ctx,
                retry_decision=decision,
                input_checksum=md5 or file.file_id,
                report_id=file.file_id,
                source_id=local_pdf_path,
            ),
            is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
            sleep_fn=time.sleep,
        )
    except AppError as exc:
        if pdf_decision is not None and pdf_decision.reservation_key:
            finalize_budget_side_effect(
                BudgetSideEffectFinalizeRequest(
                    schema_version="1.0",
                    usage_db_path=pipeline_budget.usage_db_path,
                    reservation_key=pdf_decision.reservation_key,
                    actual_usage=RunBudgetUsage(
                        schema_version="1.0", pdfs=1 if pdf_started else 0
                    ),
                    outcome="failed",
                    error_code=exc.code,
                ),
                ctx,
            )
        if minimal_plan is not None:
            record_minimal_execution_plan_result(
                ExecutionPlanResultRequest(
                    schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    plan_hash=minimal_plan.plan_hash,
                    report_id=file.file_id,
                    execution_intent=minimal_plan.execution_intent,
                    actual_stages=[],
                    actual_external_calls=[],
                    actual_side_effects=[],
                    duration_ms=int(
                        (time.perf_counter() - execution_started_at) * 1000
                    ),
                    reusable_artifact_ids=list(minimal_plan.reusable_artifacts),
                    execution_status="failed",
                ),
                ctx,
            )
        _release_execution_lease(lease_path, lease_owner_id, ctx)
        raise
    if pdf_decision is not None and pdf_decision.reservation_key:
        finalize_budget_side_effect(
            BudgetSideEffectFinalizeRequest(
                schema_version="1.0",
                usage_db_path=pipeline_budget.usage_db_path,
                reservation_key=pdf_decision.reservation_key,
                actual_usage=RunBudgetUsage(schema_version="1.0", pdfs=1),
                outcome="completed",
            ),
            ctx,
        )
    if outcome.status == "error":
        record_workflow_failure(
            state_db=settings.state_db,
            workflow="report_generation",
            stage="report_pipeline",
            operation="generate_report",
            error=AppError(
                code="report_pipeline_outcome_error",
                message=outcome.error or "Report pipeline returned an error outcome",
                retryable=False,
            ),
            ctx=ctx,
            input_checksum=md5 or file.file_id,
            report_id=file.file_id,
            source_id=local_pdf_path,
        )
    if minimal_plan is not None:
        divergence = record_minimal_execution_plan_result(
            ExecutionPlanResultRequest(
                schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
                db_path=settings.reports_db,
                plan_hash=minimal_plan.plan_hash,
                report_id=file.file_id,
                execution_intent=minimal_plan.execution_intent,
                actual_stages=list(minimal_plan.required_stages),
                actual_external_calls=list(minimal_plan.required_external_calls),
                actual_side_effects=list(minimal_plan.expected_side_effects),
                actual_prompt_families=list(outcome.actual_prompt_families),
                duration_ms=int((time.perf_counter() - execution_started_at) * 1000),
                reusable_artifact_ids=list(minimal_plan.reusable_artifacts),
                execution_status=outcome.status,
            ),
            ctx,
        )
        if normalized_plan_mode == "enforce" and divergence:
            _release_execution_lease(lease_path, lease_owner_id, ctx)
            raise AppError(
                code="minimal_execution_plan_diverged",
                message="Actual report execution diverged from its enforced plan",
                retryable=False,
                context={"plan_hash": minimal_plan.plan_hash},
            )
    _release_execution_lease(lease_path, lease_owner_id, ctx)
    return outcome
