from __future__ import annotations

from dataclasses import replace

import pytest

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_context import RunContext
from src.contracts.validation_reliability import (
    ValidationReliabilityBuildRequest,
    ValidationReliabilityWriteRequest,
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
                idempotency_state="new",
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
    )
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=usage_db, entry=_usage_entry()
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
