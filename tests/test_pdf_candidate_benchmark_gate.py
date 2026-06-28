from __future__ import annotations

from src.contracts.candidates import Candidate
from scripts.quality.pdf_candidate_benchmark import (
    PdfCandidateBenchmarkBaselineEntry,
    PdfCandidateBenchmarkObservation,
    candidate_output_signature,
    compare_benchmark_observations,
)


def _baseline(**overrides) -> PdfCandidateBenchmarkBaselineEntry:
    values = {
        "pdf_path": "cache/benchmark_20260604/report.pdf",
        "report_name": "report",
        "expected_candidate_count": 2,
        "expected_signature": "expected-signature",
        "expected_degraded_page_count": 0,
        "baseline_median_seconds": 10.0,
        "runtime_warn_percent": 10.0,
        "runtime_fail_percent": 50.0,
    }
    values.update(overrides)
    return PdfCandidateBenchmarkBaselineEntry(**values)


def _observation(**overrides) -> PdfCandidateBenchmarkObservation:
    values = {
        "pdf_path": "cache/benchmark_20260604/report.pdf",
        "report_name": "report",
        "candidate_count": 2,
        "signature": "expected-signature",
        "degraded_page_count": 0,
        "durations_seconds": (10.2, 10.4, 10.3),
        "median_seconds": 10.3,
    }
    values.update(overrides)
    return PdfCandidateBenchmarkObservation(**values)


def test_candidate_output_signature_is_stable_for_candidate_contract_fields() -> None:
    candidates = [
        Candidate(
            schema_version="1.0",
            id="chart-0-0",
            kind="chart",
            page=0,
            bbox=(1.12345, 2.0, 30.0, 40.98765),
            preview_text="Revenue",
            caption="Figure 1",
        ),
        Candidate(
            schema_version="1.0",
            id="table-1-0",
            kind="table",
            page=1,
            bbox=(3.0, 4.0, 50.0, 60.0),
            preview_text="Table preview",
            caption="",
        ),
    ]

    assert candidate_output_signature(candidates) == candidate_output_signature(
        list(candidates)
    )
    assert candidate_output_signature(candidates) != candidate_output_signature(
        [candidates[1], candidates[0]]
    )


def test_compare_benchmark_observations_fails_candidate_equivalence_drift() -> None:
    result = compare_benchmark_observations(
        baseline_entries=(_baseline(),),
        observations=(
            _observation(
                candidate_count=3,
                signature="changed",
                degraded_page_count=1,
            ),
        ),
    )

    assert result.passed is False
    assert {failure.reason for failure in result.failures} == {
        "candidate_count_changed",
        "candidate_signature_changed",
        "degraded_page_count_changed",
    }


def test_compare_benchmark_observations_warns_and_optionally_fails_runtime_regression() -> (
    None
):
    baseline = _baseline(runtime_warn_percent=10.0, runtime_fail_percent=25.0)
    observation = _observation(median_seconds=12.0)

    warning_only = compare_benchmark_observations(
        baseline_entries=(baseline,),
        observations=(observation,),
    )
    strict_runtime = compare_benchmark_observations(
        baseline_entries=(baseline,),
        observations=(_observation(median_seconds=13.0),),
        fail_on_runtime_regression=True,
    )

    assert warning_only.passed is True
    assert [warning.reason for warning in warning_only.warnings] == [
        "runtime_regression_warning"
    ]
    assert strict_runtime.passed is False
    assert [failure.reason for failure in strict_runtime.failures] == [
        "runtime_regression_failure"
    ]


def test_compare_benchmark_observations_handles_missing_assets_by_policy() -> None:
    lenient = compare_benchmark_observations(
        baseline_entries=(_baseline(),),
        observations=(),
        skipped_pdf_paths=("cache/benchmark_20260604/report.pdf",),
        allow_missing_assets=True,
    )
    strict = compare_benchmark_observations(
        baseline_entries=(_baseline(),),
        observations=(),
        skipped_pdf_paths=("cache/benchmark_20260604/report.pdf",),
        allow_missing_assets=False,
    )

    assert lenient.passed is True
    assert [warning.reason for warning in lenient.warnings] == ["benchmark_pdf_missing"]
    assert strict.passed is False
    assert [failure.reason for failure in strict.failures] == ["benchmark_pdf_missing"]
