from __future__ import annotations

import hashlib

from src.generators.claim_validation_generator import (
    exclude_untrusted_evidence,
    validate_evidence_fidelity,
    validate_retained_claims,
)


def _evidence() -> dict:
    return {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": (
                        "Wallet adoption reached 42% in Global enterprise merchants in "
                        "2026."
                    ),
                    "page": 4,
                },
                {"id": "q1", "text": "Wallets are now core checkout infrastructure."},
            ]
        }
    }


def _soft_copy_claim(
    *,
    artifact_family: str,
    text: str,
    classification: str,
    evidence_ids: list[str],
    text_hash: str = "",
) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_family": artifact_family,
        "claim_id": f"soft_copy:{artifact_family}:{len(text)}",
        "text_hash": text_hash or hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "classification": classification,
        "evidence_ids": evidence_ids,
        "source_spans": [],
        "producing_prompt_identity": {"namespace": f"test/{artifact_family}"},
        "generation_attempt": 1,
        "regeneration_attempt": 0,
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


def test_evidence_fidelity_rejects_a_generated_finding_with_the_wrong_number() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Digital advertising grew 28% in 2025.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.readiness_status == "not_publishable"
    assert package.unsupported_factual_count == 1
    assert package.results[0].status == "unsupported"
    assert any(
        check.reason == "quantity_not_entailed" for check in package.results[0].checks
    )


def test_evidence_fidelity_excludes_an_unsupported_finding_from_editorial_input() -> (
    None
):
    packs = {"findings": {"findings": [{"id": "f1", "text": "Demand grew 28%."}]}}
    package = validate_evidence_fidelity(
        packs,
        source_spans=[{"id": "source:1", "text": "Demand grew 18%."}],
    )

    trusted = exclude_untrusted_evidence(packs, package)

    assert trusted["findings"]["findings"] == []


def test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_period() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Digital advertising grew 18% in 2026.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.results[0].status == "unsupported"
    assert any(
        check.reason == "protected_fact_timeframe_incompatible"
        for check in package.results[0].checks
    )


def test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_geography() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Advertising grew 18% in Asia in 2025.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Advertising grew 18% in Europe in 2025.",
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.results[0].status == "unsupported"
    assert any(
        check.reason == "protected_fact_geography_incompatible"
        for check in package.results[0].checks
    )


def test_evidence_fidelity_rejects_wrong_unit_and_recovers_exact_page_provenance() -> (
    None
):
    wrong_unit = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [{"id": "f1", "text": "Revenue reached $18m.", "page": 4}]
            }
        },
        source_spans=[
            {"id": "source:page:4", "page": 4, "text": "Revenue reached 18%."}
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )
    recovered_page = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f2", "text": "Revenue reached 18%."}]}},
        source_spans=[
            {"id": "source:page:4", "page": 4, "text": "Revenue reached 18%."}
        ],
    )

    assert wrong_unit.results[0].status == "unsupported"
    assert any(
        check.reason == "protected_fact_unit_currency_incompatible"
        for check in wrong_unit.results[0].checks
    )
    assert recovered_page.results[0].status == "supported"
    assert recovered_page.results[0].candidate.evidence_references[0].page == 4


def test_evidence_fidelity_recovers_page_provenance_from_exact_source_text() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Advertising grew 18% in 2025.",
                        "evidence": "Advertising grew 18% in 2025.",
                    }
                ]
            }
        },
        source_spans=[
            {"id": "source:page:3", "page": 3, "text": "Other text."},
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Advertising grew 18% in 2025.",
            },
        ],
    )

    assert package.results[0].status == "supported"
    assert package.results[0].candidate.evidence_references[0].page == 4


def test_evidence_fidelity_does_not_treat_explanatory_evidence_as_the_claim() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Digital advertising grew 18% in 2025.",
                        "evidence": (
                            "The report says search advertising grew 18% in 2025."
                        ),
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
    )

    assert package.results[0].status == "supported"
    assert not any(
        check.reason == "protected_fact_population_incompatible"
        for check in package.results[0].checks
    )


def test_evidence_fidelity_accepts_an_implicit_count_on_the_matched_page() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "All 30 covered markets grew in 2025.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": (
                    "Every one of the 30 markets covered in this report grew in 2025."
                ),
            }
        ],
    )

    assert package.results[0].status == "supported"


def test_evidence_fidelity_ignores_a_rhetorical_growth_subject_prefix() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": (
                            "Video and Social were major growth engines: total video "
                            "advertising grew 19.6%."
                        ),
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Total video advertising grew 19.6%.",
            }
        ],
    )

    assert package.results[0].status == "supported"


