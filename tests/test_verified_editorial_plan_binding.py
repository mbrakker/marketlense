from __future__ import annotations

import pytest

from src.generators.artifact_normalization import validate_verified_editorial_plan
from src.utils.errors import AppError


def _plan() -> dict:
    return {
        "report_thesis": "The report contains distinct decision signals.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "importance": "essential",
                "coverage_obligation": f"Develop proposition {index}.",
                "evidence_ids": [f"verified-fact:f{index}"],
                "feasible_candidate_ids": [f"candidate-{index}"],
            }
            for index in range(1, 3)
        ],
        "material_limitation_evidence_ids": [],
    }


def _validate(plan: dict, bindings: dict[str, set[str]] | None = None) -> dict:
    admitted_bindings = bindings or {
        "candidate-1": {"verified-fact:f1"},
        "candidate-2": {"verified-fact:f2"},
    }
    return validate_verified_editorial_plan(
        plan,
        canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
        admitted_candidate_ids={"candidate-1", "candidate-2"},
        admitted_limitation_evidence_ids=set(),
        admitted_candidate_evidence_ids=admitted_bindings,
    )


def test_verified_plan_derives_candidate_bindings_from_canonical_fact_evidence() -> (
    None
):
    plan = _plan()
    for theme in plan["themes"]:
        theme["feasible_candidate_ids"] = []

    normalized = _validate(plan)

    assert [theme["feasible_candidate_ids"] for theme in normalized["themes"]] == [
        ["candidate-1"],
        ["candidate-2"],
    ]


def test_verified_plan_ignores_untrusted_candidate_ids_with_authority() -> None:
    plan = _plan()
    del plan["themes"][0]["feasible_candidate_ids"]
    plan["themes"][1]["feasible_candidate_ids"] = ["candidate-1", "invented"]

    normalized = _validate(plan)

    assert [theme["feasible_candidate_ids"] for theme in normalized["themes"]] == [
        ["candidate-1"],
        ["candidate-2"],
    ]


def test_verified_plan_rejects_theme_without_an_admitted_evidence_binding() -> None:
    plan = _plan()
    plan["themes"][1]["importance"] = "optional"
    plan["themes"][1]["evidence_ids"] = ["verified-fact:f2"]

    with pytest.raises(
        AppError, match="exact admitted candidate evidence binding"
    ) as exc_info:
        _validate(plan, {"candidate-1": {"verified-fact:f1"}})

    assert exc_info.value.context["rule_id"] == (
        "verified_editorial_plan.candidate_evidence_binding"
    )
    assert exc_info.value.context["missing_evidence_ids"] == ["verified-fact:f2"]
