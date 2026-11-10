from __future__ import annotations

import pytest

from src.generators.artifact_normalization import (
    adaptive_final_insight_target_count,
    fallback_artifact_insights_from_findings,
    final_insight_editorial_coverage,
    normalize_artifact_editorial_plan,
    remap_editorial_plan_to_verified_facts,
    select_artifact_insights,
    validate_editorial_plan_evidence_ids,
    validate_final_insight_candidate_lineage,
    validate_substantive_editorial_theme_coverage,
)
from src.services._render_service.normalization import _coerce_limitation_items
from src.utils.errors import AppError


def _plan(*evidence_ids: str) -> dict[str, object]:
    return {
        "report_thesis": "The retained evidence defines the decision surface.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [evidence_id],
            }
            for index, evidence_id in enumerate(evidence_ids, start=1)
        ],
    }


def _finding(
    finding_id: str,
    section_id: str,
    *,
    confidence: str = "high",
    score: float = 0.9,
) -> dict[str, object]:
    return {
        "id": finding_id,
        "text": f"Finding {finding_id} has a supported implication.",
        "evidence": f"Source evidence for {finding_id}.",
        "confidence": confidence,
        "score": score,
        "pages": [4],
        "section_id": section_id,
    }


def _fidelity(*finding_ids: str) -> dict[str, object]:
    return {
        "results": [
            {
                "status": "supported",
                "candidate": {"claim_id": f"evidence:findings:{finding_id}"},
            }
            for finding_id in finding_ids
        ]
    }


def test_fallback_resolves_plan_section_refs_and_direct_ids() -> None:
    findings = {
        "findings": [
            _finding("ai-finding", "ai-infrastructure", score=0.8),
            _finding("cross-finding", "multiplatform-strategy", score=0.7),
            _finding("unsupported", "ignored", score=1.0),
        ]
    }
    selected = fallback_artifact_insights_from_findings(
        findings,
        limit=2,
        editorial_plan=_plan("ai-infrastructure", "cross-finding"),
        evidence_fidelity=_fidelity("ai-finding", "cross-finding"),
    )

    assert [item["evidence_id"] for item in selected] == [
        "ai-finding",
        "cross-finding",
    ]
    assert "unsupported" not in {item["evidence_id"] for item in selected}


def test_editorial_plan_rejects_noncanonical_evidence_ids() -> None:
    validate_editorial_plan_evidence_ids(
        _plan("finding-1", "finding-2"), {"finding-1", "finding-2"}
    )

    with pytest.raises(AppError, match="non-canonical evidence IDs"):
        validate_editorial_plan_evidence_ids(
            _plan("stale-finding-id", "finding-2"), {"finding-1", "finding-2"}
        )


def test_finding_fallback_does_not_let_one_section_monopolize_capacity():
    findings = {
        "findings": [
            _finding("a-1", "section-a", score=0.99),
            _finding("a-2", "section-a", score=0.98),
            _finding("a-3", "section-a", score=0.97),
            _finding("b-1", "section-b", score=0.7),
            _finding("c-1", "section-c", score=0.6),
        ]
    }
    selected = fallback_artifact_insights_from_findings(findings, limit=4)

    selected_ids = [item["evidence_id"] for item in selected]
    assert selected_ids[0] == "a-1"
    assert {"b-1", "c-1"}.issubset(selected_ids)
    assert len(selected_ids) == 4


def test_semantic_theme_coverage_fails_closed_for_uncovered_central_theme() -> None:
    plan = {
        "report_thesis": "The report defines two distinct decisions.",
        "themes": [
            {"theme": "Primary adoption", "priority": 2, "evidence_ids": ["f1"]},
            {
                "theme": "Implementation readiness",
                "priority": 1,
                "evidence_ids": ["f1"],
            },
        ],
    }

    with pytest.raises(AppError, match="central"):
        validate_substantive_editorial_theme_coverage(
            payload={
                "theme_coverage": [
                    {
                        "theme": "Primary adoption",
                        "status": "covered",
                        "supporting_insight_ids": ["insight-1"],
                        "explanation": "The final insight states the adoption result.",
                    },
                    {
                        "theme": "Implementation readiness",
                        "status": "uncovered",
                        "supporting_insight_ids": [],
                        "explanation": "The final roster does not discuss readiness.",
                    },
                ]
            },
            editorial_plan=plan,
            final_insights=[
                {
                    "id": "insight-1",
                    "text": "Adoption increased.",
                    "evidence_id": "f1",
                },
            ],
        )


