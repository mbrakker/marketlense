from __future__ import annotations

import pytest

from src.generators.artifact_normalization import (
    validate_substantive_editorial_theme_coverage,
)
from src.utils.errors import AppError


def _verified_material_gap_fixture() -> tuple[
    dict[str, object], list[dict[str, object]], list[dict[str, object]]
]:
    plan = {
        "report_thesis": "The report defines one decision.",
        "material_limitation_evidence_ids": [],
        "themes": [
            {
                "theme": "Primary adoption",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop the adoption decision.",
                "evidence_ids": ["verified-fact:fact-1"],
            }
        ],
    }
    candidates = [
        {
            "id": "insight-1",
            "evidence_id": "verified-fact:fact-1",
            "verified_fact_id": "fact-1",
            "verified_fact": {"fact_id": "fact-1"},
        }
    ]
    final_insights = [{"id": "insight-1", "evidence_id": "verified-fact:fact-1"}]
    return plan, candidates, final_insights


def _incomplete_material_coverage_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "theme_coverage": [
            {
                "theme": "Primary adoption",
                "status": "covered",
                "resolution": "retained",
                "supporting_insight_ids": ["insight-1"],
                "explanation": "The final wording develops the adoption decision.",
            }
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
        "material_gaps": [
            {
                "verified_fact_ids": ["fact-1"],
                "evidence_ids": ["verified-fact:fact-1"],
                "final_insight_ids": ["insight-1"],
                "explanation": (
                    "The source fact's qualifier is not developed in the final wording."
                ),
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_verified_semantic_coverage_returns_source_bound_material_gaps() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()

    with pytest.raises(AppError, match="complete material-report") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload=_incomplete_material_coverage_payload(),
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )

    assert exc_info.value.context["material_gaps"] == [
        {
            "verified_fact_ids": ["fact-1"],
            "evidence_ids": ["verified-fact:fact-1"],
            "final_insight_ids": ["insight-1"],
            "explanation": (
                "The source fact's qualifier is not developed in the final wording."
            ),
        }
    ]


def test_verified_semantic_coverage_requires_gap_when_all_themes_are_covered() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(material_gaps=[])

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_rejects_unknown_material_gap_identity() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        material_gaps=[
            {
                "verified_fact_ids": ["fact-unknown"],
                "evidence_ids": ["verified-fact:fact-unknown"],
                "final_insight_ids": [],
                "explanation": "A source-bound material gap is identified.",
            }
        ]
    )

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_requires_empty_gaps_for_complete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        report_completeness="complete",
        diagnosis="planned_theme_execution",
        recovery_action="none",
    )

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_rejects_none_for_incomplete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(recovery_action="none")

    with pytest.raises(AppError, match="incoherent") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )

    assert exc_info.value.context["assessment_contract_failure"] is True


def test_verified_semantic_coverage_rejects_replan_for_complete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        report_completeness="complete",
        diagnosis="infeasible_plan",
        recovery_action="replan",
        material_gaps=[],
    )

    with pytest.raises(AppError, match="incoherent"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )
