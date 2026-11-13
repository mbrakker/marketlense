from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators._artifact_generator.generation import (
    _build_semantic_repair_scope,
    _merge_scoped_insight_repair,
    _validate_scoped_insight_patch,
    _verified_semantic_repair_focal_facts,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure
from tests._test_artifact_generator._shared import _ctx


def _candidate(candidate_id: str, fact_id: str, *, score: float = 0.9) -> dict:
    evidence_id = f"verified-fact:{fact_id}"
    return {
        "id": candidate_id,
        "text": f"Source finding for {fact_id}.",
        "evidence_id": evidence_id,
        "evidence_ids": [evidence_id],
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
            "observations": [{"cohort": "all buyers", "value": "42%"}],
        },
        "score": score,
        "verified_fact_id": fact_id,
    }


def _fact(fact_id: str, statement: str, *, qualifier: str) -> dict:
    return {
        "fact_id": fact_id,
        "statement": statement,
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
            "observations": [
                {"cohort": "all buyers", "value": "42%"},
                {"cohort": "repeat buyers", "value": "58%"},
            ],
        },
        "qualifiers": [qualifier],
    }


def _plan() -> dict:
    return {
        "themes": [
            {
                "theme": "Demand comparison",
                "importance": "essential",
                "coverage_obligation": (
                    "Develop both populations and preserve the directional comparison."
                ),
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "feasible_candidate_ids": ["candidate-1", "candidate-2"],
                "merge_group": "demand",
            },
            {
                "theme": "Qualified signal",
                "importance": "essential",
                "coverage_obligation": "Retain the conditional source limitation.",
                "evidence_ids": ["verified-fact:f3"],
                "feasible_candidate_ids": ["candidate-3"],
                "merge_group": "",
            },
            {
                "theme": "Optional context",
                "importance": "optional",
                "coverage_obligation": "Use only if distinct.",
                "evidence_ids": ["verified-fact:f4"],
                "feasible_candidate_ids": ["candidate-4"],
                "merge_group": "",
            },
        ]
    }


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


def test_material_gap_can_repair_exact_unselected_fact_when_themes_are_covered(
) -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    current = [
        {
            "id": "candidate-1",
            "text": "Demand comparison.",
            "evidence_id": "verified-fact:f1",
        },
        {
            "id": "candidate-3",
            "text": "Qualified signal.",
            "evidence_id": "verified-fact:f3",
        },
        {
            "id": "candidate-4",
            "text": "Optional context.",
            "evidence_id": "verified-fact:f4",
        },
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Demand comparison",
                    "status": "covered",
                    "supporting_insight_ids": ["candidate-1"],
                    "explanation": "Only the first population is developed.",
                },
                {
                    "theme": "Qualified signal",
                    "status": "covered",
                    "supporting_insight_ids": ["candidate-3"],
                    "explanation": "The limitation is developed.",
                },
                {
                    "theme": "Optional context",
                    "status": "covered",
                    "supporting_insight_ids": ["candidate-4"],
                    "explanation": "The context is distinct.",
                },
            ],
            "report_completeness": "incomplete",
            "diagnosis": "material_report_completeness",
            "recovery_action": "targeted_rewrite",
        },
        error_context={
            "material_gaps": [
                {
                    "verified_fact_ids": ["f2"],
                    "evidence_ids": ["verified-fact:f2"],
                    "final_insight_ids": [],
                    "explanation": "The second population is absent.",
                }
            ]
        },
        current_insights=current,
        candidate_insights=candidates,
    )

    assert scope["mode"] == "targeted_rewrite"
    assert scope["targeted_insight_ids"] == []
    assert scope["allowed_addition_candidate_ids"] == ["candidate-2"]
    assert scope["affected_themes"] == ["Demand comparison"]
    patch = [
        {
            "id": "candidate-2",
            "text": "Repeat buyers move differently from all buyers.",
            "evidence_id": "verified-fact:f2",
        }
    ]
    _validate_scoped_insight_patch(
        {"insights_final": patch},
        repair_scope=scope,
        candidate_insights=candidates,
    )
    merged = _merge_scoped_insight_repair(
        current_insights=current,
        repaired_insights=patch,
        repair_scope=scope,
    )
    assert [item["id"] for item in merged] == [
        "candidate-1",
        "candidate-3",
        "candidate-4",
        "candidate-2",
    ]


