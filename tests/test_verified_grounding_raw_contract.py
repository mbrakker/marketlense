from __future__ import annotations

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import grounding_payload, run_grounding_check
from tests._test_validation_generator._shared import (
    FakeOpenAI,
)
from tests._test_validation_generator._shared import (
    FakePromptClient as ValidationFakePromptClient,
)
from tests._test_validation_generator._shared import (
    _ctx as validation_ctx,
)
from tests._test_validation_generator._shared import (
    _settings as validation_settings,
)
from tests.test_verified_grounding_contract_corrections import (
    _verified_editorial_request,
)


def test_verified_grounding_adapts_raw_single_verdicts_and_derives_negative_projection(
    tmp_path,
):
    request, source_identity = _verified_editorial_request(
        "This finding changes planning priorities.", "interpretive"
    )
    package = validate_retained_claims(
        request.artifacts,
        request.evidence_packs,
        source_identity=source_identity,
        verified_facts_only=True,
    )
    retained_inputs = retained_claim_semantic_inputs(
        package,
        request.evidence_packs,
        source_identity=source_identity,
    )
    inventory = grounding_payload(
        request,
        request.artifacts,
        retained_claim_inputs=retained_inputs,
    )
    protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    raw_checks = []
    all_items = [
        *inventory["retained_claims_to_ground"],
        *inventory["public_factual_items"],
    ]
    negative_item_id = inventory["public_factual_items"][0]["item_id"]
    for item in all_items:
        item_id = str(item["item_id"])
        is_negative_item = item_id == negative_item_id
        is_editorial_item = (
            str(item.get("declared_classification") or "") == "analyst_interpretation"
        )
        raw_checks.append(
            {
                "item_id": item_id,
                "classification": (
                    "analyst_interpretation" if is_editorial_item else "factual_claim"
                ),
                "entailment_outcome": (
                    "not_established" if is_negative_item else "entailed"
                ),
                "violation_type": (
                    "unsupported_factual_claim" if is_negative_item else "none"
                ),
                "proposition_status": ("unknown" if is_negative_item else "compatible"),
                "protected_facts": protected_facts,
                "reason": (
                    "The linked canonical evidence does not establish the claim."
                    if is_negative_item
                    else "The linked canonical evidence supports this item."
                ),
            }
        )

    # Provider-owned shape: no text, section, or duplicated unsupported record.
    issues = run_grounding_check(
        request=request,
        settings=validation_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=ValidationFakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"checks": raw_checks},
            complete_grounding_contract=False,
        ),
        ctx=validation_ctx(),
        source_id=source_identity,
        retained_claim_package=package,
        retained_claim_inputs=retained_inputs,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "grounding"
    assert "[factual_claim|not_established]" in issues[0].message
    assert "validation_grounding_invalid_json" not in issues[0].message
