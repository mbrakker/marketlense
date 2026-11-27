from __future__ import annotations

from dataclasses import replace

import pytest

from src.generators.verified_claims_canary import admit_visual_authority_candidates
from src.utils.cache_utils import sha256_json
from tests.test_verified_claims_visual_authority_canary import (
    SOURCE_IDENTITY,
    _candidate,
    _evidence_packs,
    _response,
    _result,
)


def _admit(source_reading, *, assessment=None, comparison=None):
    candidate = _candidate(page=5)
    base_result = _result(candidate)
    fact_content = {
        key: base_result.verified_fact[key]
        for key in ("statement", "metric", "qualifiers")
    }
    result = replace(
        base_result,
        inspected_physical_pages=[5],
        source_reading=source_reading,
        source_reading_assessment=(
            assessment
            if assessment is not None
            else {
                "outcome": "supported",
                "supporting_physical_pages": [5],
                "explanation": "The source reading covers the claim on page 5.",
                "source_reading_digest": sha256_json(source_reading),
            }
        ),
        source_reading_comparison=(
            comparison
            if comparison is not None
            else {
                "outcome": "supported",
                "supporting_physical_pages": [5],
                "explanation": "The source reading covers the final claim.",
                "source_reading_digest": sha256_json(source_reading),
                "claim_digest": sha256_json(candidate["text"]),
                "fact_content_digest": sha256_json(fact_content),
            }
        ),
    )
    return admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )


def _reading(*, source_identity=SOURCE_IDENTITY, page=5):
    return {
        "schema_version": "1.0",
        "source_identity": source_identity,
        "pages": [
            {
                "physical_page": page,
                "observations": [
                    "Online research before purchase rose to 42% in 2026."
                ],
                "uncertainties": [],
            }
        ],
    }


@pytest.mark.parametrize(
    "source_reading",
    [
        pytest.param({}, id="legacy-missing-reading"),
        pytest.param(
            _reading(source_identity=f"other-report|pdf-sha256:{'b' * 64}"),
            id="different-source",
        ),
        pytest.param(_reading(page=6), id="different-page"),
    ],
)
def test_verified_result_without_matching_source_reading_is_not_admitted(
    source_reading,
):
    admission = _admit(source_reading)

    assert admission.verified_facts == []
    assert admission.admitted_candidates == []


def test_verified_result_with_matching_source_reading_is_admitted():
    admission = _admit(_reading())

    assert [fact["fact_id"] for fact in admission.verified_facts] == ["candidate-1"]
    assert len(admission.admitted_candidates) == 1
    recorded = admission.verified_facts[0]["provenance"]["source_reading_assessment"]
    assert recorded["outcome"] == "supported"
    assert recorded["source_reading_digest"] == sha256_json(_reading())


@pytest.mark.parametrize(
    "assessment",
    [
        {},
        {
            "outcome": "disagreement",
            "supporting_physical_pages": [5],
            "explanation": "Conflicts",
            "source_reading_digest": "bad",
        },
        {
            "outcome": "supported",
            "supporting_physical_pages": [5],
            "explanation": "Claims match",
            "source_reading_digest": "bad",
        },
    ],
)
def test_admission_rejects_unbound_or_negative_source_assessment(assessment):
    admission = _admit(_reading(), assessment=assessment)
    assert admission.verified_facts == []


def test_admission_rejects_missing_independent_comparison():
    assert _admit(_reading(), comparison={}).verified_facts == []


def test_admission_rejects_comparison_bound_to_another_claim():
    comparison = {
        "outcome": "supported",
        "supporting_physical_pages": [5],
        "explanation": "The reading supports the claim.",
        "source_reading_digest": sha256_json(_reading()),
        "claim_digest": sha256_json("different claim"),
    }
    assert _admit(_reading(), comparison=comparison).verified_facts == []


def test_admission_rejects_comparison_bound_to_another_fact():
    candidate = _candidate(page=5)
    comparison = {
        "outcome": "supported",
        "supporting_physical_pages": [5],
        "explanation": "The reading supports the claim.",
        "source_reading_digest": sha256_json(_reading()),
        "claim_digest": sha256_json(candidate["text"]),
        "fact_content_digest": sha256_json({"statement": "different fact"}),
    }
    assert _admit(_reading(), comparison=comparison).verified_facts == []


def test_quarantined_comparison_preserves_typed_failure_reason():
    candidate = _candidate(page=5)
    unresolved = replace(
        _result(candidate, outcome="unresolved"),
        failure_reason="source_comparison_contradicted",
    )
    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(unresolved),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )
    assert (
        admission.audit["quarantined"][0]["failure_reason"]
        == "source_comparison_contradicted"
    )
