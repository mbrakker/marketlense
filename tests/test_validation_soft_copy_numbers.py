from __future__ import annotations

from hashlib import sha256

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.validation.numbers import validate_new_numbers
from tests._test_validation_generator._shared import _report


def test_number_validation_ignores_soft_planning_timeframes():
    artifacts = {
        "linkedin_post": (
            "Actions for the next 12 months: integrate verification into "
            "product and marketing release cycles."
        )
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )

    assert not any(issue.rule_id == "numbers" for issue in issues)


def test_number_issue_identifies_full_soft_copy_claim_with_us_initialism() -> None:
    sentence = "U.S. revenue reached $918 billion."
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:us-revenue",
        text_hash=sha256(sentence.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("finding-1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    issues = validate_new_numbers(
        artifacts={
            "expert_comment": sentence,
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
                [claim]
            ),
        },
        insights=[],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )

    assert any(
        issue.affected_section == "expert_comment"
        and issue.entity_id == claim.claim_id
        and issue.evidence_ids == ["finding-1"]
        for issue in issues
    )


def test_number_issue_omits_ambiguous_soft_copy_provenance() -> None:
    sentence = "U.S. revenue reached $918 billion."
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:{index}",
            text_hash=sha256(sentence.encode()).hexdigest(),
            classification="factual",
            evidence_ids=(f"finding-{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index in (1, 2)
    ]

    issues = validate_new_numbers(
        artifacts={
            "expert_comment": sentence,
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(claims),
        },
        insights=[],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )

    assert any(
        issue.affected_section == "expert_comment"
        and not issue.entity_id
        and not issue.evidence_ids
        for issue in issues
    )


def test_number_validation_grounds_rank_labels_in_linked_insight_evidence() -> None:
    evidence = (
        "The top 10 companies held 80.8% of revenue. Companies ranked 11–25 held 11.0%."
    )
    insight = {
        "id": "company-concentration",
        "text": evidence,
        "evidence": evidence,
        "evidence_id": "concentration",
        "so_what": "Revenue is concentrated among the top 10 companies and companies ranked 11–25.",
    }
    supported = validate_new_numbers(
        artifacts={"insights_final": [insight]},
        insights=[insight],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )
    incorrect = {
        **insight,
        "so_what": "Revenue is concentrated among the top 12 companies and companies ranked 11–26.",
    }
    rejected = validate_new_numbers(
        artifacts={"insights_final": [incorrect]},
        insights=[incorrect],
        report=_report(),
        evidence_texts=[],
        evidence_windows=[],
    )

    section = "insights:company-concentration.so_what"
    assert not [issue for issue in supported if issue.affected_section == section]
    rejected_messages = [
        issue.message for issue in rejected if issue.affected_section == section
    ]
    assert any("Number 12.0 not present" in message for message in rejected_messages)
    assert any("Number 26.0 not present" in message for message in rejected_messages)
