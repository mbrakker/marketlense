from __future__ import annotations

import pytest

from src.generators import artifact_normalization
from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
    select_artifact_insights,
)
from src.generators._artifact_generator.storage import _artifact_cache_meta_matches


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
        evidence="The report measures the channel mix at 42% for survey respondents in 2025.",
        evidence_spans=[
            {
                "evidence_id": "f-bound",
                "source_pack": "findings",
                "page": 9,
                "text": "The report measures the channel mix at 42% for survey respondents in 2025.",
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


def test_selector_collapses_same_bound_proposition_with_different_wording() -> None:
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

    assert [item["id"] for item in selected] == ["paraphrase"]


def test_selector_keeps_same_page_topic_when_metric_binding_differs() -> None:
    first = _insight(
        "installs",
        "f1",
        "Installs increased for the strategy segment.",
        score=0.8,
        metric={
            "label": "Installs",
            "value": "57%",
            "unit": "%",
            "subject": "Strategy segment",
            "cohort": "Strategy apps",
            "denominator": "Installs",
            "timeframe": "2024-2025",
            "observation_status": "observed",
        },
        pages=[19],
    )
    second = _insight(
        "sessions",
        "f1",
        "Sessions increased for the strategy segment.",
        score=0.79,
        metric={
            "label": "Sessions",
            "value": "57%",
            "unit": "%",
            "subject": "Strategy segment",
            "cohort": "Strategy apps",
            "denominator": "Sessions",
            "timeframe": "2024-2025",
            "observation_status": "observed",
        },
        pages=[19],
    )

    selected = select_artifact_insights(
        final_insights=[first, second],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["installs", "sessions"]


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("cohort", "Different cohort"),
        ("timeframe", "2026"),
        ("observation_status", "forecast"),
    ],
)
def test_selector_never_merges_changed_protected_metric_dimensions(
    field_name: str, changed_value: str
) -> None:
    base_metric = {
        "label": "Respondent share",
        "value": "42%",
        "unit": "%",
        "subject": "Survey respondents",
        "cohort": "Survey respondents",
        "denominator": "Respondents",
        "timeframe": "2025",
        "observation_status": "observed",
    }
    changed_metric = {**base_metric, field_name: changed_value}
    first = _insight(
        "first-dimension",
        "f1",
        "The first bound proposition.",
        score=0.8,
        metric=base_metric,
        pages=[4],
        evidence="The report records 42% among surveyed respondents.",
    )
    second = _insight(
        "second-dimension",
        "f1",
        "The second bound proposition.",
        score=0.79,
        metric=changed_metric,
        pages=[4],
        evidence="The report records 42% among surveyed respondents.",
    )

    selected = select_artifact_insights(
        final_insights=[first, second],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == [
        "first-dimension",
        "second-dimension",
    ]


def test_selector_does_not_promote_missing_evidence_binding() -> None:
    missing = _insight(
        "missing",
        "",
        "A generated observation without a retained binding.",
        score=0.99,
        pages=[12],
    )
    grounded = _insight(
        "grounded",
        "f1",
        "A retained observation with a source binding.",
        score=0.5,
        pages=[12],
    )

    selected = select_artifact_insights(
        final_insights=[missing, grounded],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["grounded"]


def test_finding_fallback_uses_supported_page_bound_alternatives() -> None:
    findings = {
        "findings": [
            {
                "id": "weak-source-order",
                "text": "A weak finding.",
                "evidence": "Weak source text.",
                "confidence": "low",
                "pages": [3],
            },
            {
                "id": "no-physical-page",
                "text": "A finding without a physical page.",
                "evidence": "No page-bound source text.",
                "confidence": "high",
                "pages": [],
            },
            {
                "id": "unsupported",
                "text": "An unsupported finding.",
                "evidence": "Unsupported source text.",
                "confidence": "high",
                "pages": [4],
            },
            {
                "id": "strong-supported",
                "text": "A high-confidence supported finding.",
                "evidence": "Supported source text.",
                "confidence": "high",
                "pages": [8],
            },
        ],
    }
    evidence_fidelity = {
        "results": [
            {
                "status": "unsupported",
                "candidate": {"claim_id": "evidence:findings:unsupported"},
            },
            {
                "status": "supported",
                "candidate": {"claim_id": "evidence:findings:strong-supported"},
            },
            {
                "status": "supported",
                "candidate": {"claim_id": "evidence:findings:weak-source-order"},
            },
        ]
    }

    selected = fallback_artifact_insights_from_findings(
        findings,
        evidence_fidelity=evidence_fidelity,
        limit=2,
    )

    assert [item["evidence_id"] for item in selected] == [
        "strong-supported",
        "weak-source-order",
    ]
    assert "unsupported" not in {item["evidence_id"] for item in selected}
    assert "no-physical-page" not in {item["evidence_id"] for item in selected}
    assert selected[0]["pages"] == [8]


def test_selection_version_invalidates_the_previous_shortlisting_behavior() -> None:
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION != (
        "stable_id_unique_selection:2"
    )


def test_old_selection_version_cannot_match_a_new_cache_key() -> None:
    expected = {
        "insight_selection_version": artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION,
        "prompts": {},
    }
    matched, reason = _artifact_cache_meta_matches(
        cached_meta={
            "key": "new-cache-key",
            "insight_selection_version": "stable_id_unique_selection:2",
        },
        expected_cache_meta=expected,
        cache_key="new-cache-key",
    )

    assert matched is False
    assert reason == "insight_selection_version_mismatch"
