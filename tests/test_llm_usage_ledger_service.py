from __future__ import annotations

import json
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contracts.costs import CostLedgerAppendRequest, CostLedgerEntry
from src.contracts.llm_usage import (
    LLMUsageExportRebuildRequest,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
    LLMUsageLedgerOutcomeUpdateRequest,
    LLMUsageLedgerReconciliationRequest,
    LLMUsageMedianRebuildRequest,
    LLMUsageProjectionStatusRequest,
    LLMUsageSpendGuardrailRequest,
)
from src.contracts.run_context import RunContext
from src.services import cost_ledger_service
from src.services import llm_usage_ledger_service as svc
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
    assert response.median_rebuild_scheduled is False
    assert response.median_task == "openai_chat_json"
    assert response.median_task_event_count == 1
    assert response.median_row_count is None
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
    assert not Path(response.median_db_path).exists()

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


def test_llm_usage_ledger_schedules_median_rebuild_on_twentieth_task_event(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    response = None
    for ordinal in range(20):
        response = svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(
                    _entry(),
                    call_ordinal=ordinal,
                ),
            ),
            _ctx(),
        )
    assert response is not None
    assert response.median_rebuild_scheduled is True
    assert response.median_task_event_count == 20

    deadline = time.monotonic() + 5.0
    median_row = None
    while time.monotonic() < deadline:
        if Path(response.median_db_path).exists():
            with sqlite3.connect(response.median_db_path) as conn:
                median_row = conn.execute(
                    """
                    select sample_count, median_input_tokens, median_output_tokens,
                           median_total_tokens
                    from llm_usage_medians
                    """
                ).fetchone()
            if median_row == (20, 10.0, 5.0, 15.0):
                break
        time.sleep(0.01)
    assert median_row == (20, 10.0, 5.0, 15.0)


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
                    task_id=("run-id:vector_store:artifacts:insights_final"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated_cost_usd=cost,
                    call_ordinal=ordinal,
                ),
            ),
            _ctx(),
        )

    svc.rebuild_usage_medians(
        LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(db_path)),
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


def test_llm_usage_ledger_manual_rebuild_failure_preserves_usage_source(
    tmp_path: Path, assert_app_error
) -> None:
    db_path = tmp_path / "usage.sqlite"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
        ),
        _ctx(),
    )
    (tmp_path / "usage_medians.sqlite").mkdir()

    with pytest.raises(AppError) as captured:
        svc.rebuild_usage_medians(
            LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(db_path)),
            _ctx(),
        )

    assert_app_error(
        captured.value,
        code="llm_usage_median_rebuild_failed",
        retryable=False,
        severity="error",
    )
    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("select count(*) from llm_usage_events").fetchone()[0]
    assert row_count == 1


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


def test_llm_usage_ledger_rejects_unmapped_terminal_error_taxonomy(
    tmp_path: Path, assert_app_error
) -> None:
    with pytest.raises(AppError) as captured:
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(tmp_path / "usage.sqlite"),
                entry=replace(
                    _entry(),
                    error_stage="output_validation",
                    error_code="unknown_terminal_error",
                ),
            ),
            _ctx(),
        )

    assert_app_error(
        captured.value,
        code="llm_usage_ledger_error_taxonomy_invalid",
        retryable=False,
        severity="error",
    )


def test_llm_usage_ledger_allocates_distinct_ordinals_for_concurrent_direct_calls(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    direct_entry = replace(_entry(), request_id=None, call_ordinal=None)

    def append_one() -> int:
        response = svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0", db_path=str(db_path), entry=direct_entry
            ),
            _ctx(),
        )
        assert response.inserted is True
        return response.call_ordinal

    with ThreadPoolExecutor(max_workers=6) as executor:
        ordinals = list(executor.map(lambda _: append_one(), range(12)))

    assert sorted(ordinals) == list(range(12))
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from llm_usage_events").fetchone() == (12,)


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


