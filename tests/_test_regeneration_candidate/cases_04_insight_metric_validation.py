from __future__ import annotations

from .cases_02_candidate_lineage import (
    _retained_artifact_and_evidence,
    deepcopy,
    validate_insight_metrics,
)


def test_candidate_blocks_unsupported_more_than_doubled_language() -> None:
    artifacts, _ = _retained_artifact_and_evidence()
    insight = deepcopy(artifacts["insights_final"][0])
    insight["text"] = "The reported spending power more than doubled."

    issues = validate_insight_metrics(
        insights=[insight],
        evidence_map={insight["evidence_id"]: insight["evidence"]},
    )

    assert any(
        issue.severity == "error" and "more than doubled" in issue.message
        for issue in issues
    )


__all__ = ["test_candidate_blocks_unsupported_more_than_doubled_language"]
