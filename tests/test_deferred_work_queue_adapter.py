from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.contracts.deferred_work import (
    DeferredWorkListRequest,
    DeferredWorkQueueMigrationRequest,
)
from src.contracts.run_budget import BudgetRequest, RunBudget, RunBudgetLimits
from src.orchestrators.deferred_work_queue_adapter import (
    migrate_deferred_work_to_workflow_queue,
)
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    list_deferred_work,
)
from src.services.workflow_queue_service import get_workflow_job
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="deferred-work-queue-adapter-test")


def _fixture_pdf() -> str:
    return str(
        Path("tests/fixtures/pdf_benchmark/golden")
        / "JULIUS BAER - Secular-outlook-2026_ACIG.pdf"
    )


def _deferred_request(
    tmp_path, *, workflow_id: str = "report_generation"
) -> BudgetRequest:
    now = datetime.now(timezone.utc)
    return BudgetRequest(
        schema_version="1.0",
        budget=RunBudget(
            schema_version="1.0",
            run_id="legacy-deferred-run",
            publisher_name="Legacy Publisher",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            limit_decision="defer",
            run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
        ),
        run_id="legacy-deferred-run",
        workflow_id=workflow_id,
        publisher_id="Legacy Publisher",
        report_id="legacy-report",
        source_id="legacy-source",
        stage="analysis_complete",
        plan_hash="legacy-plan-hash",
        reusable_artifact_references=(("local_pdf", _fixture_pdf(), ""),),
        resource_type="llm_provider",
        operation="generate_report",
        estimated_calls=2,
        idempotency_key=f"legacy:{workflow_id}",
        deferred_earliest_run_at_utc=(now - timedelta(seconds=1)).isoformat(),
        deferred_deadline_at_utc=(now + timedelta(hours=1)).isoformat(),
        deferred_max_attempts=3,
    )


def test_report_generation_deferred_work_migrates_idempotently_to_source_ingest(
    tmp_path,
) -> None:
    ctx = _ctx()
    decision = evaluate_budget_request(_deferred_request(tmp_path), ctx)
    assert decision.decision == "defer"
    request = DeferredWorkQueueMigrationRequest(
        schema_version="1.0",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        state_db=str(tmp_path / "state.sqlite"),
    )

    first = migrate_deferred_work_to_workflow_queue(request, ctx)
    second = migrate_deferred_work_to_workflow_queue(request, ctx)

    assert first.inspected_count == 1
    assert first.records[0].outcome == "submitted"
    assert second.records[0].outcome == "deduplicated"
    job = get_workflow_job(
        str(tmp_path / "state.sqlite"), first.records[0].workflow_job_id, ctx
    )
    assert job is not None
    assert job.queue_name == "source_ingest"
    assert job.status == "pending"
    assert job.execution_plan_hash == "legacy-plan-hash"
    legacy = list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0", usage_db_path=str(tmp_path / "usage.sqlite")
        ),
        ctx,
    ).records
    assert legacy[0].status == "pending"


def test_unsupported_legacy_work_is_retained_and_reported(tmp_path) -> None:
    ctx = _ctx()
    evaluate_budget_request(
        _deferred_request(tmp_path, workflow_id="unsupported_workflow"), ctx
    )

    response = migrate_deferred_work_to_workflow_queue(
        DeferredWorkQueueMigrationRequest(
            schema_version="1.0",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            state_db=str(tmp_path / "state.sqlite"),
        ),
        ctx,
    )

    assert response.records[0].outcome == "unresolved"
    assert response.records[0].reason == "unsupported_legacy_workflow"
