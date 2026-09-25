import json
from pathlib import Path

import pytest

from src.generators._artifact_generator.storage import build_key_figures

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "key_figure_selection" / "scenarios.json"
)
_DOUBLEVERIFY_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "key_figure_selection"
    / "doubleverify_threshold_projection.json"
)


@pytest.fixture(scope="module")
def scenarios() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _source_backed_insights(metrics: list[dict]) -> list[dict]:
    return [
        {
            "id": str(metric["metric_id"]),
            "evidence_id": str(metric["evidence_id"]),
            "evidence": str(metric["evidence"]),
        }
        for metric in metrics
    ]


@pytest.mark.parametrize(
    "scenario_name",
    [
        "many_strong_distinct_metrics",
        "many_redundant_metrics",
        "one_strong_metric_only",
        "qualitative_report",
        "forecast_vs_observed",
    ],
)
def test_key_figure_selection_uses_only_strong_distinct_source_metrics(
    scenarios: dict, scenario_name: str
) -> None:
    scenario = scenarios[scenario_name]

    figures = build_key_figures(
        metric_spine=scenario["metrics"],
        evidence_packs={},
        summary=scenario.get("summary"),
        insights_final=_source_backed_insights(scenario["metrics"]),
    )

    assert {figure["figure_id"] for figure in figures} == set(scenario["expected_ids"])
    assert len(figures) <= 5


def test_key_figure_selection_preserves_forecast_and_observed_source_context(
    scenarios: dict,
) -> None:
    scenario = scenarios["forecast_vs_observed"]
    figures = build_key_figures(
        metric_spine=scenario["metrics"],
        evidence_packs={},
        insights_final=_source_backed_insights(scenario["metrics"]),
    )

    assert [figure["observation_status"] for figure in figures] == [
        "forecast",
        "observed",
    ]
    assert [(figure["geography"], figure["timeframe"]) for figure in figures] == [
        ("Europe", "2026 to 2030"),
        ("Europe", "2026"),
    ]


def test_key_figure_selection_rejects_a_metric_that_fails_source_relationship_fidelity(
) -> None:
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": "temporal-mismatch",
                "evidence_id": "temporal-mismatch",
                "label": "Average daily social-video time in 2024E",
                "value": "0:48",
                "unit": "",
                "timeframe": "2024E",
                "confidence": "high",
            }
        ],
        evidence_packs={},
        insights_final=[
            {
                "id": "temporal-mismatch",
                "evidence_id": "temporal-mismatch",
                "text": "Average daily social-video time reaches 0:48 in 2024E.",
                "evidence": (
                    "Average daily social-video time: 2023 0:48; "
                    "2024E 0:52; 2028E 0:57."
                ),
            }
        ],
    )

    assert figures == []


def test_doubleverify_threshold_projection_is_omitted_from_its_bound_evidence() -> None:
    fixture = json.loads(_DOUBLEVERIFY_FIXTURE_PATH.read_text(encoding="utf-8"))

    figures = build_key_figures(
        metric_spine=fixture["metric_spine"],
        evidence_packs={},
        insights_final=fixture["insights_final"],
    )

    assert not any(
        figure["figure_id"] == "display-viewability-duration-criterion-retained-5"
        for figure in figures
    )
    apac_sibling = next(
        figure
        for figure in figures
        if figure["figure_id"] == "q1-2026-apac-authentic-viewable-rate"
    )
    assert (
        apac_sibling["figure"],
        apac_sibling["evidence_id"],
        apac_sibling["source_page"],
    ) == ("63%", "s2", 3)
    assert any(
        insight["evidence_id"] == "s4"
        and "at least 50%" in insight["evidence"]
        for insight in fixture["insights_final"]
    )


