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


def test_assemble_artifacts_builds_universal_claim_ledger() -> None:
    payload = assemble_artifacts_payload(
        report_id="ledger-report",
        report_name="Ledger Report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        toc_bundle={"toc_entries": []},
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
                "evidence_id": "f1",
                "caption": "Wallet adoption rose to 42 percent.",
                "confidence": "high",
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
    "test_build_executive_advisory_artifacts_surfaces_not_found_states",
    "test_assemble_artifacts_builds_universal_claim_ledger",
    "test_assemble_artifacts_builds_topics_key_figures_and_chart_cards",
    "test_generate_artifacts_passes_metric_spine_to_editorial_prompts",
]
