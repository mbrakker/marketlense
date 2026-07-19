from __future__ import annotations

from src.generators.claim_validation_generator import validate_retained_claims


def _evidence() -> dict:
    return {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Wallet adoption reached 42% in Global enterprise merchants in 2026.",
                    "page": 4,
                },
                {"id": "q1", "text": "Wallets are now core checkout infrastructure."},
            ]
        }
    }


def test_numeric_and_quote_claims_pass_without_semantic_call() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Wallet adoption reached 42% in 2026.",
                        "evidence_id": "f1",
                    }
                ]
            },
            "quotes_final": [
                {
                    "text": '"Wallets are now core checkout infrastructure."',
                    "evidence_id": "q1",
                }
            ],
        },
        _evidence(),
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.readiness_status == "awaiting_review"
    assert package.semantic_validation_count == 0
    assert package.unsupported_factual_count == 0


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
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.semantic_validation_count == 0


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

    def semantic(candidate, cited):
        calls.append((candidate.claim_id, cited))
        return True, "semantic_supported", "exec-identity"

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
        semantic_validator=semantic,
    )

    assert package.readiness_status == "awaiting_review"
    assert package.semantic_validation_count == 1
    assert len(calls) == 1
    assert package.semantic_execution_identities == ["exec-identity"]
