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


def test_findings_targeted_fallback_recovers_incomplete_numeric_body_relationship(
    tmp_path,
):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    section_id = "gaming-finding-keeping-users"
    section_title = "Finding and keeping users"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": section_id,
                "title": section_title,
                "summary": "Gaming installs and sessions differ by subvertical.",
                "key_points": [
                    (
                        "For Global gaming apps, YoY 2024–2025 casino installs "
                        "+22% and sessions -5%; slots installs +46% and "
                        "sessions -5%."
                    )
                ],
                "pages": [17, 18, 19],
            }
        ],
    }
    source_excerpt = (
        "Gaming app install and session growth by subvertical YoY 2024 - 2025 "
        "(Global). Casino and slots both achieved strong install growth of "
        "22% and 46%, but sessions decreased 5% in each category."
    )
    partial = {
        "findings": [
            {
                "id": "casino-only",
                "text": (
                    "For Global gaming apps, casino installs rose 22% while "
                    "sessions decreased 5% year over year between 2024 and 2025."
                ),
                "evidence": source_excerpt,
                "pages": [19],
                "section_id": section_id,
                "section_title": section_title,
            }
        ]
    }
    complete = {
        "findings": [
            {
                "id": "casino-and-slots",
                "text": (
                    "For Global gaming apps, casino games� installs rose 22% "
                    "while sessions decreased 5% year over year between 2024 "
                    "and 2025; slots games� installs rose 46% while sessions "
                    "decreased 5% year over year between 2024 and 2025."
                ),
                "evidence": source_excerpt,
                "pages": [19],
                "section_id": section_id,
                "section_title": section_title,
            }
        ]
    }

    class PartialThenTargetedClient:
        def __init__(self):
            self.findings_requests = []

        def openai_respond_with_vector_store(self, request, ctx):
            task_id = str(ctx.task_id)
            if task_id.endswith(":doc_map"):
                payload = doc_map
            elif task_id.endswith(":targeted_fallback"):
                self.findings_requests.append((request, "targeted_fallback"))
                payload = complete
            else:
                self.findings_requests.append((request, "primary"))
                payload = partial
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=11,
                output_tokens=7,
                tool_calls=1,
                model=request.model,
                file_search_results=[
                    OpenAIFileSearchResult(
                        schema_version="1.0",
                        file_id="file-1",
                        filename="frozen-report.pdf",
                        score=0.9,
                        text=source_excerpt,
                        queries=["gaming installs sessions 2024 2025 page 19"],
                    )
                ],
            )

        def openai_chat_json(self, request, ctx):
            self.findings_requests.append((request, "targeted_fallback_source_pages"))
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(complete),
                parsed_json=complete,
                input_tokens=11,
                output_tokens=7,
                tool_calls=0,
                model=request.model,
            )

    client = PartialThenTargetedClient()
    prompt_client = RecordingPromptClient()
    observed = []
    packs = generate_evidence_packs(
        report_id="gaming-report",
        report_name="gaming-report.pdf",
        vector_store_id="vs_gaming",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:gaming-report"),
        source_spans=[
            {"id": "pdf:p19", "page": 19, "text": source_excerpt},
            {"id": "pdf:p20", "page": 20, "text": "Unmapped next-page text."},
        ],
        openai_client=client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        findings_retrieval_results_observer=(
            lambda results, stage: observed.append(
                (stage, [query for result in results for query in result.queries])
            )
        ),
    )

    assert [stage for _request, stage in client.findings_requests] == [
        "primary",
        "targeted_fallback_source_pages",
    ]
    assert client.findings_requests[0][0].include_file_search_results
    assert [stage for stage, _queries in observed] == [
        "primary",
        "targeted_fallback_source_pages",
    ]
    assert observed[-1][1] == []
    assert all(
        "gaming installs" in query for _stage, queries in observed for query in queries
    )
    assert prompt_client.findings_variables is not None
    fallback_sections = json.loads(
        prompt_client.findings_variables["doc_map_sections_json"]
    )
    assert "2024 to 2025" in fallback_sections[0]["key_points"][0]
    target_pages = json.loads(
        prompt_client.findings_variables["findings_target_source_pages_json"]
    )
    assert target_pages == [{"page": 19, "text": source_excerpt}]
    assert (
        "only the independently extracted source-page excerpts"
        in prompt_client.findings_variables["findings_targeted_fallback_instruction"]
    )
    assert (
        "Return only findings"
        in prompt_client.findings_variables["findings_targeted_fallback_instruction"]
    )
    assert (
        "paired measures"
        in prompt_client.findings_variables["findings_targeted_fallback_instruction"]
    )
    assert (
        "year over year between"
        in prompt_client.findings_variables["findings_targeted_fallback_instruction"]
    )
    assert any(
        finding["id"] == "casino-and-slots"
        and "casino installs" in finding["text"]
        and "slots installs" in finding["text"]
        and "�" not in finding["text"]
        and "46%" in finding["text"]
        and "sessions decreased 5%" in finding["text"]
        for finding in packs["findings"]["findings"]
    ), packs
    assert not any(
        finding["id"] == "casino-only" for finding in packs["findings"]["findings"]
    )
    assert packs["evidence_fidelity"]["deterministic_pass_count"] >= 1
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0


