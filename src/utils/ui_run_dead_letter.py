from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.ui_run_control import (
    UiRunDeadLetterArtifactLinks,
    UiRunDeadLetterErrorTaxonomy,
    UiRunDeadLetterIdentity,
    UiRunDeadLetterRecord,
    UiRunDeadLetterRemediation,
    UiRunFailureClassification,
    UiRunRecord,
)
from src.utils.cache_utils import sha256_json

DEAD_LETTER_TRIAGE_STATUSES = {
    "open",
    "recovery_requested",
    "discarded",
    "escalated",
}
DEAD_LETTER_ACTIONS = {
    "auto_triaged",
    "retry_requested",
    "discarded",
    "escalated",
}
DEAD_LETTER_CATEGORIES = {
    "config_validation",
    "permission_blocked",
    "external_dependency",
    "artifact_io",
    "content_gap",
    "workflow_bug",
    "unknown",
}

_DEFAULT_RUNBOOK_LINK = "docs/ops/top_failure_runbooks.md"
_RUNBOOK_LINKS_BY_FAILURE_CODE = {
    "pdf_text_unextractable": f"{_DEFAULT_RUNBOOK_LINK}#pdf_text_unextractable",
    "pdf_text_ocr_failed": f"{_DEFAULT_RUNBOOK_LINK}#pdf_text_ocr_failed",
    "browser_download_timeout": f"{_DEFAULT_RUNBOOK_LINK}#browser_download_timeout",
    "publisher_inventory_http_empty": (
        f"{_DEFAULT_RUNBOOK_LINK}#publisher_inventory_http_empty"
    ),
}


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def infer_dead_letter_stage(*, run_type: str, error_code: str) -> str:
    code = _normalized_text(error_code).lower()
    stable_run_type = _normalized_text(run_type).lower()
    if code.startswith("ui_run_payload_"):
        return "request_validation"
    if code.startswith("publisher_inventory_"):
        return "publisher_discovery"
    if code.startswith("browser_download_") or code.startswith("report_download_"):
        return "report_download"
    if code.startswith("drive_"):
        return "drive_access"
    if code.startswith("wp_"):
        return "publish_wordpress"
    if code.startswith("openai_") or code.startswith("llm_"):
        return "llm_call"
    if code.startswith("ui_run_worker_") or code == "ui_run_launch_failed":
        return "worker_runtime"
    if stable_run_type == "publish":
        return "publish_pipeline"
    if stable_run_type == "ingest":
        return "ingest_pipeline"
    if stable_run_type == "candidate_extraction":
        return "candidate_extraction"
    if stable_run_type == "cover_images":
        return "cover_generation"
    if stable_run_type == "publisher_discovery":
        return "publisher_discovery"
    if stable_run_type == "report_download":
        return "report_download"
    if stable_run_type == "acquisition_audit":
        return "acquisition_audit"
    return stable_run_type or "unknown"


def infer_dead_letter_category(
    *,
    run_type: str,
    error_code: str,
    error_message: str,
    retryable: bool | None,
) -> tuple[str, str]:
    code = _normalized_text(error_code).lower()
    message = _normalized_text(error_message).lower()
    stage = infer_dead_letter_stage(run_type=run_type, error_code=error_code)
    if code.startswith("ui_run_payload_") or any(
        token in code
        for token in (
            "missing",
            "invalid",
            "config",
        )
    ):
        return (
            "config_validation",
            f"{stage} failed because required input or configuration was invalid.",
        )
    if any(
        token in code or token in message
        for token in ("auth", "permission", "captcha", "forbidden", "blocked")
    ):
        return (
            "permission_blocked",
            f"{stage} was blocked by permissions, auth, or access controls.",
        )
    if any(token in code for token in ("file_", "directory_", "upload_", "manifest_")):
        return (
            "artifact_io",
            f"{stage} failed while reading, writing, or validating local artifacts.",
        )
    if any(
        token in code
        for token in (
            "empty",
            "quality",
            "validation",
            "unreachable_archive",
            "no_report_assets",
        )
    ):
        return (
            "content_gap",
            f"{stage} completed with content-quality or source-coverage failure conditions.",
        )
    if retryable is True or any(
        token in code or token in message
        for token in (
            "timeout",
            "tempor",
            "rate_limit",
            "request_failed",
            "unavailable",
            "connect",
            "retry",
        )
    ):
        return (
            "external_dependency",
            f"{stage} exhausted retries against an external dependency or runtime boundary.",
        )
    if any(token in code for token in ("worker", "launch_failed", "unknown")):
        return (
            "workflow_bug",
            f"{stage} failed inside the local worker or orchestration path.",
        )
    return (
        "unknown",
        f"{stage} failed without a more specific dead-letter triage category.",
    )


