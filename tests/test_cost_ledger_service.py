import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contracts.files import WriteBytesRequest
from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerEntry,
    CostReportRequest,
    CostRollupRequest,
)
from src.contracts.run_context import RunContext
from src.services import cost_ledger_service
from src.services.cost_ledger_service import (
    append_entry,
    generate_cost_report,
    rollup_daily,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _write_entries(path: Path, entries: list[CostLedgerEntry]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.__dict__) + "\n")


def test_append_entry_writes_jsonl(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    entry = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_id="run1",
        task_id="task1",
        span_id="span1",
        step_name="openai_analyze",
        model="gpt-5",
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=None,
        tool_calls=0,
        estimated_cost_usd=0.05,
    )
    append_entry(
        CostLedgerAppendRequest(
            schema_version="1.0", path=str(ledger_path), entry=entry
        ),
        _ctx(),
    )

    content = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    row = json.loads(content[0])
    assert row["model"] == "gpt-5"
    assert row["input_tokens"] == 1000
    assert row["estimated_cost_usd"] == 0.05


def test_rollup_daily_sums_by_day(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    yesterday = now - timedelta(days=1)
    entries = [
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run",
            task_id="t1",
            span_id="s1",
            step_name="openai_analyze",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            cached_input_tokens=None,
            tool_calls=1,
            estimated_cost_usd=0.01,
        ),
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run",
            task_id="t2",
            span_id="s2",
            step_name="rank_candidates",
            model="gpt-5",
            input_tokens=200,
            output_tokens=25,
            cached_input_tokens=None,
            tool_calls=0,
            estimated_cost_usd=0.02,
        ),
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=yesterday.isoformat(),
            run_id="run",
            task_id="t3",
            span_id="s3",
            step_name="openai_analyze",
            model="gpt-5",
            input_tokens=300,
            output_tokens=75,
            cached_input_tokens=None,
            tool_calls=0,
            estimated_cost_usd=0.03,
        ),
    ]
    _write_entries(ledger_path, entries)
    out_path = tmp_path / "cost-daily.json"
    resp = rollup_daily(
        CostRollupRequest(
            schema_version="1.0", ledger_path=str(ledger_path), out_path=str(out_path)
        ),
        _ctx(),
    )
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "totals" in data
    assert len(data["totals"]) == 2
    today_key = now.date().isoformat()
    yesterday_key = yesterday.date().isoformat()
    assert data["totals"][today_key]["total_usd"] == 0.03
    assert data["totals"][today_key]["input_tokens"] == 300
    assert data["totals"][today_key]["output_tokens"] == 75
    assert data["totals"][today_key]["tool_calls"] == 1
    assert data["totals"][yesterday_key]["total_usd"] == 0.03
    assert "totals_by_run" in data
    assert data["totals_by_run"]["run"]["estimated_cost_usd"] == 0.06
    assert data["totals_by_run"]["run"]["total_input_tokens"] == 600
    assert "totals_by_task" in data
    assert data["totals_by_task"]["t2"]["estimated_cost_usd"] == 0.02
    assert resp.totals_by_run["run"].total_output_tokens == 150
    assert resp.totals_by_task["t1"].total_tool_calls == 1
    assert data["ledger_state"]["ledger_path"] == str(ledger_path)
    assert data["ledger_state"]["size_bytes"] > 0


