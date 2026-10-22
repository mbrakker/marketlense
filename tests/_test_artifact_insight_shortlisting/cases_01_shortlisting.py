from __future__ import annotations

import pytest

from src.generators import artifact_normalization
from src.generators._artifact_generator.storage import (
    derive_metric_spine_from_insights,
)
from src.generators.artifact_normalization import (
    select_artifact_insights,
)


def _plan(*evidence_ids: str) -> dict[str, object]:
    return {
        "report_thesis": "Retained evidence defines the decision surface.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [evidence_id],
            }
            for index, evidence_id in enumerate(evidence_ids, start=1)
        ],
    }


def _insight(
    insight_id: str,
    evidence_id: str,
    text: str,
    *,
    score: float,
    metric: dict[str, str] | None = None,
    pages: list[int] | None = None,
    evidence: str = "Retained evidence supports the proposition.",
    evidence_spans: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    return {
        "id": insight_id,
        "evidence_id": evidence_id,
        "text": text,
        "evidence": evidence,
        "evidence_spans": evidence_spans or [],
        "metric": metric or {},
        "pages": pages or [],
        "score": score,
        **extra,
    }


def _shared_evidence_span_candidates(
    first_span: dict[str, object],
    second_span: dict[str, object],
    *,
    first_pages: list[int],
    second_pages: list[int],
) -> list[dict[str, object]]:
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    shared_evidence = "The report provides a generic supporting excerpt."
    return [
        _insight(
            "shared",
            "f1",
            "The first source proposition.",
            score=0.99,
            metric=metric,
            evidence=shared_evidence,
            pages=first_pages,
            evidence_spans=[first_span],
        ),
        _insight(
            "shared",
            "f1",
            "The second source proposition.",
            score=0.01,
            metric=metric,
            evidence=shared_evidence,
            pages=second_pages,
            evidence_spans=[second_span],
        ),
    ]


def test_selector_prefers_bound_relevant_finding_over_generic_high_score() -> None:
    generic = _insight(
        "generic",
        "f-generic",
        "The market is changing.",
        score=0.99,
        evidence="The market is changing.",
        pages=[2],
    )
    bound = _insight(
        "bound",
        "f-bound",
        "The measured cohort shifted its channel mix.",
        score=0.72,
        decision_relevance_score=0.92,
        metric_strength_score=0.95,
        novelty_score=0.88,
        metric={
            "label": "Channel mix",
            "value": "42%",
            "unit": "%",
            "subject": "Measured cohort",
            "cohort": "Survey respondents",
            "denominator": "Respondents",
            "timeframe": "2025",
            "observation_status": "observed",
        },
        pages=[9],
        evidence=(
            "The report measures the channel mix at 42% for survey respondents in 2025."
        ),
        evidence_spans=[
            {
                "evidence_id": "f-bound",
                "source_pack": "findings",
                "page": 9,
                "text": (
                    "The report measures the channel mix at 42% for survey respondents "
                    "in 2025."
                ),
            }
        ],
    )

    selected = select_artifact_insights(
        final_insights=[generic, bound],
        candidate_insights=[],
        editorial_plan=_plan("f-generic", "f-bound"),
    )

    assert selected[0]["id"] == "bound"
    assert selected[0]["pages"] == [9]
    assert selected[0]["evidence_spans"][0]["page"] == 9


def test_selector_keeps_same_evidence_id_with_different_propositions() -> None:
    shared_evidence = "The report records 42% among surveyed respondents in 2025."
    metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "subject": "Survey respondents",
        "cohort": "Survey respondents",
        "denominator": "Respondents",
        "timeframe": "2025",
        "observation_status": "observed",
    }
    first = _insight(
        "first",
        "f1",
        "Survey respondents recorded a 42% share in 2025.",
        score=0.7,
        metric=metric,
        pages=[4],
        evidence=shared_evidence,
    )
    paraphrase = _insight(
        "paraphrase",
        "f1",
        "In 2025, 42% was recorded for the surveyed respondents.",
        score=0.9,
        metric=metric,
        pages=[4],
        evidence=shared_evidence,
    )

    selected = select_artifact_insights(
        final_insights=[first, paraphrase],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert {item["id"] for item in selected} == {"first", "paraphrase"}


def test_selector_preserves_final_wording_over_higher_scored_candidate() -> None:
    candidate_metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "subject": "Survey respondents",
        "cohort": "Survey respondents",
        "denominator": "Respondents",
        "timeframe": "2025",
        "observation_status": "observed",
    }
    candidate = _insight(
        "slot-1",
        "f1",
        "The retained candidate wording.",
        score=0.99,
        metric=candidate_metric,
        pages=[4],
        evidence="The retained source proposition.",
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "text": "The retained source proposition.",
            }
        ],
    )
    final = _insight(
        "slot-1",
        "f-drifted",
        "The final editorial rewrite.",
        score=0.2,
        metric={"label": "Drifted", "value": "99%", "unit": "%"},
        pages=[99],
        evidence="A drifted source proposition.",
        evidence_spans=[
            {
                "evidence_id": "f-drifted",
                "source_pack": "findings",
                "page": 99,
                "text": "A drifted source proposition.",
            }
        ],
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
    )

    assert len(selected) == 1
    assert selected[0]["id"] == "slot-1"
    assert selected[0]["text"] == "The final editorial rewrite."
    assert selected[0]["evidence_id"] == "f1"
    assert selected[0]["evidence"] == "The retained source proposition."
    assert selected[0]["pages"] == [4]
    assert selected[0]["evidence_spans"] == candidate["evidence_spans"]
    assert selected[0]["metric"] == {
        **dict.fromkeys(artifact_normalization.METRIC_FIELDS, ""),
        **{
            field_name: candidate_metric.get(field_name, "")
            for field_name in artifact_normalization.METRIC_BINDING_FIELDS
        },
        **candidate_metric,
    }


