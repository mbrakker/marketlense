from types import SimpleNamespace

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticValidationIdentity,
)
from src.contracts.pdf_text import PdfTextPage
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import (
    apply_retained_claim_semantic_results,
    attach_claim_validation_execution_identity,
    materialize_retained_claim_package,
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import grounding_payload, run_grounding_rule
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _page_grounded_claim_case():
    claim = (
        "The parallel shopper and business surveys ran from December 2025 "
        "to February 2026."
    )
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "survey-period",
                    "claim": claim,
                    "evidence_id": "methodology",
                    "evidence_spans": [
                        {"evidence_id": "methodology", "page": 78}
                    ],
                }
            ]
        }
    }
    evidence_packs = {
        "doc_map": {
            "sections": [
                {
                    "id": "methodology",
                    "summary": "The report includes a methodology section.",
                    "pages": [78],
                }
            ]
        }
    }
    package = validate_retained_claims(artifacts, evidence_packs)
    return package, evidence_packs, claim, artifacts


def _page_grounded_semantic_result(semantic_input):
    identity = ClaimSemanticValidationIdentity(
        schema_version="1.0",
        claim_id=semantic_input.candidate.claim_id,
        claim_text_hash=semantic_input.candidate.text_hash,
        evidence_ids=[
            reference.evidence_id
            for reference in semantic_input.candidate.evidence_references
        ],
        evidence_hash=semantic_input.evidence_hash,
        source_identity=semantic_input.source_identity,
        prompt_family="report_vs/validate/grounding",
        prompt_content_hash="grounding-prompt-sha256",
        execution_identity="grounding-execution-1",
        validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        model_provider="openai",
        model_name="test-model",
        configuration_policy_identity="grounding-policy-sha256",
        relevant_input_hash="grounding-input-sha256",
    )
    return ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome="entailed",
        reason="cited_page_entails_claim",
        identity=identity,
    )


def test_page_bound_claim_uses_exact_retained_pdf_page_and_hashes_it():
    package, evidence_packs, claim, _artifacts = _page_grounded_claim_case()
    page_text = (
        "The shopper and business surveys were conducted in parallel from "
        "December 2025 to February 2026.\n2026 E-Commerce Trends Report\n78"
    )

    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=[PdfTextPage(page_number=78, text=page_text)],
    )
    changed_page_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=[
            PdfTextPage(
                page_number=78,
                text=(
                    "The surveys ran at a different time according to this page.\n"
                    "2026 E-Commerce Trends Report\n78"
                ),
            )
        ],
    )

    assert len(semantic_inputs) == 1
    assert semantic_inputs[0].candidate.text == claim
    assert page_text in semantic_inputs[0].evidence_texts
    assert semantic_inputs[0].evidence_hash != changed_page_inputs[0].evidence_hash


def test_page_bound_claim_does_not_borrow_text_from_a_different_pdf_page():
    package, evidence_packs, _claim, _artifacts = _page_grounded_claim_case()
    wrong_page_text = "An unrelated passage from page 77."

    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=[PdfTextPage(page_number=77, text=wrong_page_text)],
    )

    assert len(semantic_inputs) == 1
    assert wrong_page_text not in semantic_inputs[0].evidence_texts


def test_doc_map_printed_page_resolves_to_physical_pdf_page():
    claim = "Publishers' prospects depend on adaptation and audience value."
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "conclusion",
                    "claim": claim,
                    "evidence_id": "conclusions",
                    "evidence_spans": [
                        {"evidence_id": "conclusions", "page": 42}
                    ],
                }
            ]
        }
    }
    evidence_packs = {
        "doc_map": {
            "sections": [
                {
                    "id": "conclusions",
                    "summary": (
                        "The conclusion identifies adaptation, clear purpose, "
                        "and value to specific audiences as important to "
                        "publishers' prospects."
                    ),
                    "pages": [42],
                }
            ]
        }
    }
    package = validate_retained_claims(artifacts, evidence_packs)
    wrong_physical_page = (
        "THE REUTERS INSTITUTE FOR THE STUDY OF JOURNALISM\n"
        "40\nA page about new AI devices and voice assistants."
    )
    cited_printed_page = (
        "THE REUTERS INSTITUTE FOR THE STUDY OF JOURNALISM\n"
        "42\nThe conclusions identify adaptation and audience value."
    )

    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:reuters-institute",
        source_pages=[
            PdfTextPage(page_number=42, text=wrong_physical_page),
            PdfTextPage(page_number=44, text=cited_printed_page),
        ],
    )

    assert len(semantic_inputs) == 1
    assert cited_printed_page in semantic_inputs[0].evidence_texts
    assert wrong_physical_page not in semantic_inputs[0].evidence_texts


def test_doc_map_printed_page_resolves_from_trailing_pdf_header_label():
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "stewardship",
                    "claim": "The report describes stewardship work entering 2026.",
                    "evidence_id": "introduction",
                    "evidence_spans": [
                        {"evidence_id": "introduction", "page": 6}
                    ],
                }
            ]
        }
    }
    evidence_packs = {
        "doc_map": {
            "sections": [
                {
                    "id": "introduction",
                    "summary": "The introduction previews the report's focus.",
                    "pages": [6],
                }
            ]
        }
    }
    package = validate_retained_claims(artifacts, evidence_packs)
    printed_page_six = (
        "Active Ownership Report Q4-2025 \u2022 6\n"
        "The introduction previews stewardship work entering 2026."
    )

    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:robeco",
        source_pages=[
            PdfTextPage(page_number=6, text=printed_page_six),
            PdfTextPage(page_number=7, text="A different printed page 7."),
        ],
    )

    assert len(semantic_inputs) == 1
    assert printed_page_six in semantic_inputs[0].evidence_texts


