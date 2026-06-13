from __future__ import annotations

import pytest

from src.generators.report_card_projection import select_geometry_family
from src.utils.errors import AppError


CASES = (
    ("trend", "rising", "ascending_trajectory"),
    ("trend", "falling", "descending_trajectory"),
    ("trend", "volatile", "volatility_corridor"),
    ("comparison", "converging", "convergence_funnel"),
    ("comparison", "diverging", "divergence_fan"),
    ("comparison", "volatile", "parallel_bands"),
    ("comparison", "neutral", "parallel_bands"),
    ("hierarchy", "neutral", "ranked_strata"),
    ("distribution", "neutral", "distribution_field"),
    ("concentration", "neutral", "concentration_core"),
    ("flow", "neutral", "flow_channels"),
    ("network", "neutral", "network_constellation"),
    ("hierarchy", "stable", "hierarchy_terraces"),
    ("cycle", "cyclical", "cycle_orbit"),
    ("trend", "neutral", "forecast_horizon"),
    ("uncertainty", "neutral", "uncertainty_envelope"),
    ("system", "neutral", "system_matrix"),
)


@pytest.mark.parametrize(("shape", "direction", "expected"), CASES)
def test_select_geometry_family_uses_complete_priority_table(
    shape: str,
    direction: str,
    expected: str,
) -> None:
    semantics = {
        "evidence_shape": shape,
        "direction": direction,
        "domain_layer": "forecast" if expected == "forecast_horizon" else "grid",
    }

    assert select_geometry_family(semantics) == expected


def test_geometry_table_cannot_collapse_to_one_constant_family() -> None:
    selected = [
        select_geometry_family(
            {
                "evidence_shape": shape,
                "direction": direction,
                "domain_layer": (
                    "forecast" if expected == "forecast_horizon" else "grid"
                ),
            }
        )
        for shape, direction, expected in CASES
    ]

    assert len(set(selected)) == 16
    assert sum(item != selected[0] for item in selected) >= 16


def test_select_geometry_family_rejects_unknown_shape(assert_app_error) -> None:
    with pytest.raises(AppError) as captured:
        select_geometry_family(
            {
                "evidence_shape": "literal_category_icon",
                "direction": "neutral",
                "domain_layer": "grid",
            }
        )

    assert_app_error(
        captured.value,
        code="cover_fingerprint_invalid",
        retryable=False,
    )
