from __future__ import annotations

from src.contracts.run_context import RunContext
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.services.report_store_service import (
    audit_validation_run_manifest,
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run-1", task_id="task-1", span_id="span-1"
    )


def _record(
    *, attempt: int, stage: str, terminal: bool = False, outcome: str = "succeeded"
) -> ValidationRunManifestStageRecord:
    return ValidationRunManifestStageRecord(
        schema_version="1.0",
        validation_run_id="validation-1",
        workflow_run_id="workflow-1",
        entity_type="report",
        publisher_id="publisher-1",
        report_id="report-1",
        source_identity_id="source-1",
        stage=stage,
        attempt_number=attempt,
        input_artifact_ids=("input-1",),
        output_artifact_ids=("output-1",),
        started_at_utc="2026-07-21T10:00:00Z",
        completed_at_utc="2026-07-21T10:01:00Z",
        terminal_outcome=outcome,
        failure_code="" if outcome == "succeeded" else "typed_failure",
        retryable=outcome == "failed",
        repair_disposition="not_required",
        duplicate_disposition="new",
        configuration_hash="config-hash",
        policy_hash="policy-hash",
        producer_build_identity="build-sha",
        entity_terminal=terminal,
    )


def _create(db_path: str) -> None:
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            workflow_run_id="workflow-1",
            configuration_hash="config-hash",
            policy_hash="policy-hash",
            producer_build_identity="build-sha",
            created_at_utc="2026-07-21T10:00:00Z",
        ),
        _ctx(),
    )


def test_manifest_retains_stages_and_derives_a_reconciled_final_cohort(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    first = record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=_record(attempt=1, stage="acquisition", outcome="failed"),
        ),
        _ctx(),
    )
    second = record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=_record(attempt=2, stage="acquisition"),
        ),
        _ctx(),
    )
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=_record(attempt=2, stage="publication", terminal=True),
        ),
        _ctx(),
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        _ctx(),
    )

    assert first.inserted is True
    assert second.superseded_attempts == 1
    assert audit.complete is True
    assert audit.final_cohort_report_ids == ("report-1",)
    actual_totals = {
        (item.stage, item.terminal_outcome, item.entity_count)
        for item in audit.stage_totals
    }
    assert actual_totals == {
        ("acquisition", "failed", 1),
        ("acquisition", "succeeded", 1),
        ("publication", "succeeded", 1),
    }


def test_manifest_audit_fails_closed_without_a_current_terminal_state(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=_record(attempt=1, stage="discovery"),
        ),
        _ctx(),
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        _ctx(),
    )

    assert audit.complete is False
    assert audit.incomplete_entity_ids == ("report|report-1|source-1",)
