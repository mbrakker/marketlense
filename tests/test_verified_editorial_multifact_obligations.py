import pytest

from src.generators._artifact_generator.generation import (
    _verified_editorial_obligation_context,
)
from src.utils.errors import AppError


def test_initial_obligations_include_every_canonical_fact_bound_to_candidate():
    plan = {
        "themes": [
            {
                "theme": "Comparison",
                "importance": "essential",
                "coverage_obligation": "Compare both populations.",
                "evidence_ids": ["verified-fact:first", "verified-fact:second"],
                "feasible_candidate_ids": ["combined"],
            }
        ]
    }
    candidate = {
        "id": "combined",
        "text": "Compare the two populations.",
        "evidence_id": "verified-fact:first",
        "evidence_ids": ["verified-fact:first", "verified-fact:second"],
        "verified_fact_id": "first",
    }
    facts = [
        {
            "fact_id": "first",
            "statement": "First population.",
            "metric": {"cohort": "first"},
            "qualifiers": [],
        },
        {
            "fact_id": "second",
            "statement": "Second population.",
            "metric": {"cohort": "second"},
            "qualifiers": ["Forecast"],
        },
    ]

    result = _verified_editorial_obligation_context(plan, [candidate], facts)

    assert result["themes"][0]["verified_fact_ids"] == ["first", "second"]
    assert [fact["fact_id"] for fact in result["authoritative_facts"]] == [
        "first",
        "second",
    ]
    assert result["authoritative_facts"][1]["qualifiers"] == ["Forecast"]


def test_additional_candidate_preserves_each_real_bound_fact_without_inventing_one():
    candidate = {
        "id": "additional",
        "evidence_id": "verified-fact:first",
        "evidence_ids": [
            "verified-fact:first",
            "verified-fact:second",
            "verified-fact:missing",
        ],
        "verified_fact_id": "first",
    }
    facts = [
        {
            "fact_id": "first",
            "statement": "First fact.",
            "metric": {},
            "qualifiers": [],
        },
        {
            "fact_id": "second",
            "statement": "Second fact.",
            "metric": {},
            "qualifiers": ["Conditional"],
        },
    ]

    result = _verified_editorial_obligation_context({"themes": []}, [candidate], facts)

    assert [
        (fact["fact_id"], fact["evidence_id"])
        for fact in result["additional_admitted_facts"]
    ] == [("first", "verified-fact:first"), ("second", "verified-fact:second")]
    assert result["additional_admitted_facts"][1]["qualifiers"] == ["Conditional"]


def test_additional_facts_keep_their_own_evidence_when_primary_fact_differs():
    candidate = {
        "id": "combined",
        "evidence_id": "verified-fact:first",
        "evidence_ids": ["verified-fact:first", "verified-fact:second"],
        "verified_fact_id": "second",
    }
    facts = [
        {
            "fact_id": "first",
            "statement": "First fact.",
            "metric": {},
            "qualifiers": [],
        },
        {
            "fact_id": "second",
            "statement": "Second fact.",
            "metric": {},
            "qualifiers": [],
        },
    ]

    result = _verified_editorial_obligation_context({"themes": []}, [candidate], facts)

    assert {
        fact["fact_id"]: fact["evidence_id"]
        for fact in result["additional_admitted_facts"]
    } == {"first": "verified-fact:first", "second": "verified-fact:second"}


def test_unbound_fact_id_does_not_promote_an_unrelated_canonical_fact():
    candidate = {
        "id": "combined",
        "evidence_id": "verified-fact:first",
        "evidence_ids": ["verified-fact:first"],
        "verified_fact_id": "second",
    }
    facts = [
        {
            "fact_id": "first",
            "statement": "First fact.",
            "metric": {},
            "qualifiers": [],
        },
        {
            "fact_id": "second",
            "statement": "Second fact.",
            "metric": {},
            "qualifiers": [],
        },
    ]
    plan = {
        "themes": [
            {
                "theme": "A",
                "importance": "essential",
                "evidence_ids": ["verified-fact:first"],
                "feasible_candidate_ids": ["combined"],
            }
        ]
    }

    with pytest.raises(AppError) as exc_info:
        _verified_editorial_obligation_context(plan, [candidate], facts)

    assert exc_info.value.code == "verified_editorial_candidate_binding_conflict"


def test_unbound_additional_fact_id_fails_closed():
    candidate = {
        "id": "additional",
        "evidence_id": "verified-fact:first",
        "evidence_ids": ["verified-fact:first"],
        "verified_fact_id": "second",
    }
    facts = [
        {
            "fact_id": "first",
            "statement": "First fact.",
            "metric": {},
            "qualifiers": [],
        },
        {
            "fact_id": "second",
            "statement": "Second fact.",
            "metric": {},
            "qualifiers": [],
        },
    ]

    with pytest.raises(AppError) as exc_info:
        _verified_editorial_obligation_context({"themes": []}, [candidate], facts)

    assert exc_info.value.code == "verified_editorial_candidate_binding_conflict"
