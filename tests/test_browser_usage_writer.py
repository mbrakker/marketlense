from __future__ import annotations

import sqlite3
from pathlib import Path

from src.contracts.llm_usage import LLMUsageRunSummaryRequest
from src.contracts.openai import OpenAIUsageAccountingRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download.usage_writer import BrowserUsageWriter
from src.services.llm_usage_ledger_service import read_usage_run_summary


def test_browser_usage_writer_flushes_queued_event_without_blocking_callback(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    writer = BrowserUsageWriter(
        ctx=RunContext(
            schema_version="1.0", run_id="run", task_id="task", span_id="span"
        ),
        queue_size=1,
        normalized_url="https://example.com/report",
    )
    accepted = writer.enqueue(
        OpenAIUsageAccountingRequest(
            schema_version="1.0",
            step_name="browser_use_llm_call",
            model="gpt-5-mini",
            input_tokens=11,
            output_tokens=7,
            tool_calls=0,
            cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
            cost_daily_path=str(tmp_path / "cost-daily.json"),
            emit_cost_ledger=False,
            model_pricing={},
            usage_db_path=str(db_path),
            provider="openai",
            action="browser_use_llm_call",
            call_ordinal=1,
        )
    )

    assert accepted is True
    shutdown = writer.flush(timeout_seconds=3.0)
    assert shutdown.drained is True
    assert shutdown.written_events == 1
    assert shutdown.pending_events == 0
    assert shutdown.dropped_events == 0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select action, input_tokens, output_tokens, call_ordinal from llm_usage_events"
        ).fetchone()
    assert row == ("browser_use_llm_call", 11, 7, 1)

    summary = read_usage_run_summary(
        LLMUsageRunSummaryRequest(
            schema_version="1.0",
            db_path=str(db_path),
            run_id="run",
            action="browser_use_llm_call",
        ),
        RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span"),
    )

    assert summary.call_count == 1
    assert summary.input_tokens == 11
    assert summary.output_tokens == 7
