from __future__ import annotations

from types import SimpleNamespace

from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.budget import (
    build_report_download_budget,
    build_report_download_telemetry_budget,
    read_report_download_budget_usage,
    record_report_download_budget_event,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="acquisition-run", task_id="task", span_id="span"
    )


def test_report_download_budget_records_completed_work_idempotently_in_shared_ledger(
    tmp_path,
) -> None:
    request = SimpleNamespace(
        publisher_name="Publisher",
        settings=SimpleNamespace(
            run_budget_enabled=True,
            usage_db_path=str(tmp_path / "usage.sqlite"),
            daily_spend_stop_usd=5.0,
            run_budget_max_browser_launches=2,
            run_budget_max_pdfs=2,
            run_budget_max_drive_writes=1,
            run_budget_limit_decision="stop",
        ),
    )
    budget = build_report_download_budget(request, _ctx())
    assert budget is not None

    record_report_download_budget_event(
        budget=budget,
        event_key="drive:acquisition-run:upload-1",
        metric="drive_writes",
        ctx=_ctx(),
    )
    record_report_download_budget_event(
        budget=budget,
        event_key="pdf:acquisition-run:download-1",
        metric="pdfs",
        ctx=_ctx(),
    )
    record_report_download_budget_event(
        budget=budget,
        event_key="pdf:acquisition-run:download-1",
        metric="pdfs",
        ctx=_ctx(),
    )
    usage = read_report_download_budget_usage(budget, _ctx())

    assert usage is not None
    assert usage.drive_writes == 1
    assert usage.pdfs == 1


def test_mailbox_telemetry_uses_report_run_ledger_when_enforcement_is_disabled(
    tmp_path,
) -> None:
    request = SimpleNamespace(
        publisher_name="Publisher",
        settings=SimpleNamespace(
            run_budget_enabled=False,
            usage_db_path=str(tmp_path / "usage.sqlite"),
            run_budget_policy_version="budget-policy-v3",
        ),
    )

    budget = build_report_download_telemetry_budget(request, _ctx())

    assert budget.run_id == "acquisition-run"
    assert budget.publisher_name == "Publisher"
    assert budget.usage_db_path == str(tmp_path / "usage.sqlite")
    assert budget.enabled_effect_kinds == ("mailbox_read",)
    assert budget.policy_version == "budget-policy-v3"
