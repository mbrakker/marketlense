"""Focused regressions for verified grounding recovery diagnostics."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import (
    _split_grounding_batch,
    _validate_grounding_check_coverage,
    grounding_payload,
    run_grounding_check,
)
from src.utils.errors import AppError
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _settings,
)
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _fact,
    _packs,
    _report,
    _verified_artifacts,
)


def _grounding_check(
    item_id: str,
    text: str,
    outcome: str,
    *,
    classification: str = "factual_claim",
) -> dict:
    dimension_status = (
        "compatible"
        if outcome == "entailed" and classification == "factual_claim"
        else "unknown"
    )
    return {
        "item_id": item_id,
        "section": "insights:fact-1.text",
        "text": text,
        "classification": classification,
        "entailment_outcome": outcome,
        "proposition_status": (
            "compatible"
            if outcome == "entailed" and classification == "factual_claim"
            else "unknown"
        ),
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": dimension_status,
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": (
            "The canonical source evidence matches the proposition and its "
            "protected dimensions."
            if outcome == "entailed"
            else "The canonical source evidence does not establish the proposition."
        ),
    }


def test_verified_grounding_recovery_passes_missing_public_item_id_to_model(
    tmp_path,
):
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-recovery-diagnostic",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    payload = grounding_payload(request, artifacts)
    entries = payload["retained_claims_to_ground"] + payload["public_factual_items"]
    public_item = payload["public_factual_items"][-1]

    def check(entry: dict) -> dict:
        return _grounding_check(
            entry["item_id"],
            entry["text"],
            "entailed",
            classification=entry.get("declared_classification", "factual_claim"),
        )

    complete = {"unsupported": [], "checks": [check(entry) for entry in entries]}
    incomplete = {
        "unsupported": [],
        "checks": [
            check(entry)
            for entry in entries
            if entry["item_id"] != public_item["item_id"]
        ],
    }

    class RecordingPromptClient(FakePromptClient):
        def __init__(self):
            self.rendered = []

        def render_prompt(self, prompt_request, ctx):
            self.rendered.append(
                (prompt_request.template.path, dict(prompt_request.variables))
            )
            return super().render_prompt(prompt_request, ctx)

    prompt_client = RecordingPromptClient()
    openai_client = FakeOpenAI(incomplete, complete)
    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=prompt_client,
        openai_client=openai_client,
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False,
            output_payload=None,
            reason="test_recovery_diagnostics",
        ),
    )

    assert issues == []
    repair_variables = [
        variables
        for path, variables in prompt_client.rendered
        if path == "report_vs/structured_output/repair/system"
    ]
    assert len(repair_variables) == 1
    assert public_item["item_id"] in repair_variables[0]["schema_errors"]
    assert len(openai_client.requests) == 2


def test_verified_grounding_failure_preserves_inner_contract_cause(tmp_path):
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-recovery-inner-cause",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(grounding_payload={"unsupported": []}),
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False,
            output_payload=None,
            reason="test_inner_cause",
        ),
    )

    assert len(issues) == 1
    assert "grounding_claim_check_coverage_invalid" in issues[0].message


def test_grounding_issue_retains_public_verified_evidence_for_repair(tmp_path):
    fact = _fact()
    insight = {
        "id": "fact-1",
        "text": "Adoption is rapidly growing among buyers in 2026.",
        "evidence_id": "verified-fact:fact-1",
        "evidence": fact["statement"],
        "metric": fact["metric"],
    }
    artifacts = _verified_artifacts(insight=insight, fact=fact)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-recovery-evidence-binding",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    payload = grounding_payload(request, artifacts)
    public_item = payload["public_factual_items"][0]
    entries = payload["retained_claims_to_ground"] + payload["public_factual_items"]
    checks = []
    for entry in entries:
        outcome = "not_established" if entry is public_item else "entailed"
        checks.append(
            _grounding_check(
                entry["item_id"],
                entry["text"],
                outcome,
                classification=entry.get("declared_classification", "factual_claim"),
            )
        )
    response = {
        "checks": checks,
        "unsupported": [
            {
                "item_id": public_item["item_id"],
                "section": public_item["section"],
                "text": public_item["text"],
                "classification": "factual_claim",
                "entailment_outcome": "not_established",
                "violation_type": "not_established",
                "reason": "The retained fact does not establish this wording.",
            }
        ],
    }

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(response),
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False,
            output_payload=None,
            reason="test_evidence_binding",
        ),
    )

    item_issues = [
        issue for issue in issues if issue.entity_id == public_item["item_id"]
    ]
    assert item_issues
    assert item_issues[0].evidence_ids == public_item["evidence_ids"]


def test_verified_grounding_does_not_bypass_model_verdict_for_exact_fact_text(tmp_path):
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-exact-fact-semantic-verdict",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    payload = grounding_payload(request, artifacts)
    entries = payload["retained_claims_to_ground"] + payload["public_factual_items"]
    checks = [
        _grounding_check(
            entry["item_id"],
            entry["text"],
            "not_established" if entry["section"].endswith(".text") else "entailed",
        )
        for entry in entries
    ]
    unsupported_entries = [
        entry for entry in entries if entry["section"].endswith(".text")
    ]
    response = {
        "checks": checks,
        "unsupported": [
            {
                "item_id": entry["item_id"],
                "section": entry["section"],
                "text": entry["text"],
                "classification": "factual_claim",
                "entailment_outcome": "not_established",
                "violation_type": "not_established",
                "reason": (
                    "The exact text is not sufficient to establish the complete "
                    "proposition."
                ),
            }
            for entry in unsupported_entries
        ],
    }

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(response),
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False,
            output_payload=None,
            reason="test_exact_fact_semantics",
        ),
    )

    assert issues
    assert any(
        issue.violation_type == "not_established"
        and issue.entity_id == "insight:fact-1:text"
        for issue in issues
    )


def test_failed_grounding_batch_subdivision_preserves_fact_scope_and_order():
    fact = _fact()
    batch_payload = {
        "public_factual_items": [
            {
                "item_id": f"insight:fact-{index}:text",
                "section": f"insights:fact-{index}.text",
                "text": f"Finding {index}.",
                "evidence_ids": ["verified-fact:fact-1"],
            }
            for index in range(1, 4)
        ],
        "retained_claims_to_ground": [],
        "canonical_verified_facts": {"fact-1": fact},
    }

    split_batches = _split_grounding_batch((batch_payload, []))

    assert [
        item["item_id"]
        for split_payload, _semantic_inputs in split_batches
        for item in split_payload["public_factual_items"]
    ] == [
        "insight:fact-1:text",
        "insight:fact-2:text",
        "insight:fact-3:text",
    ]
    assert all(
        split_payload["canonical_verified_facts"] == {"fact-1": fact}
        for split_payload, _semantic_inputs in split_batches
    )


@pytest.mark.parametrize(
    ("payload", "expected_context_key", "expected_id"),
    [
        (
            {
                "checks": [
                    _grounding_check("public-item", "A supported claim.", "entailed"),
                    _grounding_check("public-item", "A supported claim.", "entailed"),
                ],
                "unsupported": [],
            },
            "missing_or_ambiguous_public_item_ids",
            "public-item",
        ),
        (
            {
                "checks": [
                    _grounding_check("public-item", "A different claim.", "entailed")
                ],
                "unsupported": [],
            },
            "missing_or_ambiguous_public_item_ids",
            "public-item",
        ),
        (
            {
                "checks": [],
                "unsupported": [
                    {
                        "item_id": "public-item",
                        "text": "A supported claim.",
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "violation_type": "not_established",
                        "reason": "",
                    }
                ],
            },
            "item_ids",
            "public-item",
        ),
    ],
)
def test_verified_grounding_rejection_retains_actionable_public_item_id(
    payload, expected_context_key, expected_id
):
    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            payload,
            [],
            {},
            expected_public_items=[
                {
                    "item_id": "public-item",
                    "section": "insights:fact-1.text",
                    "text": "A supported claim.",
                }
            ],
            require_public_coverage=True,
        )

    assert exc_info.value.context[expected_context_key] == [expected_id]
    assert "returned_check_ids" in exc_info.value.context
    assert "expected_public_item_ids" in exc_info.value.context


def test_verified_grounding_rejects_non_substantive_verdict_reason() -> None:
    check = _grounding_check("public-item", "A supported claim.", "entailed")
    check["reason"] = "supported"

    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            {"checks": [check], "unsupported": []},
            [],
            {},
            expected_public_items=[
                {
                    "item_id": "public-item",
                    "section": "insights:fact-1.text",
                    "text": "A supported claim.",
                }
            ],
            require_public_coverage=True,
        )

    assert exc_info.value.context["coverage_failure_category"] == (
        "incomplete_check_reason"
    )


def test_verified_grounding_rejection_retains_missing_retained_claim_id():
    artifacts = _verified_artifacts()
    evidence_packs = _packs()
    package = validate_retained_claims(
        artifacts,
        evidence_packs,
        source_identity=SOURCE_IDENTITY,
        verified_facts_only=True,
    )
    inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity=SOURCE_IDENTITY,
    )
    assert inputs
    claim_id = inputs[0].candidate.claim_id
    retained_item_ids = {
        semantic_input.candidate.claim_id: semantic_input.candidate.claim_id
        for semantic_input in inputs
    }

    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            {"checks": [], "unsupported": []},
            inputs,
            retained_item_ids,
        )

    assert claim_id in exc_info.value.context["missing_claim_ids"]
