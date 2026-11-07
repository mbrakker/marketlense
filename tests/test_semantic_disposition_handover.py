from __future__ import annotations

from src.contracts.claim_validation import (
    ClaimCandidate,
    ClaimSemanticInput,
    semantic_claim_disposition,
)
from src.contracts.protected_facts import (
    PROTECTED_FACT_DIMENSIONS,
    ProtectedFactComparison,
)
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
    soft_copy_material_sentences,
    soft_copy_sentence_hash,
)
from src.contracts.validation import ValidationRequest
from src.generators.public_editorial_quality_generator import (
    _retained_soft_copy_sentence_items,
)
from src.generators.validation.grounding import (
    _retained_claim_semantic_results,
    grounding_payload,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _public_editorial_review_issue,
)
from tests._test_validation_generator._shared import _report


def _compatible_protected_facts() -> dict[str, dict[str, str]]:
    return {
        dimension: {
            "claim_value": "same",
            "evidence_value": "same",
            "status": "compatible",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }


def _candidate() -> ClaimCandidate:
    return ClaimCandidate(
        schema_version="1.4",
        claim_id="claim:semantic-1",
        source_family="insights_final",
        text="The retained market finding is material.",
        text_hash="claim-hash",
        kind="descriptive",
        factual=True,
    )


def test_shared_semantic_disposition_distinguishes_facts_and_editorial_copy() -> None:
    compatible = ProtectedFactComparison.from_payload(
        _compatible_protected_facts(), proposition_status="compatible"
    )

    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=compatible,
        )
        == "supported"
    )
    assert (
        semantic_claim_disposition(
            classification="analyst_interpretation",
            outcome="entailed",
            protected_facts=None,
        )
        == "supported"
    )
    assert (
        semantic_claim_disposition(
            classification="analyst_interpretation",
            outcome="not_established",
            violation_type="non_fatal_interpretation",
        )
        == "not_applicable"
    )
    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="not_established",
        )
        == "unresolved"
    )
    assert (
        semantic_claim_disposition(
            classification="",
            outcome="entailed",
        )
        == "unresolved"
    )
    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="contradicted",
            protected_facts=compatible,
        )
        == "unsupported"
    )
    incomplete_proposition = ProtectedFactComparison.from_payload(
        _compatible_protected_facts(), proposition_status="unknown"
    )
    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=incomplete_proposition,
        )
        == "unresolved"
    )
    incompatible = ProtectedFactComparison.from_payload(
        _compatible_protected_facts(), proposition_status="incompatible"
    )
    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=incompatible,
        )
        == "unsupported"
    )
    incomplete = ProtectedFactComparison.from_payload(
        {
            **_compatible_protected_facts(),
            "value": {
                "claim_value": "42%",
                "evidence_value": None,
                "status": "unknown",
            },
        },
        proposition_status="compatible",
    )
    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=incomplete,
        )
        == "unresolved"
    )
    assert (
        semantic_claim_disposition(
            classification="analyst_interpretation",
            outcome="not_established",
            violation_type="source_silent",
        )
        == "unresolved"
    )


def test_retained_grounding_result_preserves_model_classification_and_violation() -> (
    None
):
    candidate = _candidate()
    semantic_input = ClaimSemanticInput(
        schema_version="1.4",
        candidate=candidate,
        evidence_texts=["The retained market finding is material."],
        evidence_hash="evidence-hash",
        source_identity="source-1",
    )
    results = _retained_claim_semantic_results(
        [
            {
                "item_id": "claim:semantic-1",
                "text": candidate.text,
                "classification": "factual_claim",
                "entailment_outcome": "not_established",
                "violation_type": "unsupported_factual_claim",
                "proposition_status": "unknown",
                "protected_facts": {},
                "reason": "The evidence does not establish the proposition.",
            }
        ],
        [semantic_input],
        retained_item_ids={candidate.claim_id: candidate.claim_id},
        source_identity="source-1",
        prompt_family="report_vs/validate/grounding",
        execution_identity="execution-1",
        validator_version="grounding_validation_output:2.0",
        model_provider="openai",
        model_name="test-model",
        configuration_policy_identity="policy-1",
        relevant_input_hash="input-1",
        retrieval_identity="retrieval-1",
        prompt_content_hash_by_claim_id={candidate.claim_id: "a" * 64},
    )

    assert len(results) == 1
    assert results[0].classification == "factual_claim"
    assert results[0].violation_type == "unsupported_factual_claim"


def test_grounding_payload_keeps_report_specific_metric_structure() -> None:
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    fact = {
        "schema_version": "1.0",
        "fact_id": "finding-1",
        "statement": "Composite metric retained.",
        "metric": {
            "value": "42%",
            "unit": "%",
            "methodology": {"base": "weighted", "window": "rolling"},
            "qualifiers": ["respondents", "self-reported"],
        },
        "qualifiers": [],
        "source_identity": source_identity,
        "source_pdf_sha256": "a" * 64,
        "supporting_physical_pages": [1],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [1],
            "source_truth_notes_by_page": {"1": "Composite metric retained."},
        },
    }
    artifacts = {
        "verified_facts": [fact],
        "insights_final": [
            {
                "id": "insight:metric",
                "text": "Composite metric retained.",
                "evidence_id": "verified-fact:finding-1",
                "evidence": "Composite metric retained.",
                "metric": {"value": "42%", "unit": "%"},
            }
        ],
    }
    from src.utils.verified_facts import canonical_verified_evidence_packs

    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="grounding-metric-structure",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=canonical_verified_evidence_packs({"finding-1": fact}),
            vector_store_id=None,
            source_id=source_identity,
            validation_mode="verified_facts",
        ),
        artifacts,
    )

    metric = payload["insights_final"][0]["metric"]
    assert metric["methodology"] == {"base": "weighted", "window": "rolling"}
    assert metric["qualifiers"] == ["respondents", "self-reported"]


