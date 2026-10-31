# ruff: noqa: F401,F403,F405
from __future__ import annotations

import pytest

from ._shared import *  # noqa: F401,F403


def test_retained_claim_validation_uses_soft_copy_factual_provenance() -> None:
    expert_claim = "Wallet adoption reached 42% in 2026."
    linkedin_claim = '"Wallets are now core checkout infrastructure."'
    summary_claim = "Wallet adoption reached 42% in 2026."
    package = validate_retained_claims(
        {
            "summary": {"executive_summary": summary_claim},
            "expert_comment": expert_claim,
            "linkedin_post": linkedin_claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="summary",
                        text=summary_claim,
                        classification="factual",
                        evidence_ids=["f1"],
                    ),
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=expert_claim,
                        classification="factual",
                        evidence_ids=["f1"],
                    ),
                    _soft_copy_claim(
                        artifact_family="linkedin_post",
                        text=linkedin_claim,
                        classification="factual",
                        evidence_ids=["q1"],
                    ),
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=_semantic_batch_supported,
    )

    assert package.readiness_status == "awaiting_review"
    assert package.unsupported_factual_count == 0
    assert {result.candidate.source_family for result in package.results} == {
        "summary",
        "expert_comment",
        "linkedin_post",
    }


@pytest.mark.parametrize(
    ("family", "claim", "evidence"),
    [
        (
            "summary",
            "U.S. wallet adoption reached 42% in 2026.",
            "US wallet adoption reached 42% in 2026.",
        ),
        (
            "expert_comment",
            "U.K. wallet adoption reached 42% in 2026.",
            "United Kingdom wallet adoption reached 42% in 2026.",
        ),
        (
            "linkedin_post",
            "U.S. wallet adoption reached 42% in 2026.",
            "United States wallet adoption reached 42% in 2026.",
        ),
    ],
)
def test_retained_claim_validation_uses_canonical_abbreviation_sentence_grid(
    family: str, claim: str, evidence: str
) -> None:
    artifacts = {
        "summary": {"tldr": claim} if family == "summary" else {},
        **({family: claim} if family != "summary" else {}),
        "soft_copy_claim_provenance": {
            "schema_version": "1.0",
            "claims": [
                _soft_copy_claim(
                    artifact_family=family,
                    text=claim,
                    classification="factual",
                    evidence_ids=["f1"],
                )
            ],
        },
    }
    package = validate_retained_claims(
        artifacts,
        {
            "findings": {
                "findings": [{"id": "f1", "text": evidence, "evidence": evidence}]
            }
        },
        semantic_batch_validator=_semantic_batch_supported,
    )

    assert len(package.results) == 1
    assert package.results[0].status == "supported"


def test_retained_claim_validation_fails_closed_for_unknown_soft_copy_evidence() -> (
    None
):
    claim = "Wallet adoption reached 42% in 2026."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="factual",
                        evidence_ids=["unknown-evidence"],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].candidate.evidence_references[0].evidence_id == (
        "unknown-evidence"
    )


def test_retained_claim_validation_fails_closed_for_missing_soft_copy_evidence() -> (
    None
):
    claim = "Wallet adoption reached 42% in 2026."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="factual",
                        evidence_ids=[],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert "missing_evidence_reference" in package.results[0].reasons


