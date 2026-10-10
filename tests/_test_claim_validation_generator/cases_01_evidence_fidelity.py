# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_retained_claim_validation_indexes_legacy_finding_excerpt() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {"claim": "Revenue grew by 12%.", "evidence_id": "f1"}
                ]
            }
        },
        {"findings": {"findings": [{"id": "f1", "excerpt": "Revenue grew by 12%."}]}},
    )

    assert package.results[0].status == "supported"


def test_retained_claim_validation_indexes_doc_map_section_key_points() -> None:
    claim = "Adjust data covers the top 5,000 apps."
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
                        evidence_ids=["methodology"],
                    )
                ],
            },
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "methodology",
                        "title": "Methodology",
                        "summary": "The report describes the analysis scope.",
                        "key_points": ["Adjust data covers the top 5,000 apps."],
                    }
                ]
            }
        },
    )

    assert package.results[0].status == "supported"
    assert package.semantic_validation_count == 0


def test_key_figure_claim_includes_its_canonical_display_value() -> None:
    package = validate_retained_claims(
        {
            "key_figures": [
                {
                    "figure_id": "survey-coverage",
                    "figure": "1,200+ merchants",
                    "label": "Annual survey respondent count",
                    "unit": "merchants",
                    "evidence_id": "survey-basis",
                }
            ]
        },
        {
            "findings": {
                "findings": [
                    {
                        "id": "survey-basis",
                        "text": "The annual survey included 1,200+ merchants.",
                    }
                ]
            }
        },
    )

    result = package.results[0]
    assert result.candidate.claim_id == "key_figure:survey-coverage:figure"
    assert "1,200+ merchants" in result.candidate.text
    assert result.status == "supported"


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
        semantic_batch_validator=lambda *_: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
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


def test_evidence_fidelity_treats_year_over_year_endpoint_as_timeframe() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Across 2025 year over year, adoption grew 10%.",
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
                    "Adoption grew 10% over YoY 2024-2025, while average session "
                    "length was 4 minutes."
                ),
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.results[0].status == "supported"


def test_evidence_fidelity_rejects_wrong_year_over_year_endpoint() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Across 2026 year over year, adoption grew 10%.",
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
                    "Adoption grew 10% over YoY 2024-2025, while average session "
                    "length was 4 minutes."
                ),
            }
        ],
        semantic_validator=lambda *_: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert package.results[0].status == "unsupported"
    assert any(
        check.reason == "protected_fact_timeframe_incompatible"
        for check in package.results[0].checks
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


def test_evidence_fidelity_uses_exact_excerpt_when_reported_page_is_printed_page() -> (
    None
):
    excerpt = (
        "Among survey respondents, confidence in journalism prospects was 38% in 2026."
    )
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": excerpt,
                        "evidence": excerpt,
                        "pages": [3],
                    }
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:3",
                "page": 3,
                "text": "Contents\n1. Pressures on Journalism Mount\n2. Answer Engines",
            },
            {"id": "source:page:5", "page": 5, "text": excerpt},
        ],
    )

    assert package.results[0].candidate.evidence_references[0].page == 5
    assert package.results[0].status == "supported"


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


def test_evidence_fidelity_batches_identical_evidence_and_fails_closed() -> None:
    calls = []
    page_two = "Advertising has become an established channel."
    page_three = page_two

    def semantic_batch(candidates, sources):
        claim_ids = [candidate.claim_id for candidate in candidates]
        calls.append((claim_ids, sources))
        if claim_ids == ["evidence:findings:f1", "evidence:findings:f2"]:
            return {
                claim_ids[1]: (False, "semantic_unsupported", "semantic-batch-1"),
                claim_ids[0]: (True, "semantic_supported", "semantic-batch-1"),
            }
        return {}

    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Advertising is an established channel.",
                        "page": 2,
                    },
                    {
                        "id": "f2",
                        "text": "Advertising is a mature channel.",
                        "page": 2,
                    },
                    {
                        "id": "f3",
                        "text": "Retailers are changing checkout systems.",
                        "page": 3,
                    },
                ]
            }
        },
        source_spans=[
            {"id": "source:page:2", "page": 2, "text": page_two},
            {"id": "source:page:3", "page": 3, "text": page_three},
        ],
        semantic_batch_validator=semantic_batch,
    )

    by_id = {result.candidate.claim_id: result for result in package.results}
    assert len(calls) == 2
    assert calls[0] == (
        ["evidence:findings:f1", "evidence:findings:f2"],
        [page_two],
    )
    assert calls[1] == (["evidence:findings:f3"], [page_three])
    assert by_id["evidence:findings:f1"].status == "supported"
    assert by_id["evidence:findings:f2"].status == "unsupported"
    assert by_id["evidence:findings:f3"].status == "unsupported"
    assert by_id["evidence:findings:f3"].reasons == ["semantic_support_not_established"]
    assert package.semantic_validation_count == 3
    assert package.semantic_execution_identities == ["semantic-batch-1"]


def test_evidence_fidelity_marks_malformed_semantic_batch_unsupported() -> None:
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Advertising is an established channel.",
                        "page": 2,
                    },
                    {
                        "id": "f2",
                        "text": "Advertising is a mature channel.",
                        "page": 2,
                    },
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:2",
                "page": 2,
                "text": "Advertising has become an established channel.",
            }
        ],
        semantic_batch_validator=lambda *_: ["malformed"],  # type: ignore[arg-type]
    )

    assert all(result.status == "unsupported" for result in package.results)
    assert all(result.semantic_validator_used for result in package.results)
    assert package.semantic_validation_count == 2
    assert package.unsupported_factual_count == 2


def test_evidence_fidelity_duplicate_ids_fail_closed_without_call() -> None:
    calls = []

    def semantic_batch(candidates, sources):
        calls.append((candidates, sources))
        return {
            candidate.claim_id: (True, "semantic_supported", "semantic-batch")
            for candidate in candidates
        }

    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "duplicate",
                        "text": "Advertising is an established channel.",
                        "page": 2,
                    },
                    {
                        "id": "duplicate",
                        "text": "Advertising is a mature channel.",
                        "page": 2,
                    },
                ]
            }
        },
        source_spans=[
            {
                "id": "source:page:2",
                "page": 2,
                "text": "Advertising has become an established channel.",
            }
        ],
        semantic_batch_validator=semantic_batch,
    )

    assert calls == []
    assert len(package.results) == 2
    assert all(result.status == "unsupported" for result in package.results)
    assert all(
        result.reasons == ["semantic_claim_identity_ambiguous"]
        for result in package.results
    )
    assert package.semantic_validation_count == 0


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
        semantic_batch_validator=lambda *_: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
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
