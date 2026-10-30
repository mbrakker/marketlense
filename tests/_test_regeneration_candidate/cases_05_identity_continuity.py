# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403
from .cases_02_candidate_lineage import validate_regeneration_candidate


def test_candidate_allows_a_unique_same_family_evidence_continuity_when_id_changes() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed
    assert not any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_when_evidence_match_is_ambiguous() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id-1"
    duplicate = deepcopy(candidate["insights_candidates"][0])
    duplicate["id"] = "normalized-candidate-id-2"
    candidate["insights_candidates"].append(duplicate)

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_without_source_pages() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    original["pages"] = []
    original["evidence_spans"] = []
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"
    candidate["insights_candidates"][0]["pages"] = []
    candidate["insights_candidates"][0]["evidence_spans"] = []

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


__all__ = [name for name in globals() if name.startswith("test_")]
