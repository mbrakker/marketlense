# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_soft_copy_claim_provenance.py"
)

from ._split_support_test_soft_copy_claim_provenance import *  # noqa: F401,F403


def test_align_bindings_keeps_exact_and_unmatched_bindings() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Exact sentence here. Unrelated off-grid model phrasing about weather."
    exact_binding = {
        "claim": "Exact sentence here.",
        "classification": "factual",
        "evidence_ids": ["f1"],
    }
    unmatched_binding = {
        "claim": "The forecast looks cloudy for marketers worldwide.",
        "classification": "interpretive",
        "evidence_ids": ["f2"],
    }
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[exact_binding, unmatched_binding],
    )
    assert aligned[0] == exact_binding
    assert aligned[1] == unmatched_binding


def test_byte_identical_expert_and_linkedin_text_share_sentence_hashes() -> None:
    from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    text = "U.S. merchants changed course. Planning followed."
    sentences = soft_copy_material_sentences(text)
    bindings = [
        {
            "claim": sentences[0],
            "classification": "interpretive",
            "evidence_ids": [],
        },
        {
            "claim": sentences[1],
            "classification": "recommendation",
            "evidence_ids": [],
        },
    ]
    shared = {
        "text": text,
        "declared_claims": bindings,
        "evidence_span_index": {},
        "producing_prompt_identity": {"execution_identity": "same"},
        "generation_attempt": 1,
        "regeneration_attempt": 0,
    }

    expert = build_soft_copy_claim_provenance(
        artifact_family="expert_comment", **shared
    )
    linkedin = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post", **shared
    )
    summary = build_soft_copy_claim_provenance(artifact_family="summary", **shared)
    repeated_expert = build_soft_copy_claim_provenance(
        artifact_family="expert_comment", **shared
    )

    assert [claim.text_hash for claim in expert] == [
        claim.text_hash for claim in linkedin
    ]
    assert [claim.text_hash for claim in expert] == [
        claim.text_hash for claim in summary
    ]
    assert [claim.claim_id for claim in expert] == [
        claim.claim_id for claim in repeated_expert
    ]
    assert [claim.text_hash for claim in expert] == [
        sha256(sentence.encode("utf-8")).hexdigest() for sentence in sentences
    ]


def test_fragment_binding_rebuilds_only_a_canonical_material_sentence() -> None:
    from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences
    from src.generators.soft_copy_claim_provenance import (
        build_soft_copy_claim_provenance,
    )

    text = "U.S. market adoption reached 42%. Leaders should monitor the shift."
    sentences = soft_copy_material_sentences(text)
    claims = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post",
        text=text,
        declared_claims=[
            {
                "claim": "market adoption reached 42%",
                "classification": "factual",
                "evidence_ids": ["finding-1"],
            },
            {
                "claim": sentences[1],
                "classification": "recommendation",
                "evidence_ids": [],
            },
        ],
        evidence_span_index={"finding-1": []},
        producing_prompt_identity={"execution_identity": "same"},
        generation_attempt=1,
        regeneration_attempt=0,
    )

    assert [claim.text_hash for claim in claims] == [
        sha256(sentence.encode("utf-8")).hexdigest() for sentence in sentences
    ]
    assert claims[0].text_hash != sha256(b"market adoption reached 42%").hexdigest()


def test_candidate_validation_rejects_fragment_absent_from_sentence_grid() -> None:
    from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences
    from src.generators.validation.regeneration_candidate import (
        validate_regeneration_candidate,
    )

    text = "U.S. market adoption reached 42%. Leaders should monitor the shift."
    sentences = soft_copy_material_sentences(text)
    current = _assemble_soft_copy(
        linkedin_post=text,
        soft_copy_claim_bindings={
            "linkedin_post": [
                {
                    "claim": sentence,
                    "classification": "recommendation",
                    "evidence_ids": [],
                }
                for sentence in sentences
            ]
        },
    )
    candidate = dict(current)
    fragment = "market adoption reached 42%"
    candidate["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family="linkedin_post",
                claim_id=(
                    f"soft_copy:linkedin_post:{sha256(fragment.encode()).hexdigest()[:16]}"
                ),
                text_hash=sha256(fragment.encode()).hexdigest(),
                classification="recommendation",
                evidence_ids=(),
                source_spans=(),
                producing_prompt_identity={"execution_identity": "retained"},
                generation_attempt=1,
                regeneration_attempt=0,
            )
        ]
    )

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs={},
        ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )

    assert any(issue.rule_id == "soft_copy_claim_provenance" for issue in result.issues)


