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
