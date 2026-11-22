from src.generators._artifact_generator.generation import (
    _verified_editorial_obligation_context,
)


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
