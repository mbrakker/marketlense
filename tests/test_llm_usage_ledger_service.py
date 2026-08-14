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
    LLMPolicyEffectivenessRequest,
    LLMUsageExportRebuildRequest,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
    LLMUsageLedgerOutcomeUpdateRequest,
    LLMUsageLedgerReconciliationRequest,
    LLMUsageMedianRebuildRequest,
    LLMUsageProjectionStatusRequest,
    LLMUsageSpendGuardrailRequest,
    LLMUsageSpendReservationReleaseRequest,
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


def test_policy_effectiveness_is_deterministic_and_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite"
    first = replace(
        _entry(),
        metadata={"execution_identity": "identity-a", "provider_latency_ms": 20},
        workflow="report_generation",
        plan_hash="regeneration-a",
        schema_validation_status="valid",
        cache_decision="provider_hit",
    )
    second = replace(
        first,
        request_id="resp_2",
        call_ordinal=1,
        input_tokens=20,
        metadata={"execution_identity": "identity-a", "provider_latency_ms": 40},
    )
    for entry in (first, second):
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0", db_path=str(db_path), entry=entry
            ),
            _ctx(),
        )

    before = db_path.stat().st_mtime_ns
    response = svc.read_policy_effectiveness(
        LLMPolicyEffectivenessRequest(schema_version="1.0", db_path=str(db_path)),
        _ctx(),
    )

    assert db_path.stat().st_mtime_ns == before
    assert response.unattributed_legacy_call_count == 0
    assert len(response.rows) == 1
    row = response.rows[0]
    assert row.execution_identity == "identity-a"
    assert row.call_count == 2
    assert row.validation_rate == 1.0
    assert row.cache_reuse_rate == 1.0
    assert row.average_latency_ms == 30.0
    assert row.input_tokens == 30
    assert row.regeneration_count == 1


def test_policy_effectiveness_zero_provider_calls_has_no_side_effect(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.sqlite"

    response = svc.read_policy_effectiveness(
        LLMPolicyEffectivenessRequest(schema_version="1.0", db_path=str(missing_path)),
        _ctx(),
    )

    assert response.rows == []
    assert not missing_path.exists()


def test_usage_attribution_dimensions_project_from_canonical_events(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "ledger.jsonl"
    daily_path = tmp_path / "daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(
                _entry(),
                report_id="report-1",
                workflow="report_generation",
                stage="analysis",
                plan_hash="plan-1",
                artifact_family="findings",
                validation_run_id="validation-20260721",
                cohort_id="cohort-20260721",
                workflow_run_id="run",
                publisher_id="publisher-1",
                model_policy_namespace="report_vs/analysis/findings",
                policy_namespace="report_vs/analysis/findings",
                semantic_task="analysis_findings",
                configuration_hash="config-hash",
                policy_hash="policy-hash",
                producer_build_identity="build-sha",
                repair_attempt=1,
                pricing_version="card-1",
                pricing_status="matched",
            ),
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

    payload = json.loads(daily_path.read_text(encoding="utf-8"))
    assert payload["totals_by_report"]["report-1"]["estimated_cost_usd"] == 0.001
    assert (
        payload["totals_by_workflow"]["report_generation"]["total_input_tokens"] == 10
    )
    assert (
        payload["totals_by_prompt_namespace"]["report/example"]["total_output_tokens"]
        == 5
    )
    assert payload["totals_by_artifact_family"]["findings"]["total_tool_calls"] == 0
    assert payload["totals_by_stage"]["analysis"]["estimated_cost_usd"] == 0.001
    assert (
        payload["totals_by_semantic_task"]["analysis_findings"]["total_output_tokens"]
        == 5
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT report_id,workflow,stage,plan_hash,artifact_family,validation_run_id,"
            "cohort_id,workflow_run_id,publisher_id,model_policy_namespace,"
            "policy_namespace,semantic_task,configuration_hash,policy_hash,"
            "producer_build_identity,repair_attempt,pricing_version,pricing_status "
            "FROM llm_usage_events"
        ).fetchone()
    assert row == (
        "report-1",
        "report_generation",
        "analysis",
        "plan-1",
        "findings",
        "validation-20260721",
        "cohort-20260721",
        "run",
        "publisher-1",
        "report_vs/analysis/findings",
        "report_vs/analysis/findings",
        "analysis_findings",
        "config-hash",
        "policy-hash",
        "build-sha",
        1,
        "card-1",
        "matched",
    )


def test_validation_run_usage_rejects_missing_runtime_attribution(
    tmp_path: Path,
) -> None:
    with pytest.raises(AppError, match="complete runtime attribution") as exc_info:
        svc.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=str(tmp_path / "usage.sqlite"),
                entry=replace(_entry(), validation_run_id="validation-20260721"),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "llm_usage_validation_attribution_missing"


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
            try:
                with sqlite3.connect(response.median_db_path) as conn:
                    median_row = conn.execute(
                        """
                        select sample_count, median_input_tokens, median_output_tokens,
                               median_total_tokens
                        from llm_usage_medians
                        """
                    ).fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table: llm_usage_medians" not in str(exc):
                    raise
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
            "select parse_status, schema_validation_status, error_stage, error_code "
            "from llm_usage_events"
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
    segment_path = (
        ledger_path.parent / "cost-ledger.segments" / "00000000000000000002.jsonl"
    )
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


def test_cached_provider_usage_reconciliation_rejects_tampered_cached_tokens(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(
                _entry(), cached_input_tokens=8, cache_decision="provider_hit"
            ),
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

    verified = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )

    assert verified.matches is True
    assert verified.sqlite_cached_input_tokens == 8
    assert verified.export_cached_input_tokens == 8
    with sqlite3.connect(db_path) as conn:
        checkpoint_source_sha256 = conn.execute(
            "select source_sha256 from llm_usage_export_checkpoints"
        ).fetchone()
    assert checkpoint_source_sha256 is not None
    assert checkpoint_source_sha256[0]
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["cached_input_tokens"] = 0
    ledger_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    tampered = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )

    assert tampered.matches is False
    assert tampered.sqlite_cached_input_tokens == 8
    assert tampered.export_cached_input_tokens == 0


