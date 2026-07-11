from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

from src.contracts.costs import CostLedgerAppendRequest, CostRollupRequest
from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
)
from src.contracts.run_context import RunContext
from src.services import openai_accounting_service as svc
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _request(tmp_path: Path) -> OpenAIUsageAccountingRequest:
    return OpenAIUsageAccountingRequest(
        schema_version="1.0",
        step_name="openai_chat_json",
        model="gpt-test",
        input_tokens=1000,
        output_tokens=500,
        tool_calls=2,
        cached_input_tokens=100,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        model_pricing={
            "gpt-test": {
                "input_tokens_per_1k_usd": 1.0,
                "output_tokens_per_1k_usd": 2.0,
                "tool_call_usd": 0.25,
            }
        },
        request_id="req_1",
        provider="openai",
        action="openai_chat_json",
        total_tokens=1500,
        publisher_name="Test Publisher",
        report_name="Test Report",
        source_url="https://example.com/report",
        prompt_namespace="test/prompt",
        prompt_hash="prompt-hash",
        provider_decision="openai_primary",
        cache_decision="disabled",
        temperature=0.0,
        seed=7,
        timeout_seconds=30.0,
    )


def test_openai_usage_accounting_contracts_round_trip(
    tmp_path, assert_no_defaulted_required_fields
) -> None:
    request = _request(tmp_path)
    response = OpenAIUsageAccountingResponse(
        schema_version="1.0",
        recorded=True,
        estimated_cost_usd=2.5,
        ledger_path=request.cost_ledger_path,
        daily_path=request.cost_daily_path,
    )

    assert OpenAIUsageAccountingRequest(**request.__dict__) == request
    assert OpenAIUsageAccountingResponse(**response.__dict__) == response
    assert_no_defaulted_required_fields(request)
    assert_no_defaulted_required_fields(response)


def test_record_usage_appends_cost_ledger_and_rolls_up_daily(
    external_boundary_mocks_only,
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    appended_requests: list[CostLedgerAppendRequest] = []
    rollup_requests: list[CostRollupRequest] = []

    def _append_entry(request, ctx):
        appended_requests.append(request)
        return type(
            "AppendResponse", (), {"schema_version": "1.0", "path": request.path}
        )()

    def _rollup_daily(request, ctx):
        rollup_requests.append(request)
        return type(
            "RollupResponse",
            (),
            {
                "schema_version": "1.0",
                "out_path": request.out_path,
                "totals_by_date": {},
                "totals_by_run": {},
                "totals_by_task": {},
            },
        )()

    caplog.set_level(logging.INFO, logger="market_lense.openai_accounting_service")
    external_boundary_mocks_only.setattr(
        svc.cost_ledger_service, "append_entry", _append_entry
    )
    external_boundary_mocks_only.setattr(
        svc.cost_ledger_service, "rollup_daily", _rollup_daily
    )

    response = svc.record_usage(_request(tmp_path), _ctx())

    assert response.recorded is True
    assert response.estimated_cost_usd == 2.5
    assert response.ledger_path == str(tmp_path / "ledger.jsonl")
    assert response.daily_path == str(tmp_path / "daily.json")
    assert response.error is None
    assert response.usage_db_recorded is True
    assert response.usage_db_row_id == 1
    assert response.usage_db_path == str(tmp_path / "usage.sqlite")
    assert (tmp_path / "usage_medians.sqlite").exists()
    assert len(appended_requests) == 1
    entry = appended_requests[0].entry
    assert_no_defaulted_required_fields(entry)
    assert entry.step_name == "openai_chat_json"
    assert entry.model == "gpt-test"
    assert entry.input_tokens == 1000
    assert entry.output_tokens == 500
    assert entry.cached_input_tokens == 100
    assert entry.tool_calls == 2
    assert entry.estimated_cost_usd == 2.5
    assert entry.extra == {
        "request_id": "req_1",
        "provider": "openai",
        "action": "openai_chat_json",
        "publisher_name": "Test Publisher",
        "report_name": "Test Report",
        "source_url": "https://example.com/report",
        "prompt_namespace": "test/prompt",
        "prompt_hash": "prompt-hash",
        "provider_decision": "openai_primary",
        "cache_decision": "disabled",
        "event_outcome": {
            "provider_call_status": "completed",
            "parse_status": "not_applicable",
            "schema_validation_status": "not_applicable",
            "error_stage": None,
            "error_code": None,
            "call_ordinal": 0,
        },
    }
    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from llm_usage_events").fetchone()
    assert row is not None
    assert row["provider"] == "openai"
    assert row["action"] == "openai_chat_json"
    assert row["publisher_name"] == "Test Publisher"
    assert row["report_name"] == "Test Report"
    assert row["source_url"] == "https://example.com/report"
    assert row["input_tokens"] == 1000
    assert row["output_tokens"] == 500
    assert row["total_tokens"] == 1500
    assert row["estimated_cost_usd"] == 2.5
    assert row["prompt_namespace"] == "test/prompt"
    with sqlite3.connect(tmp_path / "usage_medians.sqlite") as conn:
        median_row = conn.execute(
            """
            select sample_count, median_total_tokens
            from llm_usage_medians
            where provider = ? and action = ? and model = ? and prompt_namespace = ?
            """,
            ("openai", "openai_chat_json", "gpt-test", "test/prompt"),
        ).fetchone()
    assert median_row == (1, 1500.0)
    assert rollup_requests == [
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(tmp_path / "ledger.jsonl"),
            out_path=str(tmp_path / "daily.json"),
        )
    ]
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.openai_accounting_service"
    ]
    assert [record["event"] for record in records] == [
        "openai_usage_accounting_start",
        "openai_usage_accounting_complete",
    ]
    assert_logs_have_required_fields(records)


