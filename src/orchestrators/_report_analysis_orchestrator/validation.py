"""Validation fallback and regeneration-loop execution for report analysis.

This module owns validation failure fallback, validation snapshot persistence,
and bounded artifact regeneration attempts.
"""

from __future__ import annotations

import inspect
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationAttemptResult,
    RegenerationLoopState,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.semantic_ids import ReportId
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    merge_public_editorial_quality_validation,
    quality_report_payload,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.generators.report_generation_shared import merge_artifacts_into_payload
from src.orchestrators._report_analysis_orchestrator.payload import (
    _ensure_report_payload_complete,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.utils.logging import child_context, log_event

__all__ = [
    "_evaluate_and_store_public_editorial_quality",
    "_run_validation_regeneration_loop",
    "_run_validation_with_fallback",
    "_store_validation_snapshot",
]


def _evaluate_and_store_public_editorial_quality(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    artifacts: Dict[str, Any],
    pack_name: str,
    ctx,
) -> tuple[ValidationReport | None, str]:
    """Persist the private report and adapt blockers for the existing repair loop."""
    if not isinstance(artifacts, dict):
        return None, ""
    quality = evaluate_public_editorial_quality(
        report_id=str(runtime.file.file_id),
        artifacts=artifacts,
        disabled_rule_waivers=getattr(
            runtime.settings, "public_editorial_quality_disabled_rule_waivers", {}
        ),
    )
    stored = dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            payload=quality_report_payload(quality),
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path
    rule_ids = sorted({issue.rule_id for issue in quality.issues})
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="public_editorial_quality_evaluated",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "status": quality.status,
                "issue_count": len(quality.issues),
                "rule_ids": rule_ids,
                "validator_version": quality.validator_version,
                "quality_report_path": stored,
            },
        )
    )
    if quality.status == "fail":
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="public_editorial_quality_blocked",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "rule_ids": rule_ids,
                    "repairable_issue_count": sum(
                        issue.repair_eligible for issue in quality.issues
                    ),
                    "abstained_issue_count": sum(
                        issue.repair_status == "abstained" for issue in quality.issues
                    ),
                },
            )
        )
    if quality.disabled_rule_waivers:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="public_editorial_quality_rule_waived",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "rule_ids": sorted(quality.disabled_rule_waivers),
                    "waiver_count": len(quality.disabled_rule_waivers),
                },
            )
        )
    issues = merge_public_editorial_quality_validation(
        ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
        ),
        quality,
    )
    return issues, stored


def _merge_public_editorial_quality(
    validation: ValidationReport,
    editorial_validation: ValidationReport | None,
) -> ValidationReport:
    if editorial_validation is None:
        return validation
    return ValidationReport(
        schema_version=validation.schema_version,
        status=(
            "fail"
            if validation.status == "fail" or editorial_validation.status == "fail"
            else "pass"
        ),
        issues=list(validation.issues) + list(editorial_validation.issues),
        severity=(
            "error"
            if (
                validation.severity == "error"
                or editorial_validation.severity == "error"
            )
            else validation.severity
        ),
        source_path=validation.source_path,
    )


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    return keyword in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _run_validation_with_fallback(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
    validation_req: ValidationRequest,
    pack_name: str,
    openai_client=None,
) -> ValidationReport:
    kwargs = {}
    if openai_client is not None and _accepts_keyword(
        dependencies.run_validation, "openai_client"
    ):
        kwargs["openai_client"] = openai_client
    try:
        return dependencies.run_validation(
            validation_req,
            runtime.settings,
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:{pack_name}"),
            pack_name=pack_name,
            report_name=runtime.report_name,
            md5=runtime.md5,
            **kwargs,
        )
    except Exception as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_failed",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "error": str(exc),
                    "mode": runtime.analysis_mode,
                    "pack_name": pack_name,
                },
            )
        )
        fallback_path = dependencies.analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=ReportId(runtime.file.file_id),
                pack_name=pack_name,
                report_slug=runtime.report_name,
            ),
            mode_ctx,
        ).output_path
        fallback_report = ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message=f"Validation error: {exc}",
                    severity="error",
                    affected_section="validation",
                )
            ],
            severity="error",
            source_path=fallback_path,
        )
        try:
            dependencies.analysis_store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=runtime.settings.output_dir,
                    report_id=ReportId(runtime.file.file_id),
                    pack_name=pack_name,
                    payload=fallback_report.to_dict(),
                    report_slug=runtime.report_name,
                ),
                mode_ctx,
            )
        except Exception as store_exc:  # pragma: no cover
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_store_failed",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error": str(store_exc),
                        "mode": runtime.analysis_mode,
                    },
                )
            )
        return fallback_report