def test_report_level_material_gap_authorizes_only_exact_bound_candidate() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    candidates.append(_candidate("candidate-5", "f5"))
    current = [
        {
            "id": "candidate-1",
            "text": "Demand comparison.",
            "evidence_id": "verified-fact:f1",
        },
        {
            "id": "candidate-3",
            "text": "Qualified signal.",
            "evidence_id": "verified-fact:f3",
        },
        {
            "id": "candidate-4",
            "text": "Optional context.",
            "evidence_id": "verified-fact:f4",
        },
    ]
    assessment = {
        "theme_coverage": [
            {
                "theme": theme["theme"],
                "status": "covered",
                "supporting_insight_ids": [candidate_id],
                "explanation": "The planned theme is developed.",
            }
            for theme, candidate_id in zip(
                _plan()["themes"],
                ["candidate-1", "candidate-3", "candidate-4"],
                strict=True,
            )
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
    }
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment=assessment,
        error_context={
            "material_gaps": [
                {
                    "verified_fact_ids": ["f5"],
                    "evidence_ids": ["verified-fact:f5"],
                    "final_insight_ids": [],
                    "explanation": "A report-level source proposition is absent.",
                }
            ]
        },
        current_insights=current,
        candidate_insights=candidates,
    )

    assert scope["mode"] == "targeted_rewrite"
    assert scope["affected_themes"] == []
    assert scope["allowed_addition_candidate_ids"] == ["candidate-5"]
    assert scope["material_gap_scopes"][0]["theme"] == ""
    assert scope["material_gap_scopes"][0]["authorized_candidate_ids"] == [
        "candidate-5"
    ]


@pytest.mark.parametrize(
    "gap",
    [
        {
            "verified_fact_ids": ["f9"],
            "evidence_ids": ["verified-fact:f9"],
            "final_insight_ids": [],
            "explanation": "No admitted candidate supports this proposition.",
        },
        {
            "verified_fact_ids": ["f2"],
            "evidence_ids": [],
            "final_insight_ids": [],
            "explanation": "The evidence binding is incomplete.",
        },
    ],
)
def test_unrepairable_material_gap_fails_closed(gap: dict) -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    current = [
        {
            "id": "candidate-1",
            "text": "Demand.",
            "evidence_id": "verified-fact:f1",
        },
        {
            "id": "candidate-3",
            "text": "Signal.",
            "evidence_id": "verified-fact:f3",
        },
        {
            "id": "candidate-4",
            "text": "Context.",
            "evidence_id": "verified-fact:f4",
        },
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": theme["theme"],
                    "status": "covered",
                    "supporting_insight_ids": [candidate_id],
                    "explanation": "Covered.",
                }
                for theme, candidate_id in zip(
                    _plan()["themes"],
                    ["candidate-1", "candidate-3", "candidate-4"],
                    strict=True,
                )
            ],
            "report_completeness": "incomplete",
            "diagnosis": "material_report_completeness",
            "recovery_action": "targeted_rewrite",
        },
        error_context={"material_gaps": [gap]},
        current_insights=current,
        candidate_insights=candidates,
    )

    assert scope["mode"] == "fail_closed"
    assert scope["allowed_addition_candidate_ids"] == []


def test_focal_context_preserves_complete_fact_and_exact_bindings() -> None:
    candidate = _candidate("candidate-2", "f2")
    facts = [_fact("f2", "Repeat buyers reached 58%.", qualifier="Observed in 2026.")]
    scope = {
        "authorized_candidate_ids": ["candidate-2"],
        "targeted_insight_ids": ["candidate-1"],
        "allowed_addition_candidate_ids": ["candidate-2"],
    }
    focal = _verified_semantic_repair_focal_facts(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The repeat-buyer proposition is missing.",
            }
        ],
        repair_scope=scope,
        verified_facts=facts,
        candidate_insights=[candidate],
        current_insights=[
            {"id": "candidate-1", "evidence_id": "verified-fact:f2"}
        ],
    )

    assert focal == [
        {
            "fact_id": "f2",
            "statement": "Repeat buyers reached 58%.",
            "metric": facts[0]["metric"],
            "qualifiers": ["Observed in 2026."],
            "evidence_id": "verified-fact:f2",
            "authorized_candidate_ids": ["candidate-2"],
            "affected_final_insight_ids": ["candidate-1"],
            "gap_explanation": "The repeat-buyer proposition is missing.",
        }
    ]


