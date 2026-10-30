from __future__ import annotations

from hashlib import sha256

from src.generators.soft_copy_claim_provenance import (
    assert_retained_soft_copy_claims_match_public_copy,
)
from tests.test_soft_copy_claim_provenance import _assemble_soft_copy


def test_regeneration_candidate_defers_missing_bindings_to_candidate_validator() -> (
    None
):
    original = _assemble_soft_copy(
        expert_comment="Revenue grew by 12%.",
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "evidence": "Revenue grew by 12%.", "pages": [1]}
                ]
            }
        },
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": "Revenue grew by 12%.",
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    candidate = _assemble_soft_copy(
        expert_comment="Revenue grew by 13%.",
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "evidence": "Revenue grew by 12%.", "pages": [1]}
                ]
            }
        },
        existing_soft_copy_claim_provenance=original["soft_copy_claim_provenance"],
        regeneration_attempt=1,
    )

    assert candidate["expert_comment"] == "Revenue grew by 13%."
    assert not any(
        claim["artifact_family"] == "expert_comment"
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
    )


def test_finalization_drops_provenance_for_rolled_back_repair_text() -> None:
    final_text = "Retailers rely on measurable audience signals."
    stale_repair_text = "Retailers rely on a 19% lift in audience signals."
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "evidence": "Retailers rely on measurable audience signals.",
                    "pages": [1],
                }
            ]
        }
    }
    prior = _assemble_soft_copy(
        expert_comment=final_text,
        evidence_packs=evidence_packs,
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": final_text,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    finalized = _assemble_soft_copy(
        expert_comment=final_text,
        evidence_packs=evidence_packs,
        existing_soft_copy_claim_provenance=prior["soft_copy_claim_provenance"],
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": stale_repair_text,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
        soft_copy_repair_texts={"expert_comment": [stale_repair_text]},
    )

    retained_claims = [
        item
        for item in finalized["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    ]
    assert [item["text_hash"] for item in retained_claims] == [
        sha256(final_text.encode()).hexdigest()
    ]
    assert_retained_soft_copy_claims_match_public_copy(finalized)
