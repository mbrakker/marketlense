from __future__ import annotations

import pytest

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimCandidate,
    ClaimEvidenceReference,
    ClaimSemanticGroundingResult,
    ClaimSemanticInput,
    ClaimSemanticValidationIdentity,
    ClaimValidationResult,
)
from src.contracts.protected_facts import ProtectedFactComparison
from src.generators.claim_validation_generator import (
    _apply_semantic_results,
    _claim_kind,
    _claim_requires_factual_validation,
)
from src.generators.public_editorial_quality_generator import (
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
)
from src.utils.errors import AppError
from tests._test_validation_generator._shared import _ctx


def _fact() -> dict:
    source_identity = f"semantic-authority|pdf-sha256:{'a' * 64}"
    return {
        "schema_version": "1.0",
        "fact_id": "fact-1",
        "statement": "42% of buyers adopted the workflow in 2026.",
        "metric": {
            "label": "Workflow adoption",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
            "cohort": "buyers",
            "methodology": {
                "weighting": "post-stratified",
                "unfamiliar_nested_field": {"basis": "respondent-level"},
            },
        },
        "qualifiers": ["among buyers"],
        "source_identity": source_identity,
        "source_pdf_sha256": "a" * 64,
        "supporting_physical_pages": [4],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [4],
            "source_truth_notes_by_page": {
                "4": "Page 4 reports workflow adoption among buyers."
            },
        },
    }


def _public_item() -> dict:
    return {
        "public_item_id": "insights:insight-1",
        "artifact": "insights_final",
        "field": "text",
        "text": "Buyers are moving toward the workflow.",
        "evidence_ids": ["verified-fact:fact-1"],
        "evidence_text": "stale editorial evidence must not win",
        "repair_target": "insights_final",
    }


def _review_verdict(
    *,
    item_id: str,
    classification: str = "factual_claim",
    evidence_ids: list[str] | None = None,
) -> dict:
    return {
        "item_id": item_id,
        "status": "pass",
        "classification": classification,
        "severity": "info",
        "rule_id": "",
        "hard_fail_class": "",
        "reason": (
            "The final wording is materially grounded in the retained source evidence "
            "and its protected context."
        ),
        "evidence_ids": list(evidence_ids or []),
        "repair_target": "insights_final",
    }


def test_public_review_requires_evidence_for_factual_pass() -> None:
    item = _public_item()
    payload = {"verdicts": [_review_verdict(item_id=item["public_item_id"])]}

    with pytest.raises(AppError) as exc_info:
        _validate_public_editorial_review_payload(payload, [item], _ctx())

    assert exc_info.value.code == "public_editorial_quality_review_evidence_missing"


def test_public_review_allows_pure_normative_pass_without_source_entailment() -> None:
    item = {**_public_item(), "evidence_ids": []}
    payload = {
        "verdicts": [
            _review_verdict(
                item_id=item["public_item_id"],
                classification="prescriptive_recommendation",
            )
        ]
    }

    _validate_public_editorial_review_payload(payload, [item], _ctx())


def test_public_review_receives_complete_canonical_verified_fact() -> None:
    fact = _fact()
    artifacts = {
        "verified_facts": [fact],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Buyers are moving toward the workflow.",
                "evidence_id": "verified-fact:fact-1",
                "evidence": "stale editorial evidence must not win",
            }
        ],
    }

    items = public_editorial_semantic_review_items(artifacts)
    item = next(
        item for item in items if item["public_item_id"] == "insight:insight-1:text"
    )

    assert item["evidence_text"] != "stale editorial evidence must not win"
    assert (
        item["verified_facts"]["verified-fact:fact-1"]["metric"]["methodology"]
        == fact["metric"]["methodology"]
    )


def test_every_material_claim_reaches_grounding_compatibility_boundary() -> None:
    assert (
        _claim_kind("Retailers should rebalance marketplace spending.") == "descriptive"
    )
    assert (
        _claim_requires_factual_validation(
            text="Retailers should rebalance marketplace spending.",
            kind="descriptive",
            classification="prescriptive_recommendation",
            evidence_bound=False,
        )
        is True
    )


def test_model_entailed_outcome_is_not_overridden_by_protected_fact_diagnostics() -> (
    None
):
    reference = ClaimEvidenceReference(
        schema_version="1.0",
        evidence_id="F1",
        source_pack="findings",
        page=4,
        text_hash="text-hash",
    )
    candidate = ClaimCandidate(
        schema_version="1.4",
        claim_id="claim:1",
        source_family="insights_final",
        text="The workflow reached 42% among buyers in 2026.",
        text_hash="claim-hash",
        kind="descriptive",
        factual=True,
        evidence_references=[reference],
    )
    semantic_input = ClaimSemanticInput(
        schema_version="1.0",
        candidate=candidate,
        evidence_texts=["The workflow reached 42% among buyers in 2026."],
        evidence_hash="evidence-hash",
        source_identity="source-identity",
    )
    identity = ClaimSemanticValidationIdentity(
        schema_version="1.0",
        claim_id=candidate.claim_id,
        claim_text_hash=candidate.text_hash,
        evidence_ids=["F1"],
        evidence_hash=semantic_input.evidence_hash,
        source_identity=semantic_input.source_identity,
        prompt_family="report_vs/validate/grounding",
        prompt_content_hash="prompt-hash",
        execution_identity="execution-identity",
        validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        model_provider="openai",
        model_name="gpt-6-luna",
        configuration_policy_identity="policy-hash",
        relevant_input_hash="input-hash",
    )
    result = ClaimValidationResult(
        schema_version="1.4",
        candidate=candidate,
        deterministic_status="unresolved",
        status="unresolved",
    )
    model_result = ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome="entailed",
        reason="The retained evidence entails the proposition.",
        identity=identity,
        protected_facts=ProtectedFactComparison.from_payload(
            {
                "value": {
                    "claim_value": "42",
                    "evidence_value": "99",
                    "status": "incompatible",
                }
            },
            proposition_status="incompatible",
        ),
    )

    updated = _apply_semantic_results([result], [semantic_input], [model_result])

    assert updated[0].status == "supported"
    assert updated[0].semantic_outcome == "entailed"
