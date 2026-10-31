# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_changed_numeric_claim_blocks_readiness_without_model_call() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Wallet adoption reached 43% in 2026.",
                        "evidence_id": "f1",
                    }
                ]
            }
        },
        _evidence(),
        semantic_batch_validator=_semantic_batch_contradicted,
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.semantic_validation_count == 1


def test_claim_reference_order_tolerates_root_and_page_specific_duplicates() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Wallet adoption reached 42% in 2026.",
                        "evidence_id": "f1",
                        "evidence_spans": [{"evidence_id": "f1", "page": 4}],
                    }
                ]
            }
        },
        _evidence(),
    )

    assert [item.page for item in package.results[0].candidate.evidence_references] == [
        4,
        4,
    ]


def test_unresolved_descriptive_claim_is_the_only_kind_sent_to_semantic_boundary() -> (
    None
):
    calls = []

    from .cases_03_hybrid_grounding import _semantic_result

    def semantic(claims):
        calls.append(claims)
        return [_semantic_result(claim, "entailed") for claim in claims]

    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Wallet adoption is reshaping checkout strategy.",
                        "evidence_id": "f1",
                    }
                ]
            }
        },
        _evidence(),
        semantic_batch_validator=semantic,
    )

    assert package.readiness_status == "awaiting_review"
    assert package.semantic_validation_count == 1
    assert len(calls) == 1
    assert len(calls[0]) == 1
    assert package.semantic_execution_identities == ["execution-1"]