def test_llm_usage_exports_rebuild_stably_and_reconciliation_repairs_tampering(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    for ordinal in (0, 1):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(_entry(), call_ordinal=ordinal),
            ),
            _ctx(),
        )

    request = LLMUsageExportRebuildRequest(
        schema_version="1.0",
        db_path=str(db_path),
        ledger_path=str(ledger_path),
        daily_path=str(daily_path),
    )
    first = svc.rebuild_usage_exports(request, _ctx())
    first_bytes = (ledger_path.read_bytes(), daily_path.read_bytes())
    second = svc.rebuild_usage_exports(request, _ctx())

    assert first.source_sha256 == second.source_sha256
    assert second.projected_event_count == 0
    assert first_bytes == (ledger_path.read_bytes(), daily_path.read_bytes())
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(_entry(), call_ordinal=2),
        ),
        _ctx(),
    )
    incremental = svc.rebuild_usage_exports(request, _ctx())
    assert incremental.projected_event_count == 1
    assert incremental.event_count == 3
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 3
    segment_path = ledger_path.parent / "cost-ledger.segments" / "00000000000000000002.jsonl"
    assert segment_path.read_text(encoding="utf-8").count("\n") == 1
    ledger_path.write_text('{"altered":true}\n', encoding="utf-8")
    reconciled = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
            repair=True,
        ),
        _ctx(),
    )

    assert reconciled.matches is True
    assert reconciled.repaired is True
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 3
    with sqlite3.connect(db_path) as conn:
        checkpoint = conn.execute(
            "select event_count from llm_usage_export_checkpoints"
        ).fetchone()
    assert checkpoint == (3,)


def test_finalized_projected_event_refreshes_its_derived_outcome(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    appended = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(_entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()),
        ),
        _ctx(),
    )
    svc.rebuild_usage_exports(
        LLMUsageExportRebuildRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
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

    row = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    assert outcome.updated is True
    assert outcome.export_refreshed is True
    assert row["extra"]["event_outcome"]["parse_status"] == "invalid"
    assert row["extra"]["event_outcome"]["error_code"] == "openai_response_invalid_json"


def test_projection_status_reports_bounded_pending_canonical_cost(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(_entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()),
        ),
        _ctx(),
    )

    status = svc.get_projection_status(
        LLMUsageProjectionStatusRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )

    assert status.latest_event_id == 1
    assert status.projected_event_id == 0
    assert status.pending_event_count == 1
    assert status.pending_estimated_cost_usd == 0.001
    assert status.files_valid is False


def test_daily_spend_guardrail_uses_canonical_events_not_lagging_export(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(_entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()),
        ),
        _ctx(),
    )

    guardrail = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(
            schema_version="1.0", db_path=str(db_path), warn_usd=0.001
        ),
        _ctx(),
    )

    assert guardrail.canonical_spend_usd == 0.001
    assert guardrail.decision == "warn"

    paused = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(
            schema_version="1.0",
            db_path=str(db_path),
            warn_usd=0.0001,
            pause_usd=0.001,
            stop_usd=0.002,
        ),
        _ctx(),
    )
    stopped = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(
            schema_version="1.0",
            db_path=str(db_path),
            warn_usd=0.0001,
            pause_usd=0.0005,
            stop_usd=0.001,
        ),
        _ctx(),
    )
    assert paused.decision == "pause"
    assert stopped.decision == "stop"


def test_daily_spend_guardrail_forecasts_exact_task_median_before_call(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    entry = replace(_entry(), timestamp_utc=datetime.now(timezone.utc).isoformat())
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=entry
        ),
        _ctx(),
    )
    svc.rebuild_usage_medians(
        LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(db_path)),
        _ctx(),
    )

    guardrail = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(
            schema_version="1.0",
            db_path=str(db_path),
            warn_usd=0.0015,
            provider=entry.provider,
            task=entry.action,
            action=entry.action,
            model=entry.model,
            prompt_namespace=entry.prompt_namespace,
        ),
        _ctx(),
    )

    assert guardrail.canonical_spend_usd == 0.001
    assert guardrail.median_forecast_usd == 0.001
    assert guardrail.median_sample_count == 1
    assert guardrail.projected_spend_usd == 0.002
    assert guardrail.forecast_status == "matched"
    assert guardrail.decision == "warn"


def test_concurrent_projection_generations_preserve_one_consistent_checkpoint(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    for ordinal in (0, 1):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(db_path),
                entry=replace(_entry(), call_ordinal=ordinal),
            ),
            _ctx(),
        )

    request = LLMUsageExportRebuildRequest(
        schema_version="1.0",
        db_path=str(db_path),
        ledger_path=str(ledger_path),
        daily_path=str(daily_path),
    )

    def rebuild_one() -> tuple[str, int]:
        try:
            response = svc.rebuild_usage_exports(request, _ctx())
            return ("ok", response.generation_id)
        except AppError as exc:
            return (exc.code, 0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rebuild_one(), range(2)))

    assert any(result[0] == "ok" for result in results)
    assert all(result[0] in {"ok", "llm_usage_projection_busy"} for result in results)
    reconciled = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )
    assert reconciled.matches is True
