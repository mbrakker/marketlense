# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators.artifact_normalization import select_artifact_insights

from ._shared import *  # noqa: F401,F403


def _insight(
    evidence_id: str,
    *,
    score: float,
    text: str | None = None,
    coverage_role: str = "market_context",
) -> dict[str, object]:
    return {
        "id": f"insight-{evidence_id}",
        "text": text or f"{evidence_id} changes the planning outlook.",
        "evidence_id": evidence_id,
        "evidence": f"Evidence for {evidence_id}.",
        "metric": {"label": "Planning outlook change", "value": "10", "unit": "%"},
        "pages": [int(evidence_id.removeprefix("f")) + 1],
        "score": score,
        "decision_relevance_score": score,
        "metric_strength_score": 0.8,
        "novelty_score": 0.7,
        "coverage_role": coverage_role,
        "so_what": f"{evidence_id} changes the report-specific decision.",
        "now_what": f"Plan against {evidence_id} in the next review.",
    }


def _section_linked_findings(section_count: int) -> dict[str, object]:
    return {
        "findings": {
            "findings": [
                {
                    "id": f"f{index}",
                    "text": f"Finding {index}",
                    "evidence": f"Evidence {index}",
                    "section_id": f"section-{index}",
                    "section_title": f"Theme {index}",
                    "pages": [index + 1],
                }
                for index in range(1, section_count + 1)
            ]
        }
    }


def _doc_map(section_count: int) -> dict[str, object]:
    return {
        "sections": [
            {
                "id": f"section-{index}",
                "title": f"Theme {index}",
                "summary": f"Substantive theme {index}.",
                "key_points": [f"Theme {index} point."],
                "pages": [index + 1],
            }
            for index in range(1, section_count + 1)
        ]
    }


def _editorial_plan(*evidence_ids: str) -> dict[str, object]:
    return {
        "report_thesis": "The report's retained themes determine the planning outlook.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [evidence_id],
            }
            for index, evidence_id in enumerate(evidence_ids, start=1)
        ],
    }


def test_select_artifact_insights_keeps_representative_sections_for_broad_doc_map():
    candidates = [
        _insight("f1", score=0.99, text="Macro demand is accelerating."),
        _insight("f1", score=0.98, text="Macro demand is accelerating further."),
        _insight("f2", score=0.91, coverage_role="behavior_shift"),
        _insight("f3", score=0.90, coverage_role="strategic_risk"),
        _insight("f4", score=0.89, coverage_role="operating_implication"),
        _insight("f5", score=0.88, coverage_role="investment_signal"),
        _insight("f6", score=0.87, coverage_role="proof_point"),
    ]

    selected = select_artifact_insights(
        final_insights=candidates[:3],
        candidate_insights=candidates,
        editorial_plan=_editorial_plan("f1", "f2", "f3", "f4", "f5", "f6"),
    )

    assert [item["evidence_id"] for item in selected] == [
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
    ]
    assert selected[3]["so_what"] == "f4 changes the report-specific decision."
    assert selected[3]["now_what"] == "Plan against f4 in the next review."
    assert len(selected) <= 7


def test_select_artifact_insights_keeps_distinct_grounded_slots_for_narrow_doc_map():
    candidates = [
        _insight("f1", score=0.99, text="Demand is increasing."),
        _insight("f1", score=0.98, text="Demand is increasing faster."),
        _insight("f1", score=0.97, text="Demand warrants a response."),
        _insight("f1", score=0.96, text="Demand remains the central signal."),
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=candidates,
        editorial_plan=_editorial_plan("f1", "f2"),
    )

    assert [item["text"] for item in selected] == [
        "Demand is increasing.",
        "Demand is increasing faster.",
        "Demand warrants a response.",
        "Demand remains the central signal.",
    ]
    assert len(selected) == 4


def test_select_artifact_insights_fills_report_slots_after_theme_coverage():
    candidates = [
        _insight("f1", score=0.99),
        _insight("f1", score=0.98, text="Theme one is still material."),
        _insight("f2", score=0.97),
        _insight("f3", score=0.96),
    ]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=candidates,
        editorial_plan=_editorial_plan("f1", "f2", "f3"),
    )

    assert [item["evidence_id"] for item in selected] == ["f1", "f2", "f3", "f1"]


