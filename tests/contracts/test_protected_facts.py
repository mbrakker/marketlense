from __future__ import annotations

import pytest

from src.contracts.protected_facts import (
    PROTECTED_FACT_DIMENSIONS,
    ProtectedFactComparison,
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
