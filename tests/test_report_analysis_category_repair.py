from __future__ import annotations

from types import SimpleNamespace

from src.contracts.context_category_fit import CategoryFitCandidate
from src.orchestrators.report_analysis_orchestrator import (
    _category_fit_ambiguity_ids,
    _category_fit_reclassification_candidates,
    _category_fit_repair_code,
)


def test_category_fit_ambiguity_requires_repair_when_selection_was_withheld() -> None:
    """An ambiguous primary candidate cannot silently become an uncategorized report."""
    state = SimpleNamespace(
        fit_response=SimpleNamespace(
            fits=[
                CategoryFitCandidate(
                    schema_version="1.0",
                    category_id="technology",
                    label="Technology & Innovation",
                    fit_score=0.95,
                    decision="primary",
                    why_fit="Technology is the report's dominant subject.",
                    why_not_fit="",
                    evidence_sections=["Overview"],
                    semantic_rule_status="ambiguous",
                    remediation_signal="topic_semantics_ambiguous",
                ),
                CategoryFitCandidate(
                    schema_version="1.0",
                    category_id="consumer_behavior",
                    label="Consumer Behavior & Insights",
                    fit_score=0.4,
                    decision="reject",
                    why_fit="",
                    why_not_fit="Consumer evidence is supporting only.",
                    evidence_sections=["Overview"],
                    semantic_rule_status="rejected",
                ),
            ]
        )
    )

    state.category_assignment = SimpleNamespace(categories=["technology"])

    assert _category_fit_ambiguity_ids(state) == ["technology"]
    assert _category_fit_reclassification_candidates(state) == ["technology"]
    assert _category_fit_repair_code(state) == "category_fit_contradiction"


def test_empty_category_fit_requires_one_targeted_repair() -> None:
    state = SimpleNamespace(
        category_assignment=SimpleNamespace(categories=[]),
        fit_response=SimpleNamespace(fits=[]),
    )

    assert _category_fit_repair_code(state) == "category_fit_empty"


def test_all_rejected_category_fit_is_an_explicit_uncategorized_outcome() -> None:
    state = SimpleNamespace(
        category_assignment=SimpleNamespace(categories=[]),
        fit_response=SimpleNamespace(
            fits=[
                CategoryFitCandidate(
                    schema_version="1.0",
                    category_id="technology",
                    label="Technology & Innovation",
                    fit_score=0.2,
                    decision="reject",
                    why_fit="",
                    why_not_fit="The report does not cover technology as a topic.",
                    evidence_sections=["Overview"],
                    semantic_rule_status="rejected",
                )
            ]
        ),
    )

    assert _category_fit_repair_code(state) == ""