def test_semantic_theme_coverage_fails_closed_for_noncentral_omission() -> None:
    plan = {
        "report_thesis": "The report defines two distinct decisions.",
        "themes": [
            {"theme": "Primary adoption", "priority": 1, "evidence_ids": ["f1"]},
            {
                "theme": "Implementation readiness",
                "priority": 2,
                "evidence_ids": ["f2"],
            },
        ],
    }

    with pytest.raises(AppError, match="planned theme") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload={
                "theme_coverage": [
                    {
                        "theme": "Primary adoption",
                        "status": "covered",
                        "supporting_insight_ids": ["insight-1"],
                        "explanation": "The final insight states the adoption result.",
                    },
                    {
                        "theme": "Implementation readiness",
                        "status": "partial",
                        "supporting_insight_ids": ["insight-2"],
                        "explanation": "The final roster omits the readiness result.",
                    },
                ]
            },
            editorial_plan=plan,
            final_insights=[
                {
                    "id": "insight-1",
                    "text": "Adoption increased.",
                    "evidence_id": "f1",
                },
                {
                    "id": "insight-2",
                    "text": "Readiness remains incomplete.",
                    "evidence_id": "f2",
                },
            ],
        )

    assert exc_info.value.context["omitted_themes"] == ["Implementation readiness"]


def test_semantic_theme_coverage_accepts_valid_distinct_supporting_ids() -> None:
    plan = {
        "report_thesis": "The report defines two distinct decisions.",
        "themes": [
            {"theme": "Primary adoption", "priority": 1, "evidence_ids": ["f1"]},
            {
                "theme": "Implementation readiness",
                "priority": 2,
                "evidence_ids": ["f1"],
            },
        ],
    }

    result = validate_substantive_editorial_theme_coverage(
        payload={
            "theme_coverage": [
                {
                    "theme": "Primary adoption",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-1"],
                    "explanation": "The first insight develops the adoption decision.",
                },
                {
                    "theme": "Implementation readiness",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-2"],
                    "explanation": (
                        "The second insight develops the readiness decision."
                    ),
                },
            ]
        },
        editorial_plan=plan,
        final_insights=[
            {"id": "insight-1", "text": "Adoption increased.", "evidence_id": "f1"},
            {
                "id": "insight-2",
                "text": "Implementation readiness improved.",
                "evidence_id": "f1",
            },
        ],
    )

    assert result["assessment_source"] == "independent_semantic_coverage"
    assert [item["status"] for item in result["theme_assessments"]] == [
        "covered",
        "covered",
    ]


def test_semantic_theme_coverage_rejects_supporting_insight_bound_to_other_fact() -> (
    None
):
    plan = {
        "report_thesis": "The report defines two distinct decisions.",
        "themes": [
            {"theme": "Primary adoption", "priority": 1, "evidence_ids": ["f1"]},
        ],
    }

    with pytest.raises(AppError, match="evidence-linked") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload={
                "theme_coverage": [
                    {
                        "theme": "Primary adoption",
                        "status": "covered",
                        "supporting_insight_ids": ["insight-1"],
                        "explanation": "The final wording claims to develop adoption.",
                    }
                ]
            },
            editorial_plan=plan,
            final_insights=[
                {
                    "id": "insight-1",
                    "text": "Implementation readiness improved.",
                    "evidence_id": "f2",
                }
            ],
        )

    assert exc_info.value.context["theme"] == "Primary adoption"
    assert exc_info.value.context["supporting_insight_ids"] == ["insight-1"]


def test_semantic_theme_coverage_accepts_supporting_insight_with_matching_fact() -> (
    None
):
    plan = {
        "report_thesis": "The report defines one decision.",
        "themes": [
            {"theme": "Primary adoption", "priority": 1, "evidence_ids": ["f1"]},
        ],
    }

    result = validate_substantive_editorial_theme_coverage(
        payload={
            "theme_coverage": [
                {
                    "theme": "Primary adoption",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-1"],
                    "explanation": "The final wording develops the adoption decision.",
                }
            ]
        },
        editorial_plan=plan,
        final_insights=[
            {
                "id": "insight-1",
                "text": "Adoption increased.",
                "evidence_id": "f1",
            }
        ],
    )

    assert result["theme_assessments"][0]["supporting_insight_ids"] == ["insight-1"]


