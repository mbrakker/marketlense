from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.ias_live_canary_runner import (
    run_first_attempt_canary,
    summarize_frozen_cohort_results,
)
from scripts.quality.run_frozen_reliability_cohort import _load_members


def test_cohort_member_missing_source_has_typed_terminal_result(tmp_path: Path) -> None:
    result = run_first_attempt_canary(
        runs_root=tmp_path,
        source_path=tmp_path / "missing.pdf",
        max_duration_seconds=1,
    )

    assert result["final_state"] == "failed"
    assert result["workflow_attempt_count"] == 0
    assert result["terminal_failure_code"] == "frozen_cohort_source_missing"
    assert Path(result["run_directory"]).joinpath("result.json").is_file()


def test_frozen_manifest_requires_pinned_source_provenance(tmp_path: Path) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}]}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "exactly 20 members" in str(exc)
    else:
        raise AssertionError("incomplete frozen manifest was accepted")


def test_frozen_manifest_rejects_missing_provenance_before_file_access(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}] * 20}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "incomplete source provenance" in str(exc)
    else:
        raise AssertionError("missing provenance was accepted")


def test_cohort_summary_keeps_failed_admitted_reports_in_its_denominator() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "admission_outcome": "admitted",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": False,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.30,
                "total_duration_seconds": 30.0,
            },
            {
                "admission_outcome": "admitted",
                "awaiting_review": False,
                "bounded_automatic_repair": True,
                "publication_readiness": "fail",
                "operator_intervention": False,
                "final_state": "failed",
                "terminal_failure_code": "publish_readiness_failed",
                "cost": 0.10,
                "total_duration_seconds": 10.0,
            },
            {
                "admission_outcome": "insufficient_content",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": True,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.20,
                "total_duration_seconds": 20.0,
            },
        ]
    )

    assert summary == {
        "report_count": 3,
        "admitted_report_count": 2,
        "cohort_admission_rate": 2 / 3,
        "workflow_denominator": 2,
        "first_attempt_awaiting_review_rate": 1 / 2,
        "publication_readiness_rate": 1 / 2,
        "bounded_repair_rate": 1 / 2,
        "workflow_failure_rate": 1 / 2,
        "typed_terminal_rate": 1.0,
        "operator_intervention_count": 1,
        "failure_code_pareto": {"publish_readiness_failed": 1},
        "mean_cost": 0.2,
        "median_cost": 0.2,
        "mean_duration_seconds": 20.0,
        "median_duration_seconds": 20.0,
    }
