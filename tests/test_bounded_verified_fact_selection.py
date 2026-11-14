import pytest

from src.generators.artifact_normalization import select_artifact_insights


@pytest.mark.parametrize("verified_mode", [False, True])
def test_bounded_selection_prioritizes_essential_fact_requirements(verified_mode):
    plan = {
        "report_thesis": "Two signals.",
        "themes": [
            {
                "theme": "Essential",
                "priority": 1,
                "importance": "essential",
                "evidence_ids": ["f1", "f2", "f3"],
                "required_evidence_ids": ["f1"],
                "alternative_evidence_groups": [["f2", "f3"]],
            },
            {
                "theme": "Optional",
                "priority": 2,
                "importance": "optional",
                "evidence_ids": ["f4"],
                "required_evidence_ids": ["f4"],
                "alternative_evidence_groups": [],
            },
        ],
    }
    candidates = [
        {
            "id": "c4",
            "evidence_id": "f4",
            "text": "Other signal",
            "relevance_score": 0.9,
        },
        {
            "id": "c1",
            "evidence_id": "f1",
            "text": "First signal",
            "relevance_score": 1.0,
        },
        {
            "id": "c2",
            "evidence_id": "f2",
            "text": "Second signal",
            "relevance_score": 0.1,
        },
        {
            "id": "c3",
            "evidence_id": "f3",
            "text": "Third signal",
            "relevance_score": 0.5,
        },
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=[],
        editorial_plan=plan,
        max_count=2,
        verified_mode=verified_mode,
    )

    assert [item["id"] for item in selected] == ["c1", "c2"]


def test_bounded_selection_recognizes_a_multi_fact_candidate():
    plan = {
        "report_thesis": "Two signals.",
        "themes": [
            {
                "theme": "Essential",
                "priority": 1,
                "importance": "essential",
                "evidence_ids": ["f1", "f2", "f3"],
                "required_evidence_ids": ["f1"],
                "alternative_evidence_groups": [["f2", "f3"]],
            },
            {
                "theme": "Optional",
                "priority": 2,
                "importance": "optional",
                "evidence_ids": ["f4"],
            },
        ],
    }
    candidates = [
        {
            "id": "c1",
            "evidence_id": "f1",
            "evidence_ids": ["f1", "f2"],
            "text": "Combined signal",
        },
        {"id": "c3", "evidence_id": "f3", "text": "Alternative signal"},
        {"id": "c4", "evidence_id": "f4", "text": "Other signal"},
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=[],
        editorial_plan=plan,
        max_count=2,
    )

    assert [item["id"] for item in selected] == ["c1", "c4"]
