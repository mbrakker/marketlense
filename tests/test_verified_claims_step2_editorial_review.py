from __future__ import annotations

from scripts.quality.review_verified_claims_step2_editorial import (
    _validate_result_binding,
    _validate_review_payload,
)

_DIMENSIONS = (
    "factual_fidelity",
    "analytical_validity",
    "specificity",
    "commercial_relevance",
    "editorial_quality",
    "selection_quality",
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": "approved",
        "explanation": (
            "The final claim is specific, useful, and grounded in the supplied page."
        ),
        "source_grounded_explanation": (
            "Physical page 12 reports the observed cohort relationship and the "
            "stated period; "
            "that bounded pattern supports the commercial implication."
        ),
        "supporting_physical_pages": [12],
        "source_truth_notes_by_page": {
            "12": (
                "Physical page 12 reports the observed cohort relationship for "
                "the stated period."
            )
        },
        "defects": [],
        "suggested_correction": "",
    }
    payload.update(
        {
            dimension: {
                "rating": "strong",
                "explanation": "The claim passes this dimension.",
            }
            for dimension in _DIMENSIONS
        }
    )
    payload.update(overrides)
    return payload


def test_approved_review_requires_complete_source_grounding() -> None:
    validated = _validate_review_payload(_payload(), inspected_physical_pages=[12])

    assert validated["decision"] == "approved"
    assert validated["supporting_physical_pages"] == [12]
    assert validated["diagnostics"] == []


def test_material_factual_issue_cannot_be_approved() -> None:
    validated = _validate_review_payload(
        _payload(
            factual_fidelity={
                "rating": "material_issue",
                "explanation": "The denominator is not supported by the page.",
            }
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] != "approved"
    assert "material_factual_issue_blocks_approval" in validated["diagnostics"]


def test_malformed_review_response_fails_closed() -> None:
    validated = _validate_review_payload(
        {"decision": "approved", "explanation": "looks good"},
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "review_response_invalid" in validated["diagnostics"]


def test_review_pages_must_be_inspected_and_notes_must_match() -> None:
    validated = _validate_review_payload(
        _payload(
            supporting_physical_pages=[13],
            source_truth_notes_by_page={"12": "Wrong page note."},
        ),
        inspected_physical_pages=[12],
    )

    assert validated["decision"] == "unresolved"
    assert "supporting_pages_invalid" in validated["diagnostics"]


def test_provisional_recovery_pages_are_reviewable_without_promotion() -> None:
    pages, reason = _validate_result_binding(
        {
            "source_identity": "report|pdf-sha256:" + "a" * 64,
            "physical_pages": [],
            "original_physical_pages": [],
            "inspected_physical_pages": [12, 14],
            "source_binding_status": "provisional_recovered",
        },
        {
            "sha256_matches": True,
            "sha256_expected": "a" * 64,
            "page_count": 20,
        },
    )

    assert reason == ""
    assert pages == [12, 14]