def infer_dead_letter_identity(
    *,
    record: UiRunRecord,
) -> UiRunDeadLetterIdentity:
    payload = dict(record.request_payload or {})
    summary = dict(record.result_summary or {})
    return UiRunDeadLetterIdentity(
        schema_version="1.0",
        publisher_name=_normalized_text(summary.get("publisher_name")),
        publisher_insights_url=(
            _normalized_text(payload.get("publisher_insights_url"))
            or _normalized_text(payload.get("insights_url"))
        ),
        report_url=(
            _normalized_text(payload.get("url"))
            or _normalized_text(summary.get("final_page_url"))
        ),
    )


def infer_dead_letter_artifact_links(
    *,
    registry_path: str,
    record: UiRunRecord,
) -> UiRunDeadLetterArtifactLinks:
    registry = Path(registry_path).expanduser().resolve()
    manifest_path = (
        registry.parent
        / "ui_runs"
        / _normalized_text(record.run_id)
        / "replay_manifest.json"
    )
    return UiRunDeadLetterArtifactLinks(
        schema_version="1.0",
        output_path=_normalized_text(record.output_path),
        request_path=_normalized_text(record.request_path),
        manifest_path=str(manifest_path),
        artifact_paths=[
            _normalized_text(path)
            for path in list(record.artifact_paths or [])
            if _normalized_text(path)
        ],
    )


def _first_preflight_next_action(preflight_state: dict[str, Any]) -> str:
    blockers = preflight_state.get("blockers")
    if not isinstance(blockers, list):
        return ""
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        next_action = _normalized_text(blocker.get("next_action"))
        if next_action:
            return next_action
    return ""


def _resume_stage(
    *,
    record: UiRunRecord,
    checkpoints: list[str],
) -> str:
    summary = dict(record.result_summary or {})
    for key in ("latest_safe_resume_stage", "resume_from_stage", "checkpoint_stage"):
        stage = _normalized_text(summary.get(key))
        if stage:
            return stage
    for stage in reversed([_normalized_text(item) for item in checkpoints]):
        if stage:
            return stage
    return ""


def _runbook_link(error_code: str) -> str:
    code = _normalized_text(error_code).lower()
    if code in _RUNBOOK_LINKS_BY_FAILURE_CODE:
        return _RUNBOOK_LINKS_BY_FAILURE_CODE[code]
    if code.startswith("browser_download_") or code.startswith("report_download_"):
        return _RUNBOOK_LINKS_BY_FAILURE_CODE["browser_download_timeout"]
    if code.startswith("publisher_inventory_"):
        return _RUNBOOK_LINKS_BY_FAILURE_CODE["publisher_inventory_http_empty"]
    return _DEFAULT_RUNBOOK_LINK


