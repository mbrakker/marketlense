from __future__ import annotations

from copy import deepcopy

import pytest

from src.generators.validation.regeneration_candidate import (
    _verified_editorial_obligation_issues,
    _verified_facts,
    canonical_verified_editorial_plan_revision,
    validate_regeneration_candidate,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_validation_generator._shared import _ctx


def _valid_artifact_pair() -> tuple[dict, dict]:
    original_plan = {
        "report_thesis": "The report connects three source-backed signals.",
        "themes": [
            {
                "theme": "Essential signal",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Retain the essential signal.",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": ["c1"],
            },
            {
                "theme": "Supporting signal",
                "priority": 2,
                "importance": "essential",
                "coverage_obligation": "Retain the supporting signal.",
                "evidence_ids": ["verified-fact:f2"],
                "feasible_candidate_ids": ["c2"],
            },
            {
                "theme": "Limitation",
                "priority": 3,
                "importance": "optional",
                "coverage_obligation": "Retain the limitation.",
                "evidence_ids": ["verified-fact:f3"],
                "feasible_candidate_ids": ["c3"],
            },
        ],
        "material_limitation_evidence_ids": ["verified-fact:f3"],
    }
    obligations = [
        {
            "theme": theme["theme"],
            "evidence_ids": list(theme["evidence_ids"]),
            "importance": theme["importance"],
            "coverage_obligation": theme["coverage_obligation"],
        }
        for theme in original_plan["themes"]
        if theme["importance"] == "essential"
    ]
    visual_cache = {
        "enabled": True,
        "verified_facts": [
            {"fact_id": "f1"},
            {"fact_id": "f2"},
            {"fact_id": "f3", "qualifiers": ["limited sample"]},
        ],
        "admitted_candidates": [
            {
                "id": "c1",
                "evidence_id": "verified-fact:f1",
                "verified_fact_id": "f1",
            },
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
        "audit": {
            "editorial_plan_coverage": {
                "original_plan_identity": sha256_json(original_plan),
                "original_editorial_plan": deepcopy(original_plan),
                "original_essential_obligations": deepcopy(obligations),
            }
        },
    }
    current = {
        "_cache": {"visual_authority_canary": visual_cache},
        "editorial_plan": deepcopy(original_plan),
        "insights_candidates": [
            {"id": "c1", "evidence_id": "verified-fact:f1"},
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
        "insights_final": [
            {"id": "c1", "evidence_id": "verified-fact:f1"},
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
    }
    return current, deepcopy(current)


def test_verified_regeneration_cannot_drop_original_essential_plan_evidence():
    current, candidate = _valid_artifact_pair()
    candidate["editorial_plan"]["themes"] = [
        deepcopy(current["editorial_plan"]["themes"][1]),
        deepcopy(current["editorial_plan"]["themes"][2]),
    ]
    candidate["insights_candidates"] = [
        item for item in candidate["insights_candidates"] if item["id"] != "c1"
    ]
    candidate["insights_final"] = [
        item for item in candidate["insights_final"] if item["id"] != "c1"
    ]

    issues = _verified_editorial_obligation_issues(
        current_artifacts=current,
        candidate_artifacts=candidate,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "verified_editorial_obligations"


def test_verified_regeneration_accepts_unchanged_editorial_obligations():
    current, candidate = _valid_artifact_pair()

    assert (
        _verified_editorial_obligation_issues(
            current_artifacts=current,
            candidate_artifacts=candidate,
        )
        == []
    )


def test_verified_regeneration_preserves_explicit_fact_requirements():
    current, _ = _valid_artifact_pair()
    cache = current["_cache"]["visual_authority_canary"]["audit"][
        "editorial_plan_coverage"
    ]
    plan = cache["original_editorial_plan"]
    for theme, obligation in zip(
        plan["themes"][:2], cache["original_essential_obligations"], strict=True
    ):
        theme["required_evidence_ids"] = list(theme["evidence_ids"])
        theme["alternative_evidence_groups"] = []
        obligation["required_evidence_ids"] = list(theme["evidence_ids"])
        obligation["alternative_evidence_groups"] = []
    cache["original_plan_identity"] = sha256_json(plan)
    current["editorial_plan"] = deepcopy(plan)

    assert (
        _verified_editorial_obligation_issues(
            current_artifacts=current, candidate_artifacts=deepcopy(current)
        )
        == []
    )


def test_verified_regeneration_rejects_missing_obligation_metadata():
    issues = _verified_editorial_obligation_issues(
        current_artifacts={},
        candidate_artifacts={},
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "verified_editorial_obligations"


def test_verified_regeneration_rejects_missing_candidate_plan():
    current, candidate = _valid_artifact_pair()
    candidate.pop("editorial_plan")

    issues = _verified_editorial_obligation_issues(
        current_artifacts=current,
        candidate_artifacts=candidate,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "verified_editorial_obligations"


def test_verified_regeneration_uses_retained_facts_when_canary_projection_is_sparse():
    current, candidate = _valid_artifact_pair()
    facts = current["_cache"]["visual_authority_canary"].pop("verified_facts")
    current["verified_facts"] = deepcopy(facts)
    candidate["verified_facts"] = deepcopy(facts)
    candidate["_cache"]["visual_authority_canary"].pop("verified_facts")

    assert (
        _verified_editorial_obligation_issues(
            current_artifacts=current,
            candidate_artifacts=candidate,
        )
        == []
    )


def test_verified_regeneration_falls_back_after_bad_admissions() -> None:
    current, candidate = _valid_artifact_pair()
    candidate["_cache"]["visual_authority_canary"]["admitted_candidates"] = [
        None,
        {},
    ]

    assert (
        _verified_editorial_obligation_issues(
            current_artifacts=current,
            candidate_artifacts=candidate,
        )
        == []
    )


def test_verified_regeneration_derives_binding_from_retained_admission_pool() -> None:
    current, candidate = _valid_artifact_pair()
    current["_cache"]["visual_authority_canary"]["admitted_candidates"] = [
        None,
        {},
    ]
    candidate["_cache"]["visual_authority_canary"]["admitted_candidates"] = [
        *deepcopy(
            _valid_artifact_pair()[0]["_cache"]["visual_authority_canary"][
                "admitted_candidates"
            ]
        ),
        {
            "id": "invented-candidate",
            "evidence_id": "verified-fact:f1",
            "verified_fact_id": "f1",
        },
    ]
    candidate["editorial_plan"]["themes"][0]["feasible_candidate_ids"] = [
        "invented-candidate"
    ]

    issues = _verified_editorial_obligation_issues(
        current_artifacts=current,
        candidate_artifacts=candidate,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "verified_editorial_plan_not_canonicalized"
    assert candidate["editorial_plan"]["themes"][0]["feasible_candidate_ids"] == [
        "invented-candidate"
    ]


def test_verified_editorial_plan_revision_fails_closed_without_retained_pool() -> None:
    current, candidate = _valid_artifact_pair()
    current["_cache"]["visual_authority_canary"]["admitted_candidates"] = []
    current.pop("insights_candidates")
    current.pop("insights_final")

    with pytest.raises(AppError) as exc_info:
        canonical_verified_editorial_plan_revision(
            current_artifacts=current,
            candidate_artifacts=candidate,
            original_plan=current["editorial_plan"],
            candidate_editorial_plan=candidate["editorial_plan"],
        )

    assert exc_info.value.code == "verified_editorial_plan_admission_pool_missing"


def test_verified_facts_fail_closed_without_any_fact_projection():
    assert _verified_facts({}) == {}


def test_verified_candidate_validation_includes_obligation_diagnostics():
    result = validate_regeneration_candidate(
        current_artifacts={},
        candidate_artifacts={},
        evidence_packs={},
        ctx=_ctx(),
        verified_facts_only=True,
    )

    assert any(
        item.rule_id == "verified_editorial_obligations" for item in result.issues
    )
