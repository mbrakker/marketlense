import pytest

from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import (
    _retained_claim_grounding_item_ids,
    _validate_grounding_check_coverage,
)
from src.utils.errors import AppError
from tests.test_grounding_recovery_diagnostics import _grounding_check
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _packs,
    _verified_artifacts,
)


@pytest.mark.parametrize(
    ("check_type", "unsupported_type"),
    [
        ("not_established", "hallucinated_evidence_id"),
        ("hallucinated_evidence_id", "unsupported_number"),
    ],
)
def test_reused_verdict_cannot_reclassify_source_failure(check_type, unsupported_type):
    packs = _packs()
    package = validate_retained_claims(
        _verified_artifacts(),
        packs,
        source_identity=SOURCE_IDENTITY,
        verified_facts_only=True,
    )
    inputs = retained_claim_semantic_inputs(
        package, packs, source_identity=SOURCE_IDENTITY
    )
    item_ids = _retained_claim_grounding_item_ids(inputs, set())
    claim = inputs[0].candidate
    item_id = item_ids[claim.claim_id]
    check = _grounding_check(item_id, claim.text, "not_established")
    check["violation_type"] = check_type
    unsupported = {
        "item_id": item_id,
        "text": claim.text,
        "classification": "factual_claim",
        "entailment_outcome": "not_established",
        "violation_type": unsupported_type,
        "reason": "The canonical evidence does not establish the claim.",
    }
    with pytest.raises(AppError) as error:
        _validate_grounding_check_coverage(
            {"checks": [check], "unsupported": [unsupported]}, inputs, item_ids
        )
    assert (
        error.value.context["coverage_failure_category"] == "unsupported_pair_mismatch"
    )
