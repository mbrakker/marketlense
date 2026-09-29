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


def test_full_family_finalization_replaces_obsolete_retained_provenance() -> None:
    """Fresh bindings supersede stale claims from an earlier full-family pass."""
    prior_text = "Execution readiness was becoming more visible."
    previous = _assemble_soft_copy(
        linkedin_post=prior_text,
        evidence_packs={
            "findings": {
                "findings": [{"id": "f1", "evidence": prior_text, "pages": [1]}]
            }
        },
        soft_copy_claim_bindings={
            "linkedin_post": [
                {
                    "claim": prior_text,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )
    final_text = "Execution readiness is becoming more visible."
    payload = _assemble_soft_copy(
        linkedin_post=final_text,
        evidence_packs={
            "findings": {
                "findings": [{"id": "f1", "evidence": final_text, "pages": [1]}]
            }
        },
        soft_copy_claim_bindings={
            "linkedin_post": [
                {
                    "claim": final_text,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
        existing_soft_copy_claim_provenance=previous["soft_copy_claim_provenance"],
    )

    assert payload["linkedin_post"] == final_text
    assert_retained_soft_copy_claims_match_public_copy(payload)


def test_full_family_repair_deduplicates_retained_bindings_during_assembly() -> None:
    retained_text = "Retention demand is rising."
    replaced_text = "Revenue grew by 12%."
    repaired_text = "Revenue grew by 15%."
    original = _assemble_soft_copy(
        expert_comment=f"{replaced_text} {retained_text}",
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "evidence": replaced_text, "pages": [1]},
                    {"id": "f2", "evidence": retained_text, "pages": [2]},
                    {"id": "f3", "evidence": repaired_text, "pages": [3]},
                ]
            }
        },
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": replaced_text,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                },
                {
                    "claim": retained_text,
                    "classification": "factual",
                    "evidence_ids": ["f2"],
                },
            ]
        },
    )

    payload = _assemble_soft_copy(
        expert_comment=f"{retained_text} {repaired_text}",
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "evidence": replaced_text, "pages": [1]},
                    {"id": "f2", "evidence": retained_text, "pages": [2]},
                    {"id": "f3", "evidence": repaired_text, "pages": [3]},
                ]
            }
        },
        soft_copy_claim_bindings={
            "expert_comment": [
                {
                    "claim": retained_text,
                    "classification": "factual",
                    "evidence_ids": ["f2"],
                },
                {
                    "claim": repaired_text,
                    "classification": "factual",
                    "evidence_ids": ["f3"],
                },
            ]
        },
        existing_soft_copy_claim_provenance=original["soft_copy_claim_provenance"],
        replaced_soft_copy_claim_ids={
            "expert_comment": [
                claim["claim_id"]
                for claim in original["soft_copy_claim_provenance"]["claims"]
                if claim["text_hash"] == sha256(replaced_text.encode()).hexdigest()
            ]
        },
        # Regeneration records the complete family binding set, including the
        # unchanged sentence. Assembly must keep that retained claim exactly once.
        soft_copy_repair_texts={"expert_comment": [retained_text, repaired_text]},
    )

    claims = payload["soft_copy_claim_provenance"]["claims"]
    assert [claim["text_hash"] for claim in claims] == [
        sha256(retained_text.encode()).hexdigest(),
        sha256(repaired_text.encode()).hexdigest(),
    ]
    retained_claim = claims[0]
    assert retained_claim["evidence_ids"] == ["f2"]
    assert claims[1]["evidence_ids"] == ["f3"]
    assert_retained_soft_copy_claims_match_public_copy(payload)


def test_regeneration_keeps_unchanged_summary_with_retained_provenance() -> None:
    """A sibling repair must not replace an already validated summary."""
    summary = {
        "tldr": "Revenue grew by 12%.",
        "card_tldr_compact": "Revenue grew by 12%.",
        "executive_summary": "Revenue grew by 12%. The report describes retention demand.",
        "claim_evidence_map": [
            {
                "claim": "Revenue grew by 12%.",
                "evidence_id": "f1",
                "evidence": "Revenue grew by 12%.",
                "evidence_spans": [{"evidence_id": "f1", "source_pack": "findings"}],
            }
        ],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {"id": "f1", "evidence": "Revenue grew by 12%.", "pages": [1]},
                {
                    "id": "f2",
                    "evidence": "The report describes retention demand.",
                    "pages": [2],
                },
            ]
        }
    }
    original = _assemble_soft_copy(
        summary=summary,
        evidence_packs=evidence_packs,
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": "Revenue grew by 12%.",
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                },
                {
                    "claim": "The report describes retention demand.",
                    "classification": "factual",
                    "evidence_ids": ["f2"],
                },
            ]
        },
    )
    regenerated = _assemble_soft_copy(
        summary=summary,
        evidence_packs=evidence_packs,
        existing_soft_copy_claim_provenance=original["soft_copy_claim_provenance"],
    )

    assert regenerated["summary"] == original["summary"]
    assert (
        regenerated["soft_copy_claim_provenance"]
        == original["soft_copy_claim_provenance"]
    )


def test_finalization_omits_unbound_linkedin_sentence_before_retention() -> None:
    """Optional social copy retains only sentences with declared semantics."""
    supported = "Execution readiness is becoming more visible."
    payload = _assemble_soft_copy(
        linkedin_post=(
            f"{supported} This unsupported bridge must not be retained publicly."
        ),
        evidence_packs={
            "findings": {
                "findings": [{"id": "f1", "evidence": supported, "pages": [1]}]
            }
        },
        soft_copy_claim_bindings={
            "linkedin_post": [
                {
                    "claim": supported,
                    "classification": "factual",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    assert payload["linkedin_post"] == supported
    assert_retained_soft_copy_claims_match_public_copy(payload)


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


def test_finalization_uses_direct_summary_fallback_for_unbound_copy() -> None:
    """A complete direct claim map replaces summary prose lacking bindings."""
    direct = "Revenue reached 7.30%."
    payload = _assemble_soft_copy(
        summary={
            "tldr": "The report changes the planning outlook.",
            "card_tldr_compact": "Planning outlook changed.",
            "executive_summary": "Leaders should revisit their planning outlook.",
            "claim_evidence_map": [
                {
                    "claim": direct,
                    "evidence_id": "f1",
                    "evidence": direct,
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings"}
                    ],
                }
            ],
        },
        evidence_packs={
            "findings": {"findings": [{"id": "f1", "evidence": direct, "pages": [1]}]}
        },
        soft_copy_claim_bindings={
            "summary": [
                {
                    "claim": "The report changes the planning outlook.",
                    "classification": "interpretive",
                    "evidence_ids": ["f1"],
                }
            ]
        },
    )

    assert payload["summary"]["tldr"] == direct
    assert payload["summary"]["card_tldr_compact"] == direct
    assert payload["summary"]["executive_summary"] == direct
    assert_retained_soft_copy_claims_match_public_copy(payload)


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
