from __future__ import annotations

from dataclasses import replace

import pytest

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_context import RunContext
from src.contracts.validation_reliability import (
    ValidationReliabilityBuildRequest,
    ValidationReliabilityWriteRequest,
)
from src.contracts.workflow_queue import (
    PublicationReadinessPayload,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.contracts.validation_run_manifest import (
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.services.llm_usage_ledger_service import append_usage
from src.services.report_store_service import (
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
)
from src.services.validation_reliability_service import (
    build_validation_reliability_artifact,
    write_validation_reliability_artifact,
)
from src.services.workflow_queue_service import (
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    fail_workflow_job,
    record_publication_readiness,
    requeue_workflow_job,
    start_workflow_job,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="workflow-1",
        task_id="task-1",
        span_id="span-1",
        trace_id="trace-1",
    )


def _create_run(reports_db: str) -> None:
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=reports_db,
            validation_run_id="validation-1",
            cohort_id="cohort-1",
            workflow_run_id="workflow-1",
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="build-sha",
            created_at_utc="2026-07-26T10:00:00+00:00",
        ),
        _ctx(),
    )


def _record(
    reports_db: str,
    *,
    attempt: int,
    stage: str,
    outcome: str = "succeeded",
    failure_code: str = "",
    repair_disposition: str = "not_required",
    entity_terminal: bool = False,
    idempotency_state: str = "new",
    started_at_utc: str = "2026-07-26T10:00:00+00:00",
    completed_at_utc: str = "2026-07-26T10:01:00+00:00",
) -> None:
    record_validation_run_manifest_stage(
        ValidationRunManifestRecordRequest(
            schema_version="1.0",
            db_path=reports_db,
            record=ValidationRunManifestStageRecord(
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
                started_at_utc=started_at_utc,
                completed_at_utc=completed_at_utc,
                terminal_outcome=outcome,
                failure_code=failure_code,
                retryable=outcome in {"failed", "blocked"},
                repair_disposition=repair_disposition,
                duplicate_disposition="none",
                supersession_state="current",
                idempotency_state=idempotency_state,
                configuration_hash="configuration-hash",
                policy_hash="policy-hash",
                producer_build_identity="build-sha",
                entity_terminal=entity_terminal,
            ),
        ),
        _ctx(),
    )


def _usage_entry() -> LLMUsageLedgerEntry:
    return LLMUsageLedgerEntry(
        schema_version="1.0",
        timestamp_utc="2026-07-26T10:02:00+00:00",
        provider="openai",
        action="evidence_generation",
        run_id="workflow-1",
        task_id="task-1",
        span_id="span-1",
        trace_id="trace-1",
        model="gpt-5-mini",
        request_id="request-1",
        publisher_name="Publisher",
        report_name="Report",
        source_url="https://example.com/report",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cached_input_tokens=0,
        tool_calls=0,
        estimated_cost_usd=0.012,
        prompt_namespace="report_vs/evidence/findings",
        prompt_hash="prompt-hash",
        provider_decision="openai_primary",
        cache_decision="disabled",
        temperature=0.0,
        seed=7,
        timeout_seconds=30.0,
        semantic_task="evidence_generation",
        report_id="report-1",
        workflow="report_analysis",
        stage="evidence_generation",
        artifact_family="evidence",
        validation_run_id="validation-1",
        cohort_id="cohort-1",
        workflow_run_id="workflow-1",
        publisher_id="publisher-1",
        model_policy_namespace="report_vs/evidence/findings",
        policy_namespace="report_vs/evidence/findings",
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_build_identity="build-sha",
    )


def _record_full_first_attempt(
    reports_db: str,
    *,
    attempt: int = 1,
    evidence_repair_disposition: str = "not_required",
    started_at_utc: str = "2026-07-26T10:00:00+00:00",
    completed_at_utc: str = "2026-07-26T10:01:00+00:00",
) -> None:
    for stage in (
        "admission_preflight",
        "source_preparation",
        "source_validation",
    ):
        _record(
            reports_db,
            attempt=attempt,
            stage=stage,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
        )
    _record(
        reports_db,
        attempt=attempt,
        stage="evidence_generation",
        repair_disposition=evidence_repair_disposition,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
    )
    for stage in (
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
    ):
        _record(
            reports_db,
            attempt=attempt,
            stage=stage,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
        )