def test_rollup_daily_updates_incrementally_for_appended_backfill(
    tmp_path: Path, caplog
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "cost-daily.json"
    now = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    backfill = now - timedelta(days=1)
    first_entry = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=now.isoformat(),
        run_id="run-a",
        task_id="task-a",
        span_id="span-a",
        step_name="openai_analyze",
        model="gpt-5",
        input_tokens=100,
        output_tokens=25,
        cached_input_tokens=None,
        tool_calls=0,
        estimated_cost_usd=0.01,
    )
    second_entry = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=backfill.isoformat(),
        run_id="run-b",
        task_id="task-b",
        span_id="span-b",
        step_name="rank_candidates",
        model="gpt-5",
        input_tokens=200,
        output_tokens=10,
        cached_input_tokens=None,
        tool_calls=1,
        estimated_cost_usd=0.02,
    )

    append_entry(
        CostLedgerAppendRequest(
            schema_version="1.0", path=str(ledger_path), entry=first_entry
        ),
        _ctx(),
    )
    rollup_daily(
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            out_path=str(out_path),
        ),
        _ctx(),
    )

    caplog.set_level(logging.INFO, logger="market_lense.cost_ledger_service")
    append_entry(
        CostLedgerAppendRequest(
            schema_version="1.0", path=str(ledger_path), entry=second_entry
        ),
        _ctx(),
    )
    response = rollup_daily(
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            out_path=str(out_path),
        ),
        _ctx(),
    )

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert response.totals_by_date[backfill.date().isoformat()].total_usd == 0.02
    assert response.totals_by_date[now.date().isoformat()].total_usd == 0.01
    assert response.totals_by_run["run-b"].estimated_cost_usd == 0.02
    complete_events = [
        json.loads(record.message)
        for record in caplog.records
        if '"event": "cost_ledger_rollup_complete"' in record.message
    ]
    assert complete_events
    assert complete_events[-1]["fields"]["mode"] == "incremental"
    assert complete_events[-1]["fields"]["rows_processed"] == 1
    assert data["totals_by_date"][backfill.date().isoformat()]["total_usd"] == 0.02


def test_rollup_daily_rebuilds_after_ledger_amend(tmp_path: Path, caplog) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "cost-daily.json"
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    original = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=now.isoformat(),
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
        step_name="openai_analyze",
        model="gpt-5",
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=None,
        tool_calls=0,
        estimated_cost_usd=0.01,
    )
    amended = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=now.isoformat(),
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
        step_name="openai_analyze",
        model="gpt-5",
        input_tokens=100,
        output_tokens=50,
        cached_input_tokens=None,
        tool_calls=0,
        estimated_cost_usd=0.09,
    )

    _write_entries(ledger_path, [original])
    rollup_daily(
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            out_path=str(out_path),
        ),
        _ctx(),
    )

    caplog.set_level(logging.INFO, logger="market_lense.cost_ledger_service")
    _write_entries(ledger_path, [amended])
    response = rollup_daily(
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            out_path=str(out_path),
        ),
        _ctx(),
    )

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert response.totals_by_run["run-1"].estimated_cost_usd == 0.09
    assert data["totals_by_run"]["run-1"]["estimated_cost_usd"] == 0.09
    complete_events = [
        json.loads(record.message)
        for record in caplog.records
        if '"event": "cost_ledger_rollup_complete"' in record.message
    ]
    assert complete_events
    assert complete_events[-1]["fields"]["mode"] == "full_rebuild"


def test_rollup_daily_classifies_corrupt_rollup_cache(tmp_path: Path, caplog) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    out_path = tmp_path / "cost-daily.json"
    out_path.write_text("{not-json", encoding="utf-8")
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    _write_entries(
        ledger_path,
        [
            CostLedgerEntry(
                schema_version="1.0",
                timestamp_utc=now.isoformat(),
                run_id="run-1",
                task_id="task-1",
                span_id="span-1",
                step_name="openai_analyze",
                model="gpt-5",
                input_tokens=100,
                output_tokens=50,
                cached_input_tokens=None,
                tool_calls=0,
                estimated_cost_usd=0.01,
            )
        ],
    )

    caplog.set_level(logging.INFO, logger="market_lense.cost_ledger_service")
    response = rollup_daily(
        CostRollupRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            out_path=str(out_path),
        ),
        _ctx(),
    )

    assert response.totals_by_run["run-1"].estimated_cost_usd == 0.01
    events = [
        json.loads(record.message)
        for record in caplog.records
        if '"event": "cost_rollup_cache_status"' in record.message
    ]
    assert events
    assert events[0]["fields"]["status_code"] == "invalid_json"
    assert events[0]["fields"]["recovery_policy"] == "full_rebuild"


