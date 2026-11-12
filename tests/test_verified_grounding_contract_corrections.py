from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.contracts.claim_validation import (
    normalize_claim_classification,
    semantic_claim_disposition,
)
from src.contracts.openai import OpenAIResponseResult
from src.contracts.protected_facts import (
    PROTECTED_FACT_DIMENSIONS,
    ProtectedFactComparison,
)
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
    soft_copy_sentence_hash,
)
from src.contracts.validation import ValidationIssue, ValidationRequest
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.public_editorial_quality_generator import (
    validation_issues_from_public_editorial_quality,
)
from src.generators.report_regeneration_generator import (
    _build_soft_copy_claim_evidence_package,
    _editorial_only_repair_authorized,
)
from src.generators.soft_copy_claim_provenance import (
    build_soft_copy_claim_provenance,
)
from src.generators.validation.grounding import (
    _public_factual_items,
    grounding_payload,
    run_grounding_check,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _public_editorial_review_issue,
    _validate_public_editorial_review_payload,
)
from src.utils.errors import AppError
from tests._test_report_regeneration_generator._split_support_test_report_regeneration_generator import (  # noqa: E501
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakeOpenAIClient,
    _FakePromptClient,
    _settings,
    regenerate_artifacts,
)
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    _report,
)
from tests._test_validation_generator._shared import (
    FakePromptClient as ValidationFakePromptClient,
)
from tests._test_validation_generator._shared import (
    _ctx as validation_ctx,
)
from tests._test_validation_generator._shared import (
    _settings as validation_settings,
)


def _passing_public_report_verdict() -> dict:
    return {
        "status": "pass",
        "severity": "info",
        "rule_id": "",
        "hard_fail_class": "",
        "reason": "The report remains coherent and within the retained review scope.",
        "evidence_ids": [],
        "repair_target": "",
        "affected_item_id": "",
        "dimensions": {
            dimension: {
                "status": "pass",
                "reason": "The report satisfies this review dimension.",
            }
            for dimension in (
                "material_coverage",
                "analytical_depth",
                "distinctness",
                "limitations",
            )
        },
    }


def test_claim_classification_normalizer_covers_retained_and_canonical_vocabularies():
    assert normalize_claim_classification("factual") == "factual_claim"
    assert normalize_claim_classification("factual_claim") == "factual_claim"
    assert normalize_claim_classification("interpretive") == "analyst_interpretation"
    assert (
        normalize_claim_classification("analyst_interpretation")
        == "analyst_interpretation"
    )
    assert normalize_claim_classification("recommendation") == (
        "prescriptive_recommendation"
    )
    assert normalize_claim_classification("prescriptive_recommendation") == (
        "prescriptive_recommendation"
    )
    assert normalize_claim_classification("unknown") == ""


def test_editorial_disposition_fails_closed_for_incomplete_empirical_facts():
    dimensions = {
        dimension: {
            "claim_value": "same",
            "evidence_value": "same",
            "status": "compatible",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    dimensions["value"] = {
        "claim_value": "42%",
        "evidence_value": None,
        "status": "unknown",
    }
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="compatible"
    )

    assert (
        semantic_claim_disposition(
            classification="analyst_interpretation",
            outcome="entailed",
            protected_facts=comparison,
        )
        == "unresolved"
    )


def test_editorial_disposition_allows_source_only_unknown_value():
    dimensions = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    dimensions["value"] = {
        "claim_value": None,
        "evidence_value": "42%",
        "status": "unknown",
    }
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="compatible"
    )

    assert (
        semantic_claim_disposition(
            classification="analyst_interpretation",
            outcome="entailed",
            protected_facts=comparison,
        )
        == "supported"
    )


def test_factual_disposition_allows_explicit_absence_marker_for_unknown_dimension():
    dimensions = {
        dimension: {
            "claim_value": "same",
            "evidence_value": "same",
            "status": "compatible",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    dimensions["attribution"] = {
        "claim_value": "Not specified",
        "evidence_value": "Not specified",
        "status": "unknown",
    }
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="compatible"
    )

    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=comparison,
        )
        == "supported"
    )


