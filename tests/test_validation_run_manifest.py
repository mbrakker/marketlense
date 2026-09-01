from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.publish import PublishOutcome
from src.contracts.run_context import RunContext
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestAttemptResolveRequest,
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
    resolve_validation_run_manifest_attempt,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run-1", task_id="task-1", span_id="span-1"
    )


def _record(
    *,
    attempt: int,
    stage: str,
    terminal: bool = False,
    outcome: str = "succeeded",
    report_id: str = "report-1",
    source_identity_id: str = "source-1",
    failure_code: str = "",
    idempotency_state: str = "new",
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
        report_id=report_id,
        source_identity_id=source_identity_id,
        stage=stage,
        attempt_number=attempt,
        parent_attempt_number=attempt - 1 if attempt > 1 else 0,
        input_artifact_ids=("input-1",),
        output_artifact_ids=("output-1",),
        started_at_utc="2026-07-21T10:00:00Z",
        completed_at_utc="2026-07-21T10:01:00Z",
        terminal_outcome=terminal_outcome,
        failure_code=(
            failure_code
            or (
                ""
                if terminal_outcome
                in {"succeeded", "publish_ready", "published_verified"}
                else "typed_failure"
            )
        ),
        retryable=terminal_outcome == "failed",
        repair_disposition="not_required",
        duplicate_disposition="new",
        supersession_state="current",
        idempotency_state=idempotency_state,
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


def test_manifest_attempt_resolution_requires_one_cohort_wide_lineage(tmp_path) -> None:
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

    next_attempt = resolve_validation_run_manifest_attempt(
        ValidationRunManifestAttemptResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            mode="next_replay",
        ),
        _ctx(),
    )
    current_attempt = resolve_validation_run_manifest_attempt(
        ValidationRunManifestAttemptResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            mode="current",
        ),
        _ctx(),
    )

    assert (next_attempt.attempt_number, next_attempt.parent_attempt_number) == (2, 1)
    assert (current_attempt.attempt_number, current_attempt.parent_attempt_number) == (
        1,
        0,
    )


def _insert_legacy_shadow_attempt(
    db_path: str,
    *,
    report_id: str = "report-1",
    source_identity_id: str,
    terminal_outcome: str = "",
) -> None:
    """Model a malformed current row written by a pre-invariant workflow."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO validation_run_entity_attempts(
                attempt_id, validation_run_id, entity_key, entity_type, publisher_id,
                report_id, source_identity_id, cohort_id, attempt_number,
                parent_attempt_number, cohort_disposition, is_current, created_at_utc,
                terminal_outcome, terminal_stage, failure_code, completed_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"legacy-shadow-{report_id}-{source_identity_id}",
                "validation-1",
                f"report|{report_id}|{source_identity_id}",
                "report",
                "publisher-1",
                report_id,
                source_identity_id,
                "cohort-1",
                1,
                0,
                "final_validation",
                1,
                "2026-07-21T10:00:00Z",
                terminal_outcome,
                "ingestion" if terminal_outcome else "",
                "",
                "2026-07-21T10:01:00Z" if terminal_outcome else "",
            ),
        )


def test_next_replay_supersedes_current_identity_not_in_frozen_cohort(tmp_path) -> None:
    """A replay keeps historical bad identity records out of its current lineage."""
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
    _insert_legacy_shadow_attempt(
        db_path,
        source_identity_id="checksum-that-is-not-a-cohort-identity",
    )

    next_attempt = resolve_validation_run_manifest_attempt(
        ValidationRunManifestAttemptResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            validation_run_id="validation-1",
            mode="next_replay",
        ),
        _ctx(),
    )

    with sqlite3.connect(db_path) as conn:
        current_identity_rows = conn.execute(
            "SELECT source_identity_id FROM validation_run_entity_attempts "
            "WHERE validation_run_id='validation-1' AND is_current=1"
        ).fetchall()
        superseded_shadow_rows = conn.execute(
            "SELECT is_current FROM validation_run_entity_attempts "
            "WHERE validation_run_id='validation-1' "
            "AND source_identity_id='checksum-that-is-not-a-cohort-identity'"
        ).fetchall()

    assert (next_attempt.attempt_number, next_attempt.parent_attempt_number) == (2, 1)
    assert current_identity_rows == [("source-1",)]
    assert superseded_shadow_rows == [(0,)]


def test_manifest_rejects_stage_identity_that_conflicts_with_frozen_member(
    tmp_path,
) -> None:
    """A processing stage cannot introduce a second identity for an admitted report."""
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

    with pytest.raises(AppError, match="immutable identity"):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                record=_record(
                    attempt=1,
                    stage="taxonomy",
                    source_identity_id="checksum-that-is-not-a-cohort-identity",
                ),
            ),
            _ctx(),
        )


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


def test_analysis_stage_recorder_preserves_inherited_identity_over_pdf_checksum(
    tmp_path,
) -> None:
    """A frozen cohort cannot gain a checksum-keyed analysis-stage entity."""
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    ctx = replace(
        _ctx(),
        producer_commit_sha="build-sha",
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        report_id="report-1",
        source_identity_id="source:admitted-report",
        publisher_id="publisher-1",
        configuration_hash="config-hash",
        policy_hash="policy-hash",
    )

    record_validation_analysis_stage(
        settings=SimpleNamespace(reports_db=db_path),
        ctx=ctx,
        stage="taxonomy",
        source_identity_id="pdf-checksum",
    )

    with sqlite3.connect(db_path) as connection:
        identities = connection.execute(
            "SELECT DISTINCT source_identity_id FROM validation_run_entity_attempts"
        ).fetchall()
    assert identities == [("source:admitted-report",)]


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
        ("wordpress_lookup", "succeeded"),
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
    assert "report|report-1|source-1:ingestion" in (
        audit.missing_required_stage_entity_ids
    )
    assert "report|report-1|source-1:repeat_publication" in (
        audit.missing_required_stage_entity_ids
    )


def test_manifest_audit_fails_when_a_frozen_cohort_member_disappears(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    for record in (
        _record(attempt=1, stage="discovery"),
        _record(attempt=1, stage="ingestion", terminal=True),
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0", db_path=db_path, record=record
            ),
            _ctx(),
        )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE validation_run_entity_attempts SET is_current=0
            WHERE validation_run_id='validation-1' AND report_id='report-1'
            """
        )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        _ctx(),
    )

    assert audit.complete is False
    assert audit.missing_cohort_report_ids == ("report-1",)
    assert audit.totals_reconciled is False