def test_retained_claim_validation_rejects_invented_soft_copy_quantity() -> None:
    claim = "Wallet adoption reached 43% in 2026."
    package = validate_retained_claims(
        {
            "linkedin_post": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="linkedin_post",
                        text=claim,
                        classification="factual",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=_semantic_batch_contradicted,
    )

    assert package.readiness_status == "not_publishable"
    assert package.results[0].semantic_outcome == "contradicted"
    assert package.results[0].semantic_validator_used is True


def test_retained_claim_validation_rejects_soft_copy_protected_fact_mismatch() -> None:
    claim = "Wallet adoption reached 42% in 2025."
    package = validate_retained_claims(
        {
            "summary": {"tldr": claim},
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="summary",
                        text=claim,
                        classification="factual",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=lambda inputs: [
            ClaimSemanticGroundingResult(
                schema_version="1.0",
                outcome="entailed",
                reason="contradictory_timeframe_verdict",
                identity=_semantic_result(inputs[0]).identity,
                protected_facts=ProtectedFactComparison.from_payload(
                    {
                        "timeframe": {
                            "claim_value": "2025",
                            "evidence_value": "2026",
                            "status": "incompatible",
                        }
                    },
                    proposition_status="compatible",
                ),
            )
        ],
    )

    assert package.readiness_status == "not_publishable"
    assert package.results[0].status == "unresolved"
    assert (
        package.results[0].semantic_disagreement
        == "entailed_with_incompatible_protected_facts"
    )
    assert package.results[0].semantic_validator_used is True


def test_retained_claim_validation_keeps_soft_copy_interpretation_nonfactual() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="interpretive",
                        evidence_ids=[],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.unresolved_factual_count == 0
    assert package.results[0].candidate.kind == "descriptive"
    assert package.results[0].candidate.factual is True


def test_retained_claim_validation_does_not_trust_interpretive_numeric_repair() -> None:
    claim = "Wallet adoption reached 43% in 2026."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="interpretive",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 0
    assert package.unresolved_factual_count == 1
    assert package.results[0].candidate.factual is True


def test_supported_interpretive_numeric_repair_remains_groundable() -> None:
    claim = "Wallet adoption reached 42% in 2026."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="interpretive",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=_semantic_batch_supported,
    )

    assert package.readiness_status == "awaiting_review"
    assert package.unsupported_factual_count == 0
    assert package.unresolved_factual_count == 0
    assert package.results[0].candidate.factual is True


def test_recommendation_with_unsupported_causal_assertion_is_not_exempt() -> None:
    claim = "Leaders should expand wallets because wallets caused the lift."
    package = validate_retained_claims(
        {
            "linkedin_post": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="linkedin_post",
                        text=claim,
                        classification="recommendation",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unresolved_factual_count == 1
    assert package.results[0].candidate.factual is True


def test_retained_claim_validation_does_not_downgrade_declared_factual_copy() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
    from .cases_03_hybrid_grounding import _semantic_result

    package = validate_retained_claims(
        {
            "linkedin_post": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="linkedin_post",
                        text=claim,
                        classification="factual",
                        evidence_ids=["q1"],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=lambda claims: [
            _semantic_result(claims[0], "entailed")
        ],
    )

    assert package.readiness_status == "awaiting_review"
    assert package.results[0].candidate.kind == "descriptive"
    assert package.results[0].candidate.factual is True
    assert package.results[0].semantic_validator_used is True


def test_retained_claim_validation_rejects_partial_unknown_soft_copy_evidence() -> None:
    claim = "Wallet adoption reached 42% in 2026."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="factual",
                        evidence_ids=["f1", "unknown-evidence"],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert "unknown_evidence_reference" in package.results[0].reasons
    assert {
        reference.evidence_id
        for reference in package.results[0].candidate.evidence_references
    } == {
        "f1",
        "unknown-evidence",
    }


def test_retained_claim_validation_requires_current_soft_copy_provenance() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
    package = validate_retained_claims({"expert_comment": claim}, _evidence())

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].candidate.factual is True
    assert package.results[0].reasons == ["soft_copy_provenance_missing"]


def test_retained_claim_validation_rejects_malformed_soft_copy_provenance() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="unsupported",
                        evidence_ids=[],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].reasons == ["soft_copy_provenance_invalid"]


def test_retained_claim_validation_rejects_unbound_soft_copy_sentence() -> None:
    supported = "Wallet adoption reached 42% in 2026."
    unbound = "Leaders should treat wallets as core checkout infrastructure."
    package = validate_retained_claims(
        {
            "expert_comment": f"{supported} {unbound}",
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=supported,
                        classification="factual",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[1].reasons == ["soft_copy_provenance_sentence_missing"]


def test_retained_claim_validation_rejects_soft_copy_provenance_hash_mismatch() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="interpretive",
                        evidence_ids=[],
                        text_hash="a" * 64,
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].reasons == ["soft_copy_provenance_sentence_missing"]


def test_retained_claim_validation_rejects_ambiguous_soft_copy_provenance() -> None:
    claim = "Wallet adoption reached 42% in 2026."
    binding = _soft_copy_claim(
        artifact_family="expert_comment",
        text=claim,
        classification="factual",
        evidence_ids=["f1"],
    )
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [binding, dict(binding)],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].reasons == ["soft_copy_provenance_ambiguous"]


def test_recommendation_with_material_qualitative_premise_requires_evidence() -> None:
    claim = (
        "Retailers should reconsider marketplace investment because consumers are "
        "shifting toward direct purchasing."
    )
    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="recommendation",
                        evidence_ids=[],
                    )
                ],
            },
        },
        _evidence(),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].candidate.factual is True
    assert "missing_evidence_reference" in package.results[0].reasons


