# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators._artifact_generator.storage import _validate_cover_semantics

from ._shared import *  # noqa: F401,F403


def _assemble_summary_payload(summary, *, ctx=None):
    family_status = build_artifact_family_status(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )
    family_status["summary"] = {
        "schema_version": "1.0",
        "family": "summary",
        "source": "artifact",
        "status": "generated",
        "confidence_score": 1.0,
        "policy_action": "keep",
        "reason": "",
    }
    return assemble_artifacts_payload(
        report_id="report-card-summary",
        report_name="Report Card Summary",
        doc_map={"sections": []},
        evidence_packs={},
        toc_bundle={"toc_entries": []},
        summary=summary,
        cover_semantics=_cover_semantics(),
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
        source_status={"not_available": False, "reason": ""},
        family_status=family_status,
        ctx=ctx or _ctx(),
    )


def test_assemble_artifacts_accepts_complete_card_tldrs():
    payload = _assemble_summary_payload(
        {
            "tldr": (
                "Retail growth depends on trust, invisible AI, and experience-led "
                "discovery through 2026."
            ),
            "card_tldr_compact": (
                "Trust and invisible AI reshape retail discovery through 2026."
            ),
            "executive_summary": "The report describes evidence-backed retail shifts.",
            "claim_evidence_map": [],
        }
    )

    assert payload["schema_version"] == "3.0"
    assert payload["summary"]["card_tldr_compact"].endswith(".")


def test_assemble_artifacts_retains_canonical_category_ids():
    summary = {
        "tldr": "Retail growth depends on retained source evidence through 2026.",
        "card_tldr_compact": "Retail growth depends on retained source evidence.",
        "executive_summary": "The report describes evidence-backed retail shifts.",
        "claim_evidence_map": [],
    }
    family_status = build_artifact_family_status(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )

    payload = assemble_artifacts_payload(
        report_id="report-card-categories",
        report_name="Report Card Categories",
        doc_map={"sections": []},
        evidence_packs={},
        toc_bundle={"toc_entries": []},
        summary=summary,
        cover_semantics=_cover_semantics(),
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
        source_status={"not_available": False, "reason": ""},
        family_status=family_status,
        category_ids=["consumer-retail", "digital-commerce"],
        ctx=_ctx(),
    )

    assert payload["categories"] == ["consumer-retail", "digital-commerce"]


def test_cover_semantics_normalizes_provider_enum_formatting():
    result = _validate_cover_semantics(
        {
            "evidence_shape": "Trend",
            "direction": "RISING",
            "geography_scope": "Unknown",
            "evidence_density": "metric rich",
            "domain_layer": "Grid",
            "selection_reason": "The supplied figures show an upward trajectory.",
        },
        ctx=_ctx(),
    )

    assert result == {
        "evidence_shape": "trend",
        "direction": "rising",
        "geography_scope": "unknown",
        "evidence_density": "metric_rich",
        "domain_layer": "grid",
        "selection_reason": "The supplied figures show an upward trajectory.",
    }


@pytest.mark.parametrize(
    ("field_name", "value", "error_code"),
    (
        (
            "card_tldr_compact",
            "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen.",
            "card_tldr_compact_invalid",
        ),
        (
            "card_tldr_compact",
            "Clipped compact summary...",
            "card_tldr_compact_invalid",
        ),
        ("tldr", "Incomplete standard summary", "card_tldr_standard_invalid"),
    ),
)
def test_assemble_artifacts_rejects_invalid_card_tldrs(
    field_name,
    value,
    error_code,
    assert_app_error,
):
    summary = {
        "tldr": "Retail conditions are changing across markets.",
        "card_tldr_compact": "Retail conditions are changing.",
        "executive_summary": "The report describes evidence-backed retail shifts.",
        "claim_evidence_map": [],
    }
    summary[field_name] = value

    with pytest.raises(AppError) as captured:
        _assemble_summary_payload(summary)

    assert_app_error(captured.value, code=error_code, retryable=False)