def test_findings_targeted_fallback_keeps_ma_means_as_deal_counts(tmp_path):
    from dataclasses import replace

    from src.contracts.openai import OpenAIResponseResult

    section_id = "diverging-risk-appetites-between-buyers"
    section_title = "Diverging risk appetites between buyers"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": section_id,
                "title": section_title,
                "summary": (
                    "Compares planned M&A deal counts for corporate and PE buyers."
                ),
                "key_points": [
                    "Planned number of M&A deals in 2026: Corporate mean 5.2; "
                    "Private Equity mean 7.3."
                ],
                "pages": [14, 15, 16, 17],
            }
        ],
    }
    source_excerpt = (
        "Planned number of M&A deals in 2026, corporate vs. private equity: "
        "5.2 Mean 7.3 Mean. Corporate Private Equity."
    )
    empty = {
        "evidence_pack": {
            "findings": [],
            "not_found_reason": "findings_not_found",
        }
    }
    fallback = {
        "findings": [
            {
                "id": "corporate-deal-mean",
                "text": "Corporate dealmakers planned a mean of 5.2 M&A deals in 2026.",
                "evidence": source_excerpt,
                "pages": [],
                "section_id": section_id,
                "section_title": section_title,
            },
            {
                "id": "private-equity-deal-mean",
                "text": (
                    "Private equity dealmakers planned a mean of 7.3 M&A deals in 2026."
                ),
                "evidence": source_excerpt,
                "pages": [],
                "section_id": section_id,
                "section_title": section_title,
            },
        ]
    }

    class DealMeanClient:
        def openai_respond_with_vector_store(self, request, ctx):
            payload = doc_map if str(ctx.task_id).endswith(":doc_map") else empty
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=4,
                output_tokens=3,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            if request.artifact_family == "validation_semantic":
                metrics_text = request.user_prompt.split("Metrics (JSON):", 1)[1]
                metrics_text = metrics_text.split("Quotes (JSON):", 1)[0].strip()
                metrics = json.loads(metrics_text)
                payload = {
                    "metrics": [
                        {
                            "id": metric["id"],
                            "supported": True,
                            "confidence": 1.0,
                            "reason": "The source chart supports the deal-count mean.",
                        }
                        for metric in metrics
                    ],
                    "quotes": [],
                }
            else:
                payload = fallback
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=4,
                output_tokens=3,
                tool_calls=0,
                model=request.model,
            )

    packs = generate_evidence_packs(
        report_id="kpmg-deal-means",
        report_name="kpmg-deal-means.pdf",
        vector_store_id="vs_kpmg_deal_means",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:kpmg-deal-means"),
        source_spans=[{"id": "pdf:p15", "page": 15, "text": source_excerpt}],
        openai_client=DealMeanClient(),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    findings = packs["findings"]["findings"]
    assert [finding["pages"] for finding in findings] == [[15], [15]]
    assert "5.2 deals" in findings[0]["text"]
    assert "7.3 deals" in findings[1]["text"]
    assert all("M&A deals" not in finding["text"] for finding in findings)
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0
    assert packs["evidence_fidelity"]["deterministic_pass_count"] >= 2


def test_findings_target_source_page_context_is_bounded_and_page_scoped():
    from src.generators.evidence_pack_generator import _findings_target_source_pages

    targets = [{"id": "target", "pages": list(range(1, 16))}]
    source_spans = [
        {"id": f"pdf:p{page}", "page": page, "text": f"Page {page} evidence."}
        for page in range(1, 16)
    ]

    excerpts = _findings_target_source_pages(targets, source_spans)

    assert [excerpt["page"] for excerpt in excerpts] == list(range(1, 13))
    assert all(
        excerpt["text"] == f"Page {excerpt['page']} evidence." for excerpt in excerpts
    )


def test_findings_target_source_pages_select_complete_numeric_relationship_page():
    from src.generators.evidence_pack_generator import _findings_target_source_pages

    target = {
        "id": "gaming-subverticals",
        "pages": [17, 18, 19, 20],
        "key_point": (
            "Casino installs +22% and sessions -5%; slots installs +46% and "
            "sessions -5%."
        ),
    }
    source_spans = [
        {"id": "pdf:p17", "page": 17, "text": "Europe installs fell 7%."},
        {"id": "pdf:p19", "page": 19, "text": "Casino 22% and -5%; slots 46% and -5%."},
        {"id": "pdf:p20", "page": 20, "text": "Sessions averaged 30 minutes."},
        {"id": "pdf:p21", "page": 21, "text": "Unmapped CPI page."},
    ]

    excerpts = _findings_target_source_pages([target], source_spans)

    assert excerpts == [{"page": 19, "text": "Casino 22% and -5%; slots 46% and -5%."}]


def test_findings_retrieval_target_keeps_multiple_high_value_key_points():
    from src.generators.evidence_pack_generator import _findings_retrieval_targets

    regional = (
        "Gaming app install and session growth, YoY 2024–2025: Global installs "
        "-3% and sessions +1%; Europe installs -7% and sessions +3%; LATAM "
        "installs -9% and sessions +0.4%; MENA installs +2% and sessions +7%; "
        "North America installs -5% and sessions -2%; APAC installs -1% and "
        "sessions -0.4%."
    )
    subvertical = (
        "Gaming app install and session growth by subvertical, YoY 2024–2025 "
        "(Global): casual installs +19% and sessions +37%; hyper-casual installs "
        "+4% and sessions +31%; strategy installs flat and sessions +57%; casino "
        "installs +22% and sessions -5%; slots installs +46% and sessions -5%."
    )
    retention = (
        "Gaming app retention rates, 2024–2025 (Global): all games retained "
        "27% on day 1, 13% on day 7, 8% on day 14, and 5% on day 30; "
        "hyper-casual retained 27%, 8%, 6%, and 2%. Gaming CPI reached $0.56, "
        "up 30%; slots CPI reached $4.47, idle RPG $3.19, and strategy $1.03."
    )
    doc_map = {
        "sections": [
            {
                "id": "gaming",
                "title": "Finding and keeping users",
                "summary": "Commercial gaming app outcomes.",
                "key_points": [regional, subvertical, retention],
                "pages": [17, 18, 19, 20, 21, 22, 23],
            }
        ]
    }

    target = _findings_retrieval_targets(doc_map)[0]

    assert target["key_points"] == [subvertical]
    assert target["key_point"] == subvertical
    assert regional not in target["key_points"]


def test_misleading_doc_map_does_not_promote_unsupported_finding(tmp_path):
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
    empty = {"findings": [], "not_found_reason": "findings_not_found"}

    class UnsupportedThenAbstainClient:
        def __init__(self):
            self.findings_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            if str(ctx.task_id).endswith(":doc_map"):
                payload = doc_map
            else:
                self.findings_calls += 1
                payload = misleading if self.findings_calls == 1 else empty
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
                text=json.dumps(empty),
                parsed_json=empty,
                input_tokens=3,
                output_tokens=2,
                tool_calls=0,
                model=request.model,
            )

    client = UnsupportedThenAbstainClient()
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
    assert packs["findings"]["findings"] == []
    assert packs["evidence_fidelity"]["unsupported_factual_count"] >= 1


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

    assert (
        _missing_findings_retrieval_targets(
            targets, findings, {"internet-media-revenue-forecast"}
        )
        == []
    )


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

    assert _missing_findings_retrieval_targets(targets, [], set()) == [targets[0]]


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


