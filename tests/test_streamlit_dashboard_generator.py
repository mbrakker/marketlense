from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.contracts.streamlit_dashboard import (
    DirectoryCountCheck,
    DirectoryCountsRequest,
    LedgerEntriesLoadRequest,
    LogEventLoadRequest,
    LogFileDiscoveryRequest,
    StateRowsLoadRequest,
    ValidationArtifactSummaryRequest,
)
from src.generators import streamlit_dashboard_generator as gen
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def test_discover_log_files_sorts_by_mtime_desc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gen,
        "list_directory",
        lambda req, ctx: SimpleNamespace(
            entries=[
                SimpleNamespace(path="logs/market_lense_2026-02-01.log", name="market_lense_2026-02-01.log", mtime_utc=1.0, size_bytes=11),
                SimpleNamespace(path="logs/market_lense_2026-02-02.log", name="market_lense_2026-02-02.log", mtime_utc=3.0, size_bytes=12),
            ]
        ),
    )

    response = gen.discover_log_files(
        LogFileDiscoveryRequest(schema_version="1.0", log_dir="logs", file_prefix="market_lense", limit=100),
        _ctx(),
    )

    assert [item.path for item in response.records] == [
        "logs/market_lense_2026-02-02.log",
        "logs/market_lense_2026-02-01.log",
    ]


def test_load_log_events_parses_structured_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        "12:01:02 | INFO | market_lense.test | "
        '{"run_id":"r1","task_id":"t1","span_id":"s1","event":"ingest_start","role":"orchestrator","module":"m","fields":{}}\n'
        "plain text line\n"
    )
    monkeypatch.setattr(gen, "read_text", lambda req, ctx: SimpleNamespace(content=payload))

    response = gen.load_log_events(
        LogEventLoadRequest(
            schema_version="1.0",
            log_paths=["logs/market_lense_2026-02-09.log"],
            max_lines_per_file=100,
        ),
        _ctx(),
    )

    assert len(response.events) == 1
    assert response.events[0]["event"] == "ingest_start"
    assert response.events[0]["log_path"] == "logs/market_lense_2026-02-09.log"
    assert str(response.events[0].get("timestamp_utc")).startswith("2026-02-09T12:01:02")


def test_summarize_validation_artifacts_extracts_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gen,
        "list_directory",
        lambda req, ctx: SimpleNamespace(
            entries=[
                SimpleNamespace(path="out/r1/validation.json", name="validation.json", mtime_utc=2.0, size_bytes=22),
                SimpleNamespace(path="out/r2/validation_policy.json", name="validation_policy.json", mtime_utc=3.0, size_bytes=33),
            ]
        ),
    )

    def _read_text(req, ctx):
        if req.path.endswith("validation_policy.json"):
            return SimpleNamespace(content='{"status":"fail","severity":"error"}')
        return SimpleNamespace(content='{"status":"pass","severity":"info"}')

    monkeypatch.setattr(gen, "read_text", _read_text)

    response = gen.summarize_validation_artifacts(
        ValidationArtifactSummaryRequest(schema_version="1.0", output_dir="out", limit=10),
        _ctx(),
    )

    assert len(response.rows) == 2
    assert response.rows[0].path == "out/r2/validation_policy.json"
    assert response.rows[0].chip_level == "error"
    assert response.rows[1].chip_level == "info"


def test_load_state_rows_invalid_kind_raises() -> None:
    with pytest.raises(AppError) as exc_info:
        gen.load_state_rows(
            StateRowsLoadRequest(schema_version="1.0", state_db="state.db", kind="unknown", limit=10),
            _ctx(),
        )
    assert exc_info.value.code == "invalid_state_kind"


def test_collect_directory_counts_captures_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _list_directory(req, ctx):
        if req.glob_pattern == "broken":
            raise AppError(code="directory_not_found", message="missing", retryable=False)
        return SimpleNamespace(entries=[SimpleNamespace(path="a"), SimpleNamespace(path="b")])

    monkeypatch.setattr(gen, "list_directory", _list_directory)

    response = gen.collect_directory_counts(
        DirectoryCountsRequest(
            schema_version="1.0",
            checks=[
                DirectoryCountCheck(
                    schema_version="1.0",
                    name="ok",
                    root_dir="out",
                    glob_pattern="*.html",
                    recursive=False,
                    include_dirs=False,
                ),
                DirectoryCountCheck(
                    schema_version="1.0",
                    name="bad",
                    root_dir="out",
                    glob_pattern="broken",
                    recursive=True,
                    include_dirs=True,
                ),
            ],
            limit=100,
        ),
        _ctx(),
    )

    assert len(response.rows) == 2
    assert response.rows[0].name == "ok"
    assert response.rows[0].count == 2
    assert response.rows[1].name == "bad"
    assert response.rows[1].count == 0
    assert response.rows[1].error == "missing"


def test_load_ledger_entries_keeps_last_n_valid_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gen,
        "read_text",
        lambda req, ctx: SimpleNamespace(content='{"usd":1}\nnot-json\n{"usd":2}\n{"usd":3}\n'),
    )

    response = gen.load_ledger_entries(
        LedgerEntriesLoadRequest(schema_version="1.0", ledger_path="state/costs.jsonl", limit=2),
        _ctx(),
    )

    assert response.entries == [{"usd": 2}, {"usd": 3}]
