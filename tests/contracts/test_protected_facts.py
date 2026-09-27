from __future__ import annotations

import pytest

from src.contracts.protected_facts import (
    PROTECTED_FACT_DIMENSIONS,
    ProtectedFactComparison,
    compare_protected_fact_texts,
)


def test_protected_fact_comparison_keeps_missing_dimensions_unknown() -> None:
    comparison = ProtectedFactComparison.from_payload(
        {
            "value": {
                "claim_value": "52%",
                "evidence_value": "52%",
                "status": "compatible",
            }
        }
    )

    assert comparison.dimension("value").status == "compatible"
    assert comparison.dimension("timeframe").status == "unknown"
    assert comparison.dimension("timeframe").claim_value is None
    assert comparison.dimension("timeframe").evidence_value is None


def test_protected_fact_comparison_does_not_mark_a_missing_value_compatible() -> None:
    comparison = ProtectedFactComparison.from_payload(
        {
            "timeframe": {
                "claim_value": "2026",
                "evidence_value": None,
                "status": "compatible",
            }
        }
    )

    assert comparison.dimension("timeframe").status == "unknown"


def test_single_explicit_numeric_mismatch_remains_incompatible() -> None:
    comparison = compare_protected_fact_texts(
        "Digital advertising grew 28%.", "Digital advertising grew 18%."
    )

    assert comparison.dimension("value").status == "incompatible"
    assert comparison.dimension("unit_currency").status == "compatible"


@pytest.mark.parametrize("dimension", PROTECTED_FACT_DIMENSIONS)
def test_protected_fact_comparison_preserves_each_incompatible_dimension(
    dimension: str,
) -> None:
    comparison = ProtectedFactComparison.from_payload(
        {
            dimension: {
                "claim_value": "claim literal",
                "evidence_value": "evidence literal",
                "status": "incompatible",
            }
        }
    )

    assert comparison.incompatible_dimensions == (dimension,)


def test_protected_fact_comparison_preserves_combined_incompatibilities() -> None:
    comparison = ProtectedFactComparison.from_payload(
        {
            "population": {
                "claim_value": "companies",
                "evidence_value": "respondents",
                "status": "incompatible",
            },
            "observation_status": {
                "claim_value": "observed",
                "evidence_value": "forecast",
                "status": "incompatible",
            },
        },
        proposition_status="incompatible",
    )

    assert comparison.proposition_status == "incompatible"
    assert comparison.incompatible_dimensions == (
        "factual_proposition",
        "population",
        "observation_status",
    )


def test_protected_direction_matches_the_relevant_fact_in_mixed_evidence() -> None:
    comparison = compare_protected_fact_texts(
        "Installs fell 6%.",
        "Revenue grew 9%. Installs fell 6%. Retention declined 2%.",
    )

    assert comparison.dimension("direction").status == "compatible"


def test_protected_direction_rejects_an_explicit_inversion() -> None:
    comparison = compare_protected_fact_texts("Installs grew 6%.", "Installs fell 6%.")

    assert comparison.dimension("direction").status == "incompatible"


def test_protected_direction_does_not_read_growth_noun_as_direction() -> None:
    comparison = compare_protected_fact_texts(
        "Revenue growth declined 18%.", "Revenue growth increased 18%."
    )

    assert comparison.dimension("direction").status == "incompatible"


@pytest.mark.parametrize(
    ("claim", "evidence"),
    [
        ("U.S. adoption grew 10%.", "United States adoption grew 10%."),
        ("US adoption grew 10%.", "U.S. adoption grew 10%."),
        ("U.K. adoption grew 10%.", "United Kingdom adoption grew 10%."),
        ("UK adoption grew 10%.", "U.K. adoption grew 10%."),
    ],
)
def test_protected_geography_accepts_only_canonical_country_aliases(
    claim: str, evidence: str
) -> None:
    comparison = compare_protected_fact_texts(claim, evidence)

    assert comparison.dimension("geography").status == "compatible"


def test_protected_comparison_rejects_different_explicit_year_baselines() -> None:
    comparison = compare_protected_fact_texts(
        "Revenue grew 18% compared with 2024.",
        "Revenue grew 18% compared with 2023.",
    )

    assert comparison.dimension("comparison").status == "incompatible"


def test_protected_comparison_leaves_ambiguous_baseline_wording_unknown() -> None:
    comparison = compare_protected_fact_texts(
        "Revenue grew 18% compared with 2024.",
        "Revenue grew 18% compared with the prior year.",
    )

    assert comparison.dimension("comparison").status == "unknown"
