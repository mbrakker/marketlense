# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_derive_metric_spine_selects_strong_supported_metrics() -> None:
    spine = derive_metric_spine(
        {
            "key_metrics": {
                "metrics": [
                    {
                        "metric_id": "m2",
                        "label": "Low support metric",
                        "value": "",
                        "unit": "percent",
                        "evidence_id": "ev2",
                    },
                    {
                        "metric_id": "m1",
                        "label": "Wallet adoption",
                        "value": "42",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "enterprise merchants",
                        "geography": "Global",
                        "comparator": "2025",
                        "delta": "+7 points",
                        "sample_size": "n=500",
                        "evidence_id": "ev1",
                    },
                ]
            }
        }
    )

    assert spine == [
        {
            "schema_version": "1.0",
            "metric_id": "m1",
            "label": "Wallet adoption",
            "value": "42",
            "unit": "percent",
            "timeframe": "2026",
            "segment": "enterprise merchants",
            "geography": "Global",
            "comparator": "2025",
            "baseline": "",
            "delta": "+7 points",
            "sample_size": "n=500",
            "confidence": "source_backed",
            "missing_context_notes": [],
            "evidence_id": "ev1",
        }
    ]


def test_metric_spine_prioritizes_high_priority_theme_over_context_and_id() -> None:
    spine = derive_metric_spine(
        {
            "key_metrics": {
                "key_metrics": [
                    {
                        "metric_id": "a-secondary",
                        "metric": "Secondary metric",
                        "value": "12",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "all respondents",
                        "geography": "Global",
                        "evidence_id": "metric-secondary",
                    },
                    {
                        "metric_id": "z-headline",
                        "metric": "Headline metric",
                        "value": "68",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "decision makers",
                        "evidence_id": "metric-headline",
                    },
                ]
            }
        },
        editorial_plan={
            "report_thesis": "The headline metric changes the planning outlook.",
            "themes": [
                {
                    "theme": "Headline change",
                    "priority": 1,
                    "evidence_ids": ["metric-headline"],
                },
                {
                    "theme": "Secondary context",
                    "priority": 2,
                    "evidence_ids": ["metric-secondary"],
                },
            ],
        },
    )

    assert [item["metric_id"] for item in spine] == [
        "z-headline",
        "a-secondary",
    ]
    assert spine[0]["evidence_id"] == "metric-headline"
    assert spine[0]["value"] == "68"


def test_derive_metric_spine_keeps_incomplete_headline_metric_source_backed() -> None:
    spine = derive_metric_spine(
        {
            "key_metrics": {
                "key_metrics": [
                    {
                        "metric_id": "secondary",
                        "metric": "Complete secondary metric",
                        "value": "12",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "all respondents",
                        "geography": "Global",
                        "evidence_id": "metric-secondary",
                    },
                    {
                        "metric_id": "headline",
                        "metric": "Incomplete headline metric",
                        "value": "68",
                        "unit": "percent",
                        "evidence_id": "metric-headline",
                    },
                ]
            }
        },
        editorial_plan={
            "report_thesis": "The headline metric changes the planning outlook.",
            "themes": [
                {
                    "theme": "Headline change",
                    "priority": 1,
                    "evidence_ids": ["metric-headline"],
                },
                {
                    "theme": "Secondary context",
                    "priority": 2,
                    "evidence_ids": ["metric-secondary"],
                },
            ],
        },
    )

    assert [item["metric_id"] for item in spine] == ["headline", "secondary"]
    assert spine[0]["missing_context_notes"] == [
        "timeframe",
        "segment",
        "geography",
    ]
    assert spine[0]["evidence_id"] == "metric-headline"


def test_derive_metric_spine_from_insights_uses_embedded_metric_contract() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight_ai_purchases",
                "text": (
                    "AI recommendations already drive purchases: "
                    "46% of shoppers make purchases based on AI recommendations."
                ),
                "evidence_id": "q5",
                "metric": {
                    "value": "46",
                    "unit": "percent",
                    "timeframe": "2026",
                    "segment": "shoppers",
                    "confidence": "high",
                },
            }
        ]
    )

    assert spine == [
        {
            "schema_version": "1.0",
            "metric_id": "insight_ai_purchases",
            "label": "AI recommendations already drive purchases",
            "value": "46",
            "unit": "percent",
            "timeframe": "2026",
            "segment": "shoppers",
            "geography": "",
            "comparator": "",
            "baseline": "",
            "delta": "",
            "sample_size": "",
            "confidence": "high",
            "missing_context_notes": ["geography"],
            "evidence_id": "q5",
        }
    ]


