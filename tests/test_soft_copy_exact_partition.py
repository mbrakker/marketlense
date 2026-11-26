import hashlib

import pytest

from src.contracts import soft_copy_claim_provenance as contract
from src.generators.soft_copy_claim_provenance import (
    build_soft_copy_claim_provenance,
    retained_soft_copy_claims_cover_text,
)
from src.utils.errors import AppError

TEXT = "U.S. Pay TV declined. Revenue rose."
BINDINGS = [
    {
        "claim": "U.S. Pay TV declined.",
        "classification": "factual",
        "evidence_ids": ["e1"],
    },
    {"claim": "Revenue rose.", "classification": "factual", "evidence_ids": ["e2"]},
]


def build(text=TEXT, bindings=BINDINGS):
    return build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=text,
        declared_claims=bindings,
        evidence_span_index={},
        producing_prompt_identity={},
        generation_attempt=1,
        regeneration_attempt=0,
    )


def test_fresh_and_retained_hashes_resolve_identical_atomic_spans():
    claims = build()
    assert [c.text_hash for c in claims] == [
        contract.soft_copy_sentence_hash(b["claim"]) for b in BINDINGS
    ]
    assert contract.resolve_soft_copy_public_text_partition(
        text=TEXT, claim_bindings=BINDINGS
    ) == ["U.S. Pay TV declined.", "Revenue rose."]
    assert contract.resolve_soft_copy_public_text_partition(
        text=TEXT, retained_claims=claims
    ) == ["U.S. Pay TV declined.", "Revenue rose."]
    assert retained_soft_copy_claims_cover_text(text=TEXT, claims=claims)


def test_repeated_claim_occurrences_survive_partition():
    text = "U.S. Pay TV declined. U.S. Pay TV declined."
    bindings = [BINDINGS[0]]
    claims = build(text, bindings)
    assert contract.resolve_soft_copy_public_text_partition(
        text=text, retained_claims=claims
    ) == ["U.S. Pay TV declined.", "U.S. Pay TV declined."]


def test_overlapping_or_conflicting_declarations_fail_closed():
    overlap = BINDINGS + [
        {"claim": TEXT, "classification": "interpretive", "evidence_ids": []}
    ]
    with pytest.raises(AppError):
        build(TEXT, overlap)
    conflicting = [BINDINGS[0], {**BINDINGS[0], "evidence_ids": ["other"]}, BINDINGS[1]]
    with pytest.raises(AppError):
        build(TEXT, conflicting)


def test_ambiguous_partition_and_incomplete_coverage_have_distinct_codes():
    bindings = [
        {"claim": claim, "classification": "interpretive", "evidence_ids": []}
        for claim in ("One.", "Two.", "One. Two.")
    ]
    with pytest.raises(AppError) as ambiguous:
        contract.resolve_soft_copy_public_text_partition(
            text="One. Two.", claim_bindings=bindings
        )
    assert ambiguous.value.code == "soft_copy_claim_provenance_ambiguous"
    with pytest.raises(AppError) as incomplete:
        contract.resolve_soft_copy_public_text_partition(
            text="One. Two.", claim_bindings=bindings[:1]
        )
    assert incomplete.value.code == "soft_copy_claim_provenance_coverage_invalid"
    with pytest.raises(AppError) as overlap:
        contract.resolve_soft_copy_public_text_partition(
            text="One Two Three Four",
            claim_bindings=[{"claim": "One Two"}, {"claim": "Two Three"}],
        )
    assert overlap.value.code == "soft_copy_claim_provenance_ambiguous"


def test_legacy_without_exact_declaration_remains_available():
    assert contract.resolve_soft_copy_public_text_partition(
        text="First sentence. Second sentence.", claim_bindings=[]
    ) == ["First sentence.", "Second sentence."]


def test_partial_declaration_cannot_acquire_undeclared_claim_text():
    text = "U.S. market adoption reached 42%."
    bindings = [
        {
            "claim": "market adoption reached 42%",
            "classification": "factual",
            "evidence_ids": ["e1"],
        }
    ]
    with pytest.raises(AppError):
        build(text, bindings)


def test_unmatched_declaration_reports_hashes_without_public_or_claim_text():
    public_text = "Sales rose."
    declared_claim = "Profits fell."
    with pytest.raises(AppError) as failure:
        contract.resolve_soft_copy_public_text_partition(
            text=public_text, claim_bindings=[{"claim": declared_claim}]
        )

    assert failure.value.code == "soft_copy_claim_provenance_coverage_invalid"
    assert failure.value.context == {
        "claim_sha256": hashlib.sha256(declared_claim.encode()).hexdigest(),
        "public_text_sha256": hashlib.sha256(public_text.encode()).hexdigest(),
    }
    assert public_text not in str(failure.value.context)
    assert declared_claim not in str(failure.value.context)