def test_factual_disposition_still_fails_closed_for_material_unknown_dimension():
    dimensions = {
        dimension: {
            "claim_value": "same",
            "evidence_value": "same",
            "status": "compatible",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    dimensions["attribution"] = {
        "claim_value": "Acme Research",
        "evidence_value": None,
        "status": "unknown",
    }
    comparison = ProtectedFactComparison.from_payload(
        dimensions, proposition_status="compatible"
    )

    assert (
        semantic_claim_disposition(
            classification="factual_claim",
            outcome="entailed",
            protected_facts=comparison,
        )
        == "unresolved"
    )


def test_unbound_editorial_quality_failure_is_valid_negative_verdict():
    item = {
        "public_item_id": "soft_copy:expert_comment:generic",
        "artifact": "expert_comment",
        "field": "expert_comment",
        "evidence_ids": [],
        "evidence_text": "",
        "repair_target": "expert_comment",
    }
    payload = {
        "verdicts": [
            {
                "item_id": item["public_item_id"],
                "status": "fail",
                "classification": "analyst_interpretation",
                "severity": "error",
                "rule_id": "public_editorial_quality.semantic_generic_copy",
                "hard_fail_class": "editorial_quality",
                "reason": (
                    "The sentence repeats a generic implication without a specific "
                    "commercial decision or conditional next step."
                ),
                "evidence_ids": [],
                "repair_target": "expert_comment",
            }
        ],
        "report_verdict": _passing_public_report_verdict(),
    }

    _validate_public_editorial_review_payload(payload, [item], validation_ctx())


def test_unbound_factual_failure_still_requires_evidence():
    item = {
        "public_item_id": "soft_copy:expert_comment:factual",
        "artifact": "expert_comment",
        "field": "expert_comment",
        "evidence_ids": [],
        "evidence_text": "",
        "repair_target": "expert_comment",
    }
    payload = {
        "verdicts": [
            {
                "item_id": item["public_item_id"],
                "status": "fail",
                "classification": "factual_claim",
                "severity": "error",
                "rule_id": "public_editorial_quality.semantic_generic_copy",
                "hard_fail_class": "editorial_quality",
                "reason": "The sentence asserts an unsupported empirical result.",
                "evidence_ids": [],
                "repair_target": "expert_comment",
            }
        ],
        "report_verdict": _passing_public_report_verdict(),
    }

    with pytest.raises(AppError) as caught:
        _validate_public_editorial_review_payload(payload, [item], validation_ctx())

    assert caught.value.code == "public_editorial_quality_review_evidence_missing"


def test_editorial_failure_cannot_hide_item_verified_fact_context():
    item = {
        "public_item_id": "soft_copy:expert_comment:fact-context",
        "artifact": "expert_comment",
        "field": "expert_comment",
        "evidence_ids": [],
        "evidence_text": "",
        "verified_facts": {"verified-fact:f1": {"fact_id": "f1"}},
        "repair_target": "expert_comment",
    }
    payload = {
        "verdicts": [
            {
                "item_id": item["public_item_id"],
                "status": "fail",
                "classification": "analyst_interpretation",
                "severity": "error",
                "rule_id": "public_editorial_quality.semantic_generic_copy",
                "hard_fail_class": "editorial_quality",
                "reason": "The item hides a source-backed factual premise.",
                "evidence_ids": [],
                "repair_target": "expert_comment",
            }
        ],
        "report_verdict": _passing_public_report_verdict(),
    }

    with pytest.raises(AppError) as caught:
        _validate_public_editorial_review_payload(payload, [item], validation_ctx())

    assert caught.value.code == "public_editorial_quality_review_evidence_missing"


def test_report_editorial_quality_failure_without_evidence_is_valid():
    item = {
        "public_item_id": "soft_copy:expert_comment:generic-report",
        "artifact": "expert_comment",
        "field": "expert_comment",
        "evidence_ids": [],
        "evidence_text": "",
        "repair_target": "expert_comment",
    }
    payload = {
        "verdicts": [
            {
                "item_id": item["public_item_id"],
                "status": "fail",
                "classification": "analyst_interpretation",
                "severity": "error",
                "rule_id": "public_editorial_quality.semantic_generic_copy",
                "hard_fail_class": "editorial_quality",
                "reason": "The item is factually harmless but needs stronger analysis.",
                "evidence_ids": [],
                "repair_target": "expert_comment",
            }
        ],
        "report_verdict": {
            "status": "fail",
            "severity": "error",
            "rule_id": "public_editorial_quality.report_acceptance",
            "hard_fail_class": "report_editorial_acceptance",
            "reason": (
                "The report remains factually covered but lacks analytical depth."
            ),
            "evidence_ids": [],
            "repair_target": "expert_comment",
            "affected_item_id": item["public_item_id"],
            "dimensions": {
                "material_coverage": {
                    "status": "pass",
                    "reason": "Material admitted findings remain represented.",
                },
                "analytical_depth": {
                    "status": "fail",
                    "reason": "The Expert View repeats the finding without analysis.",
                },
                "distinctness": {
                    "status": "pass",
                    "reason": "The selected items remain distinct.",
                },
                "limitations": {
                    "status": "pass",
                    "reason": "Material limitations remain represented.",
                },
            },
        },
    }

    _validate_public_editorial_review_payload(
        payload,
        [item],
        validation_ctx(),
        {"evidence_context": [], "verified_facts": {}},
    )


def test_retained_editorial_aliases_reach_verified_grounding_without_fake_evidence():
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    fact = {
        "schema_version": "1.0",
        "fact_id": "finding-1",
        "statement": "The retained finding is source-backed.",
        "metric": {"label": "Finding", "value": "1", "unit": "index"},
        "qualifiers": [],
        "source_identity": source_identity,
        "source_pdf_sha256": "a" * 64,
        "supporting_physical_pages": [1],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [1],
            "source_truth_notes_by_page": {
                "1": "The retained finding is source-backed."
            },
        },
    }
    text = "This finding changes planning priorities."
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:interpretive",
        text_hash=soft_copy_sentence_hash(text),
        classification="interpretive",
        evidence_ids=(),
        source_spans=(),
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    items = _public_factual_items(
        artifacts={
            "expert_comment": text,
            "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
                [claim]
            ),
        },
        evidence_packs={},
        report_title="",
        publisher="",
        insights=[],
        summary={},
        verified_facts={"finding-1": fact},
        strict_atomic_provenance=True,
    )
    item = next(item for item in items if item["item_id"] == claim.claim_id)
    assert item["declared_classification"] == "analyst_interpretation"
    assert item["evidence_ids"] == []


