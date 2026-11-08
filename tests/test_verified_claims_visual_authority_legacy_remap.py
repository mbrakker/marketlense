import pytest

from src.generators.artifact_normalization import remap_editorial_plan_to_verified_facts
from src.utils.errors import AppError


def test_verified_fact_context_fails_closed_when_coverage_has_one_mapped_theme():
    plan = {
        "report_thesis": "The report has a planning thesis.",
        "themes": [
            {"theme": "Theme 1", "priority": 1, "evidence_ids": ["finding-1"]},
            {"theme": "Unsupported", "priority": 2, "evidence_ids": ["missing"]},
        ],
    }
    facts = [
        {
            "fact_id": "candidate-1",
            "provenance": {"discovery_evidence_ids": ["finding-1"]},
        }
    ]

    with pytest.raises(AppError, match="Verified-fact editorial coverage"):
        remap_editorial_plan_to_verified_facts(plan, facts)


def test_already_verified_plan_is_idempotent_and_preserves_contract_metadata():
    plan = {
        "schema_version": "verified_editorial_plan:1",
        "plan_identity": "plan-123",
        "report_thesis": "The report has a planning thesis.",
        "themes": [
            {
                "theme": "Theme 1",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Retain the first fact.",
                "evidence_ids": ["verified-fact:candidate-1"],
                "feasible_candidate_ids": ["candidate-1"],
            },
            {
                "theme": "Theme 2",
                "priority": 2,
                "importance": "optional",
                "evidence_ids": ["verified-fact:candidate-2"],
                "merge_group": "group-1",
            },
        ],
        "material_limitation_evidence_ids": ["verified-fact:candidate-2"],
    }
    facts = [
        {"fact_id": "candidate-1"},
        {"fact_id": "candidate-2"},
    ]

    assert remap_editorial_plan_to_verified_facts(plan, facts) == plan