def test_public_soft_copy_uses_canonical_sentence_segmentation() -> None:
    text = "U.S. respondents preferred wallets by 42%. The next step is conditional."
    sentences = soft_copy_material_sentences(text)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:{index}",
            text_hash=soft_copy_sentence_hash(sentence),
            classification="interpretive",
            evidence_ids=(),
            source_spans=(),
            producing_prompt_identity={"namespace": "test"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]

    items = _retained_soft_copy_sentence_items(
        artifacts={
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(claims)
        },
        artifact="expert_comment",
        field="expert_comment",
        text=text,
        evidence_items=[],
    )

    assert [item["public_item_id"] for item in items] == [
        claim.claim_id for claim in claims
    ]


def test_retained_grounding_merges_editorial_failure_subtype_without_losing_facts() -> (
    None
):
    candidate = _candidate()
    semantic_input = ClaimSemanticInput(
        schema_version="1.4",
        candidate=candidate,
        evidence_texts=[],
        evidence_hash="evidence-hash",
        source_identity="source-1",
    )
    results = _retained_claim_semantic_results(
        {
            "checks": [
                {
                    "item_id": candidate.claim_id,
                    "text": candidate.text,
                    "classification": "analyst_interpretation",
                    "entailment_outcome": "not_established",
                    "proposition_status": "unknown",
                    "protected_facts": {},
                    "reason": "The source does not state this implication literally.",
                }
            ],
            "unsupported": [
                {
                    "item_id": candidate.claim_id,
                    "text": candidate.text,
                    "classification": "analyst_interpretation",
                    "entailment_outcome": "not_established",
                    "violation_type": "non_fatal_interpretation",
                    "reason": "The interpretation remains defensible and relevant.",
                }
            ],
        },
        [semantic_input],
        retained_item_ids={candidate.claim_id: candidate.claim_id},
        source_identity="source-1",
        prompt_family="report_vs/validate/grounding",
        execution_identity="execution-1",
        validator_version="grounding_validation_output:2.0",
        model_provider="openai",
        model_name="test-model",
        configuration_policy_identity="policy-1",
        relevant_input_hash="input-1",
        retrieval_identity="retrieval-1",
        prompt_content_hash_by_claim_id={candidate.claim_id: "a" * 64},
    )

    assert len(results) == 1
    assert results[0].classification == "analyst_interpretation"
    assert results[0].violation_type == "non_fatal_interpretation"
    assert (
        semantic_claim_disposition(
            classification=results[0].classification,
            outcome=results[0].outcome,
            violation_type=results[0].violation_type,
            protected_facts=results[0].protected_facts,
        )
        == "not_applicable"
    )


def test_verified_grounding_exposes_missing_atomic_provenance_as_typed_item() -> None:
    source_identity = "frozen-report|pdf-sha256:" + "b" * 64
    fact = {
        "schema_version": "1.0",
        "fact_id": "finding-1",
        "statement": "The retained finding is source-backed.",
        "metric": {"label": "Finding", "value": "1", "unit": "index"},
        "qualifiers": [],
        "source_identity": source_identity,
        "source_pdf_sha256": "b" * 64,
        "supporting_physical_pages": [1],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [1],
            "source_truth_notes_by_page": {
                "1": "The retained finding is source-backed."
            },
        },
    }
    artifacts = {
        "verified_facts": [fact],
        "insights_final": [
            {
                "id": "insight:metric",
                "text": "The retained finding is source-backed.",
                "evidence_id": "verified-fact:finding-1",
            }
        ],
        "expert_comment": "This finding creates a useful planning implication.",
    }
    from src.utils.verified_facts import canonical_verified_evidence_packs

    payload = grounding_payload(
        ValidationRequest(
            schema_version="1.0",
            report_id="grounding-provenance-defect",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=canonical_verified_evidence_packs({"finding-1": fact}),
            vector_store_id=None,
            source_id=source_identity,
            validation_mode="verified_facts",
        ),
        artifacts,
    )

    item = next(
        item
        for item in payload["public_factual_items"]
        if item["section"] == "expert_comment"
    )
    assert item["evidence_ids"] == []
    assert item["provenance_error"] == "grounding_public_claim_provenance_invalid"


def test_editorial_review_allows_bounded_unbound_wording_repair_only() -> None:
    item = {
        "public_item_id": "expert_comment:claim-1",
        "artifact": "expert_comment",
        "field": "expert_comment",
        "evidence_ids": [],
        "evidence_text": "",
    }
    issue = _public_editorial_review_issue(
        report_id="report-1",
        item=item,
        rule_id="public_editorial_quality.semantic_generic_copy",
        severity="error",
        hard_fail_class="editorial_quality",
        explanation=(
            "The recommendation is generic and needs a specific conditional action."
        ),
        evidence_ids=[],
        repair_target="expert_comment",
        classification="prescriptive_recommendation",
    )
    assert issue.repair_eligible is True
    assert issue.repair_target == "expert_comment"

    factual = _public_editorial_review_issue(
        report_id="report-1",
        item=item,
        rule_id="public_editorial_quality.semantic_evidence_missing",
        severity="error",
        hard_fail_class="missing_evidence",
        explanation="A factual sentence has no retained evidence.",
        evidence_ids=[],
        repair_target="expert_comment",
        classification="factual_claim",
    )
    assert factual.repair_eligible is False