def infer_dead_letter_remediation(
    *,
    record: UiRunRecord,
    classification: UiRunFailureClassification,
    step_id: str,
) -> UiRunDeadLetterRemediation:
    payload = dict(record.request_payload or {})
    summary = dict(record.result_summary or {})
    control = payload.get("workflow_control")
    workflow_control = control if isinstance(control, dict) else {}
    execution_plan = workflow_control.get("execution_plan")
    plan = execution_plan if isinstance(execution_plan, dict) else {}
    workflow_id = _normalized_text(
        workflow_control.get("workflow")
    ) or _normalized_text(record.run_type)
    checkpoint_stage = classification.resume_stage or _resume_stage(
        record=record,
        checkpoints=[],
    )
    idempotency_key = _normalized_text(plan.get("idempotency_key")) or _normalized_text(
        workflow_control.get("idempotency_key")
    )
    if not idempotency_key:
        idempotency_key = f"ui_run:{record.run_id}"
    budget_context = {
        key: workflow_control[key]
        for key in ("budget_profile", "budget_limit", "budget_status")
        if key in workflow_control
    }
    if "budget_context" in summary and isinstance(summary["budget_context"], dict):
        budget_context.update(summary["budget_context"])
    return UiRunDeadLetterRemediation(
        schema_version="1.0",
        workflow_id=workflow_id,
        step_id=_normalized_text(step_id),
        checkpoint_stage=checkpoint_stage,
        input_checksum=sha256_json(payload),
        idempotency_key=idempotency_key,
        remediation_code=classification.action,
        runbook_link=_runbook_link(record.error_code),
        budget_context=budget_context,
    )


def classify_ui_run_failure(
    *,
    record: UiRunRecord,
    structured_events: list[dict[str, Any]] | None = None,
    output_tail: str = "",
    checkpoints: list[str] | None = None,
    preflight_state: dict[str, Any] | None = None,
) -> UiRunFailureClassification:
    del structured_events
    code = _normalized_text(record.error_code).lower()
    message = _normalized_text(record.error_message).lower()
    tail = _normalized_text(output_tail).lower()
    checkpoint_names = list(checkpoints or [])
    preflight = dict(preflight_state or {})
    side_effect_warning = (
        "Review persisted artifacts and idempotency keys before repeating side effects."
    )

    credential_action = _first_preflight_next_action(preflight)
    if credential_action or any(
        token in f"{code} {message}"
        for token in ("credential", "api_key", "oauth", "missing_api_key")
    ):
        return UiRunFailureClassification(
            schema_version="1.0",
            action="request_credential",
            reason="Failure evidence indicates missing or invalid credentials.",
            side_effect_warning="No expensive side effects should be retried until credentials are fixed.",
            retryable=False,
            suggested_command=credential_action,
        )

    resume_stage = _resume_stage(record=record, checkpoints=checkpoint_names)
    if code == "card_publication_date_invalid" and record.run_type in {
        "ingest",
        "report_generation",
    }:
        repair_stage = resume_stage or "analysis_complete"
        return UiRunFailureClassification(
            schema_version="1.0",
            action="repair_report_card_publication_date",
            reason=(
                "Report-card manifest creation failed because no source-supported "
                "publication date was available."
            ),
            side_effect_warning=(
                "Repair only the report-card publication date from typed registry "
                "artifacts or an audited operator override, then resume from the "
                f"{repair_stage} checkpoint to avoid upstream model calls."
            ),
            retryable=False,
            resume_stage=repair_stage,
            suggested_command=(
                "remediate report-card publication date, then "
                f"--resume-from-stage {repair_stage}"
            ),
        )
    if resume_stage and record.run_type in {"ingest", "report_generation"}:
        return UiRunFailureClassification(
            schema_version="1.0",
            action="resume_from_checkpoint",
            reason=f"Run has a completed checkpoint suitable for resume: {resume_stage}.",
            side_effect_warning="Resume from the checkpoint to avoid repeating completed stages.",
            retryable=True,
            resume_stage=resume_stage,
            suggested_command=f"--resume-from-stage {resume_stage}",
        )

    if code == "ui_run_launch_failed" or any(
        token in f"{code} {message} {tail}"
        for token in ("permissionerror", "locked", "launch_failed")
    ):
        return UiRunFailureClassification(
            schema_version="1.0",
            action="cleanup_transient_resource",
            reason="The worker launch failed before workflow execution completed.",
            side_effect_warning="Cleanup only local worker/output resources before retrying.",
            retryable=False,
        )

    if record.error_retryable is True:
        retry_later = any(
            token in f"{code} {message}"
            for token in ("rate_limit", "quota", "temporarily_unavailable")
        )
        return UiRunFailureClassification(
            schema_version="1.0",
            action="retry_later" if retry_later else "retry_now",
            reason="The failed AppError is marked retryable by the workflow boundary.",
            side_effect_warning=side_effect_warning,
            retryable=True,
        )

    if record.run_type == "publish" and any(
        token in code for token in ("render", "projection", "artifact")
    ):
        return UiRunFailureClassification(
            schema_version="1.0",
            action="publish_only_continuation",
            reason="Publish run failed after upstream artifacts were already produced.",
            side_effect_warning="Continue only the publish side effect after confirming artifact IDs.",
            retryable=False,
        )

    if any(token in code for token in ("validation", "quality", "content_gap")):
        return UiRunFailureClassification(
            schema_version="1.0",
            action="mark_permanent",
            reason="Failure evidence indicates a non-retryable validation or content-quality failure.",
            side_effect_warning="Do not retry without changing source content or validation inputs.",
            retryable=False,
        )

    return UiRunFailureClassification(
        schema_version="1.0",
        action="mark_permanent",
        reason="Failure evidence is non-retryable and has no safe automated recovery path.",
        side_effect_warning=side_effect_warning,
        retryable=False,
    )