def test_grounding_rule_can_validate_claim_against_its_cited_source_page(tmp_path):
    package, evidence_packs, claim, artifacts = _page_grounded_claim_case()
    page_text = (
        "The shopper and business surveys were conducted in parallel from "
        "December 2025 to February 2026.\n2026 E-Commerce Trends Report\n78"
    )
    request = ValidationRequest(
        schema_version="1.0",
        report_id="dhl-ecommerce",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {
                        "id": "survey-period",
                        "claim": claim,
                        "evidence_id": "methodology",
                        "evidence_spans": [
                            {"evidence_id": "methodology", "page": 78}
                        ],
                    }
                ]
            }
        },
        evidence_packs=evidence_packs,
        source_id="source:dhl-ecommerce",
        source_pages=[PdfTextPage(page_number=78, text=page_text)],
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity=request.source_id,
        source_pages=request.source_pages,
    )
    payload = grounding_payload(
        request,
        request.artifacts,
        retained_claim_inputs=semantic_inputs,
    )
    checks = [
        {
            "item_id": entry["item_id"],
            "section": entry["section"],
            "text": entry["text"],
            "classification": "factual_claim",
            "entailment_outcome": "entailed",
            "proposition_status": "compatible",
            "protected_facts": {
                dimension: {
                    "claim_value": None,
                    "evidence_value": None,
                    "status": "unknown",
                }
                for dimension in PROTECTED_FACT_DIMENSIONS
            },
            "reason": "cited_source_page_entails_claim",
        }
        for entry in payload["retained_claims_to_ground"]
    ]
    model_client = FakeOpenAI(grounding_payload={"unsupported": [], "checks": checks})
    runtime = SimpleNamespace(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        prepared=SimpleNamespace(
            grounding_use_vector_store=False,
            evidence_texts=[],
            evidence_windows=[],
        ),
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        source_id=request.source_id,
        vector_store_content_hash="",
        retained_claim_validation=package,
    )

    issues = run_grounding_rule(runtime)

    result = next(
        item
        for item in runtime.retained_claim_validation.results
        if item.candidate.claim_id == "summary_claim:survey-period"
    )
    assert issues == []
    assert result.status == "supported"
    assert result.semantic_outcome == "entailed"
    assert result.semantic_identity is not None
    assert result.semantic_identity.evidence_hash == semantic_inputs[0].evidence_hash


def test_final_materialization_reuses_matching_page_bound_semantic_result():
    package, evidence_packs, _claim, artifacts = _page_grounded_claim_case()
    source_pages = [
        PdfTextPage(
            page_number=78,
            text=(
                "The shopper and business surveys were conducted in parallel "
                "from December 2025 to February 2026.\n"
                "2026 E-Commerce Trends Report\n78"
            ),
        )
    ]
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=source_pages,
    )
    semantic_input = semantic_inputs[0]
    candidate = apply_retained_claim_semantic_results(
        package,
        semantic_inputs,
        [_page_grounded_semantic_result(semantic_input)],
    )
    candidate_payload = attach_claim_validation_execution_identity(
        candidate,
        report_id="dhl-ecommerce",
        source_id="source:dhl-ecommerce",
        source_md5="source-md5-dhl",
        configuration_hash="config-sha256",
        policy_hash="policy-sha256",
    )

    retained, failure_code = materialize_retained_claim_package(
        candidate_payload,
        report_id="dhl-ecommerce",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        final_html="<html><body>Validated report.</body></html>",
        source_id="source:dhl-ecommerce",
        source_md5="source-md5-dhl",
        configuration_hash="config-sha256",
        policy_hash="policy-sha256",
        source_pages=source_pages,
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["semantic_validation_count"] == 1
    assert retained["unresolved_factual_count"] == 0
    assert retained["results"][0]["semantic_identity"]["evidence_hash"] == (
        semantic_input.evidence_hash
    )


def test_final_materialization_rejects_stale_page_bound_semantic_result():
    package, evidence_packs, _claim, artifacts = _page_grounded_claim_case()
    source_pages = [
        PdfTextPage(
            page_number=78,
            text=(
                "The shopper and business surveys were conducted in parallel "
                "from December 2025 to February 2026."
            ),
        )
    ]
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=source_pages,
    )
    semantic_input = semantic_inputs[0]
    candidate = apply_retained_claim_semantic_results(
        package,
        semantic_inputs,
        [_page_grounded_semantic_result(semantic_input)],
    )
    candidate_payload = attach_claim_validation_execution_identity(
        candidate,
        report_id="dhl-ecommerce",
        source_id="source:dhl-ecommerce",
        source_md5="source-md5-dhl",
        configuration_hash="config-sha256",
        policy_hash="policy-sha256",
    )

    retained, failure_code = materialize_retained_claim_package(
        candidate_payload,
        report_id="dhl-ecommerce",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        final_html="<html><body>Validated report.</body></html>",
        source_id="source:dhl-ecommerce",
        source_md5="source-md5-dhl",
        configuration_hash="config-sha256",
        policy_hash="policy-sha256",
        source_pages=[
            PdfTextPage(
                page_number=78,
                text="A different page body.\n2026 E-Commerce Trends Report\n78",
            )
        ],
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["semantic_validation_count"] == 0
    assert retained["unresolved_factual_count"] == 1
    assert retained["readiness_status"] == "not_publishable"