def test_align_bindings_resolves_punctuation_and_case_variance() -> None:
    """Mechanically equivalent quotes bind without a model repair attempt."""

    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_claim_bindings_cover_public_text,
    )

    post = (
        "Marketers plan to raise budgets by 12% in 2026. Leaders remain "
        "cautious about attribution spend."
    )
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "marketers plan to raise budgets by 12% in 2026",
                "classification": "factual",
                "evidence_ids": ["f1"],
            },
            {
                "claim": "Leaders remain cautious about attribution spend",
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            },
        ],
    )
    assert [binding["claim"] for binding in aligned] == [
        "Marketers plan to raise budgets by 12% in 2026.",
        "Leaders remain cautious about attribution spend.",
    ]
    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=aligned,
    )


def test_align_bindings_resolves_quoted_clause_within_unique_sentence() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_uncovered_sentences,
    )

    post = (
        "Retail media networks now capture the majority of new brand budgets "
        "across every measured region this year."
    )
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "Retail media networks now capture",
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
        ],
    )
    assert [binding["claim"] for binding in aligned] == [
        post,
    ]
    assert (
        soft_copy_uncovered_sentences(
            artifact_family="linkedin_post",
            public_output=post,
            claim_bindings=aligned,
        )
        == []
    )


def test_align_bindings_resolves_sentence_quoted_with_extra_words() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Attribution windows keep shrinking for performance teams."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": (
                    "Key insight: attribution windows keep shrinking for "
                    "performance teams overall"
                ),
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            }
        ],
    )
    assert [binding["claim"] for binding in aligned] == [post]
    assert aligned[0]["evidence_ids"] == ["f2"]


def test_align_bindings_leaves_ambiguous_clause_unmatched() -> None:
    """An ambiguous quote stays unmatched so coverage still fails closed."""

    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_uncovered_sentences,
    )

    post = "First generic growth signal appeared early. Second generic growth signal appeared late."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "generic growth signal appeared",
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
        ],
    )
    assert (
        soft_copy_uncovered_sentences(
            artifact_family="linkedin_post",
            public_output=post,
            claim_bindings=aligned,
        )
        != []
    )


def test_align_bindings_drops_noise_once_coverage_is_complete() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
        soft_copy_claim_bindings_cover_public_text,
    )

    post = "Exact sentence here."
    exact_binding = {
        "claim": "Exact sentence here.",
        "classification": "factual",
        "evidence_ids": ["f1"],
    }
    stray_binding = {
        "claim": "stray model noise",
        "classification": "interpretive",
        "evidence_ids": [],
    }
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[exact_binding, stray_binding],
    )
    assert aligned == [exact_binding]
    assert soft_copy_claim_bindings_cover_public_text(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=aligned,
    )


def test_align_bindings_dedupes_sentences_keeping_first_declaration() -> None:
    from src.contracts.soft_copy_claim_provenance import (
        align_soft_copy_claim_bindings_to_sentences,
    )

    post = "Repeated sentence here."
    aligned = align_soft_copy_claim_bindings_to_sentences(
        artifact_family="linkedin_post",
        public_output=post,
        claim_bindings=[
            {
                "claim": "Repeated sentence here.",
                "classification": "factual",
                "evidence_ids": ["f1"],
            },
            {
                "claim": "Repeated sentence here.",
                "classification": "interpretive",
                "evidence_ids": ["f2"],
            },
        ],
    )
    assert len(aligned) == 1
    assert aligned[0]["evidence_ids"] == ["f1"]