def build_dead_letter_record(
    *,
    registry_path: str,
    record: UiRunRecord,
    failed_at_utc: str,
    updated_at_utc: str,
    triage_status: str = "open",
    recovery_run_id: str = "",
    last_action: str = "auto_triaged",
    last_action_note: str = "",
    last_action_at_utc: str = "",
) -> UiRunDeadLetterRecord:
    retryable = bool(record.error_retryable)
    severity = _normalized_text(record.error_severity) or "error"
    stage = infer_dead_letter_stage(
        run_type=record.run_type,
        error_code=record.error_code,
    )
    category, reason = infer_dead_letter_category(
        run_type=record.run_type,
        error_code=record.error_code,
        error_message=record.error_message,
        retryable=record.error_retryable,
    )
    classification = classify_ui_run_failure(record=record)
    result_summary = asdict(record).get("result_summary", {})
    result_summary["failure_classification"] = {
        "schema_version": classification.schema_version,
        "action": classification.action,
        "reason": classification.reason,
        "side_effect_warning": classification.side_effect_warning,
        "retryable": classification.retryable,
        "resume_stage": classification.resume_stage,
        "suggested_command": classification.suggested_command,
    }
    auto_note = f"{classification.action}: {classification.reason}"
    return UiRunDeadLetterRecord(
        schema_version="1.0",
        run_id=record.run_id,
        run_type=record.run_type,
        display_name=record.display_name,
        run_status=record.status,
        triage_status=triage_status,
        triage_category=category,
        triage_reason=reason,
        failed_at_utc=failed_at_utc,
        updated_at_utc=updated_at_utc,
        error_taxonomy=UiRunDeadLetterErrorTaxonomy(
            schema_version="1.0",
            error_code=_normalized_text(record.error_code),
            error_message=_normalized_text(record.error_message),
            retryable=retryable,
            severity=severity,
            stage=stage,
        ),
        identity=infer_dead_letter_identity(record=record),
        artifact_links=infer_dead_letter_artifact_links(
            registry_path=registry_path,
            record=record,
        ),
        remediation=infer_dead_letter_remediation(
            record=record,
            classification=classification,
            step_id=stage,
        ),
        result_summary=result_summary,
        recovery_run_id=_normalized_text(recovery_run_id),
        last_action=_normalized_text(last_action),
        last_action_note=_normalized_text(last_action_note) or auto_note,
        last_action_at_utc=_normalized_text(last_action_at_utc),
    )
