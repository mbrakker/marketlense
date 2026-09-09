import json
from pathlib import Path

import pytest

from src.generators._artifact_generator.storage import build_key_figures


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "key_figure_selection" / "scenarios.json"
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


def test_key_figure_selection_rejects_a_metric_that_fails_source_relationship_fidelity() -> (
    None
):
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": "temporal-mismatch",
                "evidence_id": "temporal-mismatch",
                "label": "Average daily social-video time in 2024E",
                "value": "0:48 in 2024E",
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
                "text": "Average daily social-video time reaches 0:52 in 2024E.",
                "evidence": (
                    "Average daily social-video time: 2023 0:48; "
                    "2024E 0:52; 2028E 0:57."
                ),
            }
        ],
    )

    assert figures == []


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
                else "In 2026, 75% of Europe retail-media teams use AI in campaign workflows."
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
