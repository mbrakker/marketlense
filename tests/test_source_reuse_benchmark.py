from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from scripts.quality.benchmark_source_reuse import build_source_reuse_benchmark
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.services.report_store_service import upsert_metadata
from src.utils.logging import new_run_context


def test_source_reuse_benchmark_compares_retained_usage_with_zero_call_replay(
    tmp_path,
) -> None:
    reports_db = tmp_path / "reports.sqlite"
    usage_db = tmp_path / "usage.sqlite"
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    ctx = new_run_context(task_id="source_reuse_benchmark")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(reports_db),
            file_id="owner-report",
            title="Retained report",
            html_path=str(html_path),
            md5="a" * 32,
            source_identity_id="source:exact",
            source_metadata_hash="b" * 64,
            source_identity_status="resolved",
        ),
        ctx,
    )
    with sqlite3.connect(usage_db) as conn:
        conn.execute(
            """
            CREATE TABLE llm_usage_events (
              run_id TEXT NOT NULL,
              timestamp_utc TEXT NOT NULL,
              input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL,
              estimated_cost_usd REAL NOT NULL,
              provider_call_status TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("fresh-run", "2026-01-01T00:00:00+00:00", 100, 20, 0.01, "completed"),
                ("fresh-run", "2026-01-01T00:00:02+00:00", 200, 30, 0.02, "completed"),
            ],
        )

    benchmark = build_source_reuse_benchmark(
        reports_db=str(reports_db),
        usage_db=str(usage_db),
        owner_report_id="owner-report",
        baseline_run_id="fresh-run",
        repeats=3,
    )

    assert benchmark.quality_passed is True
    assert benchmark.owner_report_id == "owner-report"
    assert benchmark.resolved_reuse_count == 3
    assert benchmark.baseline_model_calls == 2
    assert benchmark.candidate_model_calls == 0
    assert benchmark.baseline_input_tokens == 300
    assert benchmark.candidate_input_tokens == 0
    assert benchmark.baseline_estimated_cost_usd == 0.03
    assert benchmark.candidate_estimated_cost_usd == 0.0
    assert benchmark.baseline_provider_span_ms == 2000.0


def test_source_reuse_benchmark_runs_as_a_direct_script() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(Path("scripts/quality/benchmark_source_reuse.py").resolve()),
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "canonical source-package reuse" in result.stdout
