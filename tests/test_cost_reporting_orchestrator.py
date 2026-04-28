from __future__ import annotations

import pytest

from src.contracts.costs import (
    CostReportRequest,
    CostReportResponse,
    CostReportingRequest,
    CostRollupRequest,
    CostRollupResponse,
    CostTotals,
    DailyCostTotal,
)
from src.contracts.run_context import RunContext
from src.orchestrators import cost_reporting_orchestrator as orch
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_cost_reporting_runs_requested_steps(
    caplog,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    report = CostReportResponse(
        schema_version="1.0",
        filter_type="date",
        filter_value="2026-02-10",
        totals=CostTotals(
            schema_version="1.0",
            total_input_tokens=1,
            total_output_tokens=2,
            total_tool_calls=3,
            estimated_cost_usd=0.01,
        ),
        top_steps=[],
        matched_entries=1,
    )
    rollup = CostRollupResponse(
        schema_version="1.0",
        out_path="out/cost-daily.json",
        totals_by_date={
            "2026-02-10": DailyCostTotal(
                schema_version="1.0",
                date_utc="2026-02-10",
                total_usd=0.01,
                input_tokens=1,
                output_tokens=2,
                tool_calls=3,
            )
        },
        totals_by_run={},
        totals_by_task={},
    )
    calls = {"report": 0, "rollup": 0}

    external_boundary_mocks_only.setattr(
        orch.cost_ledger_service,
        "generate_cost_report",
        lambda req, ctx: calls.__setitem__("report", calls["report"] + 1) or report,
    )
    external_boundary_mocks_only.setattr(
        orch.cost_ledger_service,
        "rollup_daily",
        lambda req, ctx: calls.__setitem__("rollup", calls["rollup"] + 1) or rollup,
    )

    response = orch.run_cost_reporting(
        CostReportingRequest(
            schema_version="1.0",
            report_request=CostReportRequest(
                schema_version="1.0", ledger_path="a.jsonl", date_utc="2026-02-10"
            ),
            rollup_request=CostRollupRequest(
                schema_version="1.0", ledger_path="a.jsonl", out_path="daily.json"
            ),
        ),
        _ctx(),
    )

    assert calls == {"report": 1, "rollup": 1}
    assert response.report == report
    assert response.rollup == rollup
    assert_logs_have_required_fields(caplog.records)


def test_cost_reporting_requires_work(
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    with pytest.raises(AppError) as exc_info:
        orch.run_cost_reporting(CostReportingRequest(schema_version="1.0"), _ctx())

    assert_app_error(
        exc_info.value,
        code="cost_reporting_request_invalid",
        retryable=False,
    )
    assert_logs_have_required_fields(caplog.records)
