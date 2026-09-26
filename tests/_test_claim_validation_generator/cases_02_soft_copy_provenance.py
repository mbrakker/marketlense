# ruff: noqa: F401,F403,F405
from __future__ import annotations

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
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.readiness_status == "awaiting_review"
    assert package.unsupported_factual_count == 0
    assert {result.candidate.source_family for result in package.results} == {
        "summary",
        "expert_comment",
        "linkedin_post",
    }


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
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.readiness_status == "not_publishable"
    assert any(
        check.reason == "quantity_not_entailed" for check in package.results[0].checks
    )


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
    )

    assert package.readiness_status == "not_publishable"
    assert any(
        check.reason == "protected_fact_timeframe_incompatible"
        for check in package.results[0].checks
    )


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

    assert package.readiness_status == "awaiting_review"
    assert package.unsupported_factual_count == 0
    assert package.results[0].candidate.kind == "interpretive"
    assert package.results[0].candidate.factual is False


def test_retained_claim_validation_does_not_downgrade_declared_factual_copy() -> None:
    claim = "Leaders should treat wallets as core checkout infrastructure."
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
        semantic_validator=lambda *_: (True, "semantic_supported", "semantic-1"),
    )

    assert package.readiness_status == "awaiting_review"
    assert package.results[0].candidate.kind == "interpretive"
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
