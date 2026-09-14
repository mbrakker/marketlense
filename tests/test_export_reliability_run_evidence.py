from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

from scripts.quality import export_reliability_run_evidence
from scripts.quality.export_reliability_run_evidence import export_run_evidence

_RETAINED_COHORT_ROOT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "quality"
    / "reliability-cohort-20260914-bfab37bb"
)


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
        "INSERT INTO validation_run_cohort_members VALUES (?, ?, ?, ?)",
        (run_id, "r2", "p2", "s2"),
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
        },
        {
            "report_id": "r2",
            "terminal_outcome": "missing",
            "terminal_stage": "",
            "failure_code": "validation_terminal_outcome_missing",
        },
    ]
    assert json.loads(output_dir.joinpath("failure_details.json").read_text()) == {
        "validation_run_id": run_id,
        "terminal_failures": [
            {
                "report_id": "r1",
                "terminal_outcome": "permanent_failure",
                "terminal_stage": "ingestion",
                "failure_code": "typed_failure",
            },
            {
                "report_id": "r2",
                "terminal_outcome": "missing",
                "terminal_stage": "",
                "failure_code": "validation_terminal_outcome_missing",
            },
        ],
    }


def test_retained_frozen_cohort_evidence_matches_authoritative_typed_outcomes() -> None:
    """Fails if a checked-in outcome view drifts from the typed cohort result."""

    result = json.loads(
        _RETAINED_COHORT_ROOT.joinpath("cohort_result.json").read_text(encoding="utf-8")
    )
    reports = sorted(result["reports"], key=lambda item: item["report_id"])
    expected_terminal_rows = [
        {
            "report_id": report["report_id"],
            "terminal_outcome": report["final_state"],
            "terminal_stage": "",
            "failure_code": report["terminal_failure_code"],
        }
        for report in reports
    ]
    evidence_dir = _RETAINED_COHORT_ROOT / "evidence-export"
    with evidence_dir.joinpath("terminal_outcomes.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == expected_terminal_rows

    failure_rows = [row for row in expected_terminal_rows if row["failure_code"]]
    failure_details = json.loads(
        evidence_dir.joinpath("failure_details.json").read_text(encoding="utf-8")
    )
    assert failure_details["terminal_failures"] == failure_rows

    expected_pareto = dict(
        sorted(
            Counter(row["failure_code"] for row in failure_rows).items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    assert result["summary"]["failure_code_pareto"] == expected_pareto
    with evidence_dir.joinpath("failure_pareto.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {"failure_code": code, "affected_reports": str(count)}
            for code, count in expected_pareto.items()
        ]

    expected_terminal_outcomes = dict(
        sorted(
            Counter(row["terminal_outcome"] for row in expected_terminal_rows).items()
        )
    )
    awaiting_review_count = expected_terminal_outcomes.get("awaiting_review", 0)
    publication_ready_count = sum(
        report["publication_readiness"] == "pass" for report in reports
    )
    aggregate_funnel = json.loads(
        evidence_dir.joinpath("aggregate_funnel.json").read_text(encoding="utf-8")
    )
    assert aggregate_funnel == {
        "schema_version": "1.0",
        "immutable_cohort_size": len(reports),
        "terminal_outcome_complete": True,
        "missing_terminal_report_count": 0,
        "terminal_outcomes": expected_terminal_outcomes,
        "awaiting_review_count": awaiting_review_count,
        "publication_ready_count": publication_ready_count,
    }
    audit_findings = json.loads(
        evidence_dir.joinpath("audit_findings.json").read_text(encoding="utf-8")
    )
    assert audit_findings["cohort_size"] == len(reports)
    assert audit_findings["typed_terminal_outcomes"] == len(reports)
    assert audit_findings["awaiting_review"] == awaiting_review_count
    assert audit_findings["publish_ready"] == publication_ready_count
    assert audit_findings["publication_performed"] is False

    readme = _RETAINED_COHORT_ROOT.joinpath("README.md").read_text(encoding="utf-8")
    cohort_size = len(reports)
    admitted_count = sum(
        report["admission_outcome"] == "admitted" for report in reports
    )
    awaiting_review_count = sum(
        report["final_state"] == "awaiting_review" for report in reports
    )
    failure_count = sum(report["final_state"] == "failed" for report in reports)
    typed_terminal_count = sum(
        report["final_state"] in {"awaiting_review", "failed"} for report in reports
    )
    assert f"| admitted reports / admission rate | {admitted_count} / 100% |" in readme
    assert (
        f"| first-attempt `awaiting_review` | {awaiting_review_count} / {cohort_size} "
        f"({awaiting_review_count * 100 // cohort_size}%) |"
    ) in readme
    assert (
        f"| workflow failures | {failure_count} / {cohort_size} "
        f"({failure_count * 100 // cohort_size}%) |"
    ) in readme
    assert (
        f"| typed-terminal outcomes | {typed_terminal_count} / {cohort_size} (100%) |"
    ) in readme
    assert (
        "| operator interventions | "
        f"{result['summary']['operator_intervention_count']} |"
    ) in readme
    pareto_rows = [f"| `{code}` | {count} |" for code, count in expected_pareto.items()]
    assert all(row in readme for row in pareto_rows)
    assert [readme.index(row) for row in pareto_rows] == sorted(
        readme.index(row) for row in pareto_rows
    )


def test_frozen_outcome_export_projects_only_authoritative_cohort_results(
    tmp_path: Path,
) -> None:
    """Fails if a frozen exporter reconstructs terminal states or Pareto."""

    cohort_result = tmp_path / "cohort_result.json"
    cohort_result.write_text(
        json.dumps(
            {
                "cohort_size": 3,
                "reports": [
                    {
                        "report_id": "r2",
                        "final_state": "failed",
                        "terminal_failure_code": "schema_reference_missing",
                        "publication_readiness": "fail",
                    },
                    {
                        "report_id": "r1",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                    {
                        "report_id": "r3",
                        "final_state": "failed",
                        "terminal_failure_code": "schema_reference_missing",
                        "publication_readiness": "fail",
                    },
                ],
                "summary": {"failure_code_pareto": {"schema_reference_missing": 2}},
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "evidence"

    export_reliability_run_evidence.export_frozen_cohort_outcome_views(
        cohort_result_path=cohort_result,
        output_dir=output_dir,
    )

    with output_dir.joinpath("terminal_outcomes.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        assert list(csv.DictReader(handle)) == [
            {
                "report_id": "r1",
                "terminal_outcome": "awaiting_review",
                "terminal_stage": "",
                "failure_code": "",
            },
            {
                "report_id": "r2",
                "terminal_outcome": "failed",
                "terminal_stage": "",
                "failure_code": "schema_reference_missing",
            },
            {
                "report_id": "r3",
                "terminal_outcome": "failed",
                "terminal_stage": "",
                "failure_code": "schema_reference_missing",
            },
        ]
    assert json.loads(output_dir.joinpath("failure_details.json").read_text()) == {
        "terminal_failures": [
            {
                "report_id": "r2",
                "terminal_outcome": "failed",
                "terminal_stage": "",
                "failure_code": "schema_reference_missing",
            },
            {
                "report_id": "r3",
                "terminal_outcome": "failed",
                "terminal_stage": "",
                "failure_code": "schema_reference_missing",
            },
        ]
    }
    assert json.loads(output_dir.joinpath("aggregate_funnel.json").read_text()) == {
        "schema_version": "1.0",
        "immutable_cohort_size": 3,
        "terminal_outcome_complete": True,
        "missing_terminal_report_count": 0,
        "terminal_outcomes": {"awaiting_review": 1, "failed": 2},
        "awaiting_review_count": 1,
        "publication_ready_count": 1,
    }
    audit_findings = json.loads(output_dir.joinpath("audit_findings.json").read_text())
    assert audit_findings["typed_terminal_outcomes"] == 3
    assert audit_findings["awaiting_review"] == 1
    assert audit_findings["publish_ready"] == 1


def test_frozen_outcome_export_rejects_missing_members_and_inconsistent_pareto(
    tmp_path: Path,
) -> None:
    """Fails closed rather than exporting an incomplete or self-contradictory cohort."""

    cohort_result = tmp_path / "cohort_result.json"
    cohort_result.write_text(
        json.dumps(
            {
                "cohort_size": 3,
                "reports": [
                    {
                        "report_id": "r1",
                        "final_state": "failed",
                        "terminal_failure_code": "schema_reference_missing",
                        "publication_readiness": "fail",
                    },
                    {
                        "report_id": "r2",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                ],
                "summary": {"failure_code_pareto": {"schema_reference_missing": 2}},
            }
        ),
        encoding="utf-8",
    )

    try:
        export_reliability_run_evidence.export_frozen_cohort_outcome_views(
            cohort_result_path=cohort_result,
            output_dir=tmp_path / "evidence",
        )
    except ValueError as exc:
        assert str(exc) == "cohort_result reports do not match declared cohort_size"
    else:
        raise AssertionError("incomplete frozen cohort outcome source was exported")

    cohort_result.write_text(
        json.dumps(
            {
                "cohort_size": 2,
                "reports": [
                    {
                        "report_id": "r1",
                        "final_state": "failed",
                        "terminal_failure_code": "schema_reference_missing",
                        "publication_readiness": "fail",
                    },
                    {
                        "report_id": "r2",
                        "final_state": "awaiting_review",
                        "terminal_failure_code": "",
                        "publication_readiness": "pass",
                    },
                ],
                "summary": {"failure_code_pareto": {"schema_reference_missing": 2}},
            }
        ),
        encoding="utf-8",
    )
    try:
        export_reliability_run_evidence.export_frozen_cohort_outcome_views(
            cohort_result_path=cohort_result,
            output_dir=tmp_path / "evidence",
        )
    except ValueError as exc:
        assert str(exc) == "cohort_result failure Pareto does not match typed outcomes"
    else:
        raise AssertionError("inconsistent frozen cohort failure Pareto was exported")
