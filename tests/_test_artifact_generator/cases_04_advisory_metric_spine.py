# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators.artifact_normalization import normalize_artifact_insights

from ._shared import *  # noqa: F401,F403


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


def test_metric_label_survives_candidate_to_final_insight_to_key_figure() -> None:
    candidate = normalize_artifact_insights(
        [
            {
                "id": "iab-video-growth",
                "text": (
                    "Search retained the largest share of U.S. digital ad revenue. "
                    "Digital video revenue grew 19.2%."
                ),
                "evidence_id": "iab-video",
                "metric": {
                    "label": "Digital video revenue growth",
                    "value": "19.2%",
                    "unit": "",
                },
            }
        ],
        prefix="candidate",
    )
    final = normalize_artifact_insights(candidate, prefix="insight")

    spine = derive_metric_spine_from_insights(final)
    figures = build_key_figures(metric_spine=spine, evidence_packs={})

    assert spine[0]["label"] == "Digital video revenue growth"
    assert spine[0]["evidence_id"] == "iab-video"
    assert figures[0]["figure"] == "19.2%"
    assert figures[0]["label"] == "Digital video revenue growth"
    assert figures[0]["evidence_id"] == "iab-video"


def test_iab_19_2_key_figure_uses_its_explicit_digital_video_label() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "iab_video_19_2_key_figure.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": fixture["insight_id"],
                "text": fixture["insight_text"],
                "evidence_id": fixture["evidence_id"],
                "metric": fixture["metric"],
            }
        ]
    )

    assert spine[0]["value"] == "19.2%"
    assert spine[0]["label"] == "Digital video revenue growth"
    assert spine[0]["evidence_id"] == "iab-video"


def test_activate_2026_128_million_key_figure_uses_its_explicit_metric_label() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "activate_2026_128m_key_figure.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": fixture["insight_id"],
                "text": fixture["insight_text"],
                "evidence_id": fixture["evidence_id"],
                "metric": fixture["metric"],
            }
        ]
    )

    assert spine[0]["value"] == "128 million"
    assert spine[0]["label"] == "Monthly U.S. adult generative AI users"
    assert spine[0]["evidence_id"] == "activate-ai-users"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Monthly U.S. adult generative AI users reached 128 million.", "128 million"),
        ("Monthly U.K. adult generative AI users reached 8 million.", "8 million"),
    ],
)
def test_legacy_metric_label_never_truncates_us_or_uk_abbreviations(
    text: str, value: str
) -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-users",
                "text": text,
                "evidence_id": "legacy-users",
                "metric": {"value": value, "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == text
    assert not spine[0]["label"].endswith(("U.S.", "U.K."))


def test_legacy_multi_metric_insight_uses_the_sentence_for_its_metric_not_the_first_sentence(
) -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-iab-video",
                "text": (
                    "Search retained the largest share of U.S. digital ad revenue. "
                    "Digital video revenue grew 19.2%."
                ),
                "evidence_id": "iab-video",
                "metric": {"value": "19.2%", "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == "Digital video revenue grew 19.2%."
    assert "Search retained" not in spine[0]["label"]


def test_legacy_metric_omits_key_figure_when_no_metric_specific_label_is_reliable(
) -> None:
    insight = {
        "id": "legacy-ambiguous",
        "text": "Search held 42% share; 19.2%.",
        "evidence_id": "iab-mixed",
        "metric": {"value": "19.2%", "unit": ""},
    }

    assert derive_metric_spine_from_insights([insight]) == []


def test_legacy_metric_uses_its_complete_clause_when_supporting_metrics_follow() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-activate-users",
                "text": (
                    "Monthly U.S. adult generative AI users reached 128 million in "
                    "2025, up 45 million year over year."
                ),
                "evidence_id": "activate-ai-users",
                "metric": {"value": "128 million", "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == (
        "Monthly U.S. adult generative AI users reached 128 million in 2025"
    )


def test_legacy_metric_omits_a_lowercase_clause_without_a_complete_subject() -> None:
    insight = {
        "id": "legacy-fragment",
        "text": "Search held 42% share; cited by 19.2% of users.",
        "evidence_id": "legacy-fragment",
        "metric": {"value": "19.2%", "unit": ""},
    }

    assert derive_metric_spine_from_insights([insight]) == []


def test_metric_spine_label_does_not_split_a_decimal_display() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-revenue",
                "text": (
                    "Global eCommerce is forecast to grow from $7.2 trillion "
                    "in 2024 to $10.4 trillion in 2028."
                ),
                "evidence_id": "finding-revenue",
                "metric": {
                    "value": "$7.2T to $10.4T",
                    "unit": "global sales",
                },
            }
        ]
    )

    assert spine[0]["label"] == (
        "Global eCommerce is forecast to grow from $7.2 trillion in 2024 to "
        "$10.4 trillion in 2028."
    )


