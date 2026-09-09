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


def test_key_figure_does_not_add_an_inferred_unit_to_a_source_display() -> None:
    figures = build_key_figures(
        metric_spine=[
            {
                "metric_id": "growth",
                "evidence_id": "growth-evidence",
                "label": "Internet user growth",
                "value": "58 thousand",
                "unit": "users",
                "timeframe": "2021 to 2022",
                "confidence": "high",
            }
        ],
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "growth-evidence",
                        "text": "Internet users increased by 58 thousand between 2021 and 2022.",
                    }
                ]
            }
        },
        insights_final=[
            {
                "id": "growth",
                "evidence_id": "growth-evidence",
                "evidence": "Internet users increased by 58 thousand between 2021 and 2022.",
                "text": "Internet users increased by 58 thousand between 2021 and 2022.",
            }
        ],
    )

    assert figures[0]["figure"] == "58 thousand"
