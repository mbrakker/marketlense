from __future__ import annotations

import pytest

from src.generators import artifact_normalization
from src.generators._artifact_generator.storage import _artifact_cache_meta_matches
from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
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


def test_selector_keeps_identical_public_claim_when_metric_binding_differs() -> None:
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

    selected = select_artifact_insights(
        final_insights=[first, second],
        candidate_insights=[],
        editorial_plan=_plan("f1", "f2"),
    )

    assert [item["id"] for item in selected] == ["installs", "sessions"]


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


def test_selection_version_invalidates_the_previous_shortlisting_behavior() -> None:
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION != (
        "stable_id_unique_selection:2"
    )
    assert artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION != (
        "evidence_backed_shortlisting:1"
    )


def test_old_selection_version_cannot_match_a_new_cache_key() -> None:
    expected = {
        "insight_selection_version": (
            artifact_normalization.ARTIFACT_INSIGHT_SELECTION_VERSION
        ),
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
