from __future__ import annotations

import pytest

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import grounding_payload, run_grounding_check
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
    text: str = "In creative prose, respondents may adopt X in 2026.",
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
        "item_id": "expert_comment",
        "section": "expert_comment",
        "text": text,
        "classification": "factual_claim",
        "entailment_outcome": outcome,
        "proposition_status": proposition_status,
        "protected_facts": complete_protected_facts,
        "reason": "Grounding comparison completed.",
    }


def _issues(
    tmp_path,
    check: dict,
    *,
    evidence_text: str = "52% of respondents expect X in 2026.",
):
    request = ValidationRequest(
        schema_version="1.0",
        report_id="protected-facts",
        report=_report(),
        artifacts={"expert_comment": check["text"]},
        evidence_packs={},
        vector_store_id=None,
    )
    payload = grounding_payload(request, request.artifacts)
    checks = []
    for item in payload["public_factual_items"]:
        if item["item_id"] == "expert_comment":
            current = dict(check)
        else:
            current = _check(outcome="entailed", protected_facts={}, text=item["text"])
        current["item_id"] = item["item_id"]
        current["section"] = item["section"]
        checks.append(current)
    unsupported = []
    if check["entailment_outcome"] != "entailed":
        incompatible_dimensions = [
            name
            for name, dimension in check.get("protected_facts", {}).items()
            if isinstance(dimension, dict) and dimension.get("status") == "incompatible"
        ]
        unsupported.append(
            {
                "item_id": "expert_comment",
                "section": "expert_comment",
                "text": check["text"],
                "classification": "factual_claim",
                "entailment_outcome": check["entailment_outcome"],
                "violation_type": (
                    "not_established"
                    if check["entailment_outcome"] == "not_established"
                    else "contradicted"
                ),
                "reason": (
                    "The model did not establish the complete claim."
                    + (
                        " Protected dimensions: "
                        + ", ".join(incompatible_dimensions)
                        + "."
                        if incompatible_dimensions
                        else ""
                    )
                ),
            }
        )
    return run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[evidence_text],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"unsupported": unsupported, "checks": checks}
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


def test_grounding_accepts_an_explicitly_supported_budget_reason(tmp_path) -> None:
    claim = (
        "A similar proportion (48%) are embracing cheaper alternatives, "
        "such as canned fruit instead of fresh, to manage budgets."
    )
    evidence = (
        "A similar proportion (48%) are embracing cheaper alternatives, such as "
        "canned fruit instead of fresh, highlighting a willingness to compromise "
        "on experience to manage budgets."
    )
    issues = _issues(
        tmp_path,
        _check(
            outcome="entailed",
            text=claim,
            protected_facts={
                "value": {
                    "claim_value": "48%",
                    "evidence_value": "48%",
                    "status": "compatible",
                },
                "causality": {
                    "claim_value": "cheaper alternatives used to manage budgets",
                    "evidence_value": "cheaper alternatives to manage budgets",
                    "status": "compatible",
                },
            },
        ),
        evidence_text=evidence,
    )

    assert issues == []


def test_grounding_accepts_the_supported_quantity_observation_without_a_reason(
    tmp_path,
) -> None:
    claim = (
        "Around half (49%) are buying smaller quantities, suggesting a shift "
        "toward consumption control rather than complete avoidance."
    )
    evidence = (
        "For instance, around half (49%) are buying smaller quantities, "
        "suggesting a shift toward consumption control, rather than complete avoidance."
    )
    issues = _issues(
        tmp_path,
        _check(
            outcome="entailed",
            text=claim,
            protected_facts={
                "value": {
                    "claim_value": "49%",
                    "evidence_value": "49%",
                    "status": "compatible",
                },
                "causality": {
                    "claim_value": "smaller quantities suggest consumption control",
                    "evidence_value": "smaller quantities suggest consumption control",
                    "status": "compatible",
                },
            },
        ),
        evidence_text=evidence,
    )

    assert issues == []


def test_grounding_flags_the_unsupported_reason_on_the_49_percent_finding(
    tmp_path,
) -> None:
    claim = (
        "Around half of consumers (49%) said they were buying smaller quantities "
        "to manage budgets."
    )
    evidence = (
        "For instance, around half (49%) are buying smaller quantities, suggesting "
        "a shift toward consumption control, rather than complete avoidance."
    )
    issues = _issues(
        tmp_path,
        _check(
            outcome="not_established",
            text=claim,
            protected_facts={
                "value": {
                    "claim_value": "49%",
                    "evidence_value": "49%",
                    "status": "compatible",
                },
                "causality": {
                    "claim_value": "buying smaller quantities to manage budgets",
                    "evidence_value": None,
                    "status": "unknown",
                },
            },
        ),
        evidence_text=evidence,
    )

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "[factual_claim|not_established]" in issues[0].message


@pytest.mark.parametrize(
    ("violation_type", "entailment_outcome"),
    [("contradicted", "contradicted"), ("unsupported_number", "not_established")],
)
def test_explicit_factual_failure_is_not_reclassified_by_retrieval_wording(
    tmp_path, violation_type: str, entailment_outcome: str
) -> None:
    entry = {
        "item_id": "summary:tldr",
        "section": "tldr",
        "text": "Revenue rose 42%.",
        "classification": "factual_claim",
        "entailment_outcome": entailment_outcome,
        "violation_type": violation_type,
        "reason": "Retrieval failed, and the cited source contradicts the claim.",
    }
    issues = run_grounding_check(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="retrieval-does-not-mask-fact-failure",
            report=_report(),
            artifacts={"summary": {"tldr": entry["text"]}},
            evidence_packs={},
            vector_store_id=None,
        ),
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["Revenue fell 42% in 2025."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                "unsupported": [entry],
                "checks": [
                    {
                        **_check(outcome="entailed", protected_facts={}, text="Report"),
                        "item_id": "metadata:title",
                        "section": "metadata.title",
                    }
                ],
            }
        ),
        ctx=_ctx(),
    )

    assert len(issues) == 1
    assert f"|{violation_type}]" in issues[0].message
    assert "evidence_retrieval_failure" not in issues[0].message
    assert issues[0].severity == "error"


def test_retrieval_wording_without_structured_type_does_not_soften_grounding(
    tmp_path,
) -> None:
    entry = {
        "item_id": "summary:tldr",
        "section": "tldr",
        "text": "Revenue rose 42%.",
        "classification": "factual_claim",
        "reason": "Retrieval failed; the evidence does not support the claim.",
    }
    issues = run_grounding_check(
        request=ValidationRequest(
            schema_version="1.0",
            report_id="untyped-retrieval-reason",
            report=_report(),
            artifacts={"summary": {"tldr": entry["text"]}},
            evidence_packs={},
            vector_store_id=None,
        ),
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["Revenue fell 42% in 2025."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                "unsupported": [entry],
                "checks": [
                    {
                        **_check(outcome="entailed", protected_facts={}, text="Report"),
                        "item_id": "metadata:title",
                        "section": "metadata.title",
                    }
                ],
            }
        ),
        ctx=_ctx(),
    )

    assert len(issues) == 1
    assert "schema_missing_required" in issues[0].message
    assert "evidence_retrieval_failure" not in issues[0].message
    assert issues[0].severity == "error"


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
    assert "grounding_claim_check_coverage_invalid" in issues[0].message


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
    assert "grounding_claim_check_coverage_invalid" in issues[0].message