def _verified_material_gap_fixture() -> tuple[
    dict[str, object], list[dict[str, object]], list[dict[str, object]]
]:
    plan = {
        "report_thesis": "The report defines one decision.",
        "material_limitation_evidence_ids": [],
        "themes": [
            {
                "theme": "Primary adoption",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop the adoption decision.",
                "evidence_ids": ["verified-fact:fact-1"],
            }
        ],
    }
    candidates = [
        {
            "id": "insight-1",
            "evidence_id": "verified-fact:fact-1",
            "verified_fact_id": "fact-1",
            "verified_fact": {"fact_id": "fact-1"},
        }
    ]
    final_insights = [{"id": "insight-1", "evidence_id": "verified-fact:fact-1"}]
    return plan, candidates, final_insights


def _incomplete_material_coverage_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "theme_coverage": [
            {
                "theme": "Primary adoption",
                "status": "covered",
                "resolution": "retained",
                "supporting_insight_ids": ["insight-1"],
                "explanation": "The final wording develops the adoption decision.",
            }
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
        "material_gaps": [
            {
                "verified_fact_ids": ["fact-1"],
                "evidence_ids": ["verified-fact:fact-1"],
                "final_insight_ids": ["insight-1"],
                "explanation": (
                    "The source fact's qualifier is not developed in the final wording."
                ),
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_verified_semantic_coverage_returns_source_bound_material_gaps() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()

    with pytest.raises(AppError, match="complete material-report") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload=_incomplete_material_coverage_payload(),
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )

    assert exc_info.value.context["material_gaps"] == [
        {
            "verified_fact_ids": ["fact-1"],
            "evidence_ids": ["verified-fact:fact-1"],
            "final_insight_ids": ["insight-1"],
            "explanation": (
                "The source fact's qualifier is not developed in the final wording."
            ),
        }
    ]


def test_verified_semantic_coverage_requires_gap_when_all_themes_are_covered() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(material_gaps=[])

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_rejects_unknown_material_gap_identity() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        material_gaps=[
            {
                "verified_fact_ids": ["fact-unknown"],
                "evidence_ids": ["verified-fact:fact-unknown"],
                "final_insight_ids": [],
                "explanation": "A source-bound material gap is identified.",
            }
        ]
    )

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_requires_empty_gaps_for_complete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        report_completeness="complete",
        diagnosis="planned_theme_execution",
        recovery_action="none",
    )

    with pytest.raises(AppError, match="material gap"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_semantic_coverage_rejects_none_for_incomplete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(recovery_action="none")

    with pytest.raises(AppError, match="incoherent") as exc_info:
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )

    assert exc_info.value.context["assessment_contract_failure"] is True