def test_scoped_repair_rejections_have_bounded_actionable_context() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
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
    cases = [
        ({"insights_final": []}, "field", "insights_final"),
        (
            {
                "insights_final": [
                    {
                        "id": "candidate-4",
                        "text": "Wrong.",
                        "evidence_id": "verified-fact:f4",
                    }
                ]
            },
            "invalid_insight_ids",
            "candidate-4",
        ),
        (
            {
                "insights_final": [
                    {
                        "id": "candidate-1",
                        "text": "A.",
                        "evidence_id": "verified-fact:f1",
                    },
                    {
                        "id": "candidate-1",
                        "text": "B.",
                        "evidence_id": "verified-fact:f1",
                    },
                ]
            },
            "duplicate_insight_ids",
            "candidate-1",
        ),
        (
            {
                "insights_final": [
                    {
                        "id": "candidate-1",
                        "text": "Wrong binding.",
                        "evidence_id": "verified-fact:f2",
                    }
                ]
            },
            "mismatched_primary_evidence_ids",
            "candidate-1",
        ),
    ]
    for payload, expected_key, expected_value in cases:
        with pytest.raises(AppError) as exc_info:
            _validate_scoped_insight_patch(
                payload,
                repair_scope=scope,
                candidate_insights=candidates,
            )
        context = exc_info.value.context
        assert context["rule_id"].startswith("verified_insight_repair.")
        assert context["field"]
        assert expected_value in context.get(expected_key, [context.get(expected_key)])
        assert "repair_scope" not in context
        assert "authorized_ids" not in context


def test_scoped_metric_conflict_and_unchanged_merge_are_diagnosable() -> None:
    candidates = [_candidate("candidate-1", "f1")]
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f1"],
                "evidence_ids": ["verified-fact:f1"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The comparison wording is incomplete.",
            }
        ],
        candidate_insights=candidates,
    )
    conflicting = deepcopy(candidates[0])
    conflicting["metric"] = {**conflicting["metric"], "value": "99%"}
    with pytest.raises(AppError) as exc_info:
        _validate_scoped_insight_patch(
            {"insights_final": [conflicting]},
            repair_scope=scope,
            candidate_insights=candidates,
        )
    assert exc_info.value.context["rule_id"] == (
        "verified_insight_repair.protected_metric"
    )
    assert exc_info.value.context["field"] == "insights_final.metric"
    assert "value" in exc_info.value.context["protected_dimensions"]

    with pytest.raises(AppError) as unchanged:
        _merge_scoped_insight_repair(
            current_insights=[deepcopy(candidates[0])],
            repaired_insights=[deepcopy(candidates[0])],
            repair_scope=scope,
        )
    assert unchanged.value.context["rule_id"] == "verified_insight_repair.merge"
    assert unchanged.value.context["status"] == "unchanged"


def test_scoped_repair_diagnostic_survives_structured_output_failure_path() -> None:
    def validate_payload(payload: dict) -> None:
        del payload
        raise AppError(
            code="artifact_final_insight_repair_invalid",
            message="Localized patch used an unauthorized candidate",
            context={
                "rule_id": "verified_insight_repair.authorized_id",
                "field": "insights_final.id",
                "invalid_insight_ids": ["candidate-4"],
            },
        )

    def call_model(mode: str, original_response: str, schema_errors: str):
        del mode, original_response, schema_errors
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"insights_final": [{"id": "candidate-4"}]}),
            model="gpt-5-mini",
        )

    request = StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="scoped-repair-diagnostic",
        artifact_family="insights_final",
        schema_name="artifacts",
        model="gpt-5-mini",
        terminal_failure_code="artifact_final_insight_repair_invalid",
    )
    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            request,
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=validate_payload,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    context = exc_info.value.context
    assert context["rule_id"] == "verified_insight_repair.authorized_id"
    assert context["field"] == "insights_final.id"
    assert context["invalid_insight_ids"] == ["candidate-4"]
    assert context["repair_attempt"] == 2
    assert len(context["attempt_diagnostics"]) == 3

