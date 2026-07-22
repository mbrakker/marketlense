"""Stage-level validation-manifest recording for report analysis.

This adapter owns no workflow decisions. It projects a completed orchestration
stage into the canonical report-store manifest only when the inherited context
is a frozen validation cohort.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.contracts.semantic_ids import RunId, ValidationRunId
from src.contracts.validation_run_manifest import (
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.services.report_store_service import record_validation_run_manifest_stage
from src.utils.errors import AppError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_validation_manifest_stage(
    *,
    settings: Any,
    ctx: Any,
    stage: str,
    source_identity_id: str,
    input_artifact_ids: tuple[str, ...] = (),
    output_artifact_ids: tuple[str, ...] = (),
    started_at_utc: str = "",
    terminal_outcome: str = "succeeded",
    failure_code: str = "",
    retryable: bool = False,
    repair_disposition: str = "not_required",
    duplicate_disposition: str = "none",
    idempotency_state: str = "new",
    attempt_number: int = 1,
    parent_attempt_number: int = 0,
    entity_terminal: bool = False,
) -> None:
    """Append a completed workflow stage, or no-op outside a validation cohort."""
    validation_run_id = str(getattr(ctx, "validation_run_id", "") or "").strip()
    if not validation_run_id:
        return
    required = {
        "validation_run_id": validation_run_id,
        "cohort_id": str(getattr(ctx, "cohort_id", "") or "").strip(),
        "run_id": str(getattr(ctx, "run_id", "") or "").strip(),
        "report_id": str(getattr(ctx, "report_id", "") or "").strip(),
        "source_identity_id": str(source_identity_id or "").strip(),
        "configuration_hash": str(getattr(ctx, "configuration_hash", "") or "").strip(),
        "policy_hash": str(getattr(ctx, "policy_hash", "") or "").strip(),
        "producer": str(getattr(ctx, "producer_commit_sha", "") or "").strip(),
    }
    missing = sorted(key for key, value in required.items() if not value)
    if missing:
        raise AppError(
            code="validation_manifest_context_incomplete",
            message="Validation analysis stage is missing inherited provenance",
            retryable=False,
            context={"stage": stage, "missing_fields": missing},
        )
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=str(settings.reports_db),
            record=ValidationRunManifestStageRecord(
                schema_version="1.0",
                validation_run_id=ValidationRunId(validation_run_id),
                cohort_id=required["cohort_id"],
                workflow_run_id=RunId(required["run_id"]),
                entity_type="report",
                publisher_id=(
                    str(getattr(ctx, "publisher_id", "") or "").strip()
                    or "unattributed"
                ),
                report_id=required["report_id"],
                source_identity_id=required["source_identity_id"],
                stage=stage,
                attempt_number=max(1, int(attempt_number or 1)),
                parent_attempt_number=max(0, int(parent_attempt_number or 0)),
                input_artifact_ids=tuple(
                    str(value) for value in input_artifact_ids if value
                ),
                output_artifact_ids=tuple(
                    str(value) for value in output_artifact_ids if value
                ),
                started_at_utc=started_at_utc or _utc_now(),
                completed_at_utc=_utc_now(),
                terminal_outcome=terminal_outcome,
                failure_code=failure_code,
                retryable=retryable,
                repair_disposition=repair_disposition,
                duplicate_disposition=duplicate_disposition,
                supersession_state="current",
                idempotency_state=idempotency_state,
                configuration_hash=required["configuration_hash"],
                policy_hash=required["policy_hash"],
                producer_build_identity=required["producer"],
                cohort_disposition="final_validation",
                entity_terminal=entity_terminal,
            ),
        ),
        ctx,
    )


def record_validation_analysis_stage(**kwargs: Any) -> None:
    """Compatibility name for analysis callers of the shared stage recorder."""

    record_validation_manifest_stage(**kwargs)
