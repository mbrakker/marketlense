from src.contracts.pdf_text import PdfTextPage
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)


def _case(*, excerpt_value="68", include_excerpt=True):
    claim = "68% of consumers expect brands to use data for relevant experiences."
    evidence = (
        f"{excerpt_value}% of consumers expect brands to use data "
        "for relevant experiences."
    )
    finding = {"id": "data-expectations", "text": claim, "page": 13}
    if include_excerpt:
        finding["evidence"] = f"“{evidence}”"
    artifacts = {
        "insights_final": [
            {
                "id": "data-relevance",
                "text": claim,
                "evidence_id": finding["id"],
                "evidence_spans": [{"evidence_id": finding["id"], "page": 13}],
            }
        ]
    }
    return artifacts, {"findings": {"findings": [finding]}}


def test_generated_finding_text_cannot_prove_a_number_absent_from_source_excerpt():
    artifacts, packs = _case(excerpt_value="67")

    package = validate_retained_claims(artifacts, packs)

    result = package.results[0]
    assert result.status == "unsupported"
    assert any(
        check.name == "number_value_unit_match" and check.status == "failed"
        for check in result.checks
    )


def test_direct_source_excerpt_is_not_concatenated_with_generated_copy():
    artifacts, packs = _case()
    # A descriptive claim requests semantic grounding instead of a numeric pass.
    artifacts["insights_final"][0]["text"] = (
        "Consumers expect relevant experiences from brands."
    )
    package = validate_retained_claims(artifacts, packs)

    inputs = retained_claim_semantic_inputs(
        package, packs, source_identity="source:data-expectations"
    )

    assert len(inputs) == 1
    assert inputs[0].evidence_texts
    assert all(
        text == packs["findings"]["findings"][0]["evidence"]
        for text in inputs[0].evidence_texts
    )
    bound = retained_claim_semantic_inputs(
        package,
        packs,
        source_identity="source:data-expectations",
        source_pages=[PdfTextPage(page_number=13, text="Physical page thirteen.")],
    )
    assert all(text == "Physical page thirteen." for text in bound[0].evidence_texts)


def test_source_text_remains_usable_when_no_separate_excerpt_exists():
    artifacts, packs = _case(include_excerpt=False)

    assert validate_retained_claims(artifacts, packs).results[0].status == "supported"


def test_retained_quote_text_alias_remains_usable_as_direct_evidence():
    package = validate_retained_claims(
        {
            "insights_final": [
                {
                    "id": "privacy",
                    "text": 'The report says "Privacy matters."',
                    "evidence_id": "privacy-source",
                }
            ]
        },
        {
            "quote_candidates": {
                "quotes": [{"id": "privacy-source", "quote_text": "Privacy matters."}]
            }
        },
    )

    assert package.results[0].status == "supported"