def test_build_executive_advisory_artifacts_surfaces_not_found_states() -> None:
    advisory = build_executive_advisory_artifacts(
        summary={
            "executive_summary": (
                "Wallets matter because evidence shows adoption is rising."
            )
        },
        insights_final=[
            {
                "id": "i1",
                "text": "Wallet adoption is rising among enterprise merchants.",
                "evidence_id": "ev1",
                "evidence_spans": [
                    {"evidence_id": "ev1", "source_pack": "key_metrics"}
                ],
            }
        ],
        quotes_final=[],
        metric_spine=[],
        evidence_packs={},
    )

    assert advisory["decision_brief"]["status"] == "generated"
    assert advisory["recommendations"]["status"] == "recommendations_not_found"
    assert advisory["risks"]["status"] == "risks_not_found"
    assert advisory["coverage_diagnostics"]["metric_spine_count"] == 0
    assert advisory["audience_variants"]["status"] == "not_requested"


def test_build_executive_advisory_artifacts_separates_decision_roles() -> None:
    executive_summary = (
        "Wallet adoption is rising, fraud pressure is increasing, and merchants "
        "need more flexible payment orchestration."
    )
    advisory = build_executive_advisory_artifacts(
        summary={
            "tldr": "Payment infrastructure is becoming a strategic merchant choice.",
            "executive_summary": executive_summary,
        },
        insights_final=[
            {
                "id": "i1",
                "text": "Enterprise merchants are adopting wallets faster.",
                "so_what": "Wallet coverage now shapes conversion resilience.",
                "now_what": "Prioritize wallet coverage in the next roadmap.",
                "evidence_id": "ev1",
            },
            {
                "id": "i2",
                "text": "Adoption remains uneven across merchant segments.",
                "coverage_role": "counter_signal",
                "evidence_id": "ev2",
            },
        ],
        quotes_final=[{"id": "q1", "text": "Quote", "evidence_id": "q1"}],
        metric_spine=[],
        evidence_packs={
            "recommendations": {
                "recommendations": [
                    {
                        "id": "r1",
                        "recommendation": "Test wallet coverage by merchant segment.",
                        "evidence_id": "ev1",
                    }
                ]
            },
            "risk_register": {
                "risk_register": [
                    {
                        "id": "risk1",
                        "risk": "Wallet adoption could remain uneven by segment.",
                        "evidence_id": "ev2",
                    }
                ]
            },
            "limitations": {
                "limitations": [
                    {"description": "The report does not compare every merchant segment."}
                ]
            },
        },
    )

    decision_brief = advisory["decision_brief"]
    assert decision_brief["strategic_context"] == (
        "Payment infrastructure is becoming a strategic merchant choice."
    )
    assert decision_brief["strategic_context"] != executive_summary
    assert decision_brief["decision_implications"] == [
        "Wallet coverage now shapes conversion resilience."
    ]
    assert "Enterprise merchants are adopting wallets faster." not in decision_brief[
        "decision_implications"
    ]
    assert decision_brief["priority_moves"] == [
        "Prioritize wallet coverage in the next roadmap.",
        "Test wallet coverage by merchant segment.",
    ]
    assert decision_brief["watchouts"] == [
        "Adoption remains uneven across merchant segments.",
        "Wallet adoption could remain uneven by segment.",
        "The report does not compare every merchant segment.",
    ]
    assert decision_brief["evidence_links"] == ["ev1", "ev2", "q1"]


def test_build_executive_advisory_artifacts_omits_unsupported_decision_fields() -> None:
    executive_summary = "Wallet adoption is rising among enterprise merchants."
    advisory = build_executive_advisory_artifacts(
        summary={"executive_summary": executive_summary},
        insights_final=[
            {
                "id": "i1",
                "text": "Wallet adoption is rising among enterprise merchants.",
                "evidence_id": "ev1",
            }
        ],
        quotes_final=[],
        metric_spine=[],
        evidence_packs={
            "recommendations": {
                "recommendations": [
                    {
                        "id": "r1",
                        "recommendation": "Expand wallet coverage.",
                    }
                ]
            },
            "risk_register": {
                "risk_register": [
                    {"id": "risk1", "risk": "Segment adoption may vary."}
                ]
            },
        },
    )

    decision_brief = advisory["decision_brief"]
    assert decision_brief["strategic_context"] == ""
    assert decision_brief["decision_implications"] == []
    assert decision_brief["priority_moves"] == []
    assert decision_brief["watchouts"] == []


