from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
    OpenAIUsageOutcomeUpdateRequest,
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


def test_record_usage_defers_compatibility_exports_until_projection_interval(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.openai_accounting_service")

    response = svc.record_usage(_request(tmp_path), _ctx())

    assert response.recorded is False
    assert response.estimated_cost_usd == 2.5
    assert response.ledger_path == str(tmp_path / "ledger.jsonl")
    assert response.daily_path == str(tmp_path / "daily.json")
    assert response.error is None
    assert response.usage_db_recorded is True
    assert response.usage_db_row_id == 1
    assert response.usage_db_path == str(tmp_path / "usage.sqlite")
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
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "daily.json").exists()
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


def test_record_usage_projects_compatibility_exports_on_twentieth_event(
    tmp_path,
) -> None:
    response = None
    for call_ordinal in range(20):
        response = svc.record_usage(
            replace(_request(tmp_path), call_ordinal=call_ordinal), _ctx()
        )

    assert response is not None
    assert response.recorded is True
    exported_rows = [
        json.loads(line)
        for line in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(exported_rows) == 20
    daily = json.loads((tmp_path / "daily.json").read_text(encoding="utf-8"))
    assert daily["ledger_state"]["source"] == "canonical_sqlite"
    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        checkpoint = conn.execute(
            """
            select event_count, last_projected_event_id
            from llm_usage_export_checkpoints
            """
        ).fetchone()
    assert checkpoint == (20, 20)


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


def test_finalized_model_outcome_uses_shared_projection_finalizer(tmp_path) -> None:
    request = _request(tmp_path)
    recorded = svc.record_usage(request, _ctx())

    updated = svc.update_usage_outcome(
        OpenAIUsageOutcomeUpdateRequest(
            schema_version="1.0",
            usage_db_path=request.usage_db_path,
            event_key=recorded.event_key,
            parse_status="valid",
            schema_validation_status="valid",
            cost_ledger_path=request.cost_ledger_path,
            cost_daily_path=request.cost_daily_path,
        ),
        _ctx(),
    )

    assert updated is True
    assert (tmp_path / "ledger.jsonl").is_file()
    assert (tmp_path / "daily.json").is_file()


def test_record_usage_marks_unknown_model_pricing_instead_of_zero_cost_ambiguity(
    tmp_path,
) -> None:
    response = svc.record_usage(
        replace(_request(tmp_path), model="unpriced-model", request_id="unpriced"),
        _ctx(),
    )

    assert response.estimated_cost_usd == 0.0
    assert response.pricing_status == "missing"
    assert response.pricing_key == ""
    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        metadata = json.loads(
            conn.execute("select metadata_json from llm_usage_events").fetchone()[0]
        )
    assert metadata["pricing_status"] == "missing"
    assert metadata["pricing_rates"] == {}
    assert len(metadata["pricing_file_sha256"]) == 64


def test_record_usage_persists_resolved_pricing_rates_and_file_hash(tmp_path) -> None:
    svc.record_usage(_request(tmp_path), _ctx())

    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        metadata = json.loads(
            conn.execute("select metadata_json from llm_usage_events").fetchone()[0]
        )

    assert metadata["pricing_status"] == "matched"
    assert metadata["pricing_rates"] == {
        "input_tokens_per_1k_usd": 1.0,
        "output_tokens_per_1k_usd": 2.0,
        "tool_call_usd": 0.25,
    }
    assert len(metadata["pricing_file_sha256"]) == 64


def test_record_usage_returns_typed_failure_when_canonical_export_write_fails(
    external_boundary_mocks_only, tmp_path, caplog, assert_logs_have_required_fields
) -> None:
    def _write_bytes(request, ctx):
        raise AppError(
            code="file_write_failed", message="ledger unavailable", retryable=False
        )

    caplog.set_level(logging.INFO, logger="market_lense.openai_accounting_service")
    external_boundary_mocks_only.setattr(
        svc.llm_usage_ledger_service.file_service, "write_bytes", _write_bytes
    )

    for call_ordinal in range(19):
        response = svc.record_usage(
            replace(_request(tmp_path), call_ordinal=call_ordinal), _ctx()
        )
        assert response.error is None
    response = svc.record_usage(replace(_request(tmp_path), call_ordinal=19), _ctx())

    assert response.recorded is False
    assert response.estimated_cost_usd == 2.5
    assert response.error == "ledger unavailable"
    assert response.usage_db_recorded is True
    assert response.usage_db_inserted is True
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.openai_accounting_service"
    ]
    assert [record["event"] for record in records[-2:]] == [
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
