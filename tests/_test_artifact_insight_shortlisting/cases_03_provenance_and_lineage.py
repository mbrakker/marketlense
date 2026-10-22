from __future__ import annotations

import pytest

from src.generators.artifact_normalization import (
    eligible_final_insight_candidates,
    select_artifact_insights,
    validate_final_insight_candidate_lineage,
)
from src.utils.errors import AppError


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


def test_selector_rejects_shared_top_level_text_with_disjoint_physical_spans() -> None:
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    shared_text = "The source reports 42% for surveyed respondents."
    first = _insight(
        "shared",
        "f1",
        "The first proposition.",
        score=0.99,
        metric=metric,
        evidence=shared_text,
        pages=[4],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 4,
                "start_offset": 10,
                "end_offset": 25,
                "text": shared_text,
            }
        ],
    )
    second = _insight(
        "shared",
        "f1",
        "The second proposition.",
        score=0.01,
        metric=metric,
        evidence=shared_text,
        pages=[9],
        evidence_spans=[
            {
                "evidence_id": "f1",
                "source_pack": "findings",
                "page": 9,
                "start_offset": 10,
                "end_offset": 25,
                "text": shared_text,
            }
        ],
    )

    assert (
        select_artifact_insights(
            final_insights=[],
            candidate_insights=[first, second],
            editorial_plan=_plan("f1", "f2"),
        )
        == []
    )


def test_selector_rejects_identical_span_text_with_disjoint_offsets() -> None:
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    shared_text = "The source reports 42% for surveyed respondents."
    candidates = [
        _insight(
            "shared",
            "f1",
            "The first proposition.",
            score=0.99,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "page": 4,
                    "start_offset": 10,
                    "end_offset": 25,
                    "text": shared_text,
                }
            ],
        ),
        _insight(
            "shared",
            "f1",
            "The second proposition.",
            score=0.01,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "page": 4,
                    "start_offset": 40,
                    "end_offset": 55,
                    "text": shared_text,
                }
            ],
        ),
    ]

    assert (
        select_artifact_insights(
            final_insights=[],
            candidate_insights=candidates,
            editorial_plan=_plan("f1", "f2"),
        )
        == []
    )


def test_selector_rejects_conflicting_span_source_ids_despite_matching_text() -> None:
    shared_text = "The source reports 42% for surveyed respondents."
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    candidates = [
        _insight(
            "shared",
            "f1",
            "The first proposition.",
            score=0.9,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "source_identity": "source-a",
                    "page": 4,
                    "start_offset": 10,
                    "end_offset": 25,
                    "text": shared_text,
                }
            ],
        ),
        _insight(
            "shared",
            "f1",
            "The second proposition.",
            score=0.1,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "source_identity": "source-b",
                    "page": 4,
                    "start_offset": 10,
                    "end_offset": 25,
                    "text": shared_text,
                }
            ],
        ),
    ]

    assert (
        select_artifact_insights(
            final_insights=[],
            candidate_insights=candidates,
            editorial_plan=_plan("f1", "f2"),
        )
        == []
    )


def test_eligible_final_pool_excludes_conflicting_same_id_provenance() -> None:
    shared_text = "The source reports 42% for surveyed respondents."
    metric = {"label": "Respondent share", "value": "42%", "unit": "%"}
    candidates = [
        _insight(
            "prior-final",
            "f1",
            "Candidate supported by source A.",
            score=0.1,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "source_identity": "source-a",
                    "page": 4,
                    "start_offset": 10,
                    "end_offset": 25,
                    "text": shared_text,
                }
            ],
        ),
        _insight(
            "prior-final",
            "f1",
            "Candidate supported by source B.",
            score=0.9,
            metric=metric,
            evidence=shared_text,
            pages=[4],
            evidence_spans=[
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "source_identity": "source-b",
                    "page": 4,
                    "start_offset": 10,
                    "end_offset": 25,
                    "text": shared_text,
                }
            ],
        ),
    ]

    assert eligible_final_insight_candidates(candidates) == []


def test_final_selection_rejects_unbound_final_identity_and_uses_alternative() -> None:
    final = _insight(
        "behavior-high-value-research",
        "final-only",
        "A final rewrite with no candidate lineage.",
        score=0.99,
    )
    candidate = _insight(
        "behavior-cross-check",
        "f1",
        "The eligible candidate survives final admission.",
        score=0.4,
        pages=[18],
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
        require_final_candidate_lineage=True,
    )

    assert [item["id"] for item in selected] == ["behavior-cross-check"]


def test_final_selection_preserves_editorial_rewrite_for_eligible_identity() -> None:
    candidate = _insight(
        "behavior-cross-check",
        "f1",
        "Candidate wording.",
        score=0.4,
        metric={"label": "Share", "value": "42%", "unit": "%"},
        pages=[18],
    )
    final = _insight(
        "behavior-cross-check",
        "wrong-final-id",
        "Approved final editorial wording.",
        score=0.1,
        metric={"label": "Share", "value": "99%", "unit": "%"},
    )

    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan=_plan("f1", "f2"),
        require_final_candidate_lineage=True,
    )

    assert len(selected) == 1
    assert selected[0]["id"] == "behavior-cross-check"
    assert selected[0]["text"] == "Approved final editorial wording."
    assert selected[0]["evidence_id"] == "f1"
    assert selected[0]["metric"]["value"] == "42%"


def test_final_lineage_validation_reports_unmatched_identity_before_fallback() -> None:
    candidate = _insight(
        "behavior-cross-check",
        "f1",
        "The eligible candidate survives final admission.",
        score=0.4,
        pages=[18],
    )
    final = _insight(
        "behavior-high-value-research",
        "f1",
        "An unmatched final rewrite.",
        score=0.99,
    )

    with pytest.raises(AppError) as captured:
        validate_final_insight_candidate_lineage(
            final_insights=[final], candidate_insights=[candidate]
        )

    assert captured.value.code == "artifact_final_insight_lineage_invalid"
    assert captured.value.context["invalid_insight_ids"] == [
        "behavior-high-value-research"
    ]


def test_final_lineage_validation_reports_missing_identity() -> None:
    candidate = _insight(
        "behavior-cross-check",
        "f1",
        "The eligible candidate survives final admission.",
        score=0.4,
    )
    final = _insight(
        "",
        "f1",
        "A final rewrite without a stable identity.",
        score=0.99,
    )

    with pytest.raises(AppError) as captured:
        validate_final_insight_candidate_lineage(
            final_insights=[final], candidate_insights=[candidate]
        )

    assert captured.value.code == "artifact_final_insight_lineage_invalid"
    assert captured.value.context["missing_insight_id"] is True