def test_record_usage_can_write_usage_database_without_cost_ledger(tmp_path) -> None:
    request = replace(_request(tmp_path), emit_cost_ledger=False)

    response = svc.record_usage(request, _ctx())

    assert response.recorded is False
    assert response.usage_db_recorded is True
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "daily.json").exists()
    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        row = conn.execute(
            "select action, input_tokens, output_tokens from llm_usage_events"
        ).fetchone()
    assert row == ("openai_chat_json", 1000, 500)


def test_record_usage_returns_typed_failure_when_ledger_append_fails(
    external_boundary_mocks_only, tmp_path, caplog, assert_logs_have_required_fields
) -> None:
    rollup_requests: list[CostRollupRequest] = []

    def _append_entry(request, ctx):
        raise AppError(
            code="cost_ledger_append_failed",
            message="ledger unavailable",
            retryable=False,
        )

    def _rollup_daily(request, ctx):
        rollup_requests.append(request)

    caplog.set_level(logging.INFO, logger="market_lense.openai_accounting_service")
    external_boundary_mocks_only.setattr(
        svc.cost_ledger_service, "append_entry", _append_entry
    )
    external_boundary_mocks_only.setattr(
        svc.cost_ledger_service, "rollup_daily", _rollup_daily
    )

    response = svc.record_usage(_request(tmp_path), _ctx())

    assert response.recorded is False
    assert response.estimated_cost_usd == 2.5
    assert response.error == "ledger unavailable"
    assert response.usage_db_recorded is True
    assert response.usage_db_inserted is True
    assert rollup_requests == []
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.openai_accounting_service"
    ]
    assert [record["event"] for record in records] == [
        "openai_usage_accounting_start",
        "openai_usage_accounting_failed",
    ]
    assert records[-1]["fields"]["error"] == "ledger unavailable"
    assert_logs_have_required_fields(records)


def test_llm_service_has_no_direct_cost_ledger_persistence_imports() -> None:
    source = Path("src/services/_llm_service/openai_shared.py").read_text(
        encoding="utf-8"
    )

    assert "cost_ledger_service" not in source
    assert "CostLedgerEntry" not in source
    assert "CostLedgerAppendRequest" not in source
    assert "CostRollupRequest" not in source
    assert "estimate_cost_usd" not in source
