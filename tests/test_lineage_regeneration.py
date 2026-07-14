from __future__ import annotations

import pytest

from src.utils.errors import AppError
from src.utils.lineage_regeneration import (
    build_lineage_regeneration_quality_report,
    plan_lineage_regeneration,
)


@pytest.mark.parametrize(
    ("change_kind", "resume_from_stage", "avoided_work"),
    [
        ("template", "analysis_complete", "model_generation"),
        ("prompt", "selection_complete", "crop_rendering"),
        ("model", "selection_complete", "crop_rendering"),
        ("crop", "source_prepared", "ocr"),
        ("source", "", ""),
    ],
)
def test_lineage_regeneration_plan_selects_the_minimum_safe_stage(
    change_kind: str,
    resume_from_stage: str,
    avoided_work: str,
) -> None:
    plan = plan_lineage_regeneration(
        change_kind=change_kind,
        lineage_available=True,
    )

    assert plan.resume_from_stage == resume_from_stage
    assert plan.full_regeneration_required is (change_kind == "source")
    if avoided_work:
        assert avoided_work in plan.avoided_work
    else:
        assert plan.avoided_work == []


def test_lineage_regeneration_fails_closed_when_lineage_is_missing() -> None:
    with pytest.raises(AppError) as exc_info:
        plan_lineage_regeneration(change_kind="template", lineage_available=False)

    assert exc_info.value.code == "lineage_regeneration_lineage_missing"
    assert exc_info.value.retryable is False


def test_lineage_quality_reports_known_avoided_cost_only_when_complete() -> None:
    plan = plan_lineage_regeneration(change_kind="template", lineage_available=True)

    unpriced = build_lineage_regeneration_quality_report(plan)
    priced = build_lineage_regeneration_quality_report(
        plan,
        avoided_work_costs_usd={work: 0.01 for work in plan.avoided_work},
    )

    assert unpriced.cost_status == "unpriced"
    assert unpriced.estimated_avoided_cost_usd is None
    assert priced.cost_status == "known"
    assert priced.estimated_avoided_cost_usd == 0.05
    assert priced.reused_stage_count == 3
    assert priced.regenerated_stage_count == 1
