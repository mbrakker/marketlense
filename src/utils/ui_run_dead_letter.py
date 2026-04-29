from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.ui_run_control import (
    UiRunDeadLetterArtifactLinks,
    UiRunDeadLetterErrorTaxonomy,
    UiRunDeadLetterIdentity,
    UiRunDeadLetterRecord,
    UiRunRecord,
)

DEAD_LETTER_TRIAGE_STATUSES = {
    "open",
    "recovery_requested",
    "discarded",
}
DEAD_LETTER_ACTIONS = {
    "auto_triaged",
    "retry_requested",
    "discarded",
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
    if any(token in code or token in message for token in ("auth", "permission", "captcha", "forbidden", "blocked")):
        return (
            "permission_blocked",
            f"{stage} was blocked by permissions, auth, or access controls.",
        )
    if any(token in code for token in ("file_", "directory_", "upload_", "manifest_")):
        return (
            "artifact_io",
            f"{stage} failed while reading, writing, or validating local artifacts.",
        )
    if any(token in code for token in ("empty", "quality", "validation", "unreachable_archive", "no_report_assets")):
        return (
            "content_gap",
            f"{stage} completed with content-quality or source-coverage failure conditions.",
        )
    if retryable is True or any(
        token in code or token in message
        for token in ("timeout", "tempor", "rate_limit", "request_failed", "unavailable", "connect", "retry")
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
        registry.parent / "ui_runs" / _normalized_text(record.run_id) / "replay_manifest.json"
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
        result_summary=asdict(record).get("result_summary", {}),
        recovery_run_id=_normalized_text(recovery_run_id),
        last_action=_normalized_text(last_action),
        last_action_note=_normalized_text(last_action_note),
        last_action_at_utc=_normalized_text(last_action_at_utc),
    )
