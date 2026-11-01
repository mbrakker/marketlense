from __future__ import annotations

import pytest

from src.generators.claim_validation_generator import validate_retained_claims
from tests._test_claim_validation_generator._shared import _semantic_result


def _validate(claim: str, source: str, *, supported: bool = True):
    def semantic_batch(inputs):
        return [
            _semantic_result(
                item,
                outcome="entailed" if supported else "contradicted",
                proposition_status="compatible" if supported else "incompatible",
            )
            for item in inputs
        ]

    package = validate_retained_claims(
        {
            "insights_final": [
                {"id": "privacy", "text": claim, "evidence_id": "privacy-source"}
            ]
        },
        {
            "findings": {
                "findings": [
                    {"id": "privacy-source", "text": source, "evidence": source}
                ]
            }
        },
        semantic_batch_validator=semantic_batch,
    )
    assert len(package.results) == 1
    return package.results[0]


@pytest.mark.parametrize(
    "claim",
    [
        "Consumers' expectations of brands' data use reached 68%.",
        "Consumers’ expectations of brands’ data use reached 68%.",
        "Consumers don't trust brands' data use: 68% expressed concern.",
        "Consumers don’t trust brands’ data use: 68% expressed concern.",
    ],
)
@pytest.mark.parametrize(
    "source_percent,expected_status", [(68, "supported"), (67, "unsupported")]
)
def test_apostrophes_preserve_numeric_validation(
    claim, source_percent, expected_status
) -> None:
    result = _validate(
        claim,
        claim.replace("68%", f"{source_percent}%"),
        supported=expected_status == "supported",
    )

    assert result.candidate.kind == "descriptive"
    assert result.status == expected_status
    assert result.semantic_validator_used is True
    assert not any(check.name == "quote_match" for check in result.checks)
    assert not any(check.name == "number_value_unit_match" for check in result.checks)


@pytest.mark.parametrize(
    "opening,closing", [("'", "'"), ('"', '"'), ("‘", "’"), ("“", "”")]
)
@pytest.mark.parametrize("verbatim", [True, False])
def test_actual_quotations_require_verbatim_source(opening, closing, verbatim) -> None:
    quoted = "Privacy shapes consumer trust."
    result = _validate(
        f"The report says {opening}{quoted}{closing}",
        quoted if verbatim else "Privacy has no effect on consumer trust.",
        supported=verbatim,
    )

    assert result.candidate.kind == "descriptive"
    assert result.status == ("supported" if verbatim else "unsupported")
    assert result.semantic_validator_used is True
    assert not any(check.name == "quote_match" for check in result.checks)


@pytest.mark.parametrize(
    "opening,closing,quoted,partial_source",
    [
        ("'", "'", "Consumers' expectations shape brands' data use.", "Consumers"),
        ("‘", "’", "Consumers’ expectations shape brands’ data use.", "Consumers"),
        ("'", "'", "A customer's privacy matters.", "A customer"),
        ("‘", "’", "A customer’s privacy matters.", "A customer"),
    ],
)
def test_partial_quotation_before_apostrophe_does_not_count_as_source_match(
    opening, closing, quoted, partial_source
) -> None:
    result = _validate(
        f"The report says {opening}{quoted}{closing}",
        partial_source,
        supported=False,
    )

    assert result.candidate.kind == "descriptive"
    assert result.status == "unsupported"
    assert result.semantic_validator_used is True
    assert not any(check.name == "quote_match" for check in result.checks)


@pytest.mark.parametrize("opening,closing", [("'", "'"), ("‘", "’")])
def test_ambiguous_closing_quote_and_narrator_possessive_abstains(opening, closing):
    result = _validate(
        f"The report says {opening}Privacy matters{closing} and consumers{closing} "
        "choices affect trust.",
        "Privacy matters",
        supported=True,
    )

    assert result.status == "supported"
    assert result.semantic_validator_used is True
    assert not any(
        check.reason == "ambiguous_quote_boundaries" for check in result.checks
    )


def test_possessive_metric_subject_is_checked_in_insights_and_key_figures() -> None:
    metric = {
        "label": "Consumers expecting relevant experiences",
        "subject": "Consumers' expectations of brands' data use",
        "value": "68%",
        "unit": "percent",
    }
    evidence = {
        "id": "data-use",
        "evidence": (
            "68% of consumers expect brands to use data for relevant experiences."
        ),
    }
    package = validate_retained_claims(
        {
            "insights_final": [
                {"id": "data-use", "metric": metric, "evidence_id": "data-use"}
            ],
            "key_figures": [{**metric, "id": "data-use", "evidence_id": "data-use"}],
        },
        {"findings": {"findings": [evidence]}},
        semantic_batch_validator=lambda inputs: [
            _semantic_result(item) for item in inputs
        ],
    )

    assert {result.candidate.entity_id for result in package.results} == {
        "insight:data-use:metric",
        "key_figure:data-use:figure",
    }
    assert all(result.candidate.kind == "descriptive" for result in package.results)
    assert all(result.status == "supported" for result in package.results)
    assert all(result.semantic_validator_used is True for result in package.results)
    assert all(
        check.name != "quote_match"
        for result in package.results
        for check in result.checks
    )


@pytest.mark.parametrize(
    "opening,closing,quoted",
    [
        ("'", "'", "A customer's privacy matters."),
        ("‘", "’", "A customer’s privacy matters."),
        ("'", "'", "Consumers' expectations shape brands' data use."),
        ("‘", "’", "Consumers’ expectations shape brands’ data use."),
    ],
)
@pytest.mark.parametrize("verbatim", [True, False])
def test_apostrophes_inside_real_quotations_preserve_verbatim_validation(
    opening, closing, quoted, verbatim
):
    result = _validate(
        f"The report says {opening}{quoted}{closing}",
        quoted if verbatim else "The report discusses different subject matter.",
        supported=verbatim,
    )

    assert result.candidate.kind == "descriptive"
    assert result.status == ("supported" if verbatim else "unsupported")
    assert result.semantic_validator_used is True
    assert not any(check.name == "quote_match" for check in result.checks)