def test_finalized_projected_event_refreshes_its_derived_outcome(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    appended = svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(
                _entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()
            ),
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


def test_reconciliation_rejects_canonical_outcome_payload_tampering(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
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
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["extra"]["event_outcome"]["parse_status"] = "invalid"
    ledger_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    reconciliation = svc.reconcile_usage_export(
        LLMUsageLedgerReconciliationRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )

    assert reconciliation.matches is False
    assert "canonical_event_payload_mismatch" in reconciliation.mismatch_reasons


def test_projection_status_rejects_daily_generation_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0", db_path=str(db_path), entry=_entry()
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
    daily_payload = json.loads(daily_path.read_text(encoding="utf-8"))
    daily_payload["ledger_state"]["generation_id"] += 1
    daily_path.write_text(json.dumps(daily_payload), encoding="utf-8")

    status = svc.get_projection_status(
        LLMUsageProjectionStatusRequest(
            schema_version="1.0",
            db_path=str(db_path),
            ledger_path=str(ledger_path),
            daily_path=str(daily_path),
        ),
        _ctx(),
    )

    assert status.files_valid is False


def test_projection_status_reports_bounded_pending_canonical_cost(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    ledger_path = tmp_path / "cost-ledger.jsonl"
    daily_path = tmp_path / "cost-daily.json"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(
                _entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()
            ),
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


def test_daily_spend_guardrail_uses_canonical_events_not_lagging_export(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite"
    svc.append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=str(db_path),
            entry=replace(
                _entry(), timestamp_utc=datetime.now(timezone.utc).isoformat()
            ),
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


def test_spend_guardrail_reserves_and_releases_concurrent_forecast_capacity(
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
    common = {
        "schema_version": "1.0",
        "db_path": str(db_path),
        "warn_usd": 10.0,
        "pause_usd": 0.003,
        "stop_usd": 0.004,
        "provider": entry.provider,
        "task": entry.action,
        "action": entry.action,
        "model": entry.model,
        "prompt_namespace": entry.prompt_namespace,
        "reserve_in_flight": True,
    }
    first = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(**common, reservation_key="first"), _ctx()
    )
    blocked = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(**common, reservation_key="second"), _ctx()
    )
    released = svc.release_daily_spend_reservation(
        LLMUsageSpendReservationReleaseRequest(
            schema_version="1.0", db_path=str(db_path), reservation_key="first"
        ),
        _ctx(),
    )
    after_release = svc.evaluate_daily_spend_guardrail(
        LLMUsageSpendGuardrailRequest(**common, reservation_key="second"), _ctx()
    )
    assert first.reservation_created is True
    assert blocked.in_flight_reserved_usd == 0.001
    assert blocked.decision == "pause"
    assert released.released is True
    assert after_release.decision == "allow"
    assert after_release.reservation_created is True
