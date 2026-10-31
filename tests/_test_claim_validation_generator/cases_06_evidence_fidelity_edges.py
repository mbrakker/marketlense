# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_evidence_fidelity_accepts_a_normalized_quote_and_keeps_unknown_unknown() -> (
    None
):
    quote = validate_evidence_fidelity(
        {
            "quote_candidates": {
                "quote_candidates": [
                    {"id": "q1", "text": '"Payments are now core infrastructure."'}
                ]
            }
        },
        source_spans=[
            {"id": "source:1", "text": "Payments are now core infrastructure."}
        ],
        semantic_validator=_semantic_support,
    )
    unknown = validate_evidence_fidelity(
        {"findings": {"findings": [{"id": "f1", "text": "Advertising grew 18%."}]}},
        source_spans=[{"id": "source:1", "text": "Advertising grew 18%."}],
    )

    assert quote.results[0].status == "supported"
    assert quote.semantic_validation_count == 1
    assert unknown.results[0].protected_facts is not None
    assert unknown.results[0].protected_facts.dimension("timeframe").status == "unknown"
