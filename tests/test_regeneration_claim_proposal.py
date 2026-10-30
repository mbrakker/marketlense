from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.generators.report_regeneration_generator import (
    _validated_claim_repair_proposal,
)
from src.utils.errors import AppError


def _execution() -> SimpleNamespace:
    target = RegenerationTarget(
        target_section="expert_comment",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="expert_comment",
                message="Unsupported wording.",
                severity="error",
                evidence_ids=["verified-fact:f1"],
            )
        ],
        allowed_paths=["expert_comment[claim_index=0]"],
    )
    return SimpleNamespace(
        target=target,
        runtime=SimpleNamespace(request=SimpleNamespace(report_id="report-1")),
    )


def _proposal(action: str, *, replacement_text: str = "", evidence_ids=None):
    return {
        "schema_version": "1.0",
        "action": action,
        "replacement_text": replacement_text,
        "evidence_ids_used": list(evidence_ids or []),
    }


def test_claim_repair_proposal_contains_only_replacement_and_admitted_evidence():
    proposal = _validated_claim_repair_proposal(
        {
            "schema_version": "1.0",
            "action": "replace",
            "replacement_text": "The evidence supports a narrower interpretation.",
            "evidence_ids_used": ["verified-fact:f1"],
        },
        execution=_execution(),
        grounding_package={
            "evidence_ids": ["verified-fact:f1"],
            "quarantined_evidence_ids": [],
        },
    )

    assert proposal.action == "replace"
    assert proposal.replacement_text.startswith("The evidence supports")
    assert proposal.evidence_ids_used == ["verified-fact:f1"]


def test_claim_repair_proposal_rejects_model_authored_target_metadata():
    with pytest.raises(AppError) as captured:
        _validated_claim_repair_proposal(
            {
                "schema_version": "1.0",
                "action": "replace",
                "replacement_text": "A supported replacement.",
                "evidence_ids_used": ["verified-fact:f1"],
                "path": "expert_comment[claim_index=1]",
            },
            execution=_execution(),
            grounding_package={
                "evidence_ids": ["verified-fact:f1"],
                "quarantined_evidence_ids": [],
            },
        )

    assert captured.value.code == "regeneration_repair_decision_invalid"


def test_claim_repair_proposal_rejects_quarantined_evidence():
    with pytest.raises(AppError) as captured:
        _validated_claim_repair_proposal(
            _proposal(
                "replace",
                replacement_text="A supported replacement.",
                evidence_ids=["verified-fact:f1"],
            ),
            execution=_execution(),
            grounding_package={
                "evidence_ids": ["verified-fact:f1"],
                "quarantined_evidence_ids": ["verified-fact:f1"],
            },
        )

    assert captured.value.context["reason"] == "evidence_not_retained_or_quarantined"


def test_claim_repair_proposal_rejects_removal_for_non_atomic_target():
    execution = _execution()
    execution.target = RegenerationTarget(
        target_section="expert_comment",
        issues=execution.target.issues,
        allowed_paths=["expert_comment"],
    )
    with pytest.raises(AppError) as captured:
        _validated_claim_repair_proposal(
            _proposal("remove"),
            execution=execution,
            grounding_package={"evidence_ids": [], "quarantined_evidence_ids": []},
        )

    assert captured.value.context["reason"] == "claim_proposal_removal_not_permitted"


def test_claim_repair_proposal_allows_existing_soft_copy_leaf_removal():
    proposal = _validated_claim_repair_proposal(
        _proposal("remove"),
        execution=_execution(),
        grounding_package={"evidence_ids": [], "quarantined_evidence_ids": []},
    )

    assert proposal.action == "remove"
    assert proposal.evidence_ids_used == []


def test_claim_repair_proposal_treats_exact_replacement_as_a_no_op():
    execution = _execution()
    execution.state = SimpleNamespace(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="The retained sentence.",
        linkedin_post="",
    )
    execution.target = RegenerationTarget(
        target_section="expert_comment",
        issues=execution.target.issues,
        allowed_paths=["expert_comment[claim_index=0]"],
    )

    proposal = _validated_claim_repair_proposal(
        _proposal(
            "replace",
            replacement_text="The retained sentence.",
            evidence_ids=["verified-fact:f1"],
        ),
        execution=execution,
        grounding_package={
            "evidence_ids": ["verified-fact:f1"],
            "quarantined_evidence_ids": [],
        },
    )

    assert proposal.action == "abstain"
    assert proposal.no_op is True
    assert proposal.evidence_ids_used == []
