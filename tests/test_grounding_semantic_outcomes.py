from __future__ import annotations

import pytest

from src.contracts.claim_validation import ClaimCandidate, ClaimSemanticInput
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import _exactly_evidenced_claims
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
    ("outcome", "expected_violation", "expected_severity", "expected_status"),
    [
        ("contradicted", "contradicted", "error", "fail"),
        ("not_established", "not_established", "error", "fail"),
    ],
)
def test_grounding_semantic_outcome_preserves_distinct_disposition(
    tmp_path, outcome, expected_violation, expected_severity, expected_status
):
    protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    compatible_protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "compatible",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
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
            validation_mode="deferred_grounding",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={
                "checks": [
                    {
                        "item_id": "expert_comment",
                        "section": "expert_comment",
                        "text": "Adoption surged in 2025.",
                        "classification": "factual_claim",
                        "entailment_outcome": outcome,
                        "proposition_status": "unknown",
                        "protected_facts": protected_facts,
                        "reason": "The retained evidence does not support this wording.",
                    },
                    {
                        "item_id": "metadata:title",
                        "section": "metadata.title",
                        "text": "Report",
                        "classification": "factual_claim",
                        "entailment_outcome": "entailed",
                        "proposition_status": "compatible",
                        "protected_facts": compatible_protected_facts,
                        "reason": "The retained report identity supports the title.",
                    },
                ],
                "unsupported": [
                    {
                        "section": "expert_comment",
                        "text": "Adoption surged in 2025.",
                        "item_id": "expert_comment",
                        "classification": "factual_claim",
                        "entailment_outcome": outcome,
                        "violation_type": expected_violation,
                        "reason": (
                            "Linked retained evidence does not support the claim."
                        ),
                    }
                ],
            },
        ),
        analysis_store=FakeAnalysisStore(),
    )

    grounding_issues = [item for item in result.issues if item.rule_id == "grounding"]
    assert grounding_issues
    assert grounding_issues[0].severity == expected_severity
    assert result.status == expected_status
    assert f"[factual_claim|{expected_violation}]" in grounding_issues[0].message


def test_exact_claim_reproduced_in_linked_evidence_is_deterministically_supported():
    claim = "For U.S. adults, gaming rose 21% after shelter in place."
    semantic_input = ClaimSemanticInput(
        schema_version="1.0",
        candidate=ClaimCandidate(
            schema_version="1.4",
            claim_id="claim:gaming",
            source_family="insights_final",
            text=claim,
            text_hash="h",
            kind="numeric",
            factual=True,
        ),
        evidence_texts=[
            "Chart statement: For U.S. adults, gaming rose 21% after shelter in place."
        ],
        evidence_hash="e",
    )

    assert _exactly_evidenced_claims([semantic_input]) == set()