def test_selector_fails_closed_for_same_id_conflicting_evidence_bindings() -> None:
    stronger = _insight(
        "shared",
        "f1",
        "The first source proposition.",
        score=0.99,
        metric={"label": "Share", "value": "42%", "unit": "%"},
    )
    weaker = _insight(
        "shared",
        "f2",
        "The second source proposition.",
        score=0.01,
        metric={"label": "Share", "value": "42%", "unit": "%"},
    )
    final = _insight(
        "shared",
        "f1",
        "The final editorial rewrite.",
        score=0.5,
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[stronger, weaker],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_excludes_conflicting_candidate_id_without_final_rewrite() -> None:
    conflicting_first = _insight(
        "shared",
        "f1",
        "The first source proposition.",
        score=0.99,
    )
    conflicting_second = _insight(
        "shared",
        "f2",
        "The second source proposition.",
        score=0.01,
    )
    valid = _insight(
        "valid",
        "f3",
        "The unambiguous source proposition.",
        score=0.5,
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[conflicting_first, conflicting_second, valid],
        editorial_plan=_plan("f1", "f3"),
    )

    assert [item["id"] for item in selected] == ["valid"]


@pytest.mark.parametrize(
    ("field_name", "first_value", "second_value"),
    [
        ("value", "42%", "43%"),
        ("cohort", "Survey respondents", "Enterprise buyers"),
        ("observation_status", "observed", "forecast"),
    ],
)
def test_selector_fails_closed_for_same_id_conflicting_metric_bindings(
    field_name: str, first_value: str, second_value: str
) -> None:
    base_metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "cohort": "Survey respondents",
        "observation_status": "observed",
    }
    first_metric = {**base_metric, field_name: first_value}
    second_metric = {**base_metric, field_name: second_value}
    first = _insight(
        "shared",
        "f1",
        "The first source proposition.",
        score=0.99,
        metric=first_metric,
    )
    second = _insight(
        "shared",
        "f1",
        "The second source proposition.",
        score=0.01,
        metric=second_metric,
    )
    final = _insight(
        "shared",
        "f1",
        "The final editorial rewrite.",
        score=0.5,
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_accepts_same_id_source_consistent_representations() -> None:
    metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "cohort": "Survey respondents",
    }
    first = _insight(
        "shared",
        "f1",
        "The source wording.",
        score=0.7,
        metric=metric,
    )
    second = _insight(
        "shared",
        "f1",
        "Equivalent source wording.",
        score=0.9,
        metric=metric,
    )
    final = _insight(
        "shared",
        "f-drifted",
        "The final editorial rewrite.",
        score=0.2,
        metric={"label": "Drifted", "value": "99%", "unit": "%"},
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert len(selected) == 1
    assert selected[0]["text"] == "The final editorial rewrite."
    assert selected[0]["evidence_id"] == "f1"
    assert selected[0]["metric"] == {
        **dict.fromkeys(artifact_normalization.METRIC_FIELDS, ""),
        **{
            field_name: metric.get(field_name, "")
            for field_name in artifact_normalization.METRIC_BINDING_FIELDS
        },
        **metric,
    }


def test_selector_fails_closed_for_same_id_conflicting_physical_provenance() -> None:
    metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "cohort": "Survey respondents",
    }
    first = _insight(
        "shared",
        "f1",
        "The first source proposition.",
        score=0.99,
        metric=metric,
        evidence="The source reports 42% for the first population.",
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 40,
                "text": "The source reports 42% for the first population.",
            }
        ],
    )
    second = _insight(
        "shared",
        "f1",
        "The second source proposition.",
        score=0.01,
        metric=metric,
        evidence="The source reports 42% for the second population.",
        pages=[9],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 9,
                "start_offset": 80,
                "end_offset": 110,
                "text": "The source reports 42% for the second population.",
            }
        ],
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


