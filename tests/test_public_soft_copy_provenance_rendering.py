from __future__ import annotations

import hashlib
from copy import deepcopy

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    public_editorial_semantic_review_items,
)
from tests.test_verified_facts_validation_authority import _authority_artifacts


def test_public_prose_preserves_bound_planning_implication_and_evidence() -> None:
    text = (
        "MarketLense’s conditional planning implication: compare the surveyed "
        "buyers before allocating resources."
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id=f"soft_copy:linkedin_post:{digest[:16]}",
        text_hash=digest,
        classification="recommendation",
        evidence_ids=("verified-fact:fact-1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "test/linkedin"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = deepcopy(_authority_artifacts())
    artifacts["linkedin_post"] = text
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [claim]
    )

    quality = evaluate_public_editorial_quality(
        report_id="bound-copy", artifacts=artifacts
    )
    assert not any(
        issue.rule_id == "public_editorial_quality.material_claim_evidence_missing"
        and issue.affected_artifact == "linkedin_post"
        for issue in quality.issues
    )
    items = public_editorial_semantic_review_items(artifacts)
    assert any(
        item["public_item_id"] == claim.claim_id
        and item["text"] == text
        and "verified-fact:fact-1" in item["evidence_ids"]
        for item in items
    )

    artifacts["linkedin_post"] += " The market will double next year."
    changed = evaluate_public_editorial_quality(
        report_id="unbound-copy", artifacts=artifacts
    )
    assert any(
        issue.rule_id == "public_editorial_quality.material_claim_evidence_missing"
        and issue.affected_artifact == "linkedin_post"
        for issue in changed.issues
    )
