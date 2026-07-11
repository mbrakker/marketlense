from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.llm_usage import (
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
    LLMUsageMedianRebuildRequest,
    LLMUsageLedgerOutcomeUpdateRequest,
    LLMUsageLedgerReconciliationRequest,
)
from src.contracts.costs import CostLedgerAppendRequest, CostLedgerEntry
from src.contracts.run_context import RunContext
from src.services import cost_ledger_service, llm_usage_ledger_service as svc
from src.utils.errors import AppError


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
    assert response.median_db_path == str(tmp_path / "usage_medians.sqlite")
    assert response.median_row_count == 1
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
    with sqlite3.connect(response.median_db_path) as conn:
        median_row = conn.execute(
            """
            select sample_count, median_input_tokens, median_output_tokens,
                   median_total_tokens
            from llm_usage_medians
            where provider = ? and action = ? and model = ? and prompt_namespace = ?
            """,
            ("openai", "openai_chat_json", "gpt-5-mini", "report/example"),
        ).fetchone()
    assert median_row == (1, 10.0, 5.0, 15.0)

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.llm_usage_ledger_service"
    ]
    assert [record["event"] for record in records] == [
        "llm_usage_ledger_append_start",
        "llm_usage_ledger_medians_rebuilt",
        "llm_usage_ledger_append_complete",
    ]
    assert_logs_have_required_fields(records)


def test_llm_usage_ledger_rebuilds_exact_medians_after_each_append(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    for ordinal, input_tokens, output_tokens, expected in (
        (0, 10, 5, (1, 10.0, 5.0, 15.0)),
        (1, 30, 15, (2, 20.0, 10.0, 30.0)),
        (2, 20, 10, (3, 20.0, 10.0, 30.0)),
    ):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(
                    _entry(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    call_ordinal=ordinal,
                ),
            ),
            _ctx(),
        )
        with sqlite3.connect(tmp_path / "usage_medians.sqlite") as conn:
            row = conn.execute(
                """
                select sample_count, median_input_tokens, median_output_tokens,
                       median_total_tokens
                from llm_usage_medians
                """
            ).fetchone()
        assert row == expected


def test_llm_usage_ledger_rebuilds_median_database_from_existing_source(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
        ),
        _ctx(),
    )
    with sqlite3.connect(tmp_path / "usage_medians.sqlite") as conn:
        conn.execute("delete from llm_usage_medians")

    response = svc.rebuild_usage_medians(
        LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(db_path)),
        _ctx(),
    )

    assert response.db_path == str(db_path)
    assert response.median_db_path == str(tmp_path / "usage_medians.sqlite")
    assert response.median_row_count == 1
    with sqlite3.connect(response.median_db_path) as conn:
        row = conn.execute(
            "select sample_count, median_total_tokens from llm_usage_medians"
        ).fetchone()
    assert row == (1, 15.0)


def test_llm_usage_ledger_groups_vector_store_records_by_semantic_task(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    for ordinal, input_tokens, output_tokens, cost in (
        (0, 100, 10, 0.001),
        (1, 300, 30, 0.003),
    ):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(
                    _entry(),
                    task_id=(
                        "run-id:vector_store:artifacts:insights_final"
                    ),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated_cost_usd=cost,
                    call_ordinal=ordinal,
                ),
            ),
            _ctx(),
        )

    with sqlite3.connect(tmp_path / "usage_medians.sqlite") as conn:
        row = conn.execute(
            """
            select task, sample_count, median_input_tokens, median_output_tokens,
                   median_total_tokens, median_estimated_cost_usd
            from llm_usage_medians
            """
        ).fetchone()
    assert row == ("artifacts:insights_final", 2, 200.0, 20.0, 220.0, 0.002)


def test_llm_usage_ledger_rolls_back_usage_write_when_median_rebuild_fails(
    tmp_path: Path, assert_app_error
) -> None:
    db_path = tmp_path / "usage.sqlite"
    (tmp_path / "usage_medians.sqlite").mkdir()

    with pytest.raises(AppError) as captured:
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=_entry(),
            ),
            _ctx(),
        )

    assert_app_error(
        captured.value,
        code="llm_usage_ledger_append_failed",
        retryable=False,
        severity="error",
    )
    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("select count(*) from llm_usage_events").fetchone()[0]
    assert row_count == 0


def test_llm_usage_ledger_event_key_is_idempotent_and_call_ordinal_is_distinct(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    first = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
        ),
        _ctx(),
    )
    replay = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
        ),
        _ctx(),
    )
    separate_call = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(_entry(), request_id="resp_1", call_ordinal=1),
        ),
        _ctx(),
    )

    assert first.inserted is True
    assert replay.inserted is False
    assert replay.row_id == first.row_id
    assert separate_call.inserted is True
    assert separate_call.event_key != first.event_key
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from llm_usage_events").fetchone() == (2,)


def test_llm_usage_ledger_updates_outcome_and_reconciles_json_export(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    appended = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
        ),
        _ctx(),
    )
    outcome = svc.update_usage_outcome(
        LLMUsageLedgerOutcomeUpdateRequest(
            schema_version="1.0",
            db_path=str(db_path),
            event_key=appended.event_key,
            parse_status="invalid",
            schema_validation_status="not_validated",
            error_stage="output_validation",
            error_code="openai_response_invalid_json",
        ),
        _ctx(),
    )
    cost_ledger_service.append_entry(
        CostLedgerAppendRequest(
            schema_version="1.0",
            path=str(ledger_path),
            entry=CostLedgerEntry(
                schema_version="1.0",
                timestamp_utc=_entry().timestamp_utc,
                run_id="run",
                task_id="task",
                span_id="span",
                step_name="openai_chat_json",
                model="gpt-5-mini",
                input_tokens=10,
                output_tokens=5,
                cached_input_tokens=0,
                tool_calls=0,
                estimated_cost_usd=0.001,
            ),
        ),
        _ctx(),
    )
    reconciliation = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0", db_path=str(db_path), ledger_path=str(ledger_path)
        ),
        _ctx(),
    )

    assert outcome.updated is True
    assert reconciliation.matches is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select parse_status, schema_validation_status, error_stage, error_code from llm_usage_events"
        ).fetchone()
    assert row == (
        "invalid",
        "not_validated",
        "output_validation",
        "openai_response_invalid_json",
    )
