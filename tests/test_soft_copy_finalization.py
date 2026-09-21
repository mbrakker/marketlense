from __future__ import annotations

from hashlib import sha256

import pytest

from src.generators.soft_copy_claim_provenance import (
    assert_retained_soft_copy_claims_match_public_copy,
)
from src.utils.errors import AppError
from tests.test_soft_copy_claim_provenance import _assemble_soft_copy


def test_finalization_rebuilds_expert_provenance_after_numeric_display_correction() -> (
    None
):
    """A final source-display correction keeps its declared semantic binding."""
    payload = _assemble_soft_copy(
        expert_comment="Growth reaches 7.3% in January.",
        insights_final=[
            {
                "id": "growth",
                "text": "Growth reaches 7.3% in January.",
                "evidence_id": "f1",
                "evidence": "Growth reaches +7.30% in January 2025.",
            }
        ],
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "evidence": "Growth reaches +7.30% in January 2025.",
                        "pages": [1],
                    }
                ]
            }
        },
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": "Growth reaches 7.3% in January.",
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    assert payload["expert_comment"] == "Growth reaches +7.30% in January 2025."
    claim = next(
        item
        for item in payload["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    )
    assert claim["text_hash"] == sha256(payload["expert_comment"].encode()).hexdigest()
    assert claim["classification"] == "factual"
    assert claim["evidence_ids"] == ["f1"]


def test_finalization_rebuilds_linkedin_provenance_after_range_display_correction() -> (
    None
):
    payload = _assemble_soft_copy(
        linkedin_post=(
            "Paid subscriptions are forecast to rise from 4.1 to 5.7, which changes "
            "distribution planning."
        ),
        insights_final=[
            {
                "id": "subscriptions",
                "text": "Subscriptions are forecast to increase.",
                "evidence_id": "f1",
                "evidence": (
                    "Paid subscriptions are forecast to rise from 4.1 subscriptions "
                    "per subscriber today to 5.7 by 2024."
                ),
            }
        ],
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "evidence": (
                            "Paid subscriptions are forecast to rise from 4.1 "
                            "subscriptions per subscriber today to 5.7 by 2024."
                        ),
                        "pages": [1],
                    }
                ]
            }
        },
        soft_copy_claim_bindings={
            "linkedin_post": [
                {
                    "claim": (
                        "Paid subscriptions are forecast to rise from 4.1 to 5.7, "
                        "which changes distribution planning."
                    ),
                    "classification": "interpretive",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    final_post = (
        "Paid subscriptions are forecast to rise from 4.1 subscriptions per subscriber today "
        "to 5.7 by 2024, which changes distribution planning."
    )
    assert payload["linkedin_post"] == final_post
    claim = next(
        item
        for item in payload["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "linkedin_post"
    )
    assert claim["text_hash"] == sha256(final_post.encode()).hexdigest()
    assert claim["classification"] == "interpretive"
    assert claim["evidence_ids"] == ["f1"]


def test_finalization_derives_summary_fallback_bindings_from_retained_claim_map() -> (
    None
):
    direct = "Revenue reached 7.30%."
    payload = _assemble_soft_copy(
        summary={
            "tldr": "Unsupported forecast leads planning.",
            "card_tldr_compact": "Unsupported forecast leads planning.",
            "executive_summary": "Unsupported forecast leads planning.",
            "claim_evidence_map": [
                {
                    "claim": direct,
                    "evidence_id": "f1",
                    "evidence": direct,
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings"}
                    ],
                },
                {
                    "claim": "Planning must follow an unsupported forecast.",
                    "evidence_id": "section-1",
                    "evidence": "A descriptive section only.",
                    "evidence_spans": [
                        {"evidence_id": "section-1", "source_pack": "doc_map"}
                    ],
                },
            ],
        },
        evidence_packs={
            "findings": {"findings": [{"id": "f1", "evidence": direct, "pages": [1]}]}
        },
        doc_map={
            "sections": [{"id": "section-1", "summary": "A descriptive section only."}]
        },
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": "Unsupported forecast leads planning.",
                    "classification": "interpretive",
                    "evidence_ids": ["section-1"],
                }
            ]
        },
    )

    final_summary = payload["summary"]
    assert final_summary["tldr"] == direct
    assert final_summary["card_tldr_compact"] == direct
    assert final_summary["executive_summary"] == direct
    claims = [
        item
        for item in payload["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "summary"
    ]
    assert len(claims) == 1
    assert claims[0]["text_hash"] == sha256(direct.encode()).hexdigest()
    assert claims[0]["classification"] == "factual"
    assert claims[0]["evidence_ids"] == ["f1"]


def test_finalization_invariant_rejects_public_copy_mutated_after_provenance() -> None:
    payload = _assemble_soft_copy(
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
    payload["expert_comment"] = "Revenue grew by 13%."

    with pytest.raises(AppError) as captured:
        assert_retained_soft_copy_claims_match_public_copy(payload)

    assert captured.value.code == "soft_copy_claim_provenance_coverage_invalid"