def test_editorial_classification_survives_quality_to_regeneration_handover():
    issue = _public_editorial_review_issue(
        report_id="report-1",
        item={
            "public_item_id": "soft_copy:expert_comment:claim-1",
            "artifact": "expert_comment",
            "field": "expert_comment",
            "evidence_ids": [],
            "evidence_text": "",
        },
        rule_id="public_editorial_quality.semantic_generic_copy",
        severity="error",
        hard_fail_class="editorial_quality",
        explanation="The interpretation is generic.",
        repair_target="expert_comment",
        classification="interpretive",
    )

    assert issue.classification == "analyst_interpretation"
    assert issue.repair_eligible is True
    validation_issue = validation_issues_from_public_editorial_quality(
        type(
            "QualityReport",
            (),
            {
                "issues": [issue],
                "status": "fail",
                "publishable": False,
            },
        )()
    )[0]
    assert validation_issue.classification == "analyst_interpretation"


def test_unbound_editorial_repair_does_not_select_arbitrary_evidence():
    text = "This finding changes planning priorities."
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:claim-1",
        text_hash=soft_copy_sentence_hash(text),
        classification="interpretive",
        evidence_ids=(),
        source_spans=(),
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    issue = RegenerationIssue(
        rule_id="public_editorial_quality.semantic_generic_copy",
        affected_section="expert_comment",
        message="The interpretation is generic.",
        severity="error",
        repair_target="expert_comment",
        entity_id=claim.claim_id,
        classification="analyst_interpretation",
        violation_type="editorial_quality",
    )
    package = _build_soft_copy_claim_evidence_package(
        claim=claim,
        issue=issue,
        artifacts={},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "evidence_id": "unrelated",
                        "statement": "An unrelated finding.",
                        "text": "An unrelated finding.",
                    }
                ]
            }
        },
        quarantined_evidence_ids=(),
        claim_text=text,
    )

    assert package["editorial_only_repair"] is True
    assert package["relevant_evidence"] == []
    assert package["evidence_ids"] == []
    assert package["evidence_selection"]["strategy"] == "editorial_only"