@pytest.mark.parametrize(
    ("metric_id", "label", "value", "evidence"),
    [
        (
            "percent",
            "Retailers using the tool",
            "75%",
            "75% of retailers use the tool.",
        ),
        (
            "duration",
            "Daily viewing duration",
            "0:48",
            "Daily viewing duration was 0:48.",
        ),
        (
            "currency",
            "Annual spend",
            "$918 billion",
            "Annual spend reached $918 billion.",
        ),
        ("range", "Growth range", "10-15%", "Growth is forecast in the 10-15% range."),
    ],
)
def test_key_figure_selection_retains_values_supported_by_bound_evidence(
    metric_id: str, label: str, value: str, evidence: str
) -> None:
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": metric_id,
                "evidence_id": metric_id,
                "label": label,
                "value": value,
                "confidence": "high",
            }
        ],
        evidence_packs={},
        insights_final=[
            {"id": metric_id, "evidence_id": metric_id, "evidence": evidence}
        ],
    )

    assert [figure["figure_id"] for figure in figures] == [metric_id]


def test_unrelated_evidence_number_does_not_support_key_figure() -> None:
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": "unsupported-bound-value",
                "evidence_id": "claim-source",
                "label": "Retailers using the tool",
                "value": "75%",
                "confidence": "high",
            }
        ],
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "evidence_id": "other-source",
                        "evidence": "75% of firms reported growth.",
                    }
                ]
            }
        },
        insights_final=[
            {
                "id": "unsupported-bound-value",
                "evidence_id": "claim-source",
                "evidence": "Retailers use the tool.",
            }
        ],
    )

    assert figures == []


def test_unsupported_top_ranked_metric_does_not_block_next_valid_metric() -> None:
    metrics = [
        {
            "metric_id": "unsupported-top",
            "evidence_id": "unsupported-top",
            "label": "Retailers using the tool",
            "value": "91%",
            "confidence": "high",
        },
        {
            "metric_id": "supported-next",
            "evidence_id": "supported-next",
            "label": "Teams using AI in campaign workflows",
            "value": "75%",
            "confidence": "high",
        },
    ]
    figures = build_key_figures(
        metric_spine=metrics,
        evidence_packs={},
        summary={"executive_summary": "Retailers are using the tool."},
        insights_final=[
            {
                "id": metric["metric_id"],
                "evidence_id": metric["evidence_id"],
                "evidence": evidence,
            }
            for metric, evidence in zip(
                metrics,
                [
                    "Only 75% of firms report growth.",
                    "75% of teams use AI in workflows.",
                ],
                strict=True,
            )
        ],
    )

    assert [figure["figure_id"] for figure in figures] == ["supported-next"]


def test_key_figure_selection_considers_metrics_beyond_the_metric_spine_cap() -> None:
    metrics = [
        {
            "metric_id": f"adoption-{index}",
            "evidence_id": f"adoption-{index}",
            "label": "Retailers exploring AI for commerce media",
            "value": "68%",
            "timeframe": "2026",
            "geography": "Europe",
            "confidence": "high",
        }
        for index in range(1, 7)
    ]
    metrics.append(
        {
            "metric_id": "workflow-beyond-cap",
            "evidence_id": "workflow-beyond-cap",
            "label": "Retail-media teams using AI in campaign workflows",
            "value": "75%",
            "timeframe": "2026",
            "geography": "Europe",
            "confidence": "high",
        }
    )
    insights = [
        {
            "id": metric["metric_id"],
            "evidence_id": metric["evidence_id"],
            "evidence": (
                "In 2026, 68% of Europe retailers are exploring AI for commerce media."
                if metric["metric_id"].startswith("adoption")
                else (
                    "In 2026, 75% of Europe retail-media teams use AI "
                    "in campaign workflows."
                )
            ),
            "metric": metric,
        }
        for metric in metrics
    ]

    figures = build_key_figures(
        metric_spine=metrics[:6], evidence_packs={}, insights_final=insights
    )

    assert {figure["figure_id"] for figure in figures} == {
        "adoption-1",
        "workflow-beyond-cap",
    }