def test_select_artifact_insights_maps_pages_within_doc_map_section_ranges():
    doc_map = _doc_map(3)
    for section, page in zip(doc_map["sections"], (1, 10, 20), strict=True):
        section["pages"] = [page]
    candidates = [
        _insight("f4", score=0.99, coverage_role="market_context"),
        _insight("f5", score=0.98, coverage_role="operating_implication"),
        _insight("f6", score=0.97, coverage_role="strategic_risk"),
    ]
    candidates[0]["pages"] = [14]
    candidates[1]["pages"] = [15]
    candidates[2]["pages"] = [25]

    selected = select_artifact_insights(
        final_insights=candidates,
        candidate_insights=candidates,
        editorial_plan=_editorial_plan("f4", "f6"),
    )

    assert [item["evidence_id"] for item in selected] == ["f4", "f6", "f5"]


def test_generate_artifacts_repairs_a_clustered_broad_plan_with_early_middle_and_late_themes(
    tmp_path,
):
    doc_map = _doc_map(7)
    for section, page in zip(
        doc_map["sections"], (1, 10, 20, 30, 40, 50, 60), strict=True
    ):
        section["pages"] = [page]
    evidence = _generation_evidence(7)
    findings = evidence["findings"]["findings"]
    for finding, section_id, page in zip(
        findings,
        (
            "section-1",
            "section-1",
            "section-2",
            "section-2",
            "section-2",
            "section-4",
            "section-7",
        ),
        (2, 3, 11, 12, 13, 31, 61),
        strict=True,
    ):
        finding["section_id"] = section_id
        finding["pages"] = [page]
    candidates = [
        _insight(evidence_id, score=score, coverage_role=coverage_role)
        for evidence_id, score, coverage_role in zip(
            ("f1", "f2", "f3", "f4", "f5", "f6", "f7"),
            (0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.93),
            (
                "market_context",
                "behavior_shift",
                "strategic_risk",
                "operating_implication",
                "investment_signal",
                "proof_point",
                "counter_signal",
            ),
            strict=True,
        )
    ]
    for candidate, finding in zip(candidates, findings, strict=True):
        candidate["pages"] = list(finding["pages"])

    openai_client = FakeOpenAI(
        _generation_responses(
            candidates,
            plan_evidence_ids=["f1", "f2", "f3", "f4", "f5"],
        )
    )
    payload = generate_artifacts(
        report_id="clustered-broad-plan",
        report_name="Clustered broad plan",
        doc_map=doc_map,
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [
        theme["evidence_ids"][0] for theme in payload["editorial_plan"]["themes"]
    ] == [
        "f1",
        "f3",
        "f6",
        "f7",
        "f2",
    ]
    candidate_ids = [item["evidence_id"] for item in payload["insights_candidates"]]
    assert candidate_ids == ["f1", "f3", "f6", "f7", "f2"], candidate_ids
    insight_ids = [item["evidence_id"] for item in payload["insights_final"]]
    assert insight_ids == ["f1", "f3", "f6", "f7", "f2"], insight_ids
    assert len(payload["insights_final"]) == 5, payload["insights_final"]
    assert [step for _, _, step in openai_client.requests].count("editorial_plan") == 1
    assert len(openai_client.requests) == 8


def test_generate_artifacts_does_not_expand_a_narrow_editorial_plan(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="Demand is increasing."),
        _insight("f2", score=0.98, text="Demand is shifting."),
    ]

    payload = generate_artifacts(
        report_id="narrow-plan",
        report_name="Narrow plan",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
        ),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [
        theme["evidence_ids"][0] for theme in payload["editorial_plan"]["themes"]
    ] == [
        "f1",
        "f2",
    ]
    assert len(payload["insights_final"]) == 4, payload["insights_final"]
    assert {item["evidence_id"] for item in payload["insights_final"]} == {"f1", "f2"}


def _generation_evidence(section_count: int) -> dict[str, object]:
    evidence = _section_linked_findings(max(section_count, 2))
    evidence["quote_candidates"] = {
        "quote_candidates": [
            {
                "id": "q1",
                "text": "The retained report confirms the trend.",
                "source": "Research team",
                "page": 1,
            }
        ]
    }
    return evidence


