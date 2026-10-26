from __future__ import annotations

import pytest

from src.generators import artifact_normalization
from src.generators._artifact_generator.storage import (
    _artifact_cache_meta_matches,
)
from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
    select_artifact_insights,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
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


def test_selector_rejects_final_rewrite_without_candidate_binding() -> None:
    candidate = _insight(
        "unbound",
        "",
        "A candidate without a retained source binding.",
        score=0.9,
    )
    final = _insight(
        "unbound",
        "f-final",
        "An unsupported final rewrite.",
        score=0.1,
        metric={
            "label": "Unsupported share",
            "value": "99%",
            "unit": "%",
            "cohort": "Invented cohort",
            "observation_status": "forecast",
        },
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_deduplicates_identical_public_claims_across_evidence_ids() -> None:
    claim = "Survey respondents recorded a 42% share in 2025."
    selected = select_artifact_insights(
        final_insights=[
            _insight("first", "f1", claim, score=0.7),
            _insight("second", "f2", claim, score=0.9),
        ],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["second"]


def test_selector_replaces_duplicate_final_wording_with_bound_candidate_wording() -> (
    None
):
    claim = "The strategy segment recorded a 57% increase."
    first = _insight(
        "installs",
        "f1",
        claim,
        score=0.8,
        metric={"label": "Installs", "value": "57%", "unit": "%"},
    )
    second = _insight(
        "sessions",
        "f2",
        claim,
        score=0.79,
        metric={"label": "Sessions", "value": "57%", "unit": "%"},
    )
    first_candidate = _insight(
        "installs",
        "f1",
        "Install share rose 57% among strategy apps.",
        score=0.7,
        metric={"label": "Installs", "value": "57%", "unit": "%"},
        evidence="The source reports install share rose 57% among strategy apps.",
        pages=[4],
    )
    second_candidate = _insight(
        "sessions",
        "f2",
        "Session volume rose 57% for the strategy cohort.",
        score=0.7,
        metric={"label": "Sessions", "value": "57%", "unit": "%"},
        evidence="The source reports session volume rose 57% for the strategy cohort.",
        pages=[5],
    )

    selected = select_artifact_insights(
        final_insights=[first, second],
        candidate_insights=[first_candidate, second_candidate],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["installs", "sessions"]
    assert [item["text"] for item in selected] == [
        "Install share rose 57% among strategy apps.",
        "Session volume rose 57% for the strategy cohort.",
    ]
    assert [item["metric"]["label"] for item in selected] == [
        "Installs",
        "Sessions",
    ]
    quality = evaluate_public_editorial_quality(
        report_id="duplicate-wording-regression",
        artifacts={"insights_final": selected},
    )
    assert "public_editorial_quality.duplicate_insight" not in {
        issue.rule_id for issue in quality.issues
    }


def test_selector_fails_closed_for_duplicate_wording_with_conflicting_metrics() -> None:
    claim = "The strategy segment recorded a 57% increase."
    selected = select_artifact_insights(
        final_insights=[
            _insight(
                "installs",
                "f1",
                claim,
                score=0.8,
                metric={"label": "Installs", "value": "57%", "unit": "%"},
            ),
            _insight(
                "sessions",
                "f2",
                claim,
                score=0.79,
                metric={"label": "Sessions", "value": "57%", "unit": "%"},
            ),
        ],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_selector_does_not_use_differently_bound_candidate_wording() -> None:
    claim = "The strategy segment recorded a 57% increase."
    selected = select_artifact_insights(
        final_insights=[
            _insight(
                "installs",
                "f1",
                claim,
                score=0.8,
                metric={"label": "Installs", "value": "57%", "unit": "%"},
            ),
            _insight(
                "sessions",
                "f2",
                claim,
                score=0.79,
                metric={"label": "Sessions", "value": "57%", "unit": "%"},
            ),
        ],
        candidate_insights=[
            _insight(
                "installs",
                "f1",
                claim,
                score=0.9,
                metric={"label": "Installs", "value": "57%", "unit": "%"},
            ),
            _insight(
                "installs",
                "f1",
                "Install share rose 57% among strategy apps.",
                score=0.7,
                metric={},
            ),
            _insight(
                "sessions",
                "f2",
                claim,
                score=0.89,
                metric={"label": "Sessions", "value": "57%", "unit": "%"},
            ),
            _insight(
                "sessions",
                "f2",
                "Session volume rose 57% for the strategy cohort.",
                score=0.7,
                metric={},
            ),
        ],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


def test_verified_final_selection_does_not_insert_unselected_candidates() -> None:
    candidates = [
        _insight(
            f"candidate-{index}",
            f"f{index}",
            f"Supported proposition {index}.",
            score=1.0 - index / 100,
            pages=[index + 1],
        )
        for index in range(8)
    ]

    selected = select_artifact_insights(
        final_insights=candidates[:3],
        candidate_insights=candidates,
        editorial_plan=_plan("f0", "f1"),
        require_final_candidate_lineage=True,
        verified_mode=True,
    )

    assert [item["id"] for item in selected] == [
        "candidate-0",
        "candidate-1",
        "candidate-2",
    ]


def test_selector_fails_closed_for_candidate_only_duplicate_wording() -> None:
    claim = "The strategy segment recorded a 57% increase."
    selected = select_artifact_insights(
        final_insights=[],
        candidate_insights=[
            _insight(
                "installs",
                "f1",
                claim,
                score=0.8,
                metric={"label": "Installs", "value": "57%", "unit": "%"},
            ),
            _insight(
                "sessions",
                "f2",
                claim,
                score=0.79,
                metric={"label": "Sessions", "value": "57%", "unit": "%"},
            ),
        ],
        editorial_plan=_plan("f1", "f2"),
    )

    assert selected == []


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


def test_finding_fallback_covers_uncovered_themes_before_filling_capacity() -> None:
    findings = {
        "findings": [
            {
                "id": "f1-high-a",
                "text": "The first topic has a strong finding.",
                "evidence": "First topic source text A.",
                "confidence": "high",
                "score": 0.99,
                "pages": [3],
            },
            {
                "id": "f1-high-b",
                "text": "The first topic has another strong finding.",
                "evidence": "First topic source text B.",
                "confidence": "high",
                "score": 0.98,
                "pages": [4],
            },
            {
                "id": "f2-medium",
                "text": "The second topic has a supported finding.",
                "evidence": "Second topic source text.",
                "confidence": "medium",
                "score": 0.6,
                "pages": [5],
            },
            {
                "id": "f3-low",
                "text": "The third topic has a supported finding.",
                "evidence": "Third topic source text.",
                "confidence": "low",
                "score": 0.4,
                "pages": [6],
            },
        ]
    }

    selected = fallback_artifact_insights_from_findings(
        findings,
        editorial_plan=_plan("f1-high-a", "f2-medium", "f3-low"),
        covered_evidence_ids=["f1-high-a"],
        limit=2,
    )

    assert [item["evidence_id"] for item in selected] == [
        "f2-medium",
        "f3-low",
    ]


def test_verified_finding_fallback_preserves_stable_fact_identity() -> None:
    selected = fallback_artifact_insights_from_findings(
        {
            "findings": [
                {
                    "id": "verified-fact:fact-1",
                    "verified_fact_id": "fact-1",
                    "text": "The retained verified fact.",
                    "evidence": "The retained source evidence.",
                    "pages": [4],
                }
            ]
        },
        limit=1,
    )

    assert len(selected) == 1
    assert selected[0]["id"] == "fact-1"
    assert selected[0]["evidence_id"] == "verified-fact:fact-1"


def test_selection_version_invalidates_the_previous_shortlisting_behavior() -> None:
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION == (
        "evidence_backed_shortlisting:19"
    )
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION != (
        "stable_id_unique_selection:2"
    )
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION != (
        "evidence_backed_shortlisting:1"
    )


@pytest.mark.parametrize(
    "old_version",
    [
        "stable_id_unique_selection:2",
        "evidence_backed_shortlisting:2",
        "evidence_backed_shortlisting:3",
        "evidence_backed_shortlisting:4",
        "evidence_backed_shortlisting:5",
        "evidence_backed_shortlisting:10",
        "evidence_backed_shortlisting:15",
        "evidence_backed_shortlisting:16",
        "evidence_backed_shortlisting:17",
        "evidence_backed_shortlisting:7",
    ],
)
def test_old_selection_version_cannot_match_a_new_cache_key(old_version: str) -> None:
    expected = {
        "insight_selection_version": (
            artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION
        ),
        "prompts": {},
    }
    matched, reason = _artifact_cache_meta_matches(
        cached_meta={
            "key": "new-cache-key",
            "insight_selection_version": old_version,
        },
        expected_cache_meta=expected,
        cache_key="new-cache-key",
    )

    assert matched is False
    assert reason == "insight_selection_version_mismatch"
