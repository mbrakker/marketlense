from __future__ import annotations

import pytest

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import run_grounding_check
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _check(
    *,
    outcome: str,
    protected_facts: dict,
    proposition_status: str = "compatible",
) -> dict:
    complete_protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    complete_protected_facts.update(protected_facts)
    return {
        "section": "expert_comment",
        "text": "In creative prose, respondents may adopt X in 2026.",
        "classification": "factual_claim",
        "entailment_outcome": outcome,
        "proposition_status": proposition_status,
        "protected_facts": complete_protected_facts,
        "reason": "Grounding comparison completed.",
    }


def _issues(tmp_path, check: dict):
    return run_grounding_check(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="protected-facts",
            report=_report(),
            artifacts={"expert_comment": check["text"]},
            evidence_packs={},
            vector_store_id=None,
        ),
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["52% of respondents expect X in 2026."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"unsupported": [], "checks": [check]}
        ),
        ctx=_ctx(),
    )


def test_grounding_accepts_compatible_creative_paraphrase(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        _check(
            outcome="entailed",
            protected_facts={
                "value": {
                    "claim_value": "52%",
                    "evidence_value": "52%",
                    "status": "compatible",
                },
                "population": {
                    "claim_value": "respondents",
                    "evidence_value": "respondents",
                    "status": "compatible",
                },
                "certainty": {
                    "claim_value": "may",
                    "evidence_value": "expect",
                    "status": "compatible",
                },
            },
        ),
    )

    assert issues == []


@pytest.mark.parametrize("dimension", PROTECTED_FACT_DIMENSIONS)
def test_grounding_blocks_each_incompatible_protected_dimension(
    tmp_path, dimension: str
) -> None:
    issues = _issues(
        tmp_path,
        _check(
            outcome="contradicted",
            protected_facts={
                dimension: {
                    "claim_value": "claim literal",
                    "evidence_value": "evidence literal",
                    "status": "incompatible",
                }
            },
        ),
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "[factual_claim|contradicted]" in issues[0].message
    assert dimension in issues[0].message


def test_grounding_blocks_incompatible_proposition_and_dimensions(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        _check(
            outcome="entailed",
            proposition_status="incompatible",
            protected_facts={
                "population": {
                    "claim_value": "companies",
                    "evidence_value": "respondents",
                    "status": "incompatible",
                },
                "observation_status": {
                    "claim_value": "observed fact",
                    "evidence_value": "forecast",
                    "status": "incompatible",
                },
                "causality": {
                    "claim_value": "X causes Y",
                    "evidence_value": "X is associated with Y",
                    "status": "incompatible",
                },
            },
        ),
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    for label in (
        "factual_proposition",
        "population",
        "observation_status",
        "causality",
    ):
        assert label in issues[0].message


def test_grounding_does_not_accept_an_unknown_factual_proposition(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        _check(
            outcome="entailed",
            proposition_status="unknown",
            protected_facts={},
        ),
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "[factual_claim|unsupported_factual_claim]" in issues[0].message
