from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_context import RunContext
from src.services import llm_usage_ledger_service as svc


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
        trace_id="trace",
    )


def _entry() -> LLMUsageLedgerEntry:
    return LLMUsageLedgerEntry(
        schema_version="1.0",
        timestamp_utc="2026-07-11T12:00:00+00:00",
        provider="openai",
        action="openai_chat_json",
        run_id="run",
        task_id="task",
        span_id="span",
        trace_id="trace",
        model="gpt-5-mini",
        request_id="resp_1",
        publisher_name="Example Publisher",
        report_name="Example Report",
        source_url="https://example.com/report",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cached_input_tokens=0,
        tool_calls=0,
        estimated_cost_usd=0.001,
        prompt_namespace="report/example",
        prompt_hash="prompt-hash",
        provider_decision="openai_primary",
        cache_decision="disabled",
        temperature=0.0,
        seed=42,
        timeout_seconds=30.0,
        metadata={"route": "test"},
    )


def test_llm_usage_ledger_appends_sqlite_row(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_usage_ledger_service")
    db_path = tmp_path / "usage.sqlite"
    entry = _entry()

    response = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=entry,
        ),
        _ctx(),
    )

    assert response.row_id == 1
    assert response.db_path == str(db_path)
    assert_no_defaulted_required_fields(entry)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from llm_usage_events").fetchone()
    assert row is not None
    assert row["provider"] == "openai"
    assert row["action"] == "openai_chat_json"
    assert row["publisher_name"] == "Example Publisher"
    assert row["report_name"] == "Example Report"
    assert row["source_url"] == "https://example.com/report"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5
    assert row["total_tokens"] == 15
    assert row["provider_decision"] == "openai_primary"
    assert json.loads(row["metadata_json"]) == {"route": "test"}

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.llm_usage_ledger_service"
    ]
    assert [record["event"] for record in records] == [
        "llm_usage_ledger_append_start",
        "llm_usage_ledger_append_complete",
    ]
    assert_logs_have_required_fields(records)