def test_generate_artifacts_validates_schema_and_evidence_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": [
            {
                "summary": {
                    "tldr": "Incomplete standard summary",
                    "card_tldr_compact": "Grounded TLDR.",
                    "executive_summary": "Exec",
                    "claim_evidence_map": [],
                }
            },
            {
                "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "Revenue +10%",
                        "pages": [2],
                    }
                ],
                }
            },
        ],
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Insight 1",
                    "evidence_id": "f1",
                    "evidence": "E1",
                    "metric": {
                        "value": "10",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "US",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [2],
                    "score": 0.9,
                },
                {
                    "id": "c2",
                    "text": "Insight 2",
                    "evidence_id": "f2",
                    "evidence": "E2",
                    "metric": {
                        "value": "5",
                        "unit": "%",
                        "trend": "-",
                        "timeframe": "2023",
                        "geography": "EU",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [3],
                    "score": 0.8,
                },
                {
                    "id": "c3",
                    "text": "Insight 3",
                    "evidence_id": "f3",
                    "evidence": "E3",
                    "metric": {
                        "value": "2",
                        "unit": "pt",
                        "trend": "+",
                        "timeframe": "Q1",
                        "geography": "",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [4],
                    "score": 0.7,
                },
                {
                    "id": "c4",
                    "text": "Insight 4",
                    "evidence_id": "f4",
                    "evidence": "E4",
                    "metric": {
                        "value": "12",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "APAC",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [5],
                    "score": 0.6,
                },
                {
                    "id": "c5",
                    "text": "Insight 5",
                    "evidence_id": "f5",
                    "evidence": "E5",
                    "metric": {
                        "value": "3",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [6],
                    "score": 0.5,
                },
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Top 1",
                    "evidence_id": "f1",
                    "evidence": "E1",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "f2",
                    "text": "Top 2",
                    "evidence_id": "f2",
                    "evidence": "E2",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "f3",
                    "text": "Top 3",
                    "evidence_id": "f3",
                    "evidence": "E3",
                    "metric": {},
                    "pages": [4],
                },
                {
                    "id": "f4",
                    "text": "Top 4",
                    "evidence_id": "f4",
                    "evidence": "E4",
                    "metric": {},
                    "pages": [5],
                },
                {
                    "id": "f5",
                    "text": "Top 5",
                    "evidence_id": "f5",
                    "evidence": "E5",
                    "metric": {},
                    "pages": [6],
                },
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "We are expanding rapidly",
                    "speaker": "CEO",
                    "citation": "Earnings call",
                    "page": 3,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    fake_openai = FakeOpenAI(responses)
    analysis_store = FakeAnalysisStore()
    payload = generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert all(item["evidence_id"] for item in payload["insights_candidates"])
    assert all(item["evidence_id"] for item in payload["insights_final"])
    assert payload["summary"]["claim_evidence_map"][0]["evidence_spans"] == [
        {
            "evidence_id": "f1",
            "source_pack": "findings",
            "page": 2,
            "text": "Revenue +10% YoY",
        }
    ]
    assert payload["quotes_final"][0]["evidence_spans"] == [
        {
            "evidence_id": "q1",
            "source_pack": "quote_candidates",
            "page": 3,
            "text": "We are expanding rapidly",
        }
    ]
    assert payload["family_status"]["summary"]["status"] == "generated"
    assert payload["family_status"]["quotes"]["status"] == "generated"
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 8
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 0
    assert payload["toc_entries"][0]["section_title"] == "Intro"
    assert payload["toc_topics"] == ["Intro"]
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )
    assert analysis_store.stored and analysis_store.stored[0][2] == "artifacts"


def test_generate_artifacts_prunes_unbound_summary_claims(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": f"Grounded claim {index}",
                        "evidence_id": f"f{index}",
                        "evidence": f"Evidence {index}",
                        "pages": [index + 1],
                    }
                    for index in range(1, 5)
                ]
                + [
                    {
                        "claim": "Unsupported claim",
                        "evidence_id": "missing-source",
                        "evidence": "Model text without a known source",
                        "pages": [],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": f"c{index}",
                    "text": f"Candidate {index}",
                    "evidence_id": f"f{index}",
                    "evidence": f"Evidence {index}",
                    "metric": {},
                    "pages": [index + 1],
                }
                for index in range(1, 6)
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": f"f{index}",
                    "text": f"Final {index}",
                    "evidence_id": f"f{index}",
                    "evidence": f"Evidence {index}",
                    "metric": {},
                    "pages": [index + 1],
                }
                for index in range(1, 6)
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "We are expanding rapidly",
                    "speaker": "CEO",
                    "citation": "Earnings call",
                    "page": 3,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }

    payload = generate_artifacts(
        report_id="r_prune_unbound_claims",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    claims = payload["summary"]["claim_evidence_map"]
    assert [claim["claim"] for claim in claims] == [
        "Grounded claim 1",
        "Grounded claim 2",
        "Grounded claim 3",
        "Grounded claim 4",
    ]
    assert all(claim["evidence_spans"] for claim in claims)
    assert payload["family_status"]["summary"]["status"] == "generated"
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )


