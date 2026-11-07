from __future__ import annotations

import pytest

from src.generators.artifact_normalization import (
    validate_substantive_editorial_theme_coverage,
)
from src.utils.errors import AppError


def _coverage_plan() -> dict:
    return {
        "themes": [
            {
                "theme": "Theme 1",
                "importance": "essential",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            },
            {
                "theme": "Theme 2",
                "importance": "optional",
                "evidence_ids": ["verified-fact:f2"],
            },
        ]
    }


def _assessment(theme: str, *, status: str, resolution: str, ids: list[str]) -> dict:
    return {
        "theme": theme,
        "status": status,
        "resolution": resolution,
        "supporting_insight_ids": ids,
        "explanation": f"The final prose addresses {theme}.",
    }


def test_verified_replan_requires_the_complete_original_fact_union() -> None:
    obligations = [
        {
            "theme": "Theme 1",
            "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            "importance": "essential",
            "coverage_obligation": "Develop the comparison across both facts.",
        }
    ]
    payload = {
        "theme_coverage": [
            _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
            _assessment("Theme 2", status="covered", resolution="retained", ids=["i2"]),
        ],
        "report_completeness": "complete",
        "diagnosis": "planned_theme_execution",
        "recovery_action": "none",
        "original_essential_obligation_assessments": [
            {
                "theme": "Theme 1",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "status": "covered",
                "supporting_insight_ids": ["i1"],
                "explanation": "Only the first side of the comparison is present.",
            }
        ],
    }

    with pytest.raises(AppError, match="fully linked") as error:
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=[
                {
                    "id": "i1",
                    "text": "Signal one.",
                    "evidence_ids": ["verified-fact:f1"],
                },
                {
                    "id": "i2",
                    "text": "Signal two.",
                    "evidence_ids": ["verified-fact:f2"],
                },
            ],
            original_essential_obligations=obligations,
            require_original_obligation_assessment=True,
        )
    assert error.value.context["missing_evidence_ids"] == ["verified - fact:f2"]

    payload["original_essential_obligation_assessments"][0][
        "supporting_insight_ids"
    ] = ["i1", "i2"]
    result = validate_substantive_editorial_theme_coverage(
        payload=payload,
        editorial_plan=_coverage_plan(),
        final_insights=[
            {"id": "i1", "text": "Signal one.", "evidence_ids": ["verified-fact:f1"]},
            {"id": "i2", "text": "Signal two.", "evidence_ids": ["verified-fact:f2"]},
        ],
        original_essential_obligations=obligations,
        require_original_obligation_assessment=True,
    )
    assert result["original_essential_obligation_assessments"][0]["status"] == (
        "covered"
    )
