"""Deterministic typed compatibility ranking for retained alternative evidence."""

from __future__ import annotations

from src.generators.evidence_compatibility import (
    CompatibilityQuery,
    rank_compatible_alternatives,
)


def _entry(evidence_id: str, text: str, **extra) -> tuple[str, dict]:
    payload = {"id": evidence_id, "text": text}
    payload.update(extra)
    return evidence_id, payload


def test_compatible_evidence_ranks_above_wrong_geography_same_number() -> None:
    query = CompatibilityQuery(
        text="Online spend in Europe grew 12 percent in 2025.",
    )
    candidates = [
        _entry("compatible", "Online spend in Europe grew 12 percent in 2025."),
        _entry(
            "wrong-geography",
            "Online spend in the United States grew 12 percent in 2025.",
        ),
    ]

    ranked = rank_compatible_alternatives(query, candidates)

    assert [item.evidence_id for item in ranked] == ["compatible"]


def test_wrong_period_and_forecast_alternatives_are_rejected() -> None:
    query = CompatibilityQuery(
        text="Average daily social-video time reached 0:48 in Q1 2025.",
    )
    candidates = [
        _entry(
            "compatible", "Average daily social-video time reached 0:48 in Q1 2025."
        ),
        _entry(
            "wrong-period", "Average daily social-video time reached 0:48 in Q3 2023."
        ),
        _entry(
            "forecast-not-observed",
            "Average daily social-video time is forecast to reach 0:48 by 2025.",
        ),
    ]

    ranked = rank_compatible_alternatives(query, candidates)

    assert [item.evidence_id for item in ranked] == ["compatible"]


def test_wrong_cohort_and_wrong_denominator_are_rejected() -> None:
    query = CompatibilityQuery(
        text="34% of shoppers in Europe abandoned a cart in 2025.",
    )
    candidates = [
        _entry("compatible", "34% of shoppers in Europe abandoned a cart in 2025."),
        _entry(
            "wrong-cohort",
            "34% of marketers in Europe abandoned a cart demo in 2025.",
        ),
    ]

    ranked = rank_compatible_alternatives(query, candidates)

    assert [item.evidence_id for item in ranked] == ["compatible"]


def test_quarantined_evidence_is_never_returned_even_when_best() -> None:
    query = CompatibilityQuery(text="Retention improved to 61% in 2025.")
    candidates = [
        _entry("quarantined", "Retention improved to 61% in 2025."),
        _entry("other", "Retention planning signal from the same survey."),
    ]

    ranked = rank_compatible_alternatives(
        query, candidates, quarantined_ids=["quarantined"]
    )

    assert all(item.evidence_id != "quarantined" for item in ranked)
    assert ranked[0].evidence_id == "other"


def test_metric_payload_relevance_breaks_compatibility_ties() -> None:
    query = CompatibilityQuery(
        text="The margin metric moved.",
        metric={"value": "46%", "unit": "%", "timeframe": "2025"},
    )
    candidates = [
        _entry("metric-evidence", "Reported margin of 46% for 2025."),
        _entry(
            "other-evidence",
            "Margin discussion without the reported number.",
        ),
    ]

    ranked = rank_compatible_alternatives(query, candidates)

    assert ranked[0].evidence_id == "metric-evidence"


def test_result_is_bounded_and_deterministic() -> None:
    query = CompatibilityQuery(text="Retention planning signal from the survey.")
    candidates = [
        _entry(f"candidate-{index}", "Retention planning signal from the survey.")
        for index in range(10)
    ]

    first = rank_compatible_alternatives(query, candidates, limit=3)
    second = rank_compatible_alternatives(query, candidates, limit=3)

    assert len(first) == 3
    assert [item.evidence_id for item in first] == [item.evidence_id for item in second]
    assert [item.evidence_id for item in first] == [
        "candidate-0",
        "candidate-1",
        "candidate-2",
    ]


def test_page_proximity_prefers_same_page_evidence() -> None:
    query = CompatibilityQuery(text="Conversion improved in the quarter.", pages=[7])
    candidates = [
        _entry("same-page", "Conversion improved in the quarter.", pages=[7]),
        _entry("far-page", "Conversion improved in the quarter.", pages=[31]),
    ]

    ranked = rank_compatible_alternatives(query, candidates)

    assert ranked[0].evidence_id == "same-page"


def test_conflicting_candidate_only_is_rejected_and_abstains() -> None:
    query = CompatibilityQuery(text="Reach in Europe grew 20% in 2024.")
    candidates = [
        _entry("wrong-geography", "Reach in the United States grew 20% in 2024."),
    ]

    assert rank_compatible_alternatives(query, candidates) == []