def test_actual_expert_repair_preserves_unbound_editorial_provenance(tmp_path):
    current = _current_artifacts()
    original_claim = next(
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )
    issue = RegenerationIssue(
        rule_id="public_editorial_quality.semantic_generic_copy",
        affected_section="expert_comment",
        message="The interpretation is generic.",
        severity="error",
        repair_target="expert_comment",
        entity_id=original_claim["claim_id"],
        classification="analyst_interpretation",
        violation_type="editorial_quality",
    )
    target = RegenerationTarget(
        target_section="expert_comment",
        regenerate_steps=["expert_comment"],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["expert_comment[claim_index=0]"],
        issues=[issue],
    )

    class EditorialOnlyClient(_FakeOpenAIClient):
        def openai_chat_json(self, req, ctx):
            if "regeneration_claim_repair_proposal" in (
                req.structured_output_schema_identity or ""
            ):
                payload = {
                    "claim_repair_proposal": {
                        "schema_version": "1.0",
                        "action": "replace",
                        "replacement_text": "This finding changes planning priorities.",
                        "evidence_ids_used": [],
                    }
                }
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="req-editorial-only",
                )
            return super().openai_chat_json(req, ctx)

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[target],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=EditorialOnlyClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"].startswith(
        "This finding changes planning priorities."
    )
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{original_claim['claim_id']}"
    ]
    assert selection["strategy"] == "editorial_only"
    assert selection["selected_evidence_ids"] == []
    repaired = next(
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim.get("repaired_from_claim_id") == original_claim["claim_id"]
    )
    assert repaired["classification"] == "interpretive"
    assert repaired["evidence_ids"] == []


def test_retained_materialization_accepts_canonical_classification_aliases():
    text = "A conditional interpretation remains useful."
    claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=text,
        declared_claims=[
            {
                "claim": text,
                "classification": "analyst_interpretation",
                "evidence_ids": [],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    assert claims[0].classification == "interpretive"


def test_editorial_only_authorization_rejects_factual_or_provenance_repairs():
    text = "This finding changes planning priorities."
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:claim-1",
        text_hash=soft_copy_sentence_hash(text),
        classification="interpretive",
        evidence_ids=(),
        source_spans=(),
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    base = {
        "affected_section": "expert_comment",
        "message": "The interpretation is generic.",
        "severity": "error",
        "repair_target": "expert_comment",
        "entity_id": claim.claim_id,
        "classification": "analyst_interpretation",
    }
    assert _editorial_only_repair_authorized(
        claim=claim,
        issue=RegenerationIssue(
            rule_id="public_editorial_quality.semantic_generic_copy", **base
        ),
        claim_text=text,
    )
    assert not _editorial_only_repair_authorized(
        claim=replace_claim(claim, classification="factual"),
        issue=RegenerationIssue(
            rule_id="public_editorial_quality.semantic_generic_copy", **base
        ),
        claim_text=text,
    )
    assert not _editorial_only_repair_authorized(
        claim=claim,
        issue=RegenerationIssue(
            rule_id="public_editorial_quality.semantic_evidence_missing", **base
        ),
        claim_text=text,
    )


def replace_claim(claim: SoftCopyClaimProvenance, **changes):
    return replace(claim, **changes)


def _verified_editorial_request(
    text: str, classification: str
) -> tuple[ValidationRequest, str]:
    source_identity = "frozen-report|pdf-sha256:" + "c" * 64
    fact = {
        "schema_version": "1.0",
        "fact_id": "finding-1",
        "statement": "Wallet adoption rose among surveyed consumers.",
        "metric": {"label": "Wallet adoption", "value": "42", "unit": "%"},
        "qualifiers": [],
        "source_identity": source_identity,
        "source_pdf_sha256": "c" * 64,
        "supporting_physical_pages": [3],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [3],
            "source_truth_notes_by_page": {
                "3": "Wallet adoption rose among surveyed consumers."
            },
        },
    }
    claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:integration",
        text_hash=soft_copy_sentence_hash(text),
        classification=classification,
        evidence_ids=(),
        source_spans=(),
        producing_prompt_identity={"namespace": "test"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "verified_facts": [fact],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Wallet adoption rose among surveyed consumers.",
                "evidence_id": "verified-fact:finding-1",
                "evidence": "Wallet adoption rose among surveyed consumers.",
            }
        ],
        "expert_comment": text,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([claim]),
    }
    from src.utils.verified_facts import canonical_verified_evidence_packs

    request = ValidationRequest(
        schema_version="1.0",
        report_id="editorial-grounding-integration",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=canonical_verified_evidence_packs({"finding-1": fact}),
        source_id=source_identity,
        validation_mode="verified_facts",
    )
    return request, source_identity


