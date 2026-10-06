# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
                "evidence_spans": [{"evidence_id": "ev1", "source_pack": "findings"}],
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
            "limitations": {
                "limitations": [
                    {
                        "description": (
                            "The report does not compare every merchant segment."
                        )
                    }
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
    assert (
        "Enterprise merchants are adopting wallets faster."
        not in decision_brief["decision_implications"]
    )
    assert decision_brief["priority_moves"] == [
        "Prioritize wallet coverage in the next roadmap.",
    ]
    assert decision_brief["watchouts"] == [
        "Adoption remains uneven across merchant segments.",
        "The report does not compare every merchant segment.",
    ]
    assert decision_brief["evidence_links"] == ["ev1", "ev2", "q1"]
    assert advisory["recommendations"] == {
        "schema_version": "1.0",
        "status": "generated",
        "items": [
            {
                "id": "i1",
                "recommendation": "Prioritize wallet coverage in the next roadmap.",
                "rationale": "",
                "evidence_id": "ev1",
            }
        ],
    }
    assert advisory["risks"] == {
        "schema_version": "1.0",
        "status": "generated",
        "items": [
            {
                "id": "i2",
                "risk": "Adoption remains uneven across merchant segments.",
                "impact": "",
                "likelihood": "",
                "mitigation": "",
                "evidence_id": "ev2",
            }
        ],
    }


@pytest.mark.parametrize(
    ("display", "numeric_value", "unit_family", "unit", "magnitude"),
    [
        ("$1.3T", 1_300_000_000_000.0, "currency", "USD", "t"),
        ("€2.4bn", 2_400_000_000.0, "currency", "EUR", "bn"),
        ("12.5%", 12.5, "percent", "percent", ""),
    ],
)
def test_metric_spine_preserves_source_display_and_exposes_complete_numeric_metadata(
    display: str,
    numeric_value: float,
    unit_family: str,
    unit: str,
    magnitude: str,
) -> None:
    source_text = f"Source-backed headline metric: {display}."
    insight = {
        "id": "headline",
        "text": source_text,
        "evidence": source_text,
        "evidence_id": "metric-headline",
        "metric": {
            "label": "Source-backed headline metric",
            "value": display,
            "unit": "",
        },
    }
    spine = derive_metric_spine_from_insights([insight])

    assert spine[0]["value"] == display
    assert spine[0]["source_display_value"] == display
    assert spine[0]["numeric_metadata"] == {
        "value": numeric_value,
        "unit_family": unit_family,
        "unit": unit,
        "magnitude": magnitude,
    }
    figures = build_key_figures(
        metric_spine=spine,
        evidence_packs={},
        insights_final=[insight],
    )
    assert figures[0]["figure"] == display


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
        evidence_packs={},
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
        soft_copy_claim_bindings=_declared_soft_copy_bindings(
            {
                "tldr": "Wallet adoption is rising.",
                "card_tldr_compact": "Wallet adoption is rising.",
                "executive_summary": "Wallet adoption is rising among merchants.",
            },
            "Grounded comment.",
            "Grounded post.",
        ),
    )

    ledger = payload["claim_ledgers"]
    assert ledger[0]["claim_text"] == "Wallet adoption is rising."
    assert ledger[0]["artifact_section"] == "summary.claim_evidence_map"
    assert ledger[0]["evidence_ids"] == ["f1"]
    assert ledger[0]["support_type"] == "direct_evidence_span"
    assert ledger[0]["evidence_quality_grade"] == "direct_evidence_span"
    assert ledger[1]["canonical_claim_id"] == "ledger-report:insights_final:i1"


def test_claim_ledger_preserves_typed_evidence_source_identity() -> None:
    from src.generators._artifact_generator.storage import build_universal_claim_ledger

    ledger = build_universal_claim_ledger(
        report_id="ledger-report",
        summary={
            "claim_evidence_map": [
                {
                    "claim": "Survey respondents reported directional views.",
                    "evidence_id": "research-methodology",
                    "evidence_spans": [
                        {
                            "evidence_id": "research-methodology",
                            "source_pack": "doc_map",
                            "page": 64,
                        }
                    ],
                }
            ]
        },
        insights_final=[],
        quotes_final=[],
        metric_spine=[],
        executive_advisory={},
    )

    assert ledger[0]["evidence_ids"] == ["research-methodology"]
    assert ledger[0]["evidence_references"] == [
        {"evidence_id": "research-methodology", "source_pack": "doc_map"}
    ]
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0",
            schema_name="artifacts",
            payload={
                "toc_topics": [],
                "editorial_plan": {
                    "report_thesis": "Source spans distinguish evidence packs.",
                    "themes": [
                        {"theme": "Evidence", "priority": 1, "evidence_ids": ["f1"]},
                        {
                            "theme": "Source identity",
                            "priority": 2,
                            "evidence_ids": ["f2"],
                        },
                    ],
                },
                "summary": {
                    "tldr": "Typed source identity.",
                    "card_tldr_compact": "Typed source identity.",
                    "executive_summary": "Typed source identity is retained.",
                    "claim_evidence_map": [],
                },
                "cover_semantics": _cover_semantics(),
                "insights_candidates": [],
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
                "claim_ledgers": ledger,
            },
        ),
        _ctx(),
    )


