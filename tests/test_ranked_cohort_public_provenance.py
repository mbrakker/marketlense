from __future__ import annotations

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
    soft_copy_sentence_hash,
)
from src.generators.public_editorial_quality_generator import (
    _public_text_items,
    public_editorial_semantic_review_items,
)
from tests.test_verified_facts_validation_authority import _verified_artifacts


def test_ranked_cohort_prose_keeps_its_exact_provenance() -> None:
    text = (
        "2017 U.S. video: top-25% users with 4.5+ hours of daily attention "
        "accounted for 61% of total video time."
    )
    evidence_id = "verified-fact:fact-1"
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="summary",
        claim_id="soft_copy:summary:ranked-cohort",
        text_hash=soft_copy_sentence_hash(text),
        classification="factual",
        evidence_ids=(evidence_id,),
        source_spans=(),
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = _verified_artifacts()
    artifacts["summary"] = {
        "card_tldr_compact": text,
        "claim_evidence_map": [{"claim": text, "evidence_id": evidence_id}],
    }
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [claim]
    )
    artifacts["claim_ledgers"] = [
        {
            "claim_text": text,
            "artifact_section": "summary.claim_evidence_map",
            "evidence_ids": [evidence_id],
        }
    ]
    item = next(item for item in _public_text_items(artifacts) if item["text"] == text)
    assert item["public_item_id"] == claim.claim_id
    assert item["evidence_ids"] == [evidence_id]
    assert not item.get("provenance_error")
    reviewed = [
        item
        for item in public_editorial_semantic_review_items(artifacts)
        if item.get("text") == text and evidence_id in item.get("evidence_ids", [])
    ]
    assert len(reviewed) >= 2