def _record_durable_awaiting_review(
    state_db: str, *, operator_requeue: bool = False
) -> None:
    package_checksum = "package-1"
    record_publication_readiness(
        state_db,
        package_checksum=package_checksum,
        entity_type="report",
        package_reference="output/report-1.html",
        validation_reference="output/report-1.readiness.json",
        lineage_reference="retained:source-1",
        required_asset_status="ready",
        readiness_status="awaiting_review",
        reason="queue_readiness_deterministic_check",
        ctx=_ctx(),
    )
    submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="publication_readiness",
        job_type="publication_readiness.v1",
        payload=PublicationReadinessPayload(
            entity_type="report",
            entity_package_reference="output/report-1.html",
            package_checksum=package_checksum,
            validation_reference="output/report-1.readiness.json",
            lineage_reference="retained:source-1",
            required_asset_status="ready",
        ),
        idempotency_key="publication-readiness:report-1",
        deduplication_scope="validation-reliability-test",
        entity_type="report",
        entity_id="report-1",
        report_id="report-1",
    )
    job, created = enqueue_workflow_job(
        state_db, submission, _ctx(), now_utc="2026-07-26T10:10:00+00:00"
    )
    assert created is True
    claimed = claim_next_workflow_job(
        state_db,
        "publication_readiness",
        "worker-1",
        _ctx(),
        now_utc="2026-07-26T10:11:00+00:00",
    )
    assert claimed is not None and claimed.job_id == job.job_id
    start_workflow_job(
        state_db, job.job_id, "worker-1", _ctx(), now_utc="2026-07-26T10:12:00+00:00"
    )
    if operator_requeue:
        failed = fail_workflow_job(
            state_db,
            job.job_id,
            "worker-1",
            AppError(
                "publication_preflight_failed", "manual recovery", retryable=False
            ),
            _ctx(),
            now_utc="2026-07-26T10:13:00+00:00",
        )
        assert failed.status == "dead_letter"
        requeue_workflow_job(
            state_db,
            job.job_id,
            "operator-1",
            _ctx(),
            now_utc="2026-07-26T10:14:00+00:00",
        )
        claimed = claim_next_workflow_job(
            state_db,
            "publication_readiness",
            "worker-1",
            _ctx(),
            now_utc="2026-07-26T10:15:00+00:00",
        )
        assert claimed is not None and claimed.job_id == job.job_id
        start_workflow_job(
            state_db,
            job.job_id,
            "worker-1",
            _ctx(),
            now_utc="2026-07-26T10:16:00+00:00",
        )
    complete_workflow_job(
        state_db,
        job.job_id,
        "worker-1",
        WorkflowStageResult(
            output_reference="output/report-1.html",
            output_content_hash=package_checksum,
            output_verified=True,
        ),
        [],
        _ctx(),
        now_utc="2026-07-26T10:17:00+00:00",
    )


