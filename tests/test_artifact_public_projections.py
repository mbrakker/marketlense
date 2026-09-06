from src.generators._artifact_generator.storage import build_key_figures


def test_key_figure_support_reuses_its_linked_retained_insight_text() -> None:
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": "usage",
                "evidence_id": "usage-evidence",
                "label": "U.S. household data usage",
                "value": "475GB per month to 1,000GB per month by 2024E",
                "unit": "",
                "timeframe": "2020 to 2024E",
            }
        ],
        evidence_packs={},
        insights_final=[
            {
                "id": "usage",
                "evidence_id": "usage-evidence",
                "text": (
                    "U.S. household data usage is forecast to rise from 475GB per "
                    "month to 1,000GB per month by 2024E."
                ),
            }
        ],
    )

    assert figures[0]["why_it_matters"] == (
        "U.S. household data usage is forecast to rise from 475GB per month "
        "to 1,000GB per month by 2024E."
    )
