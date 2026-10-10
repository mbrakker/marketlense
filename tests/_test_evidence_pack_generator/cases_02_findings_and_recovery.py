# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.openai import OpenAIFileSearchResult

from ._support_cases import *  # noqa: F401,F403


def test_generate_evidence_packs_passes_doc_map_sections_to_findings_and_retains_links(
    tmp_path,
):
    prompt_client = RecordingPromptClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": multi_section_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "text": (
                                "Unified measurement connects retail media and "
                                "store outcomes."
                            ),
                            "evidence": (
                                "The report describes a shared cross-channel view."
                            ),
                            "pages": [2],
                            "section_id": "measurement-methods",
                            "section_title": "Cross-channel measurement methods",
                        },
                        {
                            "id": "finding-2",
                            "text": "Investment follows attributable outcomes.",
                            "evidence": (
                                "The outlook links buyer budgets to attribution."
                            ),
                            "pages": [8],
                            "section_id": "investment-outlook",
                            "section_title": "Investment outlook",
                        },
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    sections = json.loads(prompt_client.findings_variables["doc_map_sections_json"])
    assert [section["id"] for section in sections] == [
        "measurement-methods",
        "investment-outlook",
    ]
    assert prompt_client.findings_variables["findings_target_source_pages_json"] == ""
    assert packs["findings"]["findings"] == [
        {
            "id": "finding-1",
            "text": "Unified measurement connects retail media and store outcomes.",
            "evidence": "The report describes a shared cross-channel view.",
            "confidence": "",
            "pages": [2],
            "section_id": "measurement-methods",
            "section_title": "Cross-channel measurement methods",
        },
        {
            "id": "finding-2",
            "text": "Investment follows attributable outcomes.",
            "evidence": "The outlook links buyer budgets to attribution.",
            "confidence": "",
            "pages": [8],
            "section_id": "investment-outlook",
            "section_title": "Investment outlook",
        },
    ]


def test_generate_evidence_packs_passes_source_temporal_relationships_to_findings(
    tmp_path,
):
    prompt_client = RecordingPromptClient()
    generate_evidence_packs(
        report_id="source-temporal-pairs",
        report_name="Source temporal pairs",
        vector_store_id="vs_1",
        source_text=(
            "2019 2020 2021 2022 2023 2024E 2028E 0:20 0:28 0:36 0:43 0:48 0:52 0:57"
        ),
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": substantive_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "text": "Source-backed social-video growth.",
                            "evidence": "The source reports a social-video series.",
                            "pages": [2],
                        }
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    assert json.loads(
        prompt_client.findings_variables["source_temporal_relationships_json"]
    ) == [
        {"period": "2019", "value": "0:20"},
        {"period": "2020", "value": "0:28"},
        {"period": "2021", "value": "0:36"},
        {"period": "2022", "value": "0:43"},
        {"period": "2023", "value": "0:48"},
        {"period": "2024e", "value": "0:52"},
        {"period": "2028e", "value": "0:57"},
    ]


def test_findings_context_retains_counterbalancing_major_docmap_sections(tmp_path):
    prompt_client = RecordingPromptClient()
    packs = generate_evidence_packs(
        report_id="counterbalanced-doc-map",
        report_name="Counterbalanced DocMap",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": counterbalanced_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "benefit-1",
                            "text": "AI can improve operational efficiency.",
                            "evidence": "35% expect efficiency gains from AI.",
                            "pages": [4],
                            "section_id": "efficiency-value",
                            "section_title": "Efficiency and value",
                        },
                        {
                            "id": "risk-1",
                            "text": "AI-generated media needs trust safeguards.",
                            "evidence": "Trust concerns require governance controls.",
                            "pages": [12],
                            "section_id": "trust-governance",
                            "section_title": "Trust, risk, and governance",
                        },
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    sections = json.loads(prompt_client.findings_variables["doc_map_sections_json"])
    assert [section["id"] for section in sections] == [
        "efficiency-value",
        "cost-savings",
        "trust-governance",
    ]
    assert [finding["section_id"] for finding in packs["findings"]["findings"]] == [
        "efficiency-value",
        "trust-governance",
    ]