def test_generate_artifacts_abstains_low_confidence_families_and_marks_regeneration(
    tmp_path,
):
    responses = {
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [],
            }
        },
        "insights_candidates": {"insights_candidates": []},
        "insights_final": {"insights_final": []},
        "quotes": {"quotes_final": []},
        "expert_comment": {"expert_comment": "Keep the editorial note short."},
        "linkedin_post": {"linkedin_post": "LinkedIn summary."},
    }
    payload = generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["summary"]["tldr"] == ""
    assert payload["summary"]["executive_summary"] == ""
    assert payload["insights_candidates"] == []
    assert payload["insights_final"] == []
    assert payload["quotes_final"] == []
    assert payload["family_status"]["summary"]["status"] == "abstained"
    assert payload["family_status"]["summary"]["policy_action"] == "regenerate"
    assert payload["family_status"]["insights_bundle"]["status"] == "abstained"
    assert payload["family_status"]["insights_bundle"]["policy_action"] == "regenerate"
    assert payload["family_status"]["quotes"]["status"] == "abstained"
    assert payload["family_status"]["quotes"]["policy_action"] == "regenerate"
    assert payload["family_status"]["expert_comment"]["status"] == "generated"
    assert payload["family_status"]["expert_comment"]["policy_action"] == "keep"
    assert payload["family_status"]["linkedin_post"]["status"] == "generated"
    assert payload["family_status"]["linkedin_post"]["policy_action"] == "keep"


