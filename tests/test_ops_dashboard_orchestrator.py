from __future__ import annotations

from types import SimpleNamespace

from src.contracts.ops import OpsDashboardSnapshotRequest
from src.contracts.run_context import RunContext
from src.orchestrators import ops_dashboard_orchestrator as orch


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_collect_ops_dashboard_snapshot(
    caplog,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    external_boundary_mocks_only.setattr(
        orch.report_store_service,
        "list_metadata",
        lambda req, ctx: SimpleNamespace(
            records=[
                SimpleNamespace(file_id="f1", updated_at=2),
                SimpleNamespace(file_id="f2", updated_at=1),
            ]
        ),
    )
    external_boundary_mocks_only.setattr(
        orch.state_service,
        "list_processed",
        lambda req, ctx: SimpleNamespace(rows=[SimpleNamespace(file_id="f1")]),
    )
    external_boundary_mocks_only.setattr(
        orch.state_service,
        "list_published",
        lambda req, ctx: SimpleNamespace(rows=[SimpleNamespace(file_id="f1")]),
    )
    external_boundary_mocks_only.setattr(
        orch.state_service,
        "list_remediation_records",
        lambda req, ctx: SimpleNamespace(
            records=[
                SimpleNamespace(
                    remediation_id="rem-1",
                    workflow="publishing",
                    status="operator_action_required",
                    error_code="wordpress_credentials_missing",
                    action_code="escalate_credentials",
                    operator_next_action="refresh credentials",
                    attempt_count=1,
                    max_attempts=2,
                    checkpoint=None,
                    runbook_ref="docs/ops/recovery.md",
                )
            ]
        ),
    )
    external_boundary_mocks_only.setattr(
        orch,
        "deferred_work_metrics",
        lambda req, ctx: SimpleNamespace(
            queue_depth=2,
            oldest_age_seconds=3600,
            due_count=1,
            lease_count=1,
            completion_rate=0.5,
            repeated_deferral_count=1,
            terminal_count=0,
        ),
    )
    external_boundary_mocks_only.setattr(
        orch,
        "list_deferred_work",
        lambda req, ctx: SimpleNamespace(
            records=[
                SimpleNamespace(
                    workflow="report_generation",
                    stage="source_prepared",
                    status="pending",
                    affected_limit="day.calls",
                    attempt_count=1,
                    max_attempts=3,
                    defer_count=2,
                    earliest_run_at_utc="2026-07-18T13:00:00Z",
                    terminal_status="",
                )
            ]
        ),
    )
    external_boundary_mocks_only.setattr(
        orch.lock_service,
        "get_lock",
        lambda req, ctx: SimpleNamespace(
            found=True, lock=SimpleNamespace(owner_id="owner", pid=123)
        ),
    )
    external_boundary_mocks_only.setattr(
        orch.file_service,
        "file_stat",
        lambda req, ctx: SimpleNamespace(exists=True, size_bytes=10, mtime_utc=1.0),
    )

    response = orch.collect_ops_dashboard_snapshot(
        OpsDashboardSnapshotRequest(
            schema_version="1.0",
            output_dir="out",
            cache_dir="cache",
            state_db="state.sqlite",
            reports_db="reports.sqlite",
            ingest_lock_path="state/ingest.lock",
            usage_db_path="state/usage.sqlite",
        ),
        _ctx(),
    )

    assert len(response.reports) == 2
    assert response.reports[0]["file_id"] == "f1"
    assert len(response.processed) == 1
    assert len(response.published) == 1
    assert response.lock.found is True
    assert response.lock.owner_id == "owner"
    assert len(response.storage_health) == 4
    assert response.remediations == [
        {
            "remediation_id": "rem-1",
            "workflow": "publishing",
            "status": "operator_action_required",
            "error_code": "wordpress_credentials_missing",
            "action": "escalate_credentials",
            "next_action": "refresh credentials",
            "attempts": "1/2",
            "checkpoint": "",
            "blocker": "docs/ops/recovery.md",
        }
    ]
    assert response.deferred_work_metrics["queue_depth"] == 2
    assert response.deferred_work == [
        {
            "workflow": "report_generation",
            "stage": "source_prepared",
            "status": "pending",
            "affected_limit": "day.calls",
            "attempts": "1/3",
            "defer_count": 2,
            "earliest_run_at_utc": "2026-07-18T13:00:00Z",
            "terminal_status": "",
        }
    ]
    assert_logs_have_required_fields(caplog.records)
