from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.publish import PublishOutcome
from src.contracts.run_context import RunContext
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.orchestrators._report_analysis_orchestrator.manifest import (
    record_validation_analysis_stage,
)
from src.orchestrators.publish_orchestrator import (
    _record_validation_cohort_publish_outcomes,
)
from src.services.report_store_service import (
    audit_validation_run_manifest,
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run-1", task_id="task-1", span_id="span-1"
    )


def _record(
    *, attempt: int, stage: str, terminal: bool = False, outcome: str = "succeeded"
) -> ValidationRunManifestStageRecord:
    terminal_outcome = (
        "publish_ready" if terminal and outcome == "succeeded" else outcome
    )
    return ValidationRunManifestStageRecord(
        schema_version="1.0",
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        workflow_run_id="workflow-1",
        entity_type="report",
        publisher_id="publisher-1",
        report_id="report-1",
        source_identity_id="source-1",
        stage=stage,
        attempt_number=attempt,
        parent_attempt_number=attempt - 1 if attempt > 1 else 0,
        input_artifact_ids=("input-1",),
        output_artifact_ids=("output-1",),
        started_at_utc="2026-07-21T10:00:00Z",
        completed_at_utc="2026-07-21T10:01:00Z",
        terminal_outcome=terminal_outcome,
        failure_code=(
            ""
            if terminal_outcome in {"succeeded", "publish_ready"}
            else "typed_failure"
        ),
        retryable=terminal_outcome == "failed",
        repair_disposition="not_required",
        duplicate_disposition="new",
        supersession_state="current",
        idempotency_state="new",
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
            cohort_id="cohort-1",
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
        ("publication", "publish_ready", 1),
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


def test_manifest_rejects_nonterminal_outcomes_at_closure(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    with pytest.raises(AppError, match="invalid outcome"):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                record=_record(
                    attempt=1,
                    stage="publication",
                    terminal=True,
                    outcome="failed",
                ),
            ),
            _ctx(),
        )


def test_analysis_stage_recorder_uses_inherited_validation_provenance(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    ctx = replace(
        _ctx(),
        producer_commit_sha="build-sha",
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        report_id="report-1",
        source_identity_id="source-1",
        publisher_id="publisher-1",
        configuration_hash="config-hash",
        policy_hash="policy-hash",
    )

    record_validation_analysis_stage(
        settings=SimpleNamespace(reports_db=db_path),
        ctx=ctx,
        stage="taxonomy",
        source_identity_id="source-1",
        input_artifact_ids=("vector-store-1",),
        output_artifact_ids=("payments",),
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        ctx,
    )
    assert audit.complete is False
    assert {
        (item.stage, item.terminal_outcome, item.entity_count)
        for item in audit.stage_totals
    } == {("taxonomy", "succeeded", 1)}


def test_analysis_stage_recorder_uses_workspace_identity_for_local_runs(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            cohort_id="cohort-1",
            workflow_run_id="workflow-1",
            configuration_hash="config-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-21T10:00:00Z",
        ),
        _ctx(),
    )
    ctx = replace(
        _ctx(),
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        report_id="report-1",
        source_identity_id="source-1",
        publisher_id="publisher-1",
        configuration_hash="config-hash",
        policy_hash="policy-hash",
    )

    record_validation_analysis_stage(
        settings=SimpleNamespace(reports_db=db_path),
        ctx=ctx,
        stage="taxonomy",
        source_identity_id="source-1",
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        ctx,
    )
    assert {(item.stage, item.entity_count) for item in audit.stage_totals} == {
        ("taxonomy", 1)
    }


def test_analysis_stage_recorder_rejects_missing_validation_provenance(
    tmp_path,
) -> None:
    with pytest.raises(AppError, match="missing inherited provenance"):
        record_validation_analysis_stage(
            settings=SimpleNamespace(reports_db=str(tmp_path / "reports.sqlite")),
            ctx=replace(_ctx(), validation_run_id="validation-1"),
            stage="taxonomy",
            source_identity_id="source-1",
        )


def test_wordpress_outcome_closes_the_matching_immutable_cohort_member(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(
        json.dumps(
            {
                "cohort_id": "cohort-1",
                "configuration_hash": "config-hash",
                "policy_hash": "policy-hash",
                "members": [{"file_id": "report-1", "md5_checksum": "source-1"}],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation:cohort-1",
            cohort_id="cohort-1",
            workflow_run_id="workflow-1",
            configuration_hash="config-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-21T10:00:00Z",
        ),
        _ctx(),
    )

    _record_validation_cohort_publish_outcomes(
        cohort_manifest=str(cohort_path),
        reports_db=db_path,
        outcomes=[
            PublishOutcome(
                schema_version="1.0",
                html_path="out/report.html",
                file_id="report-1",
                status="published",
                post_id=42,
                post_url="https://sandbox.example/reports/report-1",
                publication_outcome="post_created",
                authenticated_readback_verified=True,
            )
        ],
        ctx=_ctx(),
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation:cohort-1",
        ),
        _ctx(),
    )
    assert audit.complete is True
    assert audit.final_cohort_report_ids == ("report-1",)
    assert {(item.stage, item.terminal_outcome) for item in audit.stage_totals} == {
        ("publication_preflight", "succeeded"),
        ("wordpress_write", "succeeded"),
        ("authenticated_readback", "published_verified"),
    }


def test_full_manifest_audit_reports_missing_mandatory_stages(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=_record(attempt=1, stage="publication", terminal=True),
        ),
        _ctx(),
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            require_full_workflow=True,
        ),
        _ctx(),
    )

    assert audit.complete is False
    assert "report|report-1|source-1:admission_preflight" in (
        audit.missing_required_stage_entity_ids
    )
    assert "report|report-1|source-1:ingest" in (
        audit.missing_required_stage_entity_ids
    )
    assert "report|report-1|source-1:repeat_publication" in (
        audit.missing_required_stage_entity_ids
    )