def test_assemble_artifacts_builds_topics_key_figures_and_chart_cards() -> None:
    evidence = _evidence_packs()
    evidence["findings"]["findings"][0] = {
        "id": "f1",
        "text": "Wallet adoption rose to 42 percent.",
        "evidence": "Wallet adoption rose to 42 percent.",
        "pages": [2],
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
                    "evidence": "Wallet adoption rose to 42 percent.",
                    "pages": [2],
                    "evidence_spans": [
                        {
                            "evidence_id": "f1",
                            "source_pack": "findings",
                            "page": 2,
                            "text": "Wallet adoption rose to 42 percent.",
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
                "evidence": "Wallet adoption rose to 42 percent.",
                "metric": {
                    "label": "Wallet adoption",
                    "value": "42",
                    "unit": "percent",
                    "timeframe": "2026",
                    "segment": "enterprise merchants",
                    "geography": "Global",
                    "delta": "+7 points",
                },
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
        soft_copy_claim_bindings=_declared_soft_copy_bindings(
            {
                "tldr": "Wallet adoption is rising.",
                "card_tldr_compact": "Wallet adoption is rising.",
                "executive_summary": "Wallet adoption is rising among merchants.",
            },
            "Grounded comment.",
            "Grounded post.",
        ),
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
    evidence["findings"]["findings"][0] = {
        "id": "f1",
        "text": "Enterprise wallet adoption reached 42 percent.",
        "evidence": "Enterprise wallet adoption reached 42 percent.",
        "pages": [2],
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
                    "evidence": "Enterprise wallet adoption reached 42 percent.",
                    "pages": [2],
                }
            ],
            "claim_provenance": [
                {
                    "claim": "Wallet adoption is rising.",
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
                {
                    "claim": "Wallet adoption rose.",
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
                {
                    "claim": "Wallet adoption is rising among merchants.",
                    "classification": "interpretive",
                    "evidence_ids": [],
                },
            ],
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "i1",
                    "text": "Wallet adoption: adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Enterprise wallet adoption reached 42 percent.",
                    "metric": {},
                    "pages": [2],
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Wallet adoption: adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Enterprise wallet adoption reached 42 percent.",
                    "metric": {
                        "label": "Enterprise wallet adoption",
                        "value": "42",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "enterprise merchants",
                        "geography": "Global",
                        "delta": "+7 points",
                        "sample_size": "n=500",
                    },
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

    assert payload["metric_spine"][0]["label"] == "Enterprise wallet adoption"
    assert json.loads(expert_vars["metric_spine_json"])[0]["evidence_id"] == "f1"
    assert json.loads(linkedin_vars["metric_spine_json"])[0]["label"] == (
        "Enterprise wallet adoption"
    )
