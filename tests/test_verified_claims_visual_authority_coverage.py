from __future__ import annotations

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    build_visual_authority_admitter,
)
from src.utils.errors import AppError
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeAnalysisStore,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _generation_responses,
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import _verified_admission


def test_canary_configuration_requires_expected_pdf_hash():
    with pytest.raises(AppError, match="hash-bearing source identity"):
        build_visual_authority_admitter(
            config=VisualAuthorityCanaryConfig(source_identity="report-without-hash"),
            pdf_path="report.pdf",
            default_output_dir="out",
            report_name="Report",
            evidence_packs={},
            ctx=_ctx(),
            settings=object(),
            doc_map={},
        )


def test_generation_fails_with_typed_minimum_coverage_error_after_remap(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="Retained first insight."),
        _insight("f2", score=0.98, text="Retained second insight."),
    ]

    def admit(shortlisted):
        return _verified_admission(shortlisted[:1], digest="g" * 64)

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f1"])

    with pytest.raises(AppError, match="minimum insight coverage") as error:
        generate_artifacts(
            report_id="visual-authority-minimum-coverage",
            report_name="Visual Authority Minimum Coverage",
            doc_map=_doc_map(2),
            evidence_packs=_generation_evidence(2),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=FakeOpenAI(responses),
            prompt_client=CapturingPromptClient(),
            analysis_store=FakeAnalysisStore(),
            visual_authority_admitter=admit,
        )

    assert error.value.code == "visual_authority_coverage_insufficient"