def test_manifest_audit_rejects_overlapping_reports_and_source_identities(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    records = (
        _record(attempt=1, stage="discovery"),
        _record(
            attempt=1,
            stage="discovery",
            report_id="report-2",
            source_identity_id="source-1",
        ),
        _record(
            attempt=1,
            stage="ingestion",
            report_id="report-2",
            source_identity_id="source-1",
            terminal=True,
        ),
    )
    for record in records:
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0", db_path=db_path, record=record
            ),
            _ctx(),
        )
    _insert_legacy_shadow_attempt(
        db_path,
        source_identity_id="source-2",
        terminal_outcome="publish_ready",
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0", db_path=db_path, validation_run_id="validation-1"
        ),
        _ctx(),
    )

    assert audit.complete is False
    assert audit.overlapping_current_report_ids == ("report-1",)
    assert audit.duplicate_source_identity_ids == ("source-1",)


def test_manifest_audit_surfaces_ambiguous_wordpress_lookup(tmp_path) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    for record in (
        _record(attempt=1, stage="discovery"),
        _record(
            attempt=1,
            stage="wordpress_lookup",
            outcome="failed",
            failure_code="wp_post_lookup_ambiguous",
        ),
        _record(
            attempt=1,
            stage="authenticated_readback",
            terminal=True,
            outcome="blocked",
        ),
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0", db_path=db_path, record=record
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
    assert audit.multiple_wordpress_post_report_ids == ("report-1",)


def test_full_manifest_requires_a_reused_verified_repeat_for_publication(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    _create(db_path)
    for stage in (
        "discovery",
        "candidate_qualification",
        "acquisition",
        "admission_preflight",
        "source_preparation",
        "source_validation",
        "evidence_generation",
        "structured_output_repair",
        "taxonomy",
        "category_fit",
        "artifact_generation",
        "regeneration",
        "grounding_validation",
        "semantic_validation",
        "rendering",
        "final_html_validation",
        "ingestion",
        "publication_preflight",
        "wordpress_lookup",
        "wordpress_write",
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                record=_record(attempt=1, stage=stage),
            ),
            _ctx(),
        )
    for record in (
        _record(
            attempt=1,
            stage="authenticated_readback",
            terminal=True,
            outcome="published_verified",
        ),
        _record(
            attempt=1,
            stage="repeat_publication",
            idempotency_state="new",
        ),
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0", db_path=db_path, record=record
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
    assert audit.missing_required_stage_entity_ids == (
        "report|report-1|source-1:repeat_publication_verified_reuse",
    )