def test_generate_cost_report_by_date(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run",
            task_id="t1",
            span_id="s1",
            step_name="openai_analyze",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            cached_input_tokens=None,
            tool_calls=1,
            estimated_cost_usd=0.01,
        ),
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run",
            task_id="t2",
            span_id="s2",
            step_name="rank_candidates",
            model="gpt-5",
            input_tokens=200,
            output_tokens=25,
            cached_input_tokens=None,
            tool_calls=0,
            estimated_cost_usd=0.02,
        ),
    ]
    _write_entries(ledger_path, entries)
    report = generate_cost_report(
        CostReportRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            date_utc=now.date().isoformat(),
            top_n=2,
        ),
        _ctx(),
    )
    assert report.filter_type == "date"
    assert report.matched_entries == 2
    assert report.totals.estimated_cost_usd == 0.03
    assert report.totals.total_input_tokens == 300
    assert [s.step_name for s in report.top_steps] == [
        "rank_candidates",
        "openai_analyze",
    ]


def test_generate_cost_report_by_run(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    entries = [
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run-1",
            task_id="t1",
            span_id="s1",
            step_name="openai_analyze",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            cached_input_tokens=None,
            tool_calls=1,
            estimated_cost_usd=0.01,
        ),
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run-1",
            task_id="t2",
            span_id="s2",
            step_name="rank_candidates",
            model="gpt-5",
            input_tokens=200,
            output_tokens=25,
            cached_input_tokens=None,
            tool_calls=0,
            estimated_cost_usd=0.02,
        ),
        CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=now.isoformat(),
            run_id="run-2",
            task_id="t3",
            span_id="s3",
            step_name="openai_analyze",
            model="gpt-5",
            input_tokens=300,
            output_tokens=75,
            cached_input_tokens=None,
            tool_calls=0,
            estimated_cost_usd=0.03,
        ),
    ]
    _write_entries(ledger_path, entries)
    report = generate_cost_report(
        CostReportRequest(
            schema_version="1.0",
            ledger_path=str(ledger_path),
            run_id="run-1",
            top_n=3,
        ),
        _ctx(),
    )
    assert report.filter_type == "run_id"
    assert report.filter_value == "run-1"
    assert report.totals.estimated_cost_usd == 0.03
    assert report.totals.total_output_tokens == 75
    assert [s.step_name for s in report.top_steps] == [
        "rank_candidates",
        "openai_analyze",
    ]


def test_generate_cost_report_rejects_invalid_filter_combination(
    tmp_path: Path,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        generate_cost_report(
            CostReportRequest(
                schema_version="1.0",
                ledger_path=str(tmp_path / "ledger.jsonl"),
                date_utc="2026-01-01",
                run_id="run-1",
                top_n=5,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="cost_report_filter_invalid",
        retryable=False,
    )


def test_generate_cost_report_rejects_non_positive_top_n(
    tmp_path: Path,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        generate_cost_report(
            CostReportRequest(
                schema_version="1.0",
                ledger_path=str(tmp_path / "ledger.jsonl"),
                run_id="run-1",
                top_n=0,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="cost_report_top_n_invalid",
        retryable=False,
    )


def test_generate_cost_report_rejects_invalid_date(
    tmp_path: Path,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        generate_cost_report(
            CostReportRequest(
                schema_version="1.0",
                ledger_path=str(tmp_path / "ledger.jsonl"),
                date_utc="bad-date",
                top_n=5,
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="cost_report_date_invalid",
        retryable=False,
    )


def test_append_entry_preserves_existing_ledger_when_atomic_write_fails(
    tmp_path: Path,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text('{"existing": true}\n', encoding="utf-8")
    entry = CostLedgerEntry(
        schema_version="1.0",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_id="run1",
        task_id="task1",
        span_id="span1",
        step_name="openai_analyze",
        model="gpt-5",
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=None,
        tool_calls=0,
        estimated_cost_usd=0.05,
    )

    def _fail_write(request: WriteBytesRequest, ctx: RunContext):
        raise AppError(
            code="file_write_failed",
            message="boom",
            retryable=False,
            context={"path": request.path},
        )

    external_boundary_mocks_only.setattr(
        cost_ledger_service.file_service, "write_bytes", _fail_write
    )

    with pytest.raises(AppError) as exc_info:
        append_entry(
            CostLedgerAppendRequest(
                schema_version="1.0", path=str(ledger_path), entry=entry
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="cost_ledger_append_failed", retryable=False)
    assert ledger_path.read_text(encoding="utf-8") == '{"existing": true}\n'