def test_unmatched_declaration_cannot_silently_lose_evidence():
    with pytest.raises(AppError):
        build(
            "Sales rose.",
            [
                {
                    "claim": "Sales rose.",
                    "classification": "factual",
                    "evidence_ids": ["e1"],
                },
                {
                    "claim": "Sales rose",
                    "classification": "factual",
                    "evidence_ids": ["e2"],
                },
            ],
        )


def test_retained_family_claims_can_resolve_one_summary_field():
    claims = build()
    assert contract.resolve_soft_copy_public_text_partition(
        text="U.S. Pay TV declined.", retained_claims=claims
    ) == ["U.S. Pay TV declined."]
    with pytest.raises(AppError):
        contract.resolve_soft_copy_public_text_partition(
            text="U.S. Pay TV declined.",
            retained_claims=claims,
            require_all_retained=True,
        )


def test_retained_hashes_do_not_match_inside_a_unicode_token():
    whole = build(
        "CaféPay rose.",
        [
            {
                "claim": "CaféPay rose.",
                "classification": "interpretive",
                "evidence_ids": [],
            }
        ],
    )
    sibling = build(
        "Pay", [{"claim": "Pay", "classification": "interpretive", "evidence_ids": []}]
    )
    assert contract.resolve_soft_copy_public_text_partition(
        text="CaféPay rose.", retained_claims=whole + sibling
    ) == ["CaféPay rose."]


def test_artifact_assembly_retains_atomic_claim_hashes():
    from src.generators._artifact_generator.storage import (
        _soft_copy_claim_provenance_payload,
    )

    payload = _soft_copy_claim_provenance_payload(
        summary={},
        expert_comment=TEXT,
        linkedin_post="",
        doc_map={},
        evidence_packs={},
        bindings={"expert_comment": BINDINGS},
        prompt_identities={},
        generation_attempts={},
        existing_provenance=None,
        replaced_families=[],
        replaced_claim_ids={},
        repair_texts={},
        repair_lineage={},
        regeneration_attempt=0,
    )
    assert [item["text_hash"] for item in payload["claims"]] == [
        contract.soft_copy_sentence_hash(b["claim"]) for b in BINDINGS
    ]


def test_full_assembly_keeps_capitalized_initialism_atomic():
    from tests._test_soft_copy_claim_provenance._split_support_test_soft_copy_claim_provenance import (  # noqa: E501
        _assemble_soft_copy,
    )

    artifact = _assemble_soft_copy(
        expert_comment=TEXT, soft_copy_claim_bindings={"expert_comment": BINDINGS}
    )
    assert artifact["expert_comment"] == TEXT
    claims = contract.soft_copy_claim_provenance_from_payload(
        artifact["soft_copy_claim_provenance"]
    )
    assert contract.resolve_soft_copy_public_text_partition(
        text=TEXT,
        retained_claims=[
            claim for claim in claims if claim.artifact_family == "expert_comment"
        ],
    ) == [binding["claim"] for binding in BINDINGS]


def test_full_summary_assembly_keeps_capitalized_initialism_atomic():
    from tests._test_soft_copy_claim_provenance._split_support_test_soft_copy_claim_provenance import (  # noqa: E501
        _assemble_soft_copy,
    )

    summary = {
        "tldr": TEXT,
        "card_tldr_compact": TEXT,
        "executive_summary": TEXT,
        "claim_evidence_map": [],
    }
    artifact = _assemble_soft_copy(
        summary=summary, soft_copy_claim_bindings={"summary": BINDINGS}
    )
    assert artifact["summary"]["tldr"] == TEXT
    claims = contract.soft_copy_claim_provenance_from_payload(
        artifact["soft_copy_claim_provenance"]
    )
    assert contract.resolve_soft_copy_public_text_partition(
        text=TEXT,
        retained_claims=[
            claim for claim in claims if claim.artifact_family == "summary"
        ],
    ) == [binding["claim"] for binding in BINDINGS]


def test_final_artifact_rebuild_uses_retained_atomic_boundaries():
    from src.generators._artifact_generator.storage import (
        _rebuild_final_soft_copy_claim_provenance,
    )

    claims = build()
    artifacts = {
        "summary": {},
        "expert_comment": TEXT,
        "linkedin_post": "",
        "soft_copy_claim_provenance": contract.soft_copy_claim_provenance_to_payload(
            claims
        ),
    }
    _rebuild_final_soft_copy_claim_provenance(artifacts=artifacts, promoted_baseline={})
    assert [
        item["text_hash"] for item in artifacts["soft_copy_claim_provenance"]["claims"]
    ] == [claim.text_hash for claim in claims]
