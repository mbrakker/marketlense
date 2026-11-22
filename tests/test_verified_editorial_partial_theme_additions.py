from __future__ import annotations

import pytest

from src.generators._artifact_generator.generation import (
    _build_semantic_repair_scope,
    _merge_scoped_insight_repair,
    _validate_scoped_insight_patch,
)
from tests.test_verified_editorial_first_pass_and_scoped_repair import _candidate, _plan


def _partial_scope(
    *,
    material_gaps: list[dict] | None,
    candidate_insights: list[dict] | None = None,
) -> dict:
    candidates = candidate_insights or [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    return _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Demand comparison",
                    "status": "partial",
                    "supporting_insight_ids": ["candidate-1"],
                    "explanation": "The second population is not developed.",
                }
            ],
            "diagnosis": "planned_theme_execution",
            "recovery_action": "targeted_rewrite",
        },
        error_context={"material_gaps": material_gaps or []},
        current_insights=[
            {
                "id": "candidate-1",
                "text": "Existing first population insight.",
                "evidence_id": "verified-fact:f1",
            }
        ],
        candidate_insights=candidates,
    )


def test_partial_theme_gap_authorizes_exactly_matching_feasible_addition() -> None:
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ]
    )

    assert scope["allowed_addition_candidate_ids"] == ["candidate-2"]
    assert scope["authorized_candidate_ids"] == ["candidate-1", "candidate-2"]


@pytest.mark.parametrize(
    "material_gaps",
    [
        [
            {
                "verified_fact_ids": ["f9"],
                "evidence_ids": ["verified-fact:f9"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "No matching candidate exists.",
            }
        ],
        [
            {
                "verified_fact_ids": ["f1"],
                "evidence_ids": ["verified-fact:f1"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The existing fact is incomplete.",
            }
        ],
        [],
    ],
)
def test_partial_theme_does_not_authorize_unbound_or_redundant_additions(
    material_gaps: list[dict],
) -> None:
    scope = _partial_scope(material_gaps=material_gaps)

    assert scope["allowed_addition_candidate_ids"] == []
    assert scope["authorized_candidate_ids"] == ["candidate-1"]


def test_partial_theme_rejects_candidate_with_unrelated_exact_binding() -> None:
    candidates = [
        _candidate("candidate-1", "f1"),
        _candidate("candidate-2", "f3"),
    ]
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ],
        candidate_insights=candidates,
    )

    assert scope["allowed_addition_candidate_ids"] == []


def test_partial_theme_authorized_addition_merges_without_mutating_current_roster() -> (
    None
):
    candidates = [_candidate("candidate-1", "f1"), _candidate("candidate-2", "f2")]
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ],
        candidate_insights=candidates,
    )
    patch = [
        {
            "id": "candidate-2",
            "text": "The second population moves in the opposite direction.",
            "evidence_id": "verified-fact:f2",
        }
    ]

    _validate_scoped_insight_patch(
        {"insights_final": patch},
        repair_scope=scope,
        candidate_insights=candidates,
    )
    merged = _merge_scoped_insight_repair(
        current_insights=[
            {
                "id": "candidate-1",
                "text": "Existing first population insight.",
                "evidence_id": "verified-fact:f1",
            }
        ],
        repaired_insights=patch,
        repair_scope=scope,
    )

    assert [item["id"] for item in merged] == ["candidate-1", "candidate-2"]