def test_reliability_artifact_is_deterministic_and_measures_recovery(tmp_path) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    _record(reports_db, attempt=1, stage="admission_preflight")
    _record(reports_db, attempt=1, stage="source_preparation")
    _record(reports_db, attempt=1, stage="source_validation")
    _record(
        reports_db,
        attempt=1,
        stage="evidence_generation",
        outcome="failed",
        failure_code="provider_timeout",
        started_at_utc="2026-07-26T10:00:00+00:00",
        completed_at_utc="2026-07-26T10:05:00+00:00",
    )
    _record(reports_db, attempt=2, stage="admission_preflight")
    _record(reports_db, attempt=2, stage="source_preparation")
    _record(reports_db, attempt=2, stage="source_validation")
    _record(
        reports_db,
        attempt=2,
        stage="evidence_generation",
        repair_disposition="targeted_repair",
        started_at_utc="2026-07-26T10:06:00+00:00",
        completed_at_utc="2026-07-26T10:10:00+00:00",
    )
    for stage in ("taxonomy", "category_fit", "artifact_generation"):
        _record(reports_db, attempt=2, stage=stage)
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(_usage_entry(), timestamp_utc="2026-07-26T10:04:00+00:00"),
        ),
        _ctx(),
    )

    request = ValidationReliabilityBuildRequest(
        schema_version="1.0",
        reports_db_path=reports_db,
        usage_db_path=usage_db,
        validation_run_id="validation-1",
    )
    first = build_validation_reliability_artifact(request, _ctx())
    second = build_validation_reliability_artifact(request, _ctx())

    assert first == second
    observed_transitions = [
        (row.from_state, row.to_state, row.conversion_rate) for row in first.transitions
    ]
    assert observed_transitions[:2] == [
        ("admitted", "source_prepared", 1.0),
        ("source_prepared", "evidence_complete", 1.0),
    ]
    failure = first.failed_transitions[0]
    assert (failure.from_state, failure.to_state, failure.failure_count) == (
        "source_prepared",
        "evidence_complete",
        1,
    )
    assert failure.failure_codes[0].failure_code == "provider_timeout"
    assert failure.median_duration_ms == 300_000
    assert failure.p95_duration_ms == 300_000
    assert failure.provider_call_count_before_failure == 1
    assert failure.total_tokens_before_failure == 120
    assert failure.estimated_cost_usd_before_failure == 0.012
    assert failure.successful_recovery_rate == 1.0
    assert first.failure_pareto[0].transition_pairs == (
        "source_prepared->evidence_complete",
    )
    first_attempt_stage = next(
        row
        for row in first.first_attempt_entities[0].stages
        if row.to_state == "evidence_complete"
    )
    assert first_attempt_stage.first_pass is False
    assert first_attempt_stage.eventual_success is True
    assert first_attempt_stage.first_failure_code == "provider_timeout"
    assert first_attempt_stage.first_failure_stage == "evidence_generation"
    assert first_attempt_stage.recovery_type == "bounded_recovery"
    assert first_attempt_stage.attempts_required == 2
    assert first_attempt_stage.operator_intervention is False
    assert first_attempt_stage.provider_call_count_before_recovery == 1
    assert first_attempt_stage.total_tokens_before_recovery == 120
    assert first_attempt_stage.estimated_cost_usd_before_recovery == 0.012
    first_attempt_transition = next(
        row
        for row in first.first_attempt_transitions
        if row.to_state == "evidence_complete"
    )
    assert first_attempt_transition.first_pass_conversion_rate == 0.0
    assert first_attempt_transition.eventual_conversion_rate == 1.0
    analysis_transition = next(
        row
        for row in first.first_attempt_transitions
        if row.to_state == "analysis_complete"
    )
    assert analysis_transition.first_attempt_eligible_entity_count == 0
    assert analysis_transition.bounded_recovery_entity_count == 0
    assert first.first_attempt_failure_pareto[0].failure_code == "provider_timeout"

    target = tmp_path / "reliability.json"
    response = write_validation_reliability_artifact(
        ValidationReliabilityWriteRequest(
            schema_version="1.0", artifact_path=str(target), artifact=first
        ),
        _ctx(),
    )
    assert response.artifact_hash == first.artifact_hash
    assert target.is_file()


