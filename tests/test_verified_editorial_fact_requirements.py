from copy import deepcopy

import pytest

from src.generators.artifact_normalization import (
    final_insight_editorial_coverage,
    validate_verified_editorial_plan,
    validate_verified_editorial_plan_revision,
)
from src.utils.errors import AppError


def _plan():
    return {
        "report_thesis": "Two decision signals.",
        "material_limitation_evidence_ids": [],
        "themes": [
            {
                "theme": "One",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop the complete signal.",
                "evidence_ids": ["f1", "f2", "f3"],
                "required_evidence_ids": ["f1"],
                "alternative_evidence_groups": [["f2", "f3"]],
                "feasible_candidate_ids": ["c1", "c2", "c3"],
            },
            {
                "theme": "Two",
                "priority": 2,
                "importance": "optional",
                "coverage_obligation": "Develop the other signal.",
                "evidence_ids": ["f4"],
                "required_evidence_ids": ["f4"],
                "alternative_evidence_groups": [],
                "feasible_candidate_ids": ["c4"],
            },
        ],
    }


def _arguments():
    return {
        "canonical_evidence_ids": {"f1", "f2", "f3", "f4"},
        "admitted_candidate_ids": {"c1", "c2", "c3", "c4"},
        "admitted_limitation_evidence_ids": set(),
        "admitted_candidate_evidence_ids": {
            "c1": {"f1"},
            "c2": {"f2"},
            "c3": {"f3"},
            "c4": {"f4"},
        },
    }


def test_selection_requires_mandatory_fact_and_one_declared_alternative():
    candidates = [{"id": f"c{n}", "evidence_id": f"f{n}"} for n in range(1, 5)]
    missing = final_insight_editorial_coverage(
        final_insights=[candidates[1]],
        candidate_insights=candidates,
        editorial_plan=_plan(),
    )
    covered = final_insight_editorial_coverage(
        final_insights=[candidates[0], candidates[2]],
        candidate_insights=candidates,
        editorial_plan=_plan(),
    )
    assert "One" in missing["omitted_essential_themes"]
    assert "One" not in covered["omitted_essential_themes"]


def test_verified_plan_preserves_required_and_alternative_fact_decisions():
    plan = validate_verified_editorial_plan(_plan(), **_arguments())
    assert plan["themes"][0]["required_evidence_ids"] == ["f1"]
    assert plan["themes"][0]["alternative_evidence_groups"] == [["f2", "f3"]]


def test_verified_plan_rejects_a_missing_decision_array():
    plan = _plan()
    del plan["themes"][0]["alternative_evidence_groups"]
    with pytest.raises(AppError):
        validate_verified_editorial_plan(plan, **_arguments())


@pytest.mark.parametrize("theme_index", [0, 1])
def test_new_verified_plan_requires_fact_decisions_for_each_theme(theme_index):
    plan = _plan()
    del plan["themes"][theme_index]["required_evidence_ids"]
    del plan["themes"][theme_index]["alternative_evidence_groups"]
    with pytest.raises(AppError) as error:
        validate_verified_editorial_plan(
            plan, **_arguments(), require_fact_requirements=True
        )
    assert error.value.context["planning_contract_failure"] is True


def test_legacy_verified_plan_without_fact_decisions_remains_valid():
    plan = _plan()
    for theme in plan["themes"]:
        del theme["required_evidence_ids"]
        del theme["alternative_evidence_groups"]
    assert validate_verified_editorial_plan(plan, **_arguments())


def test_new_verified_plan_accepts_explicit_fact_decisions():
    result = validate_verified_editorial_plan(
        _plan(), **_arguments(), require_fact_requirements=True
    )
    assert result["themes"][0]["alternative_evidence_groups"] == [["f2", "f3"]]


def test_verified_plan_rejects_unavailable_indispensable_fact():
    arguments = _arguments()
    arguments["admitted_candidate_evidence_ids"]["c1"] = {"f4"}
    with pytest.raises(AppError):
        validate_verified_editorial_plan(_plan(), **arguments)


def test_verified_plan_rejects_alternative_group_without_an_admitted_candidate():
    arguments = _arguments()
    arguments["admitted_candidate_evidence_ids"]["c2"] = {"f4"}
    arguments["admitted_candidate_evidence_ids"]["c3"] = {"f4"}
    with pytest.raises(AppError):
        validate_verified_editorial_plan(_plan(), **arguments)


def test_verified_plan_accepts_one_available_alternative():
    arguments = _arguments()
    arguments["admitted_candidate_evidence_ids"]["c2"] = {"f4"}
    assert validate_verified_editorial_plan(_plan(), **arguments)


@pytest.mark.parametrize(
    "required,groups",
    [
        (["f1"], [["f2", "unknown"]]),
        (["f1", "f1"], [["f2", "f3"]]),
        (["f1", "f2"], [["f2", "f3"]]),
        (["f1"], [["f2"]]),
        (["f1"], [["f2", "f2"]]),
        (["f1"], []),
    ],
)
def test_verified_plan_rejects_invalid_fact_decisions(required, groups):
    plan = _plan()
    plan["themes"][0]["required_evidence_ids"] = required
    plan["themes"][0]["alternative_evidence_groups"] = groups
    with pytest.raises(AppError):
        validate_verified_editorial_plan(plan, **_arguments())


def test_replan_cannot_weaken_an_original_required_fact():
    original = _plan()
    revised = deepcopy(original)
    revised["themes"][0]["required_evidence_ids"] = []
    revised["themes"][0]["alternative_evidence_groups"] = [["f1", "f2", "f3"]]
    with pytest.raises(AppError):
        validate_verified_editorial_plan_revision(original, revised, **_arguments())


def test_replan_can_choose_one_original_alternative_as_required():
    original = _plan()
    revised = deepcopy(original)
    revised["themes"][0]["required_evidence_ids"] = ["f1", "f2"]
    revised["themes"][0]["alternative_evidence_groups"] = []
    revised["themes"][0]["evidence_ids"] = ["f1", "f2"]
    assert validate_verified_editorial_plan_revision(original, revised, **_arguments())