def test_verified_editorial_aliases_reach_grounding_but_mislabeled_fact_fails(
    tmp_path,
):
    for classification in ("interpretive", "recommendation"):
        request, source_identity = _verified_editorial_request(
            "This finding changes planning priorities.", classification
        )
        issues = run_grounding_check(
            request=request,
            settings=validation_settings(tmp_path),
            grounding_use_vector_store=False,
            evidence_texts=[],
            evidence_windows=[],
            prompt_client=ValidationFakePromptClient(),
            openai_client=FakeOpenAI(grounding_payload={"checks": []}),
            ctx=validation_ctx(),
            source_id=source_identity,
        )
        assert issues == []

    text = "This means wallet adoption caused a 20% conversion uplift."
    request, source_identity = _verified_editorial_request(text, "interpretive")
    issues = run_grounding_check(
        request=request,
        settings=validation_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=ValidationFakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                "unsupported": [
                    {
                        "section": "expert_comment",
                        "text": text,
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "violation_type": "unsupported_number",
                        "reason": "The source does not support the asserted uplift.",
                    }
                ]
            }
        ),
        ctx=validation_ctx(),
        source_id=source_identity,
    )
    assert any(issue.violation_type == "unsupported_number" for issue in issues)


def test_verified_grounding_contract_failure_is_not_a_prose_repair_target():
    issue = ValidationIssue(
        schema_version="1.0",
        message="Grounding response coverage is incomplete.",
        severity="error",
        affected_section="grounding",
        rule_id="grounding",
        violation_type="grounding_claim_check_coverage_invalid",
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts={"verified_facts": [{"fact_id": "fact-1"}]},
        broad_retry_available=False,
    )

    assert plan.targets == []
    assert plan.unmappable_issues[0].violation_type == (
        "grounding_claim_check_coverage_invalid"
    )


def test_trusted_verified_mode_does_not_downgrade_when_artifact_marker_is_missing():
    issue = ValidationIssue(
        schema_version="1.0",
        message="Grounding verdict is incomplete.",
        severity="error",
        affected_section="insights:insight-1.text",
        rule_id="grounding",
        violation_type="grounding_claim_verdict_incomplete",
        entity_id="insight:insight-1:text",
        evidence_ids=["verified-fact:f1"],
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts={
            "insights_final": [{"id": "insight-1", "evidence_id": "verified-fact:f1"}]
        },
        broad_retry_available=False,
        verified_mode=True,
    )

    assert plan.targets == []
    assert plan.unmappable_issues[0].violation_type == (
        "grounding_claim_verdict_incomplete"
    )


