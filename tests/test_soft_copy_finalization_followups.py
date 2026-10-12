from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from src.generators.soft_copy_claim_provenance import (
    assert_retained_soft_copy_claims_match_public_copy,
)
from src.utils.errors import AppError
from tests.test_soft_copy_claim_provenance import _assemble_soft_copy


def test_persisted_summary_can_pass_while_unbound_regeneration_candidate_fails() -> (
    None
):
    retained_sentence = "The report describes a distinct market shift."
    summary = {
        "tldr": retained_sentence,
        "card_tldr_compact": retained_sentence,
        "executive_summary": retained_sentence,
        "claim_evidence_map": [],
    }
    persisted = _assemble_soft_copy(
        summary=summary,
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": retained_sentence,
                    "classification": "interpretive",
                    "evidence_ids": [],
                }
            ]
        },
    )
    assert_retained_soft_copy_claims_match_public_copy(persisted)

    candidate = deepcopy(persisted)
    candidate["summary"]["tldr"] = "Mobile sessions rose during 2025."

    with pytest.raises(AppError) as captured:
        assert_retained_soft_copy_claims_match_public_copy(candidate)

    assert captured.value.code == "soft_copy_claim_provenance_coverage_invalid"
    assert captured.value.context["artifact_family"] == "summary"
    assert_retained_soft_copy_claims_match_public_copy(persisted)


def test_targeted_summary_removal_preserves_unrelated_claim_text() -> None:
    retained_tldr = "The report describes a focused market shift."
    retained_card = "The market response continues to evolve."
    retained_summary_claim = "The report documents the strategic shift."
    removed_claim = "An unsupported adjacent claim was removed."
    original_summary = {
        "tldr": retained_tldr,
        "card_tldr_compact": retained_card,
        "executive_summary": f"{retained_summary_claim} {removed_claim}",
        "claim_evidence_map": [],
    }
    original = _assemble_soft_copy(
        summary=original_summary,
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": retained_tldr,
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
                {
                    "claim": retained_card,
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
                {
                    "claim": retained_summary_claim,
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
                {
                    "claim": removed_claim,
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
            ]
        },
    )
    candidate_summary = {
        **original_summary,
        "executive_summary": retained_summary_claim,
        "claim_evidence_map": [
            {
                "claim": "The strategic segment recorded 52% growth.",
                "evidence_id": "section-1",
                "evidence_spans": [
                    {
                        "evidence_id": "section-1",
                        "source_pack": "doc_map",
                        "page": 1,
                        "text": "A strategic segment was discussed.",
                    }
                ],
            },
            {
                "claim": "The report identifies data adoption.",
                "evidence_id": "finding-1",
                "evidence": "The report identifies data adoption.",
            },
        ],
    }
    removed_claim_hash = sha256(removed_claim.encode()).hexdigest()
    removed_claim_id = f"soft_copy:summary:{removed_claim_hash[:16]}"

    finalized = _assemble_soft_copy(
        summary=candidate_summary,
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "evidence": "The report identifies data adoption.",
                        "pages": [1],
                    }
                ]
            }
        },
        existing_soft_copy_claim_provenance=original["soft_copy_claim_provenance"],
        replaced_soft_copy_claim_ids={"summary": [removed_claim_id]},
    )

    assert finalized["summary"]["tldr"] == retained_tldr
    assert finalized["summary"]["card_tldr_compact"] == retained_card
    assert finalized["summary"]["executive_summary"] == retained_summary_claim
    assert_retained_soft_copy_claims_match_public_copy(finalized)


def test_merchant_risk_council_summary_discards_rolled_back_repair_provenance() -> None:
    final_claim = "The report summarizes merchant payment operations."
    rolled_back_claim = "The report says digital wallet use rose 31% in 2026."
    summary = {
        "tldr": final_claim,
        "card_tldr_compact": final_claim,
        "executive_summary": final_claim,
        "claim_evidence_map": [],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "mrc-f1",
                    "evidence": final_claim,
                    "pages": [1],
                }
            ]
        }
    }
    prior = _assemble_soft_copy(
        summary=summary,
        evidence_packs=evidence_packs,
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": final_claim,
                    "classification": "factual",
                    "evidence_ids": ["mrc-f1"],
                }
            ]
        },
    )

    finalized = _assemble_soft_copy(
        summary=summary,
        evidence_packs=evidence_packs,
        existing_soft_copy_claim_provenance=prior["soft_copy_claim_provenance"],
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": final_claim,
                    "classification": "factual",
                    "evidence_ids": ["mrc-f1"],
                },
                {
                    "claim": rolled_back_claim,
                    "classification": "factual",
                    "evidence_ids": ["mrc-f1"],
                },
            ]
        },
        soft_copy_repair_texts={"summary": [rolled_back_claim]},
    )

    summary_claims = [
        item
        for item in finalized["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "summary"
    ]
    assert [item["text_hash"] for item in summary_claims] == [
        sha256(final_claim.encode()).hexdigest()
    ]
    assert_retained_soft_copy_claims_match_public_copy(finalized)


def test_finalization_deduplicates_identical_retained_provenance_records() -> None:
    final_text = "Retailers rely on measurable audience signals."
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "evidence": final_text,
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
    provenance = prior["soft_copy_claim_provenance"]
    provenance["claims"] = [*provenance["claims"], provenance["claims"][0]]

    finalized = _assemble_soft_copy(
        expert_comment=final_text,
        evidence_packs=evidence_packs,
        existing_soft_copy_claim_provenance=provenance,
    )

    retained_claims = [
        item
        for item in finalized["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    ]
    assert len(retained_claims) == 1
    assert_retained_soft_copy_claims_match_public_copy(finalized)
