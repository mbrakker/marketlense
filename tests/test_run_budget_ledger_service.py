from __future__ import annotations

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_budget import (
    RunBudget,
    RunBudgetEventAppendRequest,
    RunBudgetUsageReadRequest,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    append_run_budget_side_effect,
    append_usage,
    read_run_budget_usage,
)


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="budget-run", task_id="budget-task", span_id="budget-span")


def _budget(db_path: str) -> RunBudget:
    return RunBudget(
        schema_version="1.0", run_id="budget-run", publisher_name="Publisher",
        usage_db_path=db_path, day_utc="2026-07-14", max_drive_writes=2,
    )


def test_canonical_budget_ledger_merges_run_day_and_publisher_without_double_counting(tmp_path) -> None:
    db_path = str(tmp_path / "usage.sqlite")
    budget = _budget(db_path)
    ctx = _ctx()
    append_run_budget_side_effect(
        RunBudgetEventAppendRequest(schema_version="1.0", budget=budget, event_key="drive:one", metric="drive_writes"),
        ctx,
    )
    replay = append_run_budget_side_effect(
        RunBudgetEventAppendRequest(schema_version="1.0", budget=budget, event_key="drive:one", metric="drive_writes"),
        ctx,
    )
    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=db_path,
            entry=LLMUsageLedgerEntry(
                schema_version="1.0", timestamp_utc="2026-07-14T10:00:00+00:00",
                provider="openai", action="summary", run_id="other-run", task_id="task",
                span_id="span", trace_id="trace", model="gpt-5-mini", request_id="request",
                publisher_name="Publisher", report_name="report", source_url="https://example.test/report",
                input_tokens=3, output_tokens=4, total_tokens=7, cached_input_tokens=0,
                tool_calls=0, estimated_cost_usd=0.12, prompt_namespace="report", prompt_hash="hash",
                provider_decision="direct", cache_decision="miss", temperature=0.0,
                seed=None, timeout_seconds=30.0, metadata={},
            ),
        ),
        ctx,
    )

    response = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    )

    assert replay.inserted is False
    assert response.event_count == 1
    assert response.run_usage.drive_writes == 1
    assert response.day_usage.drive_writes == 1
    assert response.publisher_usage.spend_usd == 0.12
    assert response.usage.drive_writes == 1
    assert response.usage.tokens == 7
