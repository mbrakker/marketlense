from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.quality import export_reliability_run_evidence
from scripts.quality.export_reliability_run_evidence import export_run_evidence


def _seed_scoped_validation_run(
    state_dir: Path,
    *,
    validation_run_id: str,
    report_ids: tuple[str, ...] = ("r1",),
    terminal_outcome: str = "publish_ready",
) -> None:
    with sqlite3.connect(state_dir / "reports.sqlite") as connection:
        connection.executescript(
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
        for report_id in report_ids:
            connection.execute(
                "INSERT INTO validation_run_cohort_members VALUES (?, ?, ?, ?)",
                (validation_run_id, report_id, "publisher", f"source-{report_id}"),
            )
            connection.execute(
                "INSERT INTO validation_run_entity_attempts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    validation_run_id,
                    report_id,
                    terminal_outcome,
                    "publication_preflight",
                    "",
                    1,
                ),
            )


def test_successful_scoped_run_passes_when_publication_is_not_evaluated(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:successful-scoped-run"
    _seed_scoped_validation_run(
        state_dir,
        validation_run_id=run_id,
        report_ids=("r1", "r2"),
        terminal_outcome="awaiting_review",
    )

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
    )

    audit_findings = json.loads(
        output_dir.joinpath("audit_findings.json").read_text(encoding="utf-8")
    )
    assert audit_findings["disposition"] == "pass"
    assert audit_findings["status"] == "passed_reliability_targets"
    assert audit_findings["publication_disposition"] == "not_evaluated"
    assert audit_findings["publication_performed"] is False
    assert "passed" in output_dir.joinpath("AUDIT.md").read_text(encoding="utf-8")
    with output_dir.joinpath("intervention_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {
                "metric": "operator_intervention_required_terminal_failures",
                "value": "0",
            }
        ]


def test_run_usage_is_filtered_by_validation_run_id(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:usage-scope"
    _seed_scoped_validation_run(state_dir, validation_run_id=run_id)
    with sqlite3.connect(state_dir / "llm_usage.sqlite") as connection:
        connection.execute(
            """CREATE TABLE llm_usage_events (
              validation_run_id TEXT, action TEXT, semantic_task TEXT,
              prompt_namespace TEXT, provider TEXT, model TEXT,
              input_tokens INTEGER, output_tokens INTEGER,
              estimated_cost_usd REAL
            )"""
        )
        connection.executemany(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    "analyze",
                    "report_analysis",
                    "report/figure",
                    "openai",
                    "gpt-5",
                    100,
                    20,
                    0.01,
                ),
                (
                    run_id,
                    "analyze",
                    "unpriced_task",
                    "report/summary",
                    "openai",
                    "gpt-5",
                    50,
                    10,
                    None,
                ),
                (
                    "validation:other",
                    "analyze",
                    "report_analysis",
                    "report/figure",
                    "openai",
                    "gpt-5",
                    900,
                    200,
                    0.9,
                ),
            ],
        )

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
    )

    with output_dir.joinpath("llm_usage_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        usage_rows = list(csv.DictReader(handle))
    with output_dir.joinpath("cost_by_stage.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        cost_rows = list(csv.DictReader(handle))
    audit_findings = json.loads(
        output_dir.joinpath("audit_findings.json").read_text(encoding="utf-8")
    )
    assert usage_rows == [
        {
            "action": "analyze",
            "semantic_task": "report_analysis",
            "prompt_namespace": "report/figure",
            "provider": "openai",
            "model": "gpt-5",
            "input_tokens": "100",
            "output_tokens": "20",
            "estimated_cost_usd": "0.01",
        },
        {
            "action": "analyze",
            "semantic_task": "unpriced_task",
            "prompt_namespace": "report/summary",
            "provider": "openai",
            "model": "gpt-5",
            "input_tokens": "50",
            "output_tokens": "10",
            "estimated_cost_usd": "",
        },
    ]
    assert cost_rows == [
        {"stage": "report_analysis", "estimated_cost_usd": "0.010000"},
        {"stage": "unpriced_task", "estimated_cost_usd": "unavailable"},
    ]
    assert audit_findings["usage_attribution"] == {
        "status": "available",
        "scope": "validation_run_id",
        "matching_event_count": 2,
    }
    assert audit_findings["cost_attribution"] == {
        "status": "partial",
        "scope": "validation_run_id",
        "missing_cost_event_count": 1,
    }


def test_run_usage_is_unavailable_when_validation_run_id_is_not_retained(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    artifact_dir = tmp_path / "out"
    output_dir = tmp_path / "evidence"
    state_dir.mkdir()
    artifact_dir.mkdir()
    run_id = "validation:unscoped-usage"
    _seed_scoped_validation_run(state_dir, validation_run_id=run_id)
    with sqlite3.connect(state_dir / "llm_usage.sqlite") as connection:
        connection.execute(
            """CREATE TABLE llm_usage_events (
              action TEXT, semantic_task TEXT, prompt_namespace TEXT,
              provider TEXT, model TEXT, input_tokens INTEGER,
              output_tokens INTEGER, estimated_cost_usd REAL
            )"""
        )
        connection.execute(
            "INSERT INTO llm_usage_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("analyze", "report_analysis", "global", "openai", "gpt-5", 999, 999, 9.99),
        )

    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id=run_id,
    )

    with output_dir.joinpath("llm_usage_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == []
    with output_dir.joinpath("cost_by_stage.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == []
    with output_dir.joinpath("cost_by_report.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {
                "report_id": "r1",
                "estimated_cost_usd": "unavailable",
                "status": "unavailable",
            }
        ]
    audit_findings = json.loads(
        output_dir.joinpath("audit_findings.json").read_text(encoding="utf-8")
    )
    assert audit_findings["usage_attribution"] == {
        "status": "unavailable",
        "reason": "validation_run_id_not_retained",
        "matching_event_count": None,
    }
    assert audit_findings["cost_attribution"] == {
        "status": "unavailable",
        "reason": "validation_run_id_not_retained",
        "missing_cost_event_count": None,
    }


def test_successful_frozen_cohort_passes_without_publication(
    tmp_path: Path,
) -> None:
    cohort_result = tmp_path / "cohort_result.json"
    cohort_result.write_text(
        json.dumps(
            {
                "cohort_size": 2,
                "reports": [
                    {
                        "report_id": "r1",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                    {
                        "report_id": "r2",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                ],
                "summary": {"failure_code_pareto": {}},
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "evidence"

    export_reliability_run_evidence.export_frozen_cohort_outcome_views(
        cohort_result_path=cohort_result,
        output_dir=output_dir,
    )

    audit_findings = json.loads(
        output_dir.joinpath("audit_findings.json").read_text(encoding="utf-8")
    )
    assert audit_findings["disposition"] == "pass"
    assert audit_findings["status"] == "passed_reliability_targets"
    assert audit_findings["publication_performed"] is False
    assert audit_findings["publication_disposition"] == "not_evaluated"
