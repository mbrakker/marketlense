from __future__ import annotations

from scripts.quality.run_health_scorecard import (
    build_pdf_benchmark_scorecard,
    build_scorecard,
)


def test_run_health_scorecard_summarizes_retries_errors_cost_and_latency() -> None:
    scorecard = build_scorecard(
        [
            {
                "timestamp": "2026-04-22T10:00:00+00:00",
                "run_id": "run-1",
                "event": "pipeline_start",
                "fields": {"cost_usd": 0.10},
            },
            {
                "timestamp": "2026-04-22T10:00:03+00:00",
                "run_id": "run-1",
                "event": "retry_decision",
                "fields": {"cost_usd": 0.20},
            },
            {
                "timestamp": "2026-04-22T10:00:05+00:00",
                "run_id": "run-1",
                "event": "validation_failed",
                "level": "error",
                "fields": {},
            },
        ],
        max_errors=0,
        max_retries=0,
        max_cost_usd=0.25,
    )

    assert scorecard.event_count == 3
    assert scorecard.error_count == 1
    assert scorecard.retry_count == 1
    assert scorecard.validation_failure_count == 1
    assert scorecard.cost_usd == 0.3
    assert scorecard.latency_seconds == 5.0
    assert scorecard.warnings == (
        "error_count 1 exceeds 0",
        "retry_count 1 exceeds 0",
        "cost_usd 0.300000 exceeds 0.250000",
    )


def test_pdf_benchmark_scorecard_summarizes_release_evidence() -> None:
    candidate_payload = {
        "comparison": {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [
                {
                    "pdf_path": "cache/report.pdf",
                    "report_name": "report",
                    "actual_candidate_count": 12,
                    "actual_degraded_page_count": 0,
                    "actual_median_seconds": 4.5,
                    "runtime_delta_percent": -10.0,
                    "status": "passed",
                }
            ],
        }
    }
    crop_payload = {
        "comparison": {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [
                {
                    "report_root": "out/report",
                    "report_name": "report",
                    "actual_crop_artifact_count": 10,
                    "actual_refine_decision_count": 1,
                    "actual_estimated_model_call_count": 2,
                    "expected_estimated_model_call_count": 3,
                    "runtime_delta_percent": -5.0,
                    "status": "passed",
                }
            ],
        }
    }
    trend_payload = {
        "comparison": {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [
                {
                    "gate": "crop_refine",
                    "key": "out/report",
                    "report_name": "report",
                    "metric_name": "estimated_model_call_count",
                    "delta_percent": -33.333333,
                    "sample_count": 4,
                    "status": "passed",
                }
            ],
        }
    }

    scorecard = build_pdf_benchmark_scorecard(
        candidate_payloads=[candidate_payload],
        crop_refine_payloads=[crop_payload],
        trend_payloads=[trend_payload],
        source_files=("candidate.json", "crop.json", "trend.json"),
    )

    assert scorecard.evidence_complete is True
    assert scorecard.passed is True
    assert scorecard.candidate_row_count == 1
    assert scorecard.crop_refine_row_count == 1
    assert scorecard.trend_row_count == 1
    assert scorecard.rows[0].gate == "candidate"
    assert scorecard.rows[0].candidate_count == 12
    assert scorecard.rows[1].crop_artifact_count == 10
    assert scorecard.rows[1].estimated_model_call_count == 2
    assert scorecard.rows[1].estimated_model_call_delta == -1
    assert scorecard.rows[2].metric_name == "estimated_model_call_count"
    assert scorecard.rows[2].trend_delta_percent == -33.333333
    assert scorecard.failures == ()
    assert scorecard.warnings == ()


def test_pdf_benchmark_scorecard_fails_on_failed_rows_without_issue_payload() -> None:
    scorecard = build_pdf_benchmark_scorecard(
        candidate_payloads=[
            {
                "comparison": {
                    "passed": False,
                    "failures": [],
                    "warnings": [],
                    "rows": [
                        {
                            "pdf_path": "cache/report.pdf",
                            "report_name": "report",
                            "status": "failed",
                        }
                    ],
                }
            }
        ],
        crop_refine_payloads=[
            {
                "comparison": {
                    "passed": True,
                    "rows": [
                        {
                            "report_root": "out/report",
                            "report_name": "report",
                            "status": "passed",
                        }
                    ],
                }
            }
        ],
        trend_payloads=[
            {
                "comparison": {
                    "passed": True,
                    "rows": [
                        {
                            "gate": "candidate",
                            "key": "cache/report.pdf",
                            "report_name": "report",
                            "metric_name": "runtime_seconds",
                            "status": "passed",
                        }
                    ],
                }
            }
        ],
    )

    assert scorecard.evidence_complete is True
    assert scorecard.passed is False
    assert {failure.reason for failure in scorecard.failures} == {
        "benchmark_comparison_failed",
        "benchmark_row_failed",
    }


def test_run_health_scorecard_reports_missing_pdf_evidence_as_incomplete() -> None:
    scorecard = build_scorecard(
        [{"run_id": "run-1", "event": "pipeline_start", "fields": {}}],
        run_id="run-1",
        pdf_candidate_payloads=[],
        pdf_crop_refine_payloads=[],
        pdf_trend_payloads=[],
        require_pdf_benchmark_evidence=True,
    )

    assert scorecard.pdf_benchmark_scorecard is not None
    assert scorecard.pdf_benchmark_scorecard.evidence_complete is False
    assert scorecard.pdf_benchmark_scorecard.passed is False
    assert (
        "pdf_benchmark_evidence incomplete: missing candidate benchmark evidence; "
        "missing crop_refine benchmark evidence; missing trend benchmark evidence"
        in scorecard.warnings
    )


def test_run_health_scorecard_attaches_retry_telemetry_and_warns_on_exhaustion() -> (
    None
):
    scorecard = build_scorecard(
        [
            {
                "run_id": "run-1",
                "event": "report_pipeline_failed",
                "fields": {
                    "step": "report_pipeline",
                    "decision": "abort",
                    "reason": "retry_attempts_exhausted",
                    "error_code": "openai_request_failed",
                    "decision_attempt": 3,
                    "delay_seconds": 0,
                },
            }
        ],
        run_id="run-1",
        max_retry_exhaustion_rate=0.0,
    )

    assert scorecard.retry_telemetry_report is not None
    assert scorecard.retry_telemetry_report.retry_exhaustion_count == 1
    assert scorecard.retry_telemetry_report.retry_exhaustion_rate == 1.0
    assert "retry_exhaustion_rate 1.0000 exceeds 0.0000" in scorecard.warnings
