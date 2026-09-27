from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.protected_facts import compare_protected_fact_texts
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.public_editorial_quality_generator import (
    _looks_fragmentary,
    _metric_label_relationship_explanation,
    evaluate_public_editorial_quality,
)
from src.utils.quantity import extract_quantities, quantities_match

_COHORT_FIXTURE = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "reliability_cohort_grounding_false_positives.json"
    ).read_text(encoding="utf-8")
)
_COHORT_CASES = _COHORT_FIXTURE["cases"]


def _cohort_cases(kind: str) -> list[dict[str, object]]:
    return [case for case in _COHORT_CASES if case["kind"] == kind]


def _quality_rule_ids(report) -> set[str]:
    return {issue.rule_id for issue in report.issues}


def _quality_artifacts(*, text: str, evidence: str) -> dict:
    return {
        "insights_final": [
            {
                "id": "cohort-grounding-case",
                "text": text,
                "evidence_id": "cohort-evidence",
                "evidence": evidence,
                "metric": {},
                "pages": [1],
                "so_what": "The source should inform the next review.",
                "now_what": "Review the linked evidence before acting.",
            }
        ]
    }


def test_named_index_values_are_not_inferred_as_counts() -> None:
    attention = extract_quantities("EMEA Ad Attention Index 110")
    engagement = extract_quantities("EMEA Engagement Index 116")

    assert [(item.value, item.unit_family) for item in attention] == [(110, "index")]
    assert [(item.value, item.unit_family) for item in engagement] == [(116, "index")]


def test_spelled_out_percentages_ground_their_digit_forms() -> None:
    source = (
        "Seventy-nine percent read three or more reviews; "
        "eighty-four percent value authenticity; "
        "ninety-one percent want disclosure."
    )

    parsed = extract_quantities(source)

    assert [(item.value, item.unit_family) for item in parsed] == [
        (79, "percent"),
        (84, "percent"),
        (91, "percent"),
    ]


def test_report_and_pronoun_are_not_misread_as_attributed_sources() -> None:
    comparison = compare_protected_fact_texts(
        "The report presents engagement and voting as stewardship activities.",
        "The quarterly report presents engagement and voting as stewardship "
        "activities.",
    )

    assert comparison.dimension("attribution").status == "unknown"


def test_an_expectation_is_not_a_population_mismatch() -> None:
    comparison = compare_protected_fact_texts(
        "That is a stated expectation, not a reported increase in completed activity.",
        "Half of dealmakers expect carve-out activity to increase over the next "
        "12–24 months.",
    )

    assert comparison.dimension("population").status == "unknown"


def test_ordinal_words_in_party_type_do_not_become_observation_status() -> None:
    comparison = compare_protected_fact_texts(
        "The strategic choice concerns third-party measurement.",
        "The strategic choice concerns first-party measurement.",
    )

    assert comparison.dimension("observation_status").status == "unknown"


def test_edition_year_does_not_conflict_with_an_observation_period() -> None:
    comparison = compare_protected_fact_texts(
        "The 2026 edition reports data collected in 2025.",
        "Mobile app trends: 2026 edition. The analysis covers January 2024 to "
        "January 2026.",
    )

    assert comparison.dimension("timeframe").status != "incompatible"


def test_explicit_wrong_observation_year_remains_blocked() -> None:
    comparison = compare_protected_fact_texts(
        "Advertising grew 18% in 2026.", "Advertising grew 18% in 2025."
    )

    assert comparison.dimension("timeframe").status == "incompatible"


def test_independent_years_are_not_treated_as_a_continuous_range() -> None:
    comparison = compare_protected_fact_texts(
        "Consumer preference was measured in 2024.",
        "Consumer preference was measured in 2023 and 2025.",
    )

    assert comparison.dimension("timeframe").status == "incompatible"


def test_independently_linked_metrics_can_use_distinct_units() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "Average retailer spend reached $500, while 79% read "
                            "three or more reviews."
                        ),
                        "evidence_ids": ["spend", "reviews"],
                    }
                ]
            }
        },
        {
            "findings": {
                "findings": [
                    {"id": "spend", "text": "Average retailer spend reached $500."},
                    {
                        "id": "reviews",
                        "text": "Seventy-nine percent read three or more reviews.",
                    },
                ]
            }
        },
        semantic_batch_validator=lambda *_: (_ for _ in ()).throw(
            AssertionError("deterministic grounding should be sufficient")
        ),
    )

    assert package.results[0].status == "supported"


def test_independently_linked_metric_mutation_remains_blocked() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "Average retailer spend reached $500, while 80% read "
                            "three or more reviews."
                        ),
                        "evidence_ids": ["spend", "reviews"],
                    }
                ]
            }
        },
        {
            "findings": {
                "findings": [
                    {"id": "spend", "text": "Average retailer spend reached $500."},
                    {
                        "id": "reviews",
                        "text": "Seventy-nine percent read three or more reviews.",
                    },
                ]
            }
        },
    )

    assert package.results[0].status == "unsupported"
    assert "quantity_not_entailed" in package.results[0].reasons