@pytest.mark.parametrize(
    ("first_pages", "second_pages", "first_span", "second_span"),
    [
        (
            [4],
            [9],
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 20,
                "text": "The first physical excerpt.",
            },
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 9,
                "start_offset": 30,
                "end_offset": 40,
                "text": "The second physical excerpt.",
            },
        ),
        (
            [4],
            [4],
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 20,
                "text": "The first physical excerpt.",
            },
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 30,
                "end_offset": 40,
                "text": "The second physical excerpt.",
            },
        ),
        (
            [4],
            [4],
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 20,
                "text": "The same physical excerpt.",
            },
            {
                "evidence_id": "f1",
                "source_pack": "doc_map",
                "page": 4,
                "start_offset": 10,
                "end_offset": 20,
                "text": "The same physical excerpt.",
            },
        ),
    ],
)
def test_selector_fails_closed_for_shared_text_with_incompatible_spans(
    first_pages: list[int],
    second_pages: list[int],
    first_span: dict[str, object],
    second_span: dict[str, object],
) -> None:
    first, second = _shared_evidence_span_candidates(
        first_span,
        second_span,
        first_pages=first_pages,
        second_pages=second_pages,
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_fails_closed_for_disjoint_same_page_spans() -> None:
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    first = _insight(
        "shared",
        "f1",
        "The first source proposition.",
        score=0.99,
        metric=metric,
        evidence="The first source excerpt.",
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 20,
                "text": "The first source excerpt.",
            }
        ],
    )
    second = _insight(
        "shared",
        "f1",
        "The second source proposition.",
        score=0.01,
        metric=metric,
        evidence="The second source excerpt.",
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 30,
                "end_offset": 40,
                "text": "The second source excerpt.",
            }
        ],
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_accepts_overlapping_alternative_source_spans() -> None:
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    first = _insight(
        "shared",
        "f1",
        "The first source wording.",
        score=0.7,
        metric=metric,
        evidence="The first source excerpt.",
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 30,
                "text": "The first source excerpt.",
            }
        ],
    )
    second = _insight(
        "shared",
        "f1",
        "The equivalent source wording.",
        score=0.9,
        metric=metric,
        evidence="The equivalent source excerpt.",
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 25,
                "end_offset": 45,
                "text": "The equivalent source excerpt.",
            }
        ],
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["shared"]
    assert selected[0]["evidence"] == "The equivalent source excerpt."


def test_selector_accepts_legitimate_multi_page_source_representation() -> None:
    metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "cohort": "Survey respondents",
    }
    shared_excerpt = "The source reports 42% for surveyed respondents."
    first = _insight(
        "shared",
        "f1",
        "The source wording.",
        score=0.7,
        metric=metric,
        evidence=shared_excerpt,
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "text": shared_excerpt,
            }
        ],
    )
    second = _insight(
        "shared",
        "f1",
        "Equivalent source wording.",
        score=0.9,
        metric=metric,
        evidence=shared_excerpt,
        pages=[4, 5],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "text": shared_excerpt,
            },
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 5,
                "text": shared_excerpt,
            },
        ],
    )

    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[first, second],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["shared"]
    assert selected[0]["pages"] == [4, 5]