def test_generate_evidence_packs_logs_prompt_observability_and_response_metadata(
    tmp_path, caplog, assert_logs_have_required_fields
):
    caplog.set_level(logging.INFO, logger="market_lense.evidence_pack_generator")
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAIClient(substantive_doc_map()),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["doc_map"]["doc_id"] == "d1"
    events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("event") in {
            "evidence_pack_prompt_rendered",
            "evidence_pack_response_received",
        }:
            events.append(payload)

    assert len(events) >= 2
    assert_logs_have_required_fields(events)
    rendered = next(
        event
        for event in events
        if event.get("event") == "evidence_pack_prompt_rendered"
    )
    rendered_fields = rendered["fields"]
    assert rendered_fields["namespace"] == "report_vs/doc_map"
    assert rendered_fields["system_path"] == "system"
    assert rendered_fields["user_path"] == "user"
    assert "system_prompt" not in rendered_fields
    assert "user_prompt" not in rendered_fields
    assert len(rendered_fields["execution_policy_hash"]) == 64
    assert rendered_fields["resolved_model"] == "gpt-4.1-mini"
    response = next(
        event
        for event in events
        if event.get("event") == "evidence_pack_response_received"
    )
    response_fields = response["fields"]
    assert response_fields["pack"] == "doc_map"
    assert response_fields["has_json"] is True
    assert response_fields["response_chars"] == 2
    response_hash = response_fields["response_sha256"]
    assert response_hash["redaction"] == "***REDACTED***"
    assert len(response_hash["sha256"]) == 64


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