def test_reliability_artifact_rejects_usage_without_required_attribution(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    _record(reports_db, attempt=1, stage="admission_preflight")

    with pytest.raises(AppError) as exc_info:
        append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=usage_db,
                entry=replace(_usage_entry(), cohort_id=""),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "llm_usage_validation_attribution_missing"


def test_reliability_artifact_accepts_usage_from_a_frozen_cohort_replay(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    _record(reports_db, attempt=1, stage="admission_preflight")
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(_usage_entry(), workflow_run_id="workflow-replay"),
        ),
        _ctx(),
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    assert artifact.validation_run_id == "validation-1"


def test_reliability_artifact_reports_optional_repair_skips_and_downstream_blocks(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    for stage in (
        "admission_preflight",
        "source_preparation",
        "source_validation",
        "evidence_generation",
        "taxonomy",
        "category_fit",
        "artifact_generation",
    ):
        _record(reports_db, attempt=1, stage=stage)
    _record(
        reports_db,
        attempt=1,
        stage="structured_output_repair",
        outcome="skipped",
    )
    _record(
        reports_db,
        attempt=1,
        stage="grounding_validation",
        outcome="failed",
        failure_code="validation_failed",
    )
    _record(
        reports_db,
        attempt=1,
        stage="ingestion",
        outcome="permanent_failure",
        failure_code="metadata_governance_blocked",
        entity_terminal=True,
    )
    _record(
        reports_db,
        attempt=1,
        stage="wordpress_lookup",
        outcome="blocked",
        failure_code="metadata_governance_blocked",
    )
    _record(
        reports_db,
        attempt=1,
        stage="authenticated_readback",
        outcome="blocked",
        failure_code="metadata_governance_blocked",
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    assert [
        (row.from_state, row.to_state, row.conversion_rate)
        for row in artifact.transitions
    ] == [
        ("admitted", "source_prepared", 1.0),
        ("source_prepared", "evidence_complete", 1.0),
        ("evidence_complete", "analysis_complete", 1.0),
        ("analysis_complete", "validation_complete", 0.0),
        ("validation_complete", "rendered", 0.0),
        ("rendered", "publish_ready", 0.0),
        ("publish_ready", "published", 0.0),
        ("published", "readback_verified", 0.0),
    ]
    assert [
        (row.from_state, row.to_state, row.failure_count)
        for row in artifact.failed_transitions
    ] == [
        ("analysis_complete", "validation_complete", 1),
        ("rendered", "publish_ready", 1),
        ("publish_ready", "published", 1),
        ("published", "readback_verified", 1),
    ]
    assert [
        (row.failure_code, row.failure_count) for row in artifact.failure_pareto
    ] == [
        ("metadata_governance_blocked", 3),
        ("validation_failed", 1),
    ]
    awaiting_review_stage = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "awaiting_review"
    )
    assert awaiting_review_stage.terminal_failure is True
    assert awaiting_review_stage.terminal_disposition == "permanent_failure"
    rendered_stage = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "rendered"
    )
    assert rendered_stage.first_failure_code == "validation_failed"
    assert rendered_stage.first_failure_stage == "grounding_validation"


def test_first_attempt_classifies_operator_recovery_and_verified_replay(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=1, stage=stage)
    _record(
        reports_db,
        attempt=1,
        stage="evidence_generation",
        outcome="failed",
        failure_code="validation_failed",
    )
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=2, stage=stage)
    _record(
        reports_db,
        attempt=2,
        stage="evidence_generation",
        repair_disposition="operator_intervention",
        idempotency_state="replayed",
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    evidence_stage = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "evidence_complete"
    )
    assert evidence_stage.first_pass is False
    assert evidence_stage.eventual_success is True
    assert evidence_stage.recovery_type == "operator_intervention"
    assert evidence_stage.operator_intervention is True
    assert evidence_stage.verified_replay is False


def test_a21_requires_durable_awaiting_review_not_ingestion(tmp_path) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(reports_db)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    assert (
        next(
            stage
            for stage in artifact.first_attempt_entities[0].stages
            if stage.to_state == "awaiting_review"
        ).eventual_success
        is False
    )
    assert artifact.first_attempt_entities[0].eventual_success is False
    assert all(
        stage.to_state != "publish_ready"
        for stage in artifact.first_attempt_entities[0].stages
    )
    assert (
        next(
            row for row in artifact.transitions if row.to_state == "publish_ready"
        ).conversion_rate
        == 1.0
    )


def test_a21_internal_repair_loses_entity_first_pass_and_has_typed_pareto(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(
        reports_db, evidence_repair_disposition="targeted_repair"
    )
    _record_durable_awaiting_review(state_db)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    entity = artifact.first_attempt_entities[0]
    awaiting_review = next(
        stage for stage in entity.stages if stage.to_state == "awaiting_review"
    )
    assert awaiting_review.first_pass is False
    assert awaiting_review.eventual_success is True
    assert awaiting_review.recovery_type == "bounded_recovery"
    assert entity.first_pass is False
    assert entity.eventual_success is True
    assert entity.bounded_recovery is True
    assert artifact.first_attempt_failure_pareto[0].failure_code == "targeted_repair"


def test_a21_structured_output_repair_stage_loses_first_pass(tmp_path) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(reports_db)
    _record(reports_db, attempt=1, stage="structured_output_repair")
    _record_durable_awaiting_review(state_db)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    entity = artifact.first_attempt_entities[0]
    awaiting_review = next(
        stage for stage in entity.stages if stage.to_state == "awaiting_review"
    )
    assert entity.first_pass is False
    assert awaiting_review.first_pass is False
    assert awaiting_review.recovery_type == "bounded_recovery"
    assert artifact.first_attempt_failure_pareto[0].failure_code == (
        "structured_output_repair"
    )


def test_a21_automatic_later_attempt_is_bounded_recovery_with_usage(tmp_path) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=1, stage=stage)
    _record(
        reports_db,
        attempt=1,
        stage="evidence_generation",
        outcome="failed",
        failure_code="provider_timeout",
        completed_at_utc="2026-07-26T10:05:00+00:00",
    )
    _record_full_first_attempt(
        reports_db,
        attempt=2,
        started_at_utc="2026-07-26T10:06:00+00:00",
        completed_at_utc="2026-07-26T10:10:00+00:00",
    )
    _record_durable_awaiting_review(state_db)
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=usage_db,
            entry=replace(_usage_entry(), timestamp_utc="2026-07-26T10:04:00+00:00"),
        ),
        _ctx(),
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    entity = artifact.first_attempt_entities[0]
    awaiting_review = next(
        stage for stage in entity.stages if stage.to_state == "awaiting_review"
    )
    assert entity.first_pass is False
    assert entity.eventual_success is True
    assert entity.bounded_recovery is True
    assert awaiting_review.attempts_required == 2
    assert awaiting_review.recovery_type == "bounded_recovery"
    assert awaiting_review.provider_call_count_before_recovery == 1
    assert awaiting_review.total_tokens_before_recovery == 120
    assert awaiting_review.estimated_cost_usd_before_recovery == 0.012
    assert artifact.first_attempt_failure_pareto[0].failure_code == "provider_timeout"


