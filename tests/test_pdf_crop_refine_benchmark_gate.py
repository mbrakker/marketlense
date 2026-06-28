from __future__ import annotations

from scripts.quality.pdf_crop_refine_benchmark import (
    PdfCropRefineBenchmarkBaselineEntry,
    PdfCropRefineBenchmarkObservation,
    compare_benchmark_observations,
    crop_refine_decision_signature,
)


def _baseline(**overrides) -> PdfCropRefineBenchmarkBaselineEntry:
    values = {
        "report_root": "out/report",
        "report_name": "report",
        "candidate_pack_path": "out/candidate-pack/candidates/candidates.json",
        "crop_refine_path": "out/report/report_analysis/crop_refine.json",
        "crop_artifact_globs": ("out/report/candidates/*.png",),
        "expected_candidate_pack_signature": "candidate-pack-signature",
        "expected_crop_refine_signature": "crop-refine-signature",
        "expected_crop_artifact_signature": "crop-artifact-signature",
        "expected_crop_artifact_count": 2,
        "expected_refine_decision_count": 1,
        "expected_estimated_model_call_count": 2,
        "baseline_median_seconds": 1.0,
        "runtime_warn_percent": 10.0,
        "runtime_fail_percent": 25.0,
    }
    values.update(overrides)
    return PdfCropRefineBenchmarkBaselineEntry(**values)


def _observation(**overrides) -> PdfCropRefineBenchmarkObservation:
    values = {
        "report_root": "out/report",
        "report_name": "report",
        "candidate_pack_signature": "candidate-pack-signature",
        "crop_refine_signature": "crop-refine-signature",
        "crop_artifact_signature": "crop-artifact-signature",
        "crop_artifact_count": 2,
        "refine_decision_count": 1,
        "estimated_model_call_count": 2,
        "durations_seconds": (1.0, 1.1),
        "median_seconds": 1.05,
    }
    values.update(overrides)
    return PdfCropRefineBenchmarkObservation(**values)


def test_crop_refine_decision_signature_is_stable_for_semantic_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "_cache": {
            "model": "gpt-5-mini",
            "mode": "adaptive",
            "prompt_system_sha256": "system",
            "prompt_user_sha256": "user",
        },
        "results": [
            {
                "entry_key": "ignored-cache-key",
                "candidate_id": "chart-1-0",
                "is_valid_candidate": True,
                "refined_bbox": [1.12345, 2.0, 3.98765, 4.0],
                "reason": "complete chart",
                "page": 1,
            }
        ],
    }
    changed_reason = {
        **payload,
        "results": [
            {
                **payload["results"][0],
                "reason": "different",
            }
        ],
    }

    assert crop_refine_decision_signature(payload) == crop_refine_decision_signature(
        dict(payload)
    )
    assert crop_refine_decision_signature(payload) != crop_refine_decision_signature(
        changed_reason
    )


def test_compare_benchmark_observations_fails_artifact_decision_and_cost_drift() -> (
    None
):
    result = compare_benchmark_observations(
        baseline_entries=(_baseline(),),
        observations=(
            _observation(
                candidate_pack_signature="changed-pack",
                crop_refine_signature="changed-refine",
                crop_artifact_signature="changed-artifacts",
                crop_artifact_count=3,
                refine_decision_count=2,
                estimated_model_call_count=4,
            ),
        ),
    )

    assert result.passed is False
    assert {failure.reason for failure in result.failures} == {
        "candidate_pack_signature_changed",
        "crop_refine_signature_changed",
        "crop_artifact_signature_changed",
        "crop_artifact_count_changed",
        "refine_decision_count_changed",
        "estimated_model_call_count_changed",
    }


def test_compare_benchmark_observations_warns_and_fails_runtime_regression() -> None:
    baseline = _baseline(runtime_warn_percent=10.0, runtime_fail_percent=25.0)

    warning_only = compare_benchmark_observations(
        baseline_entries=(baseline,),
        observations=(_observation(median_seconds=1.2),),
    )
    strict_runtime = compare_benchmark_observations(
        baseline_entries=(baseline,),
        observations=(_observation(median_seconds=1.3),),
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
        skipped_report_roots=("out/report",),
        allow_missing_assets=True,
    )
    strict = compare_benchmark_observations(
        baseline_entries=(_baseline(),),
        observations=(),
        skipped_report_roots=("out/report",),
        allow_missing_assets=False,
    )

    assert lenient.passed is True
    assert [warning.reason for warning in lenient.warnings] == [
        "benchmark_artifacts_missing"
    ]
    assert strict.passed is False
    assert [failure.reason for failure in strict.failures] == [
        "benchmark_artifacts_missing"
    ]