def test_evidence_fidelity_accepts_a_subject_stated_after_another_growth_fact() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Central European markets grew more than 20% in 2025.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": (
                    "Video advertising grew 19.6%. At the same time, Central European "
                    "markets grew more than 20% in 2025."
                ),
            }
        ],
    )

    assert package.results[0].status == "supported"


def test_evidence_fidelity_accepts_equivalent_counted_market_subjects() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "All 30 covered markets grew in 2025.",
                        "pages": [4],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": (
                    "Every one of the 30 markets covered in this report grew in 2025."
                ),
            }
        ],
    )

    assert package.results[0].status == "supported"


def test_evidence_fidelity_does_not_recover_a_page_from_a_common_year_alone() -> None:
    package = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Revenue grew in 2025."}]}},
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "An unrelated event happened in 2025.",
            }
        ],
    )

    assert package.results[0].status == "unsupported"
    assert package.results[0].candidate.evidence_references == []


def test_evidence_fidelity_rejects_subject_rank_and_comparison_inversions() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "subject",
                        "text": "Retail media grew 18% compared with 2024.",
                    },
                    {"id": "rank", "text": "Retail media was first in 2025."},
                ]
            }
        },
        source_spans=[
            {
                "id": "source:1",
                "text": (
                    "Search advertising grew 18% compared with 2023. Retail media was "
                    "second in 2025."
                ),
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    reasons = {reason for result in package.results for reason in result.reasons}
    assert "protected_fact_population_incompatible" in reasons
    assert "protected_fact_comparison_incompatible" in reasons
    assert "protected_fact_observation_status_incompatible" in reasons


def test_evidence_fidelity_rejects_direction_and_attribution_inversions() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "direction",
                        "text": "IAB reported advertising declined 18% in 2025.",
                    },
                    {
                        "id": "attribution",
                        "text": "WFA reported advertising grew 18% in 2025.",
                    },
                ]
            }
        },
        source_spans=[
            {
                "id": "source:1",
                "text": "IAB reported advertising grew 18% in 2025.",
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert {result.status for result in package.results} == {"unsupported"}
    reasons = {reason for result in package.results for reason in result.reasons}
    assert "protected_fact_direction_incompatible" in reasons
    assert "protected_fact_attribution_incompatible" in reasons


def test_evidence_fidelity_accepts_a_numeric_paraphrase_without_semantic_call() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {"id": "f1", "text": "Advertising increased by 18% during 2025."}
                ]
            }
        },
        source_spans=[{"id": "source:1", "text": "Advertising grew 18% in 2025."}],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.results[0].status == "supported"
    assert package.semantic_validation_count == 0


def test_evidence_fidelity_rejects_an_exact_value_provided_only_as_a_bound() -> None:
    package = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Advertising grew 52%."}]}},
        source_spans=[{"id": "source:1", "text": "Advertising grew more than 20%."}],
    )

    assert package.results[0].status == "unsupported"
    assert "quantity_not_entailed" in package.results[0].reasons


def test_evidence_fidelity_semantics_for_unresolved_descriptions() -> None:
    calls = []

    def semantic(candidate, sources):
        calls.append((candidate.claim_id, sources))
        return True, "semantic_supported", "semantic-execution"

    package = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Advertising is maturing."}]}},
        source_spans=[
            {"id": "source:1", "text": "Advertising has become an established channel."}
        ],
        semantic_validator=semantic,
    )

    assert package.results[0].status == "supported"
    assert len(calls) == 1
    assert package.semantic_execution_identities == ["semantic-execution"]


def test_evidence_fidelity_rejects_fabricated_quote_and_missing_provenance() -> None:
    fabricated = validate_evidence_fidelity(
        {
            "quote_candidates": {
                "quote_candidates": [{"id": "q1", "text": '"Fabricated quote."'}]
            }
        },
        source_spans=[{"id": "source:1", "text": "A real source sentence."}],
    )
    missing = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Advertising grew 18%."}]}},
        source_spans=[],
    )

    assert fabricated.results[0].status == "unsupported"
    assert missing.results[0].status != "supported"


def test_evidence_fidelity_accepts_a_normalized_quote_and_keeps_unknown_unknown() -> (
    None
):
    quote = validate_evidence_fidelity(
        {
            "quote_candidates": {
                "quote_candidates": [
                    {"id": "q1", "text": '"Payments are now core infrastructure."'}
                ]
            }
        },
        source_spans=[
            {"id": "source:1", "text": "Payments are now core infrastructure."}
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )
    unknown = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Advertising grew 18%."}]}},
        source_spans=[{"id": "source:1", "text": "Advertising grew 18%."}],
    )

    assert quote.results[0].status == "supported"
    assert quote.semantic_validation_count == 0
    assert unknown.results[0].protected_facts is not None
    assert unknown.results[0].protected_facts.dimension("timeframe").status == "unknown"


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