def _run_validation_regeneration_loop(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    base_payload,
    current_artifacts: Dict[str, Any],
    current_validation_report: ValidationReport,
    evidence_packs: Dict[str, Any],
    source_status: Dict[str, Any],
    category_labels: List[str],
    vector_store_id: Optional[str],
    dependencies: ReportAnalysisDependencies,
    validation_openai_client=None,
    regeneration_openai_client=None,
) -> tuple[
    Dict[str, Any],
    ValidationReport,
    List[RegenerationAttemptResult],
    RegenerationLoopState,
    Dict[str, str],
]:
    max_attempts = max(1, int(runtime.settings.validation_regeneration_max_attempts))
    attempts: List[RegenerationAttemptResult] = []
    evidence_paths: Dict[str, str] = {}
    broad_retry_used = False
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="validation_regen_loop_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "max_attempts": max_attempts,
                "initial_status": current_validation_report.status,
            },
        )
    )
    final_status = current_validation_report.status
    for attempt_index in range(1, max_attempts + 1):
        if current_validation_report.status == "pass":
            final_status = "pass"
            break
        plan = _build_regeneration_plan(
            issues=current_validation_report.issues,
            artifacts=current_artifacts,
            broad_retry_available=not broad_retry_used,
        )
        public_issues = [
            issue
            for issue in current_validation_report.issues
            if str(issue.rule_id).startswith("public_editorial_quality.")
        ]
        if public_issues:
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_requested",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "rule_ids": sorted({issue.rule_id for issue in public_issues}),
                        "target_sections": [
                            target.target_section for target in plan.targets
                        ],
                    },
                )
            )
        abstained_public_issues = [
            issue for issue in public_issues if not str(issue.repair_target).strip()
        ]
        if abstained_public_issues:
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_abstained",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "rule_ids": sorted(
                            {issue.rule_id for issue in abstained_public_issues}
                        ),
                        "issue_count": len(abstained_public_issues),
                    },
                )
            )
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_plan_built",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "target_details": _regeneration_target_details(plan.targets),
                    "unmappable_issue_count": len(plan.unmappable_issues),
                },
            )
        )
        if plan.mode == "skip":
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_skip_no_targets",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(current_validation_report.issues),
                    },
                )
            )
            final_status = "skipped"
            break
        if plan.mode == "broad":
            broad_retry_used = True
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_unmappable_broad_retry",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(plan.unmappable_issues),
                    },
                )
            )
        attempt_ctx = child_context(
            mode_ctx, task_id=f"{mode_ctx.task_id}:regen:{attempt_index}"
        )
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_start",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "target_details": _regeneration_target_details(plan.targets),
                    "validation_before_status": current_validation_report.status,
                },
            )
        )
        validation_before_status = current_validation_report.status
        artifacts_before = deepcopy(current_artifacts)
        regeneration_kwargs = {}
        if regeneration_openai_client is not None and _accepts_keyword(
            dependencies.regenerate_artifacts, "openai_client"
        ):
            regeneration_kwargs["openai_client"] = regeneration_openai_client
        regeneration_response = dependencies.regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id=ReportId(runtime.file.file_id),
                report_name=runtime.report_name,
                attempt_index=attempt_index,
                plan=plan,
                current_artifacts=current_artifacts,
                doc_map=evidence_packs.get("doc_map", {}),
                evidence_packs=evidence_packs,
                settings=runtime.settings,
                ctx=attempt_ctx,
                source_status=source_status,
                categories=category_labels,
                vector_store_id=vector_store_id,
                md5=runtime.md5,
                publisher_name=runtime.publisher_name,
                source_url=runtime.source_url,
            ),
            **regeneration_kwargs,
        )
        current_artifacts = regeneration_response.updated_artifacts
        artifact_diff = _artifact_diff_summary(artifacts_before, current_artifacts)
        evidence_paths["artifacts"] = regeneration_response.artifacts_path
        evidence_paths[f"artifacts_regen_attempt_{attempt_index}"] = (
            regeneration_response.artifacts_snapshot_path
        )
        regenerated_payload = merge_artifacts_into_payload(
            deepcopy(base_payload), current_artifacts
        )
        _ensure_report_payload_complete(
            regenerated_payload,
            artifacts=current_artifacts,
            ctx=attempt_ctx,
            file_id=runtime.file.file_id,
            stage=f"regeneration_attempt_{attempt_index}",
        )
        current_validation_report = _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=attempt_ctx,
            dependencies=dependencies,
            validation_req=ValidationRequest(
                schema_version="1.0",
                report_id=ReportId(runtime.file.file_id),
                report=regenerated_payload,
                artifacts=current_artifacts,
                evidence_packs=evidence_packs,
                vector_store_id=vector_store_id,
                publisher_name=runtime.publisher_name,
                report_name=runtime.source_report_name or runtime.report_title,
                source_url=runtime.source_url,
            ),
            pack_name="validation",
            openai_client=validation_openai_client,
        )
        editorial_validation, editorial_path = (
            _evaluate_and_store_public_editorial_quality(
                runtime=runtime,
                dependencies=dependencies,
                artifacts=current_artifacts,
                pack_name=f"public_editorial_quality_regen_attempt_{attempt_index}",
                ctx=attempt_ctx,
            )
        )
        current_validation_report = _merge_public_editorial_quality(
            current_validation_report, editorial_validation
        )
        _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies,
            report=current_validation_report,
            pack_name="validation",
            ctx=attempt_ctx,
        )
        evidence_paths[f"public_editorial_quality_regen_attempt_{attempt_index}"] = (
            editorial_path
        )
        validation_snapshot_path = _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies,
            report=current_validation_report,
            pack_name=f"validation_regen_attempt_{attempt_index}",
            ctx=attempt_ctx,
        )
        if current_validation_report.source_path:
            evidence_paths["validation"] = current_validation_report.source_path
        evidence_paths[f"validation_regen_attempt_{attempt_index}"] = (
            validation_snapshot_path
        )
        attempt_result = RegenerationAttemptResult(
            attempt_index=attempt_index,
            plan_mode=plan.mode,
            regenerated_sections=regeneration_response.regenerated_sections,
            validation_before_status=validation_before_status,
            validation_after_status=current_validation_report.status,
            artifacts_path=regeneration_response.artifacts_path,
            artifacts_snapshot_path=regeneration_response.artifacts_snapshot_path,
            validation_path=current_validation_report.source_path,
            validation_snapshot_path=validation_snapshot_path,
        )
        attempts.append(attempt_result)
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_complete",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "regenerated_sections": regeneration_response.regenerated_sections,
                    "prompt_namespaces": regeneration_response.prompt_namespaces,
                    "artifacts_path": regeneration_response.artifacts_path,
                    "artifacts_snapshot_path": (
                        regeneration_response.artifacts_snapshot_path
                    ),
                    "artifact_diff": artifact_diff,
                    "validation_after_status": current_validation_report.status,
                },
            )
        )
        if public_issues:
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_completed",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "regenerated_sections": (
                            regeneration_response.regenerated_sections
                        ),
                    },
                )
            )
        if editorial_validation is not None:
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_revalidated",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "status": current_validation_report.status,
                        "quality_report_path": editorial_path,
                    },
                )
            )
        if current_validation_report.status == "pass":
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="validation_regen_pass",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                    },
                )
            )
            final_status = "pass"
            break
        final_status = current_validation_report.status

    max_reached = (
        current_validation_report.status != "pass" and len(attempts) >= max_attempts
    )

    if max_reached:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_max_attempts_reached",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_count": len(attempts),
                    "max_attempts": max_attempts,
                    "remaining_status": current_validation_report.status,
                    "unresolved_sections": [
                        issue.affected_section
                        for issue in current_validation_report.issues
                    ],
                },
            )
        )
        final_status = "fail"
    loop_state = RegenerationLoopState(
        attempt_count=len(attempts),
        max_attempts=max_attempts,
        final_status=final_status,
        max_reached=max_reached,
    )
    return (
        current_artifacts,
        current_validation_report,
        attempts,
        loop_state,
        evidence_paths,
    )


def _regeneration_target_details(targets) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for target in targets:
        rule_ids = sorted(
            {
                str(issue.rule_id or "").strip()
                for issue in target.issues
                if str(issue.rule_id or "").strip()
            }
        )
        details.append(
            {
                "target_section": target.target_section,
                "regenerate_steps": list(target.regenerate_steps),
                "prompt_namespaces": list(target.prompt_namespaces),
                "rule_ids": rule_ids,
            }
        )
    return details


def _artifact_diff_summary(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, List[str]]:
    before_keys = set(before.keys()) if isinstance(before, dict) else set()
    after_keys = set(after.keys()) if isinstance(after, dict) else set()
    common = before_keys & after_keys
    return {
        "added_keys": sorted(after_keys - before_keys),
        "removed_keys": sorted(before_keys - after_keys),
        "changed_keys": sorted(
            key for key in common if before.get(key) != after.get(key)
        ),
    }


def _store_validation_snapshot(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    report: ValidationReport,
    pack_name: str,
    ctx,
) -> str:
    output_path = dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path
    payload = report.to_dict()
    payload["source_path"] = output_path
    dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=runtime.report_name,
        ),
        ctx,
    )
    return output_path