def test_a21_queue_requeue_is_operator_intervention_not_bounded_recovery(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(reports_db)
    _record_durable_awaiting_review(state_db, operator_requeue=True)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    entity = artifact.first_attempt_entities[0]
    awaiting_review = next(
        stage for stage in entity.stages if stage.to_state == "awaiting_review"
    )
    assert entity.first_pass is False
    assert entity.operator_intervention is True
    assert entity.bounded_recovery is False
    assert awaiting_review.recovery_type == "operator_intervention"
    assert awaiting_review.operator_intervention is True
    assert (
        artifact.first_attempt_failure_pareto[0].failure_code == "operator_intervention"
    )


def test_a21_verified_replay_requires_successful_repeat_publication_evidence(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(reports_db)
    _record(
        reports_db,
        attempt=1,
        stage="repeat_publication",
        idempotency_state="reused",
    )
    _record_durable_awaiting_review(state_db)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    assert artifact.first_attempt_entities[0].verified_replay is True


def test_a21_absent_run_usage_is_unavailable_not_zero(tmp_path) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    _create_run(reports_db)
    _record_full_first_attempt(reports_db)
    _record_durable_awaiting_review(state_db)

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            state_db_path=state_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    awaiting_review = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "awaiting_review"
    )
    assert awaiting_review.usage_attribution == "unavailable"
    assert awaiting_review.provider_call_count_before_recovery is None
    assert awaiting_review.input_tokens_before_recovery is None
    assert awaiting_review.output_tokens_before_recovery is None
    assert awaiting_review.total_tokens_before_recovery is None
    assert awaiting_review.estimated_cost_usd_before_recovery is None


def test_first_attempt_does_not_count_internal_automatic_repair_as_first_pass(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=1, stage=stage)
    _record(
        reports_db,
        attempt=1,
        stage="evidence_generation",
        repair_disposition="targeted_repair",
    )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    evidence_stage = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "evidence_complete"
    )
    assert evidence_stage.first_pass is False
    assert evidence_stage.eventual_success is True
    assert evidence_stage.recovery_type == "bounded_recovery"
    assert evidence_stage.attempts_required == 1


def test_first_attempt_classifies_later_lineage_attempt_without_operator_as_bounded(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    usage_db = str(tmp_path / "usage.sqlite")
    _create_run(reports_db)
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=1, stage=stage)
    _record(
        reports_db,
        attempt=1,
        stage="evidence_generation",
        outcome="failed",
        failure_code="provider_timeout",
    )
    for stage in ("admission_preflight", "source_preparation", "source_validation"):
        _record(reports_db, attempt=2, stage=stage)
    _record(reports_db, attempt=2, stage="evidence_generation")

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=reports_db,
            usage_db_path=usage_db,
            validation_run_id="validation-1",
        ),
        _ctx(),
    )

    evidence_stage = next(
        stage
        for stage in artifact.first_attempt_entities[0].stages
        if stage.to_state == "evidence_complete"
    )
    assert evidence_stage.recovery_type == "bounded_recovery"
