from copy import deepcopy

import pytest

from src.generators.artifact_normalization import resolve_editorial_coverage_challenge
from src.utils.errors import AppError
from tests.test_verified_semantic_completeness_contract import (
    _incomplete_material_coverage_payload,
    _verified_material_gap_fixture,
)


def _context():
    plan, candidates, insights = _verified_material_gap_fixture()
    insights[0]["text"] = "Ad-supported video includes digital TV Everywhere viewing."
    original = _incomplete_material_coverage_payload()
    result = {
        "verdicts": [
            {
                "gap_index": 0,
                "verdict": "refuted",
                "explanation": "The relevant qualification is explicitly present.",
                "supporting_insight_id": "insight-1",
                "supporting_quote": (
                    "Ad-supported video includes digital TV Everywhere viewing."
                ),
            }
        ]
    }
    return plan, candidates, insights, original, result


def _resolve(plan, candidates, insights, original, challenge):
    return resolve_editorial_coverage_challenge(
        original_assessment=original,
        challenge=challenge,
        editorial_plan=plan,
        candidate_insights=candidates,
        final_insights=insights,
    )


def test_refuted_gap_can_use_existing_coverage_validator_without_mutating_review():
    plan, candidates, insights, original, challenge = _context()
    snapshot = deepcopy(original)
    effective = _resolve(plan, candidates, insights, original, challenge)
    assert original == snapshot
    assert effective["report_completeness"] == "complete"
    assert effective["material_gaps"] == []
    assert effective["theme_coverage"] == original["theme_coverage"]


def test_omission_without_nominated_insight_can_be_refuted_by_bound_insight():
    plan, candidates, insights, original, challenge = _context()
    original["material_gaps"][0]["final_insight_ids"] = []
    assert (
        _resolve(plan, candidates, insights, original, challenge)["report_completeness"]
        == "complete"
    )


def test_omission_without_nominated_insight_cannot_use_unrelated_evidence():
    plan, candidates, insights, original, challenge = _context()
    original["material_gaps"][0]["final_insight_ids"] = []
    insights[0]["evidence_id"] = "verified-fact:unrelated"
    with pytest.raises(AppError):
        _resolve(plan, candidates, insights, original, challenge)


def test_nominated_insight_cannot_refute_gap_with_unrelated_evidence():
    plan, candidates, insights, original, challenge = _context()
    insights[0]["evidence_id"] = "verified-fact:unrelated"
    with pytest.raises(AppError):
        _resolve(plan, candidates, insights, original, challenge)


@pytest.mark.parametrize("verdict", ["confirmed", "unresolved"])
def test_confirmed_or_unresolved_gap_cannot_be_removed(verdict):
    plan, candidates, insights, original, challenge = _context()
    challenge["verdicts"][0]["verdict"] = verdict
    assert _resolve(plan, candidates, insights, original, challenge) == original


def test_mixed_verdicts_preserve_all_original_gaps():
    plan, candidates, insights, original, challenge = _context()
    candidates.append(
        {
            "id": "insight-2",
            "evidence_id": "verified-fact:fact-2",
            "verified_fact_id": "fact-2",
            "verified_fact": {"fact_id": "fact-2"},
        }
    )
    insights.append({"id": "insight-2", "evidence_id": "verified-fact:fact-2"})
    original["material_gaps"].append(
        {
            "verified_fact_ids": ["fact-2"],
            "evidence_ids": ["verified-fact:fact-2"],
            "final_insight_ids": ["insight-2"],
            "explanation": "The second fact's qualification is absent.",
        }
    )
    challenge["verdicts"].append(
        {
            "gap_index": 1,
            "verdict": "confirmed",
            "explanation": "The source qualification is not present.",
        }
    )
    assert _resolve(plan, candidates, insights, original, challenge) == original


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "unknown",
        "unbound_quote",
        "unbound_insight",
        "partial_quote",
    ],
)
def test_malformed_or_unbound_challenge_fails_closed(change):
    plan, candidates, insights, original, challenge = _context()
    verdict = challenge["verdicts"][0]
    if change == "missing":
        challenge["verdicts"] = []
    elif change == "duplicate":
        challenge["verdicts"].append(deepcopy(verdict))
    elif change == "unknown":
        verdict["gap_index"] = 1
    elif change == "unbound_quote":
        verdict["supporting_quote"] = "excludes digital TV Everywhere viewing"
    elif change == "partial_quote":
        verdict["supporting_quote"] = "digital TV Everywhere"
    else:
        verdict["supporting_insight_id"] = "unknown"
    with pytest.raises(AppError):
        _resolve(plan, candidates, insights, original, challenge)


def test_refuting_material_gap_does_not_clear_other_negative_theme():
    plan, candidates, insights, original, challenge = _context()
    original["theme_coverage"][0]["status"] = "uncovered"
    original["theme_coverage"][0]["resolution"] = "unresolved"
    with pytest.raises(AppError):
        _resolve(plan, candidates, insights, original, challenge)


def test_refuting_gap_cannot_clear_uncovered_original_obligation():
    plan, candidates, insights, original, challenge = _context()
    obligations = [
        {"theme": "Primary adoption", "evidence_ids": ["verified-fact:fact-1"]}
    ]
    original["original_essential_obligation_assessments"] = [
        {
            "theme": "Primary adoption",
            "evidence_ids": ["verified-fact:fact-1"],
            "status": "uncovered",
            "supporting_insight_ids": [],
            "explanation": "The original obligation is not developed.",
        }
    ]
    with pytest.raises(AppError):
        resolve_editorial_coverage_challenge(
            original_assessment=original,
            challenge=challenge,
            editorial_plan=plan,
            candidate_insights=candidates,
            final_insights=insights,
            original_essential_obligations=obligations,
            require_original_obligation_assessment=True,
        )