def _generation_responses(
    candidates: list[dict[str, object]], *, plan_evidence_ids: list[str]
) -> dict[str, object]:
    return {
        "editorial_plan": {"editorial_plan": _editorial_plan(*plan_evidence_ids)},
        "summary": {
            "summary": {
                "tldr": "The retained evidence changes the planning outlook.",
                "card_tldr_compact": "Retained evidence changes planning.",
                "executive_summary": "The report provides evidence-backed themes.",
                "claim_evidence_map": [
                    {
                        "claim": "The retained evidence changes the planning outlook.",
                        "evidence_id": "f1",
                        "evidence": "Evidence for f1.",
                        "pages": [2],
                    }
                ],
            }
        },
        "insights_candidates": {"insights_candidates": candidates},
        "quotes": {
            "quotes_final": [
                {
                    "text": "The retained report confirms the trend.",
                    "speaker": "Research team",
                    "citation": "Report",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "insights_final": {"insights_final": candidates[:2]},
        "expert_comment": {"expert_comment": "Use the retained themes in planning."},
        "linkedin_post": {
            "linkedin_post": "The report identifies retained planning themes."
        },
    }


def test_generate_artifacts_retains_broad_doc_map_theme_coverage(tmp_path):
    candidates = [
        _insight(f"f{index}", score=1 - (index / 100), coverage_role=f"role-{index}")
        for index in range(1, 7)
    ]
    payload = generate_artifacts(
        report_id="broad-doc-map",
        report_name="Broad DocMap",
        doc_map=_doc_map(6),
        evidence_packs=_generation_evidence(6),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(
                candidates, plan_evidence_ids=[f"f{index}" for index in range(1, 7)]
            )
        ),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [item["evidence_id"] for item in payload["insights_final"]] == [
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
    ]
    assert payload["family_status"]["insights_bundle"]["status"] == "generated"


def test_generate_artifacts_fills_narrow_doc_map_to_required_grounded_slots(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="Demand is increasing."),
        _insight("f1", score=0.98, text="Demand is increasing faster."),
        _insight("f1", score=0.97, text="Demand warrants a response."),
    ]
    payload = generate_artifacts(
        report_id="narrow-doc-map",
        report_name="Narrow DocMap",
        doc_map=_doc_map(1),
        evidence_packs=_generation_evidence(1),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
        ),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [item["evidence_id"] for item in payload["insights_final"]] == [
        "f1",
        "f2",
        "f1",
        "f1",
        "f1",
    ]
    assert payload["family_status"]["insights_bundle"]["status"] == "generated"


def test_generate_artifacts_completes_broad_theme_coverage_from_findings(tmp_path):
    candidates = [
        _insight(
            "f1",
            score=1 - (index / 100),
            text=f"Macro demand signal {index} remains material.",
        )
        for index in range(1, 7)
    ]
    payload = generate_artifacts(
        report_id="broad-clustered-candidates",
        report_name="Broad clustered candidates",
        doc_map=_doc_map(6),
        evidence_packs=_generation_evidence(6),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(
                candidates, plan_evidence_ids=[f"f{index}" for index in range(1, 7)]
            )
        ),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [item["evidence_id"] for item in payload["insights_final"]] == [
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
    ]


__all__ = [
    "test_select_artifact_insights_keeps_representative_sections_for_broad_doc_map",
    "test_select_artifact_insights_keeps_distinct_grounded_slots_for_narrow_doc_map",
    "test_select_artifact_insights_fills_report_slots_after_theme_coverage",
    "test_select_artifact_insights_maps_pages_within_doc_map_section_ranges",
    "test_generate_artifacts_repairs_a_clustered_broad_plan_with_early_middle_and_late_themes",
    "test_generate_artifacts_does_not_expand_a_narrow_editorial_plan",
    "test_generate_artifacts_retains_broad_doc_map_theme_coverage",
    "test_generate_artifacts_fills_narrow_doc_map_to_required_grounded_slots",
    "test_generate_artifacts_completes_broad_theme_coverage_from_findings",
]