def test_selector_removes_final_only_protected_metric_additions() -> None:
    candidate = _insight(
        "shared",
        "f1",
        "The retained source proposition.",
        score=0.8,
        metric={"label": "Share", "value": "42%", "unit": "%"},
    )
    final = _insight(
        "shared",
        "f-drifted",
        "The final editorial rewrite.",
        score=0.2,
        metric={
            "label": "Share",
            "value": "99%",
            "unit": "%",
            "subject": "Enterprise buyers",
            "cohort": "Enterprise buyers",
            "denominator": "All buyers",
            "timeframe": "2026 forecast",
            "geography": "Global",
            "observation_status": "forecast",
        },
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
    )

    assert len(selected) == 1
    assert selected[0]["text"] == "The final editorial rewrite."
    assert selected[0]["metric"] == {
        **dict.fromkeys(
            (*artifact_normalization.METRIC_FIELDS,)
            + artifact_normalization.METRIC_BINDING_FIELDS,
            "",
        ),
        "label": "Share",
        "value": "42%",
        "unit": "%",
    }


def test_supported_candidate_numeric_binding_survives_downstream_metric_spine() -> None:
    candidate = _insight(
        "shared",
        "f1",
        "The retained source proposition.",
        score=0.8,
        metric={
            "label": "Respondent share",
            "value": "42%",
            "unit": "%",
            "subject": "Survey respondents",
        },
    )
    final = _insight(
        "shared",
        "f-final",
        "The final editorial rewrite.",
        score=0.2,
        metric={
            "label": "Respondent share",
            "value": "99%",
            "unit": "%",
            "timeframe": "2026 forecast",
            "geography": "Global",
        },
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
    )
    metric_spine = derive_metric_spine_from_insights(selected)

    assert selected[0]["text"] == "The final editorial rewrite."
    assert selected[0]["metric"]["value"] == "42%"
    assert selected[0]["metric"]["timeframe"] == ""
    assert selected[0]["metric"]["geography"] == ""
    assert metric_spine[0]["value"] == "42%"
    assert metric_spine[0]["timeframe"] == ""
    assert metric_spine[0]["geography"] == ""


def test_source_bound_metric_drops_unbound_timeframe() -> None:
    insight = _insight(
        "criteo-performance-retention",
        "s4-performance-retention-recommendations",
        "For 2023 plans, agency respondents recommended performance over "
        "brand awareness.",
        score=0.8,
        evidence=(
            "51% of agency respondents recommend brands focus on performance versus "
            "45% who say brand awareness."
        ),
        metric={
            "label": "Agency recommendations",
            "value": "51% versus 45%",
            "unit": "%",
            "timeframe": "2023 plans",
            "segment": "Agency respondents",
            "cohort": "Agency respondents",
            "observation_status": "observed",
        },
        pages=[8],
    )

    artifact_normalization.preserve_public_source_displays(
        summary={},
        insights_final=[insight],
        expert_comment="",
        linkedin_post="",
    )

    assert insight["metric"]["value"] == "51% versus 45%"
    assert insight["metric"]["timeframe"] == ""
    assert insight["metric"]["segment"] == "Agency respondents"


def test_candidate_normalization_drops_unbound_calendar_timeframe() -> None:
    normalized = artifact_normalization.normalize_artifact_insights(
        [
            _insight(
                "criteo-performance-retention",
                "s4-performance-retention-recommendations",
                "Agency respondents recommended performance over brand awareness.",
                score=0.8,
                evidence=(
                    "51% of agency respondents recommend brands focus on performance "
                    "versus 45% who say brand awareness."
                ),
                metric={
                    "label": "Agency recommendations",
                    "value": "51% versus 45%",
                    "unit": "%",
                    "timeframe": "2023 plans",
                },
                pages=[8],
            )
        ],
        prefix="candidate",
    )

    assert normalized[0]["metric"]["timeframe"] == ""
    assert normalized[0]["metric"]["value"] == "51% versus 45%"


def test_candidate_normalization_preserves_supported_paraphrased_timeframe() -> None:
    normalized = artifact_normalization.normalize_artifact_insights(
        [
            _insight(
                "agentic-search-plans",
                "quote-001",
                "Retailers are planning agentic search implementation.",
                score=0.8,
                evidence=(
                    "Adoption is projected to increase significantly, with 61% "
                    "planning implementation within the next 12 months."
                ),
                metric={
                    "label": "Agentic search implementation plans",
                    "value": "61%",
                    "unit": "%",
                    "timeframe": "61% plan implementation within the next 12 months",
                },
                pages=[5],
            )
        ],
        prefix="candidate",
    )

    assert (
        normalized[0]["metric"]["timeframe"]
        == "61% plan implementation within the next 12 months"
    )
