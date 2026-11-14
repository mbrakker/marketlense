from src.generators.artifact_normalization import select_artifact_insights


def test_final_null_evidence_ids_do_not_survive_candidate_restoration() -> None:
    candidate = {
        "id": "i1",
        "text": "Source-backed finding.",
        "evidence_id": "f1",
        "evidence": "Supporting source.",
        "pages": [3],
        "metric": {},
    }
    final = {**candidate, "text": "Editorial rewrite.", "evidence_ids": None}
    selected = select_artifact_insights(
        final_insights=[final],
        candidate_insights=[candidate],
        editorial_plan={
            "report_thesis": "Two signals.",
            "themes": [
                {"theme": "One", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Two", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
    )
    assert len(selected) == 1
    assert selected[0]["text"] == "Editorial rewrite."
    assert selected[0]["evidence_id"] == "f1"
    assert selected[0]["pages"] == [3]
    assert "evidence_ids" not in selected[0]


def test_null_final_ids_restore_candidate_multifact_binding() -> None:
    candidate = {
        "id": "i1",
        "text": "Source-backed finding.",
        "evidence_id": "f1",
        "evidence_ids": ["f1", "f2"],
        "evidence": "Supporting source.",
        "pages": [3],
        "metric": {},
    }
    selected = select_artifact_insights(
        final_insights=[{**candidate, "evidence_ids": None}],
        candidate_insights=[candidate],
        editorial_plan={
            "report_thesis": "Signals.",
            "themes": [
                {"theme": "One", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Two", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
    )
    assert selected[0]["evidence_ids"] == ["f1", "f2"]
