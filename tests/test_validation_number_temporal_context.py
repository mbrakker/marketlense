from __future__ import annotations

import hashlib

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.validation.numbers import validate_new_numbers


def test_number_rule_keeps_temporal_context_local_to_each_sentence() -> None:
    artifacts = {
        "summary": {
            "executive_summary": (
                "Year-over-year growth was 16.0% in 2024. "
                "Year-over-year growth was 10.5% in 2025."
            )
        }
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=None,  # type: ignore[arg-type]
        evidence_texts=[],
    )

    assert issues == []


def test_number_rule_keeps_soft_copy_claim_identity_for_targeted_rebinding() -> None:
    sentence = "The retention rate reached 3.0%."
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:retention-rate",
        text_hash=hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
        classification="factual",
        evidence_ids=("finding-1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "linkedin_post": sentence,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([claim]),
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=None,  # type: ignore[arg-type]
        evidence_texts=[],
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "numbers"
    assert issues[0].entity_id == claim.claim_id
