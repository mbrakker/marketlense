from __future__ import annotations

import pytest

from src.contracts.validation import ValidationRequest
from src.generators.validation_generator import validate_report
from tests._test_validation_generator._shared import (
    FakeAnalysisStore,
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


@pytest.mark.parametrize(
    ("outcome", "expected_violation"),
    [
        ("contradicted", "contradicted"),
        ("not_established", "unsupported_factual_claim"),
    ],
)
def test_grounding_semantic_outcome_preserves_hard_failure(
    tmp_path, outcome, expected_violation
):
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id=f"r-grounding-{outcome}",
            report=_report(),
            artifacts={
                "insights_final": [],
                "expert_comment": "Adoption surged in 2025.",
            },
            evidence_packs={},
            vector_store_id=None,
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={
                "unsupported": [
                    {
                        "section": "expert_comment",
                        "text": "Adoption surged in 2025.",
                        "classification": "factual_claim",
                        "entailment_outcome": outcome,
                        "reason": "Linked retained evidence does not support the claim.",
                    }
                ]
            },
        ),
        analysis_store=FakeAnalysisStore(),
    )

    grounding_issues = [item for item in result.issues if item.rule_id == "grounding"]
    assert grounding_issues
    assert grounding_issues[0].severity == "error"
    assert f"[factual_claim|{expected_violation}]" in grounding_issues[0].message