def test_verified_grounding_rejects_stale_unbound_semantic_input(tmp_path):
    request, source_identity = _verified_editorial_request(
        "This finding changes planning priorities.", "interpretive"
    )
    package = validate_retained_claims(
        request.artifacts,
        request.evidence_packs,
        source_identity=source_identity,
        verified_facts_only=True,
    )
    inputs = retained_claim_semantic_inputs(
        package,
        request.evidence_packs,
        source_identity=source_identity,
    )
    unbound = next(item for item in inputs if not item.candidate.evidence_references)
    stale_candidate = replace(unbound.candidate, allow_unbound_evidence=False)
    stale_input = replace(unbound, candidate=stale_candidate)

    with pytest.raises(AppError) as caught:
        run_grounding_check(
            request=request,
            settings=validation_settings(tmp_path),
            grounding_use_vector_store=False,
            evidence_texts=[],
            evidence_windows=[],
            prompt_client=ValidationFakePromptClient(),
            openai_client=FakeOpenAI(grounding_payload={"checks": []}),
            ctx=validation_ctx(),
            source_id=source_identity,
            retained_claim_package=package,
            retained_claim_inputs=[stale_input],
        )

    assert caught.value.code == "grounding_verified_semantic_input_invalid"


def test_verified_grounding_accepts_one_model_owned_verdict_per_item(tmp_path):
    request, source_identity = _verified_editorial_request(
        "This finding changes planning priorities.", "interpretive"
    )
    inventory = grounding_payload(request, request.artifacts)
    protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    response = {
        "checks": [
            {
                "item_id": item["item_id"],
                "classification": (
                    "analyst_interpretation"
                    if str(item["item_id"]).startswith("soft_copy:")
                    else "factual_claim"
                ),
                "entailment_outcome": "entailed",
                "violation_type": "none",
                "proposition_status": "compatible",
                "protected_facts": protected_facts,
                "reason": "The linked canonical evidence supports this item.",
            }
            for item in inventory["public_factual_items"]
        ]
    }

    issues = run_grounding_check(
        request=request,
        settings=validation_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=ValidationFakePromptClient(),
        openai_client=FakeOpenAI(grounding_payload=response),
        ctx=validation_ctx(),
        source_id=source_identity,
    )

    assert issues == []


def test_verified_grounding_adapts_raw_single_verdicts_and_derives_negative_projection(
    tmp_path,
):
    request, source_identity = _verified_editorial_request(
        "This finding changes planning priorities.", "interpretive"
    )
    package = validate_retained_claims(
        request.artifacts,
        request.evidence_packs,
        source_identity=source_identity,
        verified_facts_only=True,
    )
    retained_inputs = retained_claim_semantic_inputs(
        package,
        request.evidence_packs,
        source_identity=source_identity,
    )
    inventory = grounding_payload(
        request,
        request.artifacts,
        retained_claim_inputs=retained_inputs,
    )
    protected_facts = {
        dimension: {
            "claim_value": None,
            "evidence_value": None,
            "status": "unknown",
        }
        for dimension in PROTECTED_FACT_DIMENSIONS
    }
    raw_checks = []
    all_items = [
        *inventory["retained_claims_to_ground"],
        *inventory["public_factual_items"],
    ]
    negative_item_id = inventory["public_factual_items"][0]["item_id"]
    for item in all_items:
        item_id = str(item["item_id"])
        is_negative_item = item_id == negative_item_id
        is_editorial_item = (
            str(item.get("declared_classification") or "") == "analyst_interpretation"
        )
        raw_checks.append(
            {
                "item_id": item_id,
                "classification": (
                    "analyst_interpretation" if is_editorial_item else "factual_claim"
                ),
                "entailment_outcome": (
                    "not_established" if is_negative_item else "entailed"
                ),
                "violation_type": (
                    "unsupported_factual_claim" if is_negative_item else "none"
                ),
                "proposition_status": ("unknown" if is_negative_item else "compatible"),
                "protected_facts": protected_facts,
                "reason": (
                    "The linked canonical evidence does not establish the claim."
                    if is_negative_item
                    else "The linked canonical evidence supports this item."
                ),
            }
        )

    # This is intentionally the provider-owned shape: no text, section, or
    # duplicated unsupported record.  The adapter must restore canonical
    # inventory fields and derive the downstream negative projection.
    issues = run_grounding_check(
        request=request,
        settings=validation_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=ValidationFakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"checks": raw_checks},
            complete_grounding_contract=False,
        ),
        ctx=validation_ctx(),
        source_id=source_identity,
        retained_claim_package=package,
        retained_claim_inputs=retained_inputs,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "grounding"
    assert "[factual_claim|not_established]" in issues[0].message
    assert "validation_grounding_invalid_json" not in issues[0].message