def test_emplifi_linked_behavior_and_review_percentages_are_supported() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "For purchases over $/£500, more than half of consumers "
                            "visit at least three websites and spend over an hour "
                            "researching; separately, 79% of consumers read three or "
                            "more reviews before buying."
                        ),
                        "evidence_ids": ["high-value", "reviews"],
                    }
                ]
            }
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "high-value",
                        "title": "High value research",
                        "summary": (
                            "For purchases over $/£500, more than half of consumers "
                            "visit three or more websites and spend over an hour "
                            "researching."
                        ),
                    },
                    {
                        "id": "reviews",
                        "title": "Reviews",
                        "summary": (
                            "Seventy-nine percent of consumers read three or more "
                            "reviews before buying."
                        ),
                    },
                ]
            }
        },
    )

    assert package.results[0].status == "supported"


def test_emplifi_multi_evidence_wrong_percent_remains_blocked() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "91% of consumers expect AI disclosure while 85% say "
                            "service interactions should feel authentic."
                        ),
                        "evidence_ids": ["disclosure", "authenticity"],
                    }
                ]
            }
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "disclosure",
                        "title": "AI disclosure",
                        "summary": (
                            "Ninety-one percent expect brands to disclose AI use."
                        ),
                    },
                    {
                        "id": "authenticity",
                        "title": "Authenticity",
                        "summary": (
                            "Eighty-four percent say service interactions should "
                            "feel authentic."
                        ),
                    },
                ]
            }
        },
    )

    assert package.results[0].status == "unsupported"
    assert "quantity_not_entailed" in package.results[0].reasons


def test_quote_validation_matches_an_exact_quoted_span_in_a_paraphrase() -> None:
    package = validate_retained_claims(
        {
            "quotes_final": [
                {
                    "text": (
                        "The recommendation calls for an ‘asset-light’ operating "
                        "model to support partnership-led growth."
                    ),
                    "evidence_id": "strategy",
                }
            ]
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "strategy",
                        "title": "Strategy",
                        "summary": (
                            "The company should follow an asset-light model and "
                            "build partnerships."
                        ),
                    }
                ]
            }
        },
    )

    assert package.results[0].status == "supported"


def test_quote_validation_still_rejects_a_fabricated_quoted_span() -> None:
    package = validate_retained_claims(
        {
            "quotes_final": [
                {
                    "text": "The recommendation calls for a ‘guaranteed’ "
                    "operating model.",
                    "evidence_id": "strategy",
                }
            ]
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "strategy",
                        "title": "Strategy",
                        "summary": "The company should follow an asset-light model.",
                    }
                ]
            }
        },
    )

    assert package.results[0].status == "unsupported"
    assert "quote_not_matched" in package.results[0].reasons


def test_complete_short_sentence_is_not_a_fragment() -> None:
    assert not _looks_fragmentary("Scope matters.")


def test_incomplete_short_clause_remains_fragmentary() -> None:
    assert _looks_fragmentary("Scope for")


def test_explicit_combined_category_accepts_the_rounded_sum() -> None:
    evidence = "Display accounts for 45.85% of spend; CTV accounts for 30.83%."

    assert (
        _metric_label_relationship_explanation(
            "Display and CTV together account for 77% of spend.", evidence
        )
        == ""
    )


def test_combined_category_rejects_a_value_outside_the_rounded_sum() -> None:
    evidence = "Display accounts for 45.85% of spend; CTV accounts for 30.83%."

    assert _metric_label_relationship_explanation(
        "Display and CTV together account for 78% of spend.", evidence
    )


def test_combined_category_rejects_partial_match_with_three_labels() -> None:
    evidence = (
        "Display accounts for 45.85% of spend; CTV accounts for 30.83%; "
        "Search accounts for 14.17%."
    )

    assert _metric_label_relationship_explanation(
        "Display, CTV and Search together account for 45% of spend.", evidence
    )


@pytest.mark.parametrize(
    "case", _cohort_cases("quantity"), ids=lambda case: str(case["case_id"])
)
def test_frozen_cohort_quantity_cases_retain_exact_units(
    case: dict[str, object],
) -> None:
    claim_quantities = extract_quantities(str(case["claim"]))
    evidence_quantities = extract_quantities(str(case["evidence"]))

    assert claim_quantities
    assert any(
        candidate.unit_family == case["expected_unit_family"]
        and any(
            quantities_match(candidate, evidence) for evidence in evidence_quantities
        )
        for candidate in claim_quantities
    )


@pytest.mark.parametrize(
    "case", _cohort_cases("protected"), ids=lambda case: str(case["case_id"])
)
def test_frozen_cohort_protected_fact_cases_stay_unknown(
    case: dict[str, object],
) -> None:
    comparison = compare_protected_fact_texts(str(case["claim"]), str(case["evidence"]))

    assert comparison.dimension(str(case["dimension"])).status == "unknown"