def test_assemble_artifacts_builds_universal_claim_ledger() -> None:
    payload = assemble_artifacts_payload(
        report_id="ledger-report",
        report_name="Ledger Report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        toc_bundle={"toc_entries": []},
        editorial_plan=_default_editorial_plan(),
        summary={
            "tldr": "Wallet adoption is rising.",
            "card_tldr_compact": "Wallet adoption is rising.",
            "executive_summary": "Wallet adoption is rising among merchants.",
            "claim_evidence_map": [
                {
                    "claim": "Wallet adoption is rising.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                }
            ],
        },
        cover_semantics=_cover_semantics(),
        insights_candidates=[],
        insights_final=[
            {
                "id": "i1",
                "text": "Enterprise merchants are adopting wallets faster.",
                "evidence_id": "f1",
                "evidence": "Revenue +10% YoY",
                "metric": {},
                "pages": [2],
            }
        ],
        quotes_final=[],
        expert_comment="Grounded comment.",
        linkedin_post="Grounded post.",
        source_status={"not_available": False, "reason": ""},
        family_status=build_artifact_family_status(
            summary={
                "tldr": "Wallet adoption is rising.",
                "card_tldr_compact": "Wallet adoption is rising.",
                "executive_summary": "Wallet adoption is rising among merchants.",
                "claim_evidence_map": [{"claim": "Wallet adoption is rising."}],
            },
            insights_candidates=[],
            insights_final=[
                {
                    "id": "i1",
                    "text": "Enterprise merchants are adopting wallets faster.",
                    "evidence_id": "f1",
                }
            ],
            quotes_final=[],
            expert_comment="Grounded comment.",
            linkedin_post="Grounded post.",
        ),
        ctx=_ctx(),
    )

    ledger = payload["claim_ledgers"]
    assert ledger[0]["claim_text"] == "Wallet adoption is rising."
    assert ledger[0]["artifact_section"] == "summary.claim_evidence_map"
    assert ledger[0]["evidence_ids"] == ["f1"]
    assert ledger[0]["support_type"] == "direct_evidence_span"
    assert ledger[0]["evidence_quality_grade"] == "direct_evidence_span"
    assert ledger[1]["canonical_claim_id"] == "ledger-report:insights_final:i1"


def test_assemble_artifacts_builds_topics_key_figures_and_chart_cards() -> None:
    evidence = _evidence_packs()
    evidence["key_metrics"] = {
        "metrics": [
            {
                "metric_id": "m1",
                "label": "Wallet adoption",
                "value": "42",
                "unit": "percent",
                "timeframe": "2026",
                "segment": "enterprise merchants",
                "geography": "Global",
                "delta": "+7 points",
                "evidence_id": "f1",
            }
        ]
    }
    evidence["visual_candidates"] = {
        "chart_candidates": [
            {
                "chart_id": "chart-1",
                "candidate_id": "chart-1",
                "evidence_id": "f1",
                "caption": "Wallet adoption rose to 42 percent.",
                "confidence": "high",
                "crop_qa_accepted": True,
                "source_page": 2,
            }
        ]
    }

    payload = assemble_artifacts_payload(
        report_id="artifact-cards",
        report_name="Artifact Cards",
        doc_map=_doc_map(),
        evidence_packs=evidence,
        toc_bundle={
            "toc_entries": [
                {
                    "section_id": "s1",
                    "section_title": "Adoption Signals",
                    "display_title": "Adoption Signals",
                    "summary": "Enterprise wallet adoption is rising in 2026.",
                    "key_points": ["Enterprise merchant adoption", "Global demand"],
                    "pages": [2],
                    "order": 1,
                }
            ]
        },
        editorial_plan=_default_editorial_plan(),
        summary={
            "tldr": "Wallet adoption is rising.",
            "card_tldr_compact": "Wallet adoption is rising.",
            "executive_summary": "Wallet adoption is rising among merchants.",
            "claim_evidence_map": [
                {
                    "claim": "Wallet adoption is rising.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                    "evidence_spans": [
                        {
                            "evidence_id": "f1",
                            "source_pack": "findings",
                            "page": 2,
                            "text": "Revenue +10% YoY",
                        }
                    ],
                }
            ],
        },
        cover_semantics=_cover_semantics(),
        insights_candidates=[],
        insights_final=[
            {
                "id": "i1",
                "text": "Enterprise merchants are adopting wallets faster.",
                "evidence_id": "f1",
                "evidence": "Revenue +10% YoY",
                "metric": {},
                "pages": [2],
            }
        ],
        quotes_final=[],
        expert_comment="Grounded comment.",
        linkedin_post="Grounded post.",
        source_status={"not_available": False, "reason": ""},
        family_status=build_artifact_family_status(
            summary={
                "tldr": "Wallet adoption is rising.",
                "card_tldr_compact": "Wallet adoption is rising.",
                "executive_summary": "Wallet adoption is rising among merchants.",
                "claim_evidence_map": [{"claim": "Wallet adoption is rising."}],
            },
            insights_candidates=[],
            insights_final=[
                {
                    "id": "i1",
                    "text": "Enterprise merchants are adopting wallets faster.",
                    "evidence_id": "f1",
                }
            ],
            quotes_final=[],
            expert_comment="Grounded comment.",
            linkedin_post="Grounded post.",
        ),
        ctx=_ctx(),
    )

    assert payload["topics_covered"][0]["topic"] == "Adoption Signals"
    assert payload["topics_covered"][0]["evidence_ids"] == ["f1"]
    assert payload["key_figures"][0]["figure"] == "42 percent"
    assert payload["key_figures"][0]["source_page"] == 2
    assert payload["chart_insight_cards"][0]["card_id"] == "chart-1"
    assert payload["chart_insight_cards"][0]["status"] == "generated"
    assert payload["chart_insight_cards"][0]["candidate_id"] == "chart-1"
    assert payload["chart_insight_cards"][0]["insight_id"] == "i1"
    assert payload["chart_insight_cards"][0]["avoid_reason_if_weak"] == ""


