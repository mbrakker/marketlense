from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from scripts.quality.export_reliability_run_evidence import export_run_evidence


def test_export_run_evidence_writes_terminal_and_funnel_views(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:test"
    reports_db = state_dir / "reports.sqlite"
    conn = sqlite3.connect(reports_db)
    conn.executescript(
        """
        CREATE TABLE validation_run_cohort_members (
          validation_run_id TEXT, report_id TEXT, publisher_id TEXT,
          source_identity_id TEXT
        );
        CREATE TABLE validation_run_entity_attempts (
          validation_run_id TEXT, report_id TEXT, terminal_outcome TEXT,
          terminal_stage TEXT, failure_code TEXT, is_current INTEGER
        );
        CREATE TABLE validation_run_stage_records (
          validation_run_id TEXT, stage TEXT, terminal_outcome TEXT,
          failure_code TEXT, retryable INTEGER, repair_disposition TEXT,
          idempotency_state TEXT, started_at_utc TEXT, completed_at_utc TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO validation_run_cohort_members VALUES (?, ?, ?, ?)",
        (run_id, "r1", "p1", "s1"),
    )
    conn.execute(
        "INSERT INTO validation_run_entity_attempts VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, "r1", "permanent_failure", "ingestion", "typed_failure", 1),
    )
    conn.execute(
        "INSERT INTO validation_run_stage_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            "discovery",
            "succeeded",
            "",
            0,
            "not_required",
            "new",
            "2026-08-10T00:00:00+00:00",
            "2026-08-10T00:00:01+00:00",
        ),
    )
    conn.commit()
    conn.close()

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
    )

    assert (output_dir / "aggregate_funnel.json").is_file()
    assert (output_dir / "terminal_outcomes.csv").is_file()
    with (output_dir / "terminal_outcomes.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "report_id": "r1",
            "terminal_outcome": "permanent_failure",
            "terminal_stage": "ingestion",
            "failure_code": "typed_failure",
        }
    ]