@pytest.mark.parametrize(
    "case", _cohort_cases("quote"), ids=lambda case: str(case["case_id"])
)
def test_frozen_cohort_quoted_spans_are_matched_without_accepting_paraphrase(
    case: dict[str, object],
) -> None:
    package = validate_retained_claims(
        {"quotes_final": [{"text": case["claim"], "evidence_id": case["case_id"]}]},
        {"findings": {"findings": [{"id": case["case_id"], "text": case["evidence"]}]}},
    )

    assert package.results[0].status == "supported"


def test_frozen_cohort_combined_category_fixture_accepts_only_rounded_sum() -> None:
    case = next(case for case in _cohort_cases("combined_category"))

    assert (
        _metric_label_relationship_explanation(
            str(case["claim"]), str(case["evidence"])
        )
        == ""
    )
    report = evaluate_public_editorial_quality(
        report_id="stackadapt-combined-share",
        artifacts=_quality_artifacts(
            text=str(case["claim"]), evidence=str(case["evidence"])
        ),
    )
    mutated_report = evaluate_public_editorial_quality(
        report_id="stackadapt-combined-share",
        artifacts=_quality_artifacts(
            text=str(case["claim"]).replace("77%", "78%"),
            evidence=str(case["evidence"]),
        ),
    )

    assert (
        "public_editorial_quality.metric_label_relationship"
        not in _quality_rule_ids(report)
    )
    assert "public_editorial_quality.metric_label_relationship" in _quality_rule_ids(
        mutated_report
    )


def test_frozen_cohort_complete_sentence_fixture_is_not_fragmentary() -> None:
    case = next(case for case in _cohort_cases("complete_sentence"))

    assert not _looks_fragmentary(str(case["claim"]))
    report = evaluate_public_editorial_quality(
        report_id="adjust-short-complete-sentence",
        artifacts={"linkedin_post": str(case["claim"])},
    )

    assert "public_editorial_quality.sentence_fragment" not in _quality_rule_ids(report)


def test_algolia_multi_evidence_links_ground_sample_and_distinct_percentages() -> None:
    claim = (
        "In the report's survey of 110 respondents, 42% said they were focusing "
        "on using AI to better understand user intent, up from 34% in 2024."
    )
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {"claim": claim, "evidence_ids": ["intent", "sample"]}
                ]
            }
        },
        {
            "findings": {
                "findings": [
                    {
                        "id": "intent",
                        "text": (
                            "Notably, 42% of respondents are focusing on using AI "
                            "to better understand user intent, up from 34% in 2024."
                        ),
                    },
                    {"id": "sample", "text": "Total n=110 respondents."},
                ]
            }
        },
        semantic_batch_validator=lambda *_: (_ for _ in ()).throw(
            AssertionError("linked numerical evidence should be sufficient")
        ),
    )

    assert package.results[0].status == "supported"


def test_algolia_multi_evidence_mutation_keeps_the_changed_percent_blocked() -> None:
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "42% of respondents were focusing on user intent, "
                            "up from 34% in 2024."
                        ),
                        "evidence_id": "intent",
                    }
                ]
            }
        },
        {
            "findings": {
                "findings": [
                    {
                        "id": "intent",
                        "text": "42% of respondents focused on user intent, "
                        "up from 34% in 2024.",
                    }
                ]
            }
        },
    )
    mutated = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": (
                            "43% of respondents were focusing on user intent, "
                            "up from 34% in 2024."
                        ),
                        "evidence_id": "intent",
                    }
                ]
            }
        },
        {
            "findings": {
                "findings": [
                    {
                        "id": "intent",
                        "text": "42% of respondents focused on user intent, "
                        "up from 34% in 2024.",
                    }
                ]
            }
        },
    )

    assert package.results[0].status == "supported"
    assert mutated.results[0].status == "unsupported"


def test_criteo_metric_year_does_not_conflict_with_unrelated_forecast_year() -> None:
    package = validate_retained_claims(
        {
            "insights_final": [
                {
                    "id": "incrementality",
                    "text": (
                        "50% of agency professionals said incrementality metrics "
                        "were pushing them toward retail media based on the November "
                        "2022 survey."
                    ),
                    "evidence_id": "section-3-new-concepts-in-measurement",
                }
            ]
        },
        {
            "doc_map": {
                "sections": [
                    {
                        "id": "section-3-new-concepts-in-measurement",
                        "title": "Section 3: New concepts in measurement",
                        "summary": (
                            "The section covers campaign measurement priorities."
                        ),
                        "key_points": [
                            "50% of agency professionals said incrementality "
                            "metrics were pushing them toward retail media.",
                            "US agencies estimate digital media campaign costs "
                            "will rise by 22% in 2023.",
                        ],
                        "pages": [7],
                    }
                ]
            }
        },
        semantic_batch_validator=lambda *_: (_ for _ in ()).throw(
            AssertionError("the linked metric is explicit")
        ),
    )

    assert package.results[0].status == "supported"


def test_cohort_claim_fixture_file_has_stable_source_identity_fields() -> None:
    assert _COHORT_FIXTURE["schema_version"] == "1.0"
    assert all(
        case.get("report")
        and case.get("claim_id")
        and case.get("rule_id")
        and case.get("source_page")
        and case.get("claim")
        and case.get("evidence")
        for case in _COHORT_CASES
    )