def test_metric_spine_label_keeps_leading_abbreviation_with_its_sentence() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-retail-media",
                "text": (
                    "U.S. retail media revenue is forecast to nearly double from "
                    "$54 billion in 2024 to $101 billion in 2028."
                ),
                "evidence_id": "finding-retail-media",
                "metric": {"value": "$54B to $101B", "unit": "USD revenue"},
            }
        ]
    )

    assert spine[0]["label"] == (
        "U.S. retail media revenue is forecast to nearly double from $54 billion "
        "in 2024 to $101 billion in 2028."
    )


def test_metric_spine_label_keeps_a_complete_long_source_sentence() -> None:
    text = (
        "Generative AI is already used for shopping inspiration or research by 41% "
        "of online shoppers aged 18-34, compared with 9% of shoppers aged 55 and "
        "older."
    )
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-generative-ai",
                "text": text,
                "evidence_id": "finding-generative-ai",
                "metric": {
                    "value": "41% vs. 9%",
                    "unit": "share of online shoppers",
                },
            }
        ]
    )

    assert spine[0]["label"] == text


@pytest.mark.parametrize(
    ("value", "unit", "expected_display"),
    [
        ("70%", "percent", "70%"),
        ("$258.6", "billion", "$258.6 billion"),
        ("258.6", "$ billion", "$258.6 billion"),
        ("$7.2T to $10.4T", "", "$7.2T to $10.4T"),
    ],
)
def test_metric_spine_renders_one_clean_primary_metric(
    value: str, unit: str, expected_display: str
) -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "primary-metric",
                "text": "The source-backed insight retains supporting numbers in prose.",
                "evidence_id": "iab-primary-metric",
                "metric": {
                    "label": "Source-backed primary metric",
                    "value": value,
                    "unit": unit,
                },
            }
        ]
    )

    figures = build_key_figures(metric_spine=spine, evidence_packs={})

    assert [figure["figure"] for figure in figures] == [expected_display]


def test_metric_spine_omits_iab_semicolon_packed_metric_but_preserves_insight() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "iab_pwc_quarterly.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    insight = {
        "id": "iab-composite-metric",
        "text": fixture["source_comparison"],
        "evidence_id": fixture["report_id"],
        "metric": {
            "value": fixture["malformed_key_figure_value"],
            "unit": fixture["malformed_key_figure_unit"],
        },
    }

    assert derive_metric_spine_from_insights([insight]) == []
    assert insight["text"] == fixture["source_comparison"]
    assert insight["evidence_id"] == fixture["report_id"]


def test_metric_spine_omits_metric_when_no_clean_display_is_available() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "composite-metric",
                "text": "Supporting values remain available in the insight text.",
                "evidence_id": "source-1",
                "metric": {"value": "19.2%; $62.1; $102.9", "unit": "share"},
            }
        ]
    )

    assert spine == []


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
                        "description": "The report does not compare every merchant segment."
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
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "headline",
                "text": "Headline value",
                "evidence_id": "metric-headline",
                "metric": {
                    "label": "Source-backed headline metric",
                    "value": display,
                    "unit": "",
                },
            }
        ]
    )

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
                    "text": "Wallet adoption: adoption is rising among merchants.",
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
                    "text": "Wallet adoption: adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
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


__all__ = [
    "test_metric_label_survives_candidate_to_final_insight_to_key_figure",
    "test_iab_19_2_key_figure_uses_its_explicit_digital_video_label",
    "test_activate_2026_128_million_key_figure_uses_its_explicit_metric_label",
    "test_legacy_metric_label_never_truncates_us_or_uk_abbreviations",
    "test_legacy_multi_metric_insight_uses_the_sentence_for_its_metric_not_the_first_sentence",
    "test_legacy_metric_omits_key_figure_when_no_metric_specific_label_is_reliable",
    "test_legacy_metric_uses_its_complete_clause_when_supporting_metrics_follow",
    "test_legacy_metric_omits_a_lowercase_clause_without_a_complete_subject",
    "test_derive_metric_spine_from_insights_uses_embedded_metric_contract",
    "test_metric_spine_label_does_not_split_a_decimal_display",
    "test_metric_spine_label_keeps_leading_abbreviation_with_its_sentence",
    "test_metric_spine_label_keeps_a_complete_long_source_sentence",
    "test_metric_spine_renders_one_clean_primary_metric",
    "test_metric_spine_omits_iab_semicolon_packed_metric_but_preserves_insight",
    "test_metric_spine_omits_metric_when_no_clean_display_is_available",
    "test_metric_spine_preserves_source_display_and_exposes_complete_numeric_metadata",
    "test_build_executive_advisory_artifacts_surfaces_not_found_states",
    "test_build_executive_advisory_artifacts_separates_decision_roles",
    "test_build_executive_advisory_artifacts_omits_unsupported_decision_fields",
    "test_assemble_artifacts_builds_universal_claim_ledger",
    "test_assemble_artifacts_builds_topics_key_figures_and_chart_cards",
    "test_generate_artifacts_passes_metric_spine_to_editorial_prompts",
]
