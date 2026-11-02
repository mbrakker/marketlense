from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.orchestrators.cross_report_analysis_orchestrator import (
    _generated_from_dict,
)
from src.orchestrators.publish_orchestrator import (
    _cross_report_publish_authorization_error,
)
from src.utils.errors import AppError
from tests._test_cross_report_analysis_generator._shared import (
    FakeOpenAIClient,
    FakePromptClient,
    _analysis_inputs,
    _request,
    _settings,
)
from src.generators.cross_report_analysis_generator import (
    generate_cross_report_analysis,
    validate_cross_report_generated_analysis,
)
from tests.test_cross_report_publish_orchestrator import _package


def test_metric_normalization_language_is_telemetry_not_publication_authority(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    payload = dict(FakeOpenAIClient().payload)
    payload["title"] = "Normalized average language remains source-specific context"

    generated = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(payload),
    )
    validation = validate_cross_report_generated_analysis(
        generated,
        run_context,
        raise_on_failure=False,
    )

    assert validation.passed is True
    assert validation.metric_normalization_violations == ["normalized average"]
    assert validation.metric_comparison_assessment.status == "source_specific"


def test_missing_metric_comparison_assessment_fails_closed(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    payload = dict(FakeOpenAIClient().payload)
    payload["metric_comparison_assessment"] = None

    with pytest.raises(AppError) as exc_info:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(payload),
        )

    assert exc_info.value.code == "cross_report_metric_comparison_assessment_missing"


@pytest.mark.parametrize(
    ("assessment", "expected_issue"),
    [
        (
            {
                "status": "source_specific",
                "raw_metric_ids": ["metric-not-retained"],
                "evidence_ids": ["ev-report-a-claim-1"],
                "rationale": "The source-specific metric is retained for context.",
                "uncertainty": "",
            },
            "raw_metric_ids_unknown",
        ),
        (
            {
                "status": "unresolved",
                "raw_metric_ids": ["metric-a"],
                "evidence_ids": ["ev-report-a-claim-1"],
                "rationale": "The source metrics cannot be compared safely.",
                "uncertainty": "",
            },
            "uncertainty_missing",
        ),
        (
            {
                "status": "none",
                "raw_metric_ids": ["metric-a"],
                "evidence_ids": ["ev-report-a-claim-1"],
                "rationale": "No cross-source comparison is asserted.",
                "uncertainty": "",
            },
            "none_has_references",
        ),
    ],
)
def test_metric_comparison_assessment_rejects_invalid_structural_authority(
    tmp_path,
    run_context,
    assessment,
    expected_issue,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    payload = dict(FakeOpenAIClient().payload)
    payload["metric_comparison_assessment"] = assessment

    with pytest.raises(AppError) as exc_info:
        generate_cross_report_analysis(
            _request(),
            evidence_inputs,
            signal_result,
            agreement_result,
            _settings(tmp_path),
            run_context,
            prompt_client=FakePromptClient(),
            openai_client=FakeOpenAIClient(payload),
        )

    assert exc_info.value.code == "cross_report_metric_comparison_assessment_invalid"
    assert expected_issue in exc_info.value.context["issues"]


def test_unresolved_metric_comparison_cannot_reach_publication(
    tmp_path,
) -> None:
    package = _package(tmp_path)
    metadata = dict(package.machine_metadata)
    metadata["metric_comparison_assessment"] = {
        "status": "unresolved",
        "raw_metric_ids": ["metric-a"],
        "evidence_ids": ["ev-a"],
        "rationale": "The source metrics cannot be reconciled for a comparison.",
        "uncertainty": "The populations and denominators are not comparable.",
    }

    error = _cross_report_publish_authorization_error(
        replace(package, machine_metadata=metadata)
    )

    assert error is not None
    assert error.code == "cross_report_metric_comparison_unresolved"


def test_retained_legacy_analysis_without_metric_authority_fails_closed(
    tmp_path,
    run_context,
) -> None:
    evidence_inputs, signal_result, agreement_result = _analysis_inputs()
    generated = generate_cross_report_analysis(
        _request(),
        evidence_inputs,
        signal_result,
        agreement_result,
        _settings(tmp_path),
        run_context,
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAIClient(),
    )
    retained = asdict(generated)
    retained.pop("metric_comparison_assessment")

    with pytest.raises(AppError) as exc_info:
        _generated_from_dict(retained)

    assert exc_info.value.code == "cross_report_metric_comparison_assessment_missing"