def test_verified_semantic_coverage_rejects_replan_for_complete_report() -> None:
    plan, candidates, final_insights = _verified_material_gap_fixture()
    payload = _incomplete_material_coverage_payload(
        report_completeness="complete",
        diagnosis="infeasible_plan",
        recovery_action="replan",
        material_gaps=[],
    )

    with pytest.raises(AppError, match="incoherent"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_verified_editorial_plan_preserves_adaptive_theme_contract() -> None:
    plan = normalize_artifact_editorial_plan(
        {
            "report_thesis": "The report shows a concentrated commercial shift.",
            "material_limitation_evidence_ids": ["verified-fact:limitation"],
            "themes": [
                {
                    "theme": "Core shift",
                    "priority": 1,
                    "importance": "essential",
                    "coverage_obligation": (
                        "Develop the directional change and its qualifier."
                    ),
                    "evidence_ids": ["verified-fact:fact-1"],
                    "feasible_candidate_ids": ["candidate-1"],
                    "merge_group": "core",
                },
                {
                    "theme": "Redundant context",
                    "priority": 2,
                    "importance": "optional",
                    "coverage_obligation": "Add context only if it is not redundant.",
                    "evidence_ids": ["verified-fact:fact-2"],
                    "feasible_candidate_ids": ["candidate-2"],
                    "merge_group": "core",
                },
            ],
        }
    )

    assert plan["material_limitation_evidence_ids"] == ["verified-fact:limitation"]
    assert plan["themes"][0]["importance"] == "essential"
    assert plan["themes"][0]["coverage_obligation"].startswith("Develop")
    assert plan["themes"][1]["importance"] == "optional"
    assert plan["themes"][1]["feasible_candidate_ids"] == ["candidate-2"]
    assert plan["themes"][1]["merge_group"] == "core"


def test_verified_adaptive_target_counts_essential_merge_units_with_floor() -> None:
    assert (
        adaptive_final_insight_target_count(
            {
                "report_thesis": "The report has two related material signals.",
                "themes": [
                    {
                        "theme": "Signal one",
                        "priority": 1,
                        "importance": "essential",
                        "merge_group": "shared",
                        "evidence_ids": ["f1"],
                    },
                    {
                        "theme": "Signal two",
                        "priority": 2,
                        "importance": "essential",
                        "merge_group": "shared",
                        "evidence_ids": ["f2"],
                    },
                ],
            }
        )
        == 2
    )
    assert (
        adaptive_final_insight_target_count(
            {
                "report_thesis": "The report has two distinct material signals.",
                "themes": [
                    {
                        "theme": "Signal one",
                        "priority": 1,
                        "importance": "essential",
                        "evidence_ids": ["f1"],
                    },
                    {
                        "theme": "Signal two",
                        "priority": 2,
                        "importance": "essential",
                        "evidence_ids": ["f2"],
                    },
                    {
                        "theme": "Optional context",
                        "priority": 3,
                        "importance": "optional",
                        "evidence_ids": ["f3"],
                    },
                ],
            }
        )
        == 2
    )


def test_verified_plan_limitation_bindings_drive_rendered_projection() -> None:
    rows = _coerce_limitation_items(
        {
            "limitations": {
                "limitations": [
                    {"text": "A selected qualification.", "evidence_id": "f2"},
                    {"text": "An unrelated qualification.", "evidence_id": "f3"},
                ]
            },
            "verified_facts": {
                "verified_facts": [
                    {"fact_id": "f2", "qualifiers": ["A selected qualification."]},
                    {"fact_id": "f3", "qualifiers": ["An unrelated qualification."]},
                ]
            },
        },
        verified_mode=True,
        artifacts={
            "editorial_plan": {
                "material_limitation_evidence_ids": ["f2"],
            },
            "insights_final": [],
        },
    )

    assert rows == [{"text": "A selected qualification.", "evidence_ids": ["f2"]}]


def test_optional_uncovered_theme_is_accepted_only_with_explicit_grounded_resolution():
    plan = {
        "report_thesis": "The report defines one central decision.",
        "themes": [
            {
                "theme": "Central signal",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop the central signal.",
                "evidence_ids": ["f1"],
            },
            {
                "theme": "Redundant context",
                "priority": 2,
                "importance": "optional",
                "coverage_obligation": "Use only if it adds a distinct implication.",
                "evidence_ids": ["f2"],
            },
        ],
    }

    result = validate_substantive_editorial_theme_coverage(
        payload={
            "theme_coverage": [
                {
                    "theme": "Central signal",
                    "status": "covered",
                    "resolution": "retained",
                    "supporting_insight_ids": ["insight-1"],
                    "explanation": "The final insight develops the central signal.",
                },
                {
                    "theme": "Redundant context",
                    "status": "uncovered",
                    "resolution": "omitted",
                    "supporting_insight_ids": [],
                    "explanation": (
                        "Omitted because its context is redundant with the retained "
                        "central signal and adds no distinct decision implication."
                    ),
                },
            ],
            "report_completeness": "complete",
        },
        editorial_plan=plan,
        final_insights=[
            {
                "id": "insight-1",
                "text": "The central signal matters.",
                "evidence_id": "f1",
            }
        ],
    )

    assert result["omitted_themes"] == ["Redundant context"]
    assert result["theme_assessments"][1]["resolution"] == "omitted"


def test_essential_uncovered_theme_still_fails_closed_with_adaptive_plan():
    plan = {
        "report_thesis": "The report defines two distinct decisions.",
        "themes": [
            {
                "theme": "Central signal",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop the central signal.",
                "evidence_ids": ["f1"],
            },
            {
                "theme": "Required counter-signal",
                "priority": 2,
                "importance": "essential",
                "coverage_obligation": "Preserve the counter-signal.",
                "evidence_ids": ["f2"],
            },
        ],
    }

    with pytest.raises(AppError, match="essential"):
        validate_substantive_editorial_theme_coverage(
            payload={
                "theme_coverage": [
                    {
                        "theme": "Central signal",
                        "status": "covered",
                        "resolution": "retained",
                        "supporting_insight_ids": ["insight-1"],
                        "explanation": "The central signal is developed.",
                    },
                    {
                        "theme": "Required counter-signal",
                        "status": "uncovered",
                        "resolution": "omitted",
                        "supporting_insight_ids": [],
                        "explanation": (
                            "The final roster does not develop the counter-signal."
                        ),
                    },
                ]
            },
            editorial_plan=plan,
            final_insights=[
                {
                    "id": "insight-1",
                    "text": "The central signal.",
                    "evidence_id": "f1",
                }
            ],
        )


def test_secondary_authorized_fact_drives_mechanical_theme_coverage():
    plan = {
        "report_thesis": "The combined finding is decision relevant.",
        "themes": [
            {"theme": "Primary", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Secondary", "priority": 2, "evidence_ids": ["f2"]},
        ],
    }
    candidates = [
        {"id": "insight-1", "text": "Primary", "evidence_id": "f1"},
        {"id": "insight-2", "text": "Secondary", "evidence_id": "f2"},
    ]
    final = [
        {
            "id": "insight-1",
            "text": "The primary and secondary findings belong together.",
            "evidence_id": "f1",
            "evidence_ids": ["f2"],
        }
    ]

    coverage = final_insight_editorial_coverage(
        final_insights=final,
        candidate_insights=candidates,
        editorial_plan=plan,
    )

    assert coverage["selected_themes"] == ["Primary", "Secondary"]
    validate_final_insight_candidate_lineage(
        final_insights=final,
        candidate_insights=candidates,
    )


def test_secondary_authorized_fact_drives_semantic_theme_coverage():
    plan = {
        "report_thesis": "The combined finding is decision relevant.",
        "themes": [
            {"theme": "Primary", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Secondary", "priority": 2, "evidence_ids": ["f2"]},
        ],
    }
    candidates = [
        {"id": "insight-1", "text": "Primary", "evidence_id": "f1"},
        {"id": "insight-2", "text": "Secondary", "evidence_id": "f2"},
    ]

    result = validate_substantive_editorial_theme_coverage(
        payload={
            "theme_coverage": [
                {
                    "theme": "Primary",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-1"],
                    "explanation": "The combined wording develops the primary fact.",
                },
                {
                    "theme": "Secondary",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-1"],
                    "explanation": (
                        "The same wording develops the authorized secondary fact."
                    ),
                },
            ]
        },
        editorial_plan=plan,
        final_insights=[
            {
                "id": "insight-1",
                "text": "The primary and secondary findings belong together.",
                "evidence_id": "f1",
                "evidence_ids": ["f2"],
            }
        ],
        candidate_insights=candidates,
    )

    assert [item["status"] for item in result["theme_assessments"]] == [
        "covered",
        "covered",
    ]


def test_secondary_unauthorized_fact_is_rejected_before_coverage():
    candidates = [
        {"id": "insight-1", "text": "Primary", "evidence_id": "f1"},
    ]
    with pytest.raises(AppError, match="evidence"):
        validate_final_insight_candidate_lineage(
            final_insights=[
                {
                    "id": "insight-1",
                    "text": "Primary plus an unsupported fact.",
                    "evidence_id": "f1",
                    "evidence_ids": ["f2"],
                }
            ],
            candidate_insights=candidates,
        )


def test_verified_plan_maps_section_refs_only_through_original_findings():
    facts = [
        {
            "fact_id": "ai-fact",
            "provenance": {"discovery_candidate_id": "ai-finding"},
        },
        {
            "fact_id": "cross-fact",
            "provenance": {
                "discovery_evidence_ids": ["evidence:findings:cross-finding"]
            },
        },
    ]
    source_findings = {
        "findings": [
            _finding("ai-finding", "ai-infrastructure"),
            _finding("cross-finding", "multiplatform-strategy"),
        ]
    }

    remapped = remap_editorial_plan_to_verified_facts(
        _plan("ai-infrastructure", "cross-finding"),
        facts,
        source_findings=source_findings,
    )

    assert [theme["evidence_ids"] for theme in remapped["themes"]] == [
        ["verified-fact:ai-fact"],
        ["verified-fact:cross-fact"],
    ]


def test_verified_plan_keeps_multiple_admitted_facts_from_one_source_section():
    facts = [
        {
            "fact_id": "fact-a",
            "provenance": {"discovery_candidate_id": "finding-a"},
        },
        {
            "fact_id": "fact-b",
            "provenance": {"discovery_candidate_id": "finding-b"},
        },
        {
            "fact_id": "fact-c",
            "provenance": {"discovery_candidate_id": "finding-c"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "shared-section"),
            _finding("finding-b", "shared-section"),
            _finding("finding-c", "other-section"),
        ]
    }

    remapped = remap_editorial_plan_to_verified_facts(
        _plan("shared-section", "finding-c"),
        facts,
        source_findings=source_findings,
    )

    assert remapped["themes"][0]["evidence_ids"] == [
        "verified-fact:fact-a",
        "verified-fact:fact-b",
    ]
    assert remapped["themes"][1]["evidence_ids"] == ["verified-fact:fact-c"]


def test_verified_plan_drops_section_refs_without_admitted_finding_bindings():
    facts = [
        {
            "fact_id": "fact-a",
            "provenance": {"discovery_candidate_id": "finding-a"},
        },
        {
            "fact_id": "fact-b",
            "provenance": {"discovery_candidate_id": "finding-b"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "supported-section"),
            _finding("finding-b", "other-section"),
        ]
    }

    with pytest.raises(AppError, match="Verified-fact editorial coverage"):
        remap_editorial_plan_to_verified_facts(
            _plan("missing-section", "unsupported-section"),
            facts,
            source_findings=source_findings,
        )


def test_verified_plan_records_lost_optional_theme_after_admission():
    facts = [
        {
            "fact_id": "fact-a",
            "provenance": {"discovery_candidate_id": "finding-a"},
        },
        {
            "fact_id": "fact-c",
            "provenance": {"discovery_candidate_id": "finding-c"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "section-a"),
            _finding("finding-b", "section-b"),
            _finding("finding-c", "section-c"),
        ]
    }
    diagnostics: dict[str, object] = {}
    plan = {
        "report_thesis": "The retained evidence defines the decision surface.",
        "themes": [
            {"theme": "Central", "priority": 1, "evidence_ids": ["finding-a"]},
            {"theme": "Optional", "priority": 2, "evidence_ids": ["finding-b"]},
            {"theme": "Supported", "priority": 3, "evidence_ids": ["finding-c"]},
        ],
    }

    remapped = remap_editorial_plan_to_verified_facts(
        plan,
        facts,
        source_findings=source_findings,
        coverage_diagnostics=diagnostics,
    )

    assert [theme["theme"] for theme in remapped["themes"]] == [
        "Central",
        "Supported",
    ]
    assert diagnostics["planned_themes"] == ["Central", "Optional", "Supported"]
    assert diagnostics["supported_themes"] == ["Central", "Supported"]
    assert diagnostics["lost_themes"] == ["Optional"]
    assert diagnostics["lost_central_themes"] == []


def test_verified_plan_fails_closed_when_central_theme_is_lost():
    facts = [
        {
            "fact_id": "fact-b",
            "provenance": {"discovery_candidate_id": "finding-b"},
        },
        {
            "fact_id": "fact-c",
            "provenance": {"discovery_candidate_id": "finding-c"},
        },
    ]
    source_findings = {
        "findings": [
            _finding("finding-a", "section-a"),
            _finding("finding-b", "section-b"),
            _finding("finding-c", "section-c"),
        ]
    }
    diagnostics: dict[str, object] = {}
    plan = {
        "report_thesis": "The retained evidence defines the decision surface.",
        "themes": [
            {"theme": "Central", "priority": 1, "evidence_ids": ["finding-a"]},
            {"theme": "Supported B", "priority": 2, "evidence_ids": ["finding-b"]},
            {"theme": "Supported C", "priority": 3, "evidence_ids": ["finding-c"]},
        ],
    }

    with pytest.raises(AppError, match="central") as error:
        remap_editorial_plan_to_verified_facts(
            plan,
            facts,
            source_findings=source_findings,
            coverage_diagnostics=diagnostics,
        )

    assert error.value.code == "verified_fact_editorial_coverage_insufficient"
    assert diagnostics["lost_central_themes"] == ["Central"]


def test_verified_selection_can_retain_all_admitted_facts_as_final_model_alternatives():
    candidates = [
        {
            "id": f"fact-{index}",
            "text": f"Supported proposition {index}.",
            "evidence_id": f"finding-{index}",
            "evidence": f"Source evidence {index}.",
            "pages": [index + 1],
            "metric": {},
        }
        for index in range(6)
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=[],
        editorial_plan=_plan("finding-0", "finding-1"),
        preserve_all=True,
        verified_mode=True,
    )

    assert [item["id"] for item in selected] == [item["id"] for item in candidates]
