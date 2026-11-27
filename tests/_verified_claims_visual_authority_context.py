from src.generators.artifact_normalization import (
    build_verified_fact_doc_map,
    remap_editorial_plan_to_verified_facts,
)


def test_verified_fact_context_removes_discovery_facts_and_omits_unmapped_themes():
    source_doc_map = {
        "doc_id": "report-1",
        "title": "Report title",
        "region": "Global",
        "covered_period": "2026",
        "sections": [
            {
                "id": "section-1",
                "title": "Market signal",
                "summary": "Discovery summary must not flow downstream.",
                "key_points": ["Discovery point."],
                "pages": [4],
            }
        ],
    }
    facts = [
        {
            "fact_id": "candidate-1",
            "provenance": {
                "discovery_candidate_id": "candidate-1",
                "discovery_evidence_ids": ["finding-1"],
            },
        },
        {
            "fact_id": "candidate-2",
            "provenance": {
                "discovery_candidate_id": "candidate-2",
                "discovery_evidence_ids": ["finding-2"],
            },
        },
    ]
    plan = {
        "report_thesis": "The report has a planning thesis.",
        "themes": [
            {"theme": "Theme 1", "priority": 1, "evidence_ids": ["finding-1"]},
            {"theme": "Theme 2", "priority": 2, "evidence_ids": ["missing"]},
            {"theme": "Theme 3", "priority": 3, "evidence_ids": ["finding-2"]},
        ],
    }

    sanitized = build_verified_fact_doc_map(source_doc_map)
    remapped = remap_editorial_plan_to_verified_facts(plan, facts)

    assert sanitized == {
        "schema_version": "verified_fact_context:1.0",
        "doc_id": "report-1",
        "title": "Report title",
        "sections": [{"id": "section-1", "title": "Market signal"}],
    }
    assert [theme["evidence_ids"] for theme in remapped["themes"]] == [
        ["verified-fact:candidate-1"],
        ["verified-fact:candidate-2"],
    ]
