from __future__ import annotations

from src.contracts.deferred_work import DeferredWorkItem
from src.orchestrators.recovery_adapter_registry import build_recovery_adapter_registry
from src.orchestrators.workflow_control_orchestrator import (
    default_workflow_control_settings,
)


def test_registry_exposes_all_proven_deferred_work_resume_adapters(
    ingest_settings,
) -> None:
    registry = build_recovery_adapter_registry(
        ingest_settings=ingest_settings,
        workflow_control_settings=default_workflow_control_settings(),
    )

    assert registry.supported_workflows == (
        "report_generation",
        "report_download",
        "publisher_inventory",
    )
    assert set(registry.deferred_work_dependencies.plan_builders) == {
        "report_generation",
        "report_download",
        "publisher_inventory",
    }
    assert set(registry.deferred_work_dependencies.resumers) == {
        "report_generation",
        "report_download",
        "publisher_inventory",
    }


def _item(workflow: str, source_id: str) -> DeferredWorkItem:
    return DeferredWorkItem(
        schema_version="1.0",
        work_key=f"deferred:{workflow}",
        workflow=workflow,
        stage="route_plan",
        run_id="run-1",
        resource_type="browser",
        operation="resume",
        reason_code="budget_deferred",
        affected_limit="calls",
        earliest_run_at_utc="2026-01-01T00:00:00Z",
        deadline_at_utc="2027-01-01T00:00:00Z",
        attempt_count=1,
        max_attempts=3,
        deferred_at_utc="2026-01-01T00:00:00Z",
        updated_at_utc="2026-01-01T00:00:00Z",
        source_id=source_id,
        publisher_id="Publisher",
        plan_hash="original",
        idempotency_key="original-key",
    )


def test_acquisition_adapters_enqueue_one_idempotent_typed_recovery_job(
    ingest_settings, run_context
) -> None:
    registry = build_recovery_adapter_registry(
        ingest_settings=ingest_settings,
        workflow_control_settings=default_workflow_control_settings(),
    )
    for workflow, queue_name in (
        ("report_download", "report_acquisition"),
        ("publisher_inventory", "publisher_discovery"),
    ):
        item = _item(workflow, "https://example.test/insights")
        plan = registry.deferred_work_dependencies.plan_builders[workflow](
            item, run_context
        )
        assert plan.resume_stage.startswith("queue_")
        assert (
            registry.deferred_work_dependencies.resumers[workflow](
                item, plan, run_context
            )
            == "completed"
        )
        assert (
            registry.deferred_work_dependencies.resumers[workflow](
                item, plan, run_context
            )
            == "completed"
        )

        from src.services.workflow_queue_service import read_workflow_queue_health

        health = read_workflow_queue_health(ingest_settings.state_db, run_context)
        assert next(
            row for row in health if row.queue_name == queue_name
        ).status_counts == {"pending": 1}
