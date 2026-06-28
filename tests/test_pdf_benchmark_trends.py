from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality.pdf_benchmark_trends import (
    append_trend_run,
    compare_trend_history,
    extract_trend_run,
    run_trend_check,
)


def test_extract_trend_run_records_candidate_and_crop_refine_metrics() -> None:
    candidate_payload = {
        "generated_at": "2026-06-28T00:00:00+00:00",
        "comparison": {
            "rows": [
                {
                    "pdf_path": "cache/report.pdf",
                    "report_name": "report",
                    "actual_candidate_count": 12,
                    "actual_degraded_page_count": 0,
                    "actual_median_seconds": 5.25,
                }
            ]
        },
    }
    crop_refine_payload = {
        "generated_at": "2026-06-28T00:01:00+00:00",
        "comparison": {
            "rows": [
                {
                    "report_root": "out/report",
                    "report_name": "report",
                    "actual_crop_artifact_count": 10,
                    "actual_refine_decision_count": 1,
                    "actual_estimated_model_call_count": 2,
                    "actual_median_seconds": 0.03,
                }
            ]
        },
    }

    run = extract_trend_run(
        run_id="run-1",
        candidate_payloads=(candidate_payload,),
        crop_refine_payloads=(crop_refine_payload,),
        source_files=("candidate.json", "crop.json"),
    )

    assert [(metric.gate, metric.key) for metric in run.metrics] == [
        ("candidate", "cache/report.pdf"),
        ("crop_refine", "out/report"),
    ]
    assert run.metrics[0].candidate_count == 12
    assert run.metrics[1].crop_artifact_count == 10
    assert run.metrics[1].estimated_model_call_count == 2


def test_append_trend_run_prunes_to_retained_window() -> None:
    history = {"schema_version": "1.0", "runs": []}
    for idx in range(5):
        run = extract_trend_run(
            run_id=f"run-{idx}",
            candidate_payloads=(),
            crop_refine_payloads=(),
            source_files=(),
        )
        history = append_trend_run(history, run, retained_run_limit=3)

    assert [run["run_id"] for run in history["runs"]] == ["run-2", "run-3", "run-4"]


def test_compare_trend_history_warns_and_fails_sustained_runtime_and_cost_regression() -> (
    None
):
    history = {"schema_version": "1.0", "runs": []}
    for idx, runtime in enumerate((10.0, 11.5, 11.7, 11.8)):
        run = extract_trend_run(
            run_id=f"candidate-{idx}",
            candidate_payloads=(
                {
                    "comparison": {
                        "rows": [
                            {
                                "pdf_path": "cache/report.pdf",
                                "report_name": "report",
                                "actual_candidate_count": 12,
                                "actual_degraded_page_count": 0,
                                "actual_median_seconds": runtime,
                            }
                        ]
                    }
                },
            ),
            crop_refine_payloads=(
                {
                    "comparison": {
                        "rows": [
                            {
                                "report_root": "out/report",
                                "report_name": "report",
                                "actual_crop_artifact_count": 10,
                                "actual_refine_decision_count": 1,
                                "actual_estimated_model_call_count": 2
                                if idx == 0
                                else 3,
                                "actual_median_seconds": 0.03,
                            }
                        ]
                    }
                },
            ),
            source_files=(),
        )
        history = append_trend_run(history, run, retained_run_limit=10)

    warning_only = compare_trend_history(
        history,
        min_runs=3,
        trend_warn_percent=10.0,
        trend_fail_percent=25.0,
    )
    strict = compare_trend_history(
        history,
        min_runs=3,
        trend_warn_percent=10.0,
        trend_fail_percent=15.0,
        fail_on_trend_regression=True,
    )

    assert warning_only.passed is True
    assert {warning.reason for warning in warning_only.warnings} == {
        "runtime_trend_regression_warning",
        "estimated_model_call_trend_regression_warning",
    }
    assert strict.passed is False
    assert {failure.reason for failure in strict.failures} == {
        "runtime_trend_regression_failure",
        "estimated_model_call_trend_regression_failure",
    }


def test_run_trend_check_requires_input_paths_for_strict_release_invocation(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="At least one benchmark JSON input path"):
        run_trend_check(
            candidate_json_paths=(),
            crop_refine_json_paths=(),
            history_path=tmp_path / "history.json",
            output_json=None,
            run_id="missing-inputs",
            retained_run_limit=20,
            min_runs=3,
            trend_warn_percent=10.0,
            trend_fail_percent=25.0,
            update_history=False,
            allow_missing_inputs=False,
            fail_on_trend_regression=True,
        )