def test_summary_family_status_accepts_claim_evidence_ids_without_spans() -> None:
    status = build_artifact_family_status(
        summary={
            "tldr": "Grounded short summary.",
            "card_tldr_compact": "Grounded short summary.",
            "executive_summary": "Grounded executive summary.",
            "claim_evidence_map": [
                {
                    "claim": "Engagement drove measurable practice changes.",
                    "evidence_id": "sec-07",
                    "evidence": "The report says engagement led to tangible changes.",
                    "pages": [16],
                }
            ],
        },
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert status["summary"]["status"] == "generated"
    assert status["summary"]["policy_action"] == "keep"


def test_quote_family_abstains_doc_map_only_nonverbatim_quotes() -> None:
    status = build_artifact_family_status(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[
            {
                "text": (
                    "Expanded program includes companies linked to cattle products "
                    "and pulp and paper."
                ),
                "speaker": "Unknown",
                "citation": "Deforestation program",
                "page": 40,
                "evidence_id": "sec-10",
                "evidence_spans": [
                    {
                        "evidence_id": "sec-10",
                        "source_pack": "doc_map",
                        "page": 40,
                        "text": (
                            "Describes the expansion of the program to forest-risk "
                            "commodities and selected companies."
                        ),
                    }
                ],
            }
        ],
        expert_comment="",
        linkedin_post="",
    )

    assert status["quotes"]["status"] == "abstained"
    assert status["quotes"]["policy_action"] == "regenerate"
    assert status["quotes"]["reason"] == "quotes_missing_verbatim_source"


def test_normalize_artifact_quotes_preserves_paraphrase_marker() -> None:
    quotes = normalize_artifact_quotes(
        [
            {
                "text": "The evidence says revenue improved.",
                "speaker": "Analyst",
                "citation": "Findings",
                "evidence_id": "f1",
                "is_paraphrase": True,
            }
        ]
    )

    assert quotes[0]["is_paraphrase"] is True


def test_generate_artifacts_expands_topic_briefs_from_doc_map(tmp_path):
    responses = {
        "toc": {
            "toc_topics": [
                "Demand outlook",
                "Margin resilience",
                "Operating leverage",
            ]
        },
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Operating leverage improved through automation.",
                        "evidence_id": "f3",
                        "evidence": "Automation lifted leverage by 3 points.",
                        "pages": [4],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Demand is strongest in APAC.",
                    "evidence_id": "f1",
                    "evidence": "APAC demand up 12%.",
                    "metric": {},
                    "pages": [2],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Demand is strongest in APAC.",
                    "evidence_id": "f1",
                    "evidence": "APAC demand up 12%.",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "i2",
                    "text": "Margins stabilized in H2 as input costs eased.",
                    "evidence_id": "f2",
                    "evidence": "Input cost pressure moderated.",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "i3",
                    "text": "Operating leverage improved through automation.",
                    "evidence_id": "f3",
                    "evidence": "Automation lifted leverage by 3 points.",
                    "metric": {},
                    "pages": [4],
                },
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    payload = generate_artifacts(
        report_id="r_topic_briefs",
        report_name="report",
        doc_map={
            "doc_id": "r1",
            "title": "Report",
            "sections": [
                {
                    "id": "demand-outlook",
                    "title": "Demand outlook",
                    "summary": (
                        "Demand is strongest in APAC and improving in North America."
                    ),
                    "key_points": [
                        "APAC growth leads at +12%",
                        "North America recovered in Q4",
                    ],
                    "pages": [2],
                },
                {
                    "id": "margin-resilience",
                    "title": "Margin resilience",
                    "summary": "Margins stabilized in H2 as input costs eased.",
                    "key_points": [
                        "Input cost pressure moderated",
                        "Promotions remained disciplined",
                    ],
                    "pages": [3],
                },
            ],
        },
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    toc_entries = payload["toc_entries"]
    topic_briefs = payload["toc_topics_expanded"]
    assert len(toc_entries) == 2
    assert [entry["display_title"] for entry in toc_entries] == [
        "Demand outlook",
        "Margin resilience",
    ]
    assert topic_briefs[0]["topic"] == "Demand outlook"
    assert topic_briefs[0]["summary"] == (
        "Demand is strongest in APAC and improving in North America."
    )
    assert topic_briefs[0]["key_points"][0] == "APAC growth leads at +12%"
    assert topic_briefs[1]["section_id"] == "margin-resilience"
    assert payload["toc_topics"] == ["Demand outlook", "Margin resilience"]


def test_build_topic_briefs_avoids_positional_section_swap():
    topic_briefs = build_topic_briefs(
        toc_topics=[
            "Media receptivity and channel preferences",
            "Channel ad equity rankings",
            "Media brand ad equity",
            "Sentiments on generative AI",
            "Marketer investment priorities",
        ],
        doc_map={
            "doc_id": "doc-1",
            "title": "Media Reactions",
            "sections": [
                {
                    "id": "section-1",
                    "title": "Introduction",
                    "summary": "Study background.",
                    "key_points": [],
                    "pages": [2],
                },
                {
                    "id": "section-2",
                    "title": "Media landscape: Where do people prefer seeing advertising?",
                    "summary": (
                        "Consumer receptivity, channel preferences, and channel-level "
                        "Ad Equity rankings across APAC."
                    ),
                    "key_points": [
                        "Channel preferences differ between consumers and marketers.",
                        "DOOH leads channel Ad Equity.",
                    ],
                    "pages": [8, 10],
                },
                {
                    "id": "section-3",
                    "title": "Media brands: How do brands interact with people?",
                    "summary": (
                        "Media-brand Ad Equity rankings with Netflix and OTT "
                        "platforms leading."
                    ),
                    "key_points": [
                        "Netflix is the #1 media brand for Ad Equity.",
                        "OTT platforms dominate the rankings.",
                    ],
                    "pages": [17, 18],
                },
                {
                    "id": "section-4",
                    "title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                    "summary": (
                        "Consumer and marketer attitudes to generative AI in "
                        "advertising."
                    ),
                    "key_points": [
                        "Consumers worry about fake content.",
                        "Marketers use generative AI for creativity and efficiency.",
                    ],
                    "pages": [25],
                },
                {
                    "id": "section-5",
                    "title": "Implications for marketers",
                    "summary": (
                        "Budget priorities, investment plans, and channel implications "
                        "for marketers."
                    ),
                    "key_points": [
                        "Online video and streaming remain top priorities.",
                        "Marketers plan to increase investment in TikTok, YouTube, and Instagram.",
                    ],
                    "pages": [22, 27],
                },
            ],
        },
        summary={"claim_evidence_map": []},
        insights_final=[],
    )

    assert [item["section_id"] for item in topic_briefs] == [
        "section-2",
        "section-2",
        "section-3",
        "section-4",
        "section-5",
    ]
    assert (
        topic_briefs[2]["section_title"]
        == "Media brands: How do brands interact with people?"
    )
    assert (
        topic_briefs[3]["section_title"]
        == "Sentiments on GenAI: How do APAC consumers perceive AI?"
    )
    assert topic_briefs[4]["section_title"] == "Implications for marketers"


__all__ = [
    "test_cover_semantics_normalizes_provider_enum_formatting",
    "test_generate_artifacts_validates_schema_and_evidence_ids",
    "test_generate_artifacts_prunes_unbound_summary_claims",
    "test_generate_artifacts_abstains_low_confidence_families_and_marks_regeneration",
    "test_summary_family_status_accepts_claim_evidence_ids_without_spans",
    "test_quote_family_abstains_doc_map_only_nonverbatim_quotes",
    "test_normalize_artifact_quotes_preserves_paraphrase_marker",
    "test_generate_artifacts_expands_topic_briefs_from_doc_map",
    "test_build_topic_briefs_avoids_positional_section_swap",
]