def test_misleading_doc_map_does_not_promote_unsupported_finding(tmp_path, caplog):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    section_id = "market-growth"
    section_title = "Market growth"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": section_id,
                "title": section_title,
                "summary": "The market grew rapidly.",
                "key_points": ["Revenue reached $90B in 2026."],
                "pages": [4],
            }
        ],
    }
    misleading = {
        "findings": [
            {
                "id": "unsupported-90b",
                "text": "Market revenue reached $90B in 2026.",
                "evidence": "Market revenue reached $90B in 2026.",
                "pages": [4],
                "section_id": section_id,
                "section_title": section_title,
            }
        ]
    }
    supported_source_finding = {
        "findings": [
            {
                "id": "supported-9b",
                "text": "Market revenue reached $9B in 2026.",
                "evidence": "Market revenue reached $9B in 2026.",
                "pages": [4],
                "section_id": section_id,
                "section_title": section_title,
            }
        ]
    }

    class UnsupportedFallbackClient:
        def __init__(self):
            self.findings_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            if str(ctx.task_id).endswith(":doc_map"):
                payload = doc_map
            else:
                self.findings_calls += 1
                payload = (
                    misleading if self.findings_calls > 1 else supported_source_finding
                )
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=3,
                output_tokens=2,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            self.findings_calls += 1
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(misleading),
                parsed_json=misleading,
                input_tokens=3,
                output_tokens=2,
                tool_calls=0,
                model=request.model,
            )

    caplog.set_level(logging.INFO, logger="market_lense.evidence_pack_generator")
    client = UnsupportedFallbackClient()
    packs = generate_evidence_packs(
        report_id="misleading-docmap",
        report_name="misleading-docmap.pdf",
        vector_store_id="vs_misleading",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:misleading-docmap"),
        source_spans=[
            {
                "id": "pdf:p4",
                "page": 4,
                "text": "Market revenue reached $9B in 2026.",
            }
        ],
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert client.findings_calls == 2
    assert [finding["id"] for finding in packs["findings"]["findings"]] == [
        "supported-9b"
    ]
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0
    fallback_events = []
    for record in caplog.records:
        try:
            event = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "findings_targeted_fallback_complete":
            fallback_events.append(event)
    assert len(fallback_events) == 1
    assert fallback_events[0]["fields"]["returned_findings"] == 1
    assert fallback_events[0]["fields"]["supported_findings"] == 0


def test_supported_priority_body_finding_avoids_targeted_fallback(tmp_path):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    section_id = "revenue-growth"
    section_title = "Revenue growth"
    source_excerpt = "Revenue was up 12% in 2025."
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": section_id,
                "title": section_title,
                "summary": "Revenue growth accelerated.",
                "key_points": ["Revenue was up 12% in 2025."],
                "pages": [4],
            }
        ],
    }
    finding = {
        "findings": [
            {
                "id": "revenue-growth-2025",
                "text": "Revenue was up 12% in 2025.",
                "evidence": source_excerpt,
                "pages": [4],
                "section_id": section_id,
                "section_title": section_title,
            }
        ]
    }

    class CompleteBodyFindingClient:
        def __init__(self):
            self.findings_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            if str(ctx.task_id).endswith(":doc_map"):
                payload = doc_map
            else:
                self.findings_calls += 1
                payload = finding
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=4,
                output_tokens=3,
                tool_calls=1,
                model=request.model,
            )

    client = CompleteBodyFindingClient()
    packs = generate_evidence_packs(
        report_id="supported-body-report",
        report_name="supported-body-report.pdf",
        vector_store_id="vs_supported_body",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:supported-body-report"),
        source_spans=[{"id": "pdf:p4", "page": 4, "text": source_excerpt}],
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert client.findings_calls == 1
    assert packs["findings"]["findings"][0]["id"] == "revenue-growth-2025"
    assert packs["evidence_fidelity"]["deterministic_pass_count"] == 1


def test_supported_finding_gets_physical_page_from_validated_source_reference(
    tmp_path,
):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    source_excerpt = "Revenue was up 12% in 2025."
    section_id = "revenue-growth"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": section_id,
                "title": "Revenue growth",
                "summary": "Revenue growth accelerated.",
                "key_points": ["Revenue was up 12% in 2025."],
                "pages": [4],
            }
        ],
    }
    finding = {
        "findings": [
            {
                "id": "revenue-growth-2025",
                "text": "Revenue was up 12% in 2025.",
                "evidence": source_excerpt,
                "pages": [],
                "section_id": section_id,
                "section_title": "Revenue growth",
            }
        ]
    }

    class SupportedWithoutPageClient:
        def __init__(self):
            self.findings_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            if str(ctx.task_id).endswith(":doc_map"):
                payload = doc_map
            else:
                self.findings_calls += 1
                payload = finding
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=4,
                output_tokens=3,
                tool_calls=1,
                model=request.model,
            )

    client = SupportedWithoutPageClient()
    packs = generate_evidence_packs(
        report_id="supported-without-page",
        report_name="supported-without-page.pdf",
        vector_store_id="vs_supported_without_page",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:supported-without-page"),
        source_spans=[{"id": "pdf:p4", "page": 4, "text": source_excerpt}],
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert client.findings_calls == 1
    assert packs["findings"]["findings"][0]["pages"] == [4]
    assert packs["evidence_fidelity"]["deterministic_pass_count"] == 1


def test_semantically_supported_finding_gets_physical_page_after_final_validation(
    tmp_path,
):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    source_excerpt = (
        "Dealmakers are prioritizing transactions where integration, capability "
        "acquisition, and portfolio optimization can be executed with speed "
        "and control."
    )
    finding = {
        "findings": [
            {
                "id": "transaction-focus",
                "text": (
                    "Dealmakers now favor transactions over megadeals, prioritizing "
                    "integration, capability acquisition, and faster portfolio "
                    "optimization."
                ),
                "evidence": source_excerpt,
                "pages": [],
                "section_id": "",
                "section_title": "",
            }
        ]
    }

    class SemanticSupportWithoutFindingPageClient:
        def openai_respond_with_vector_store(self, request, ctx):
            if request.artifact_family == "doc_map":
                payload = {
                    "doc_id": "d1",
                    "title": "M&A Outlook",
                    "summary": "The report reviews current dealmaking priorities.",
                    "sections": [
                        {
                            "id": "deal-priorities",
                            "title": "Deal priorities",
                            "summary": "Dealmakers prioritize portfolio optimization.",
                            "key_points": [
                                "Dealmakers prioritize integration and portfolio "
                                "optimization."
                            ],
                            "pages": [8],
                        }
                    ],
                }
            elif request.artifact_family == "findings":
                payload = (
                    {"findings": []}
                    if str(ctx.task_id).endswith(":targeted_fallback")
                    else finding
                )
            elif request.artifact_family == "validation_semantic":
                payload = {
                    "metrics": [
                        {
                            "id": "evidence:findings:transaction-focus",
                            "supported": True,
                            "confidence": 0.99,
                            "reason": (
                                "The source supports the stated dealmaking priorities."
                            ),
                        }
                    ],
                    "quotes": [],
                }
            else:
                payload = {"not_found_reason": "fixture_insufficient_evidence"}
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=4,
                output_tokens=3,
                tool_calls=0,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            return self.openai_respond_with_vector_store(request, ctx)

    packs = generate_evidence_packs(
        report_id="semantic-page-reference",
        report_name="semantic-page-reference.pdf",
        vector_store_id="vs_semantic_page_reference",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:semantic-page-reference"),
        source_spans=[{"id": "pdf:p8", "page": 8, "text": source_excerpt}],
        openai_client=SemanticSupportWithoutFindingPageClient(),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["evidence_fidelity"]["semantic_validation_count"] == 1
    assert packs["findings"]["findings"][0]["pages"] == [8]


def test_complete_numeric_lead_does_not_trigger_secondary_numeric_fallback():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    targets = [
        {
            "id": "tech-media-growth-dollars",
            "title": "$300 Billion in Tech and Media Growth Dollars",
            "key_point": (
                "Revenue rose from $1.7T in 2017E to $2.0T in 2021E, adding "
                "$302B at 4.1% CAGR versus approximately 3% GDP CAGR."
            ),
            "pages": [3, 4, 5, 6],
        },
        {
            "id": "web-video",
            "title": "Big Influencers and Media Brands will Rule Web Video",
            "key_point": "Creator shares and video views are compared.",
            "pages": [49, 50],
        },
    ]
    findings = [
        {
            "id": "internet-media-revenue-forecast",
            "section_id": "tech-media-growth-dollars",
            "text": targets[0]["key_point"],
            "evidence": targets[0]["key_point"],
            "pages": [5],
        }
    ]

    assert _missing_findings_retrieval_targets(
        targets, findings, {"internet-media-revenue-forecast"}
    ) == [targets[1]]


def test_incomplete_numeric_lead_does_not_expand_to_secondary_numeric_target():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    targets = [
        {
            "id": "tech-media-growth-dollars",
            "title": "$300 Billion in Tech and Media Growth Dollars",
            "key_point": "Revenue grew by $302B at a 4.1% CAGR.",
            "pages": [3, 4, 5, 6],
        },
        {
            "id": "web-video",
            "title": "Big Influencers and Media Brands will Rule Web Video",
            "key_point": "50M+ creators account for 71% of views.",
            "pages": [49, 50, 51, 52],
        },
    ]

    assert _missing_findings_retrieval_targets(targets, [], set()) == targets


def test_complete_buyer_comparison_still_retrieves_missing_strategic_portfolio_target():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    targets = [
        {
            "id": "diverging-risk-appetites-between-buyers",
            "title": "Diverging risk appetites between buyers",
            "key_point": "Planned 2026 M&A deals: corporate mean 5.2; PE mean 7.3.",
            "pages": [14, 15, 16, 17],
        },
        {
            "id": "portfolio-simplification-as-a-value-creation-strategy",
            "title": "Portfolio simplification as a value creation strategy",
            "key_point": "Portfolio simplification sharpens strategic direction.",
            "pages": [18, 19, 20, 21, 22],
        },
    ]
    findings = [
        {
            "id": "buyer-deal-comparison",
            "section_id": "diverging-risk-appetites-between-buyers",
            "text": (
                "For 2026, corporate buyers averaged 5.2 M&A deals versus 7.3 for PE."
            ),
            "evidence": "2026 M&A deals: corporate mean 5.2; private equity mean 7.3.",
            "pages": [15],
        }
    ]

    assert _missing_findings_retrieval_targets(
        targets, findings, {"buyer-deal-comparison"}
    ) == [targets[1]]


def test_same_section_title_does_not_match_a_different_docmap_section_id():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    target = {
        "id": "gaming-finding-keeping-users",
        "title": "Finding and keeping users",
        "key_point": (
            "Casino installs +22% and sessions -5%; slots +46% and sessions -5%."
        ),
        "pages": [17, 18, 19, 20, 21, 22, 23],
    }
    ecommerce_finding = {
        "id": "ecommerce-session-outcome",
        "section_id": "ecommerce-finding-keeping-users",
        "section_title": "Finding and keeping users",
        "text": ("Casino installs +22% and sessions -5%; slots +46% and sessions -5%."),
        "evidence": (
            "Casino installs +22% and sessions -5%; slots +46% and sessions -5%."
        ),
        "pages": [27],
    }

    assert _missing_findings_retrieval_targets(
        [target], [ecommerce_finding], {"ecommerce-session-outcome"}
    ) == [target]


def test_generate_evidence_packs_handles_missing_json(tmp_path):
    fake_openai = FakeOpenAIClient(parsed=None)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_invalid_json"
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    fake_openai = RetryableErrorOpenAIClient()
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert_app_error(
        exc_info.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )
    assert fake_openai.call_count == 1
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_rejects_doc_map_with_only_doc_id(tmp_path):
    # `doc_id` can be present while the pack is still semantically empty.
    parsed = {"doc_id": "d1", "title": "", "sections": []}
    fake_openai = FakeOpenAIClient(parsed=parsed)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_invalid_json"
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_recovers_identifier_only_doc_map(tmp_path):
    class PlaceholderThenSubstantiveClient:
        def __init__(self):
            self.doc_map_calls = 0

        def openai_respond_with_vector_store(self, req, ctx):
            if req.artifact_family != "doc_map":
                payload = {"not_found_reason": "fixture_insufficient_evidence"}
            else:
                self.doc_map_calls += 1
                payload = (
                    {
                        "doc_id": "report-42",
                        "title": "doc_map",
                        "summary": "report-42 | vs_42 | doc_map",
                        "sections": [
                            {
                                "id": "s1",
                                "title": "Metadata",
                                "summary": (
                                    "Key metadata fields extracted from source "
                                    "evidence."
                                ),
                                "key_points": [
                                    "report_name: report-42",
                                    "vector_store_id: vs_42",
                                ],
                                "pages": [],
                                "references": [],
                            }
                        ],
                    }
                    if self.doc_map_calls == 1
                    else {
                        "doc_id": "report-42",
                        "title": "Retail Measurement Outlook 2026",
                        "summary": (
                            "The report examines how retailers use cross-channel "
                            "measurement to improve campaign decisions."
                        ),
                        "sections": [
                            {
                                "id": "measurement-methods",
                                "title": "Cross-channel measurement methods",
                                "summary": (
                                    "Explains how campaign data connects retail media, "
                                    "stores, and ecommerce activity."
                                ),
                                "key_points": [
                                    (
                                        "Retail media requires comparable campaign "
                                        "signals."
                                    ),
                                    (
                                        "Store and ecommerce activity need a shared "
                                        "measurement view."
                                    ),
                                ],
                                "pages": [3],
                                "references": [],
                            }
                        ],
                    }
                )
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                model=req.model,
            )

    client = PlaceholderThenSubstantiveClient()
    packs = generate_evidence_packs(
        report_id="report-42",
        report_name="retail-measurement-outlook.pdf",
        vector_store_id="vs_42",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert client.doc_map_calls == 2
    assert packs["doc_map"]["title"] == "Retail Measurement Outlook 2026"
    assert packs["doc_map"]["family_status"]["status"] == "generated"


def test_generate_evidence_packs_recovers_doc_map_once_inside_shared_service(tmp_path):
    fake_openai = RetryingDocMapClient()
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert packs["doc_map"]["doc_id"] == "d1"
    assert fake_openai.call_count == 7
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_parses_doc_map_json_from_text_fallback(tmp_path):
    fake_openai = TextFallbackDocMapClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["doc_map"]["doc_id"] == "d1"
    assert packs["doc_map"]["title"] == "Retail Measurement Outlook"
    assert fake_openai.call_count == 6
