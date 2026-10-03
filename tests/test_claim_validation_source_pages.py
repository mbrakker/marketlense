from types import SimpleNamespace

from src.contracts.pdf_text import PdfTextPage
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import (
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
    return package, evidence_packs, claim


def test_page_bound_claim_uses_exact_retained_pdf_page_and_hashes_it():
    package, evidence_packs, claim = _page_grounded_claim_case()
    page_text = (
        "The shopper and business surveys were conducted in parallel from "
        "December 2025 to February 2026."
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
                text="The surveys ran at a different time according to this page.",
            )
        ],
    )

    assert len(semantic_inputs) == 1
    assert semantic_inputs[0].candidate.text == claim
    assert page_text in semantic_inputs[0].evidence_texts
    assert semantic_inputs[0].evidence_hash != changed_page_inputs[0].evidence_hash


def test_page_bound_claim_does_not_borrow_text_from_a_different_pdf_page():
    package, evidence_packs, _claim = _page_grounded_claim_case()
    wrong_page_text = "An unrelated passage from page 77."

    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity="source:dhl-ecommerce",
        source_pages=[PdfTextPage(page_number=77, text=wrong_page_text)],
    )

    assert len(semantic_inputs) == 1
    assert wrong_page_text not in semantic_inputs[0].evidence_texts


def test_grounding_rule_can_validate_claim_against_its_cited_source_page(tmp_path):
    package, evidence_packs, claim = _page_grounded_claim_case()
    page_text = (
        "The shopper and business surveys were conducted in parallel from "
        "December 2025 to February 2026."
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