def test_generate_artifacts_passes_metric_spine_to_editorial_prompts(tmp_path) -> None:
    evidence = _evidence_packs()
    evidence["key_metrics"] = {
        "metrics": [
            {
                "metric_id": "m1",
                "label": "Wallet adoption",
                "value": "42",
                "unit": "percent",
                "timeframe": "2026",
                "segment": "enterprise merchants",
                "geography": "Global",
                "delta": "+7 points",
                "sample_size": "n=500",
                "evidence_id": "f1",
            }
        ]
    }
    responses = {
        "summary": {
            "tldr": "Wallet adoption is rising.",
            "tldr_card": "Wallet adoption rose.",
            "executive_summary": "Wallet adoption is rising among merchants.",
            "claim_evidence_map": [
                {
                    "claim": "Wallet adoption is rising.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                }
            ],
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "i1",
                    "text": "Wallet adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "metric": {},
                    "pages": [2],
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Wallet adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "metric": {},
                    "pages": [2],
                }
            ]
        },
        "quotes": {"quotes": []},
        "cover_semantics": _cover_semantics_response(),
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    prompt_client = CapturingPromptClient()

    payload = generate_artifacts(
        report_id="metric-spine",
        report_name="Metric Spine",
        doc_map=_doc_map(),
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        vector_store_id=None,
        categories=[],
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    expert_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/expert_comment"
    )
    linkedin_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/linkedin_post"
    )

    assert payload["metric_spine"][0]["label"] == "Wallet adoption"
    assert json.loads(expert_vars["metric_spine_json"])[0]["evidence_id"] == "f1"
    assert json.loads(linkedin_vars["metric_spine_json"])[0]["label"] == (
        "Wallet adoption"
    )


__all__ = [
    "test_derive_metric_spine_selects_strong_supported_metrics",
    "test_metric_spine_prioritizes_high_priority_theme_over_context_and_id",
    "test_derive_metric_spine_keeps_incomplete_headline_metric_source_backed",
    "test_build_executive_advisory_artifacts_surfaces_not_found_states",
    "test_build_executive_advisory_artifacts_separates_decision_roles",
    "test_build_executive_advisory_artifacts_omits_unsupported_decision_fields",
    "test_assemble_artifacts_builds_universal_claim_ledger",
    "test_assemble_artifacts_builds_topics_key_figures_and_chart_cards",
    "test_generate_artifacts_passes_metric_spine_to_editorial_prompts",
]