@pytest.mark.parametrize("family", ["summary", "expert_comment", "linkedin_post"])
def test_evidence_bound_qualitative_recommendation_reaches_semantic_grounding(
    family: str,
) -> None:
    premise = "Consumers are shifting toward direct purchasing."
    recommendation = "Retailers should reconsider marketplace investment."
    claim = f"{premise} {recommendation}"
    artifacts = {
        "summary": {"executive_summary": claim} if family == "summary" else {},
        **({family: claim} if family != "summary" else {}),
        "soft_copy_claim_provenance": {
            "schema_version": "1.0",
            "claims": [
                _soft_copy_claim(
                    artifact_family=family,
                    text=premise,
                    classification="recommendation",
                    evidence_ids=["f1"],
                ),
                _soft_copy_claim(
                    artifact_family=family,
                    text=recommendation,
                    classification="recommendation",
                    evidence_ids=["f1"],
                ),
            ],
        },
    }
    semantic_calls = []

    def semantic_batch(claims):
        semantic_calls.append(claims)
        from .cases_03_hybrid_grounding import _semantic_result

        return [_semantic_result(item, "not_established") for item in claims]

    package = validate_retained_claims(
        artifacts,
        _evidence(),
        semantic_batch_validator=semantic_batch,
    )

    assert len(semantic_calls) == 1
    assert len(semantic_calls[0]) == 2
    assert {item.candidate.text for item in semantic_calls[0]} == {
        premise,
        recommendation,
    }
    assert all(item.candidate.factual is True for item in semantic_calls[0])
    assert package.results[0].semantic_validator_used is True
    assert package.results[0].status == "unresolved"
    assert package.results[1].candidate.text == recommendation
    assert package.results[1].candidate.factual is True
    assert package.results[1].semantic_validator_used is True
    assert package.results[1].status == "unresolved"
    assert package.unresolved_factual_count == 2
    assert package.readiness_status == "not_publishable"


def test_evidence_bound_pure_normative_recommendation_remains_nonfactual() -> None:
    claim = "Retailers should reconsider marketplace investment."
    calls = []

    def semantic_batch(claims):
        calls.append(True)
        return _semantic_batch_supported(claims)

    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="recommendation",
                        evidence_ids=["f1"],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=semantic_batch,
    )

    assert calls == [True]
    assert package.results[0].candidate.factual is True
    assert package.results[0].semantic_validator_used is True
    assert package.readiness_status == "awaiting_review"


def test_evidence_independent_normative_recommendation_remains_nonfactual() -> None:
    claim = "Retailers should reconsider marketplace investment."
    calls = []

    def semantic_batch(_claims):
        calls.append(True)
        raise AssertionError("evidence-independent recommendation was grounded")

    package = validate_retained_claims(
        {
            "expert_comment": claim,
            "soft_copy_claim_provenance": {
                "schema_version": "1.0",
                "claims": [
                    _soft_copy_claim(
                        artifact_family="expert_comment",
                        text=claim,
                        classification="recommendation",
                        evidence_ids=[],
                    )
                ],
            },
        },
        _evidence(),
        semantic_batch_validator=semantic_batch,
    )

    assert calls == []
    assert package.results[0].candidate.factual is True
    assert package.results[0].status == "unsupported"
    assert package.readiness_status == "not_publishable"
