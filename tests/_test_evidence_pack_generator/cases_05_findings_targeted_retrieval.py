# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.openai import OpenAIFileSearchResult

from ._support_cases import *  # noqa: F401,F403,F405


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
                    "For Global gaming apps, casino installs rose 22% "
                    "while sessions decreased 5% year over year between 2024 "
                    "and 2025; slots installs rose 46% while sessions "
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
    assert target_pages == [
        {"page": 19, "text": source_excerpt, "source_span_ids": ["pdf:p19"]}
    ]
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
        {
            "id": f"pdf:p{page}",
            "page": page,
            "text": f"Page {page} evidence.\n{page}",
        }
        for page in range(1, 16)
    ]

    excerpts = _findings_target_source_pages(targets, source_spans)

    assert [excerpt["page"] for excerpt in excerpts] == [1, 2]
    assert all(
        excerpt["text"] == f"Page {excerpt['page']} evidence.\n{excerpt['page']}"
        for excerpt in excerpts
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

    assert excerpts == [
        {
            "page": 19,
            "text": "Casino 22% and -5%; slots 46% and -5%.",
            "source_span_ids": ["pdf:p19"],
        }
    ]

def test_findings_target_source_pages_resolve_printed_label_to_physical_pdf_page():
    from src.generators.evidence_pack_generator import _findings_target_source_pages

    target = {
        "id": "technology-media-growth",
        "title": "Technology media market growth",
        "pages": [4],
        "key_point": (
            "The market adds $302B from 2017E to 2021E, growing at 4.1% CAGR "
            "versus approximately 3% GDP."
        ),
    }
    source_spans = [
        {
            "id": "pdf:p4",
            "page": 4,
            "text": "Contents\nTechnology media market growth\n3",
        },
        {
            "id": "pdf:p5",
            "page": 5,
            "text": (
                "Technology media market\n2017E $1.7T\n2021E $2.0T\n"
                "Increase $302B\nCAGR 4.1%\nGDP approximately 3%\n4"
            ),
        },
    ]

    excerpts = _findings_target_source_pages([target], source_spans)

    assert len(excerpts) == 1
    assert excerpts[0]["page"] == 5
    assert excerpts[0]["source_span_ids"] == ["pdf:p5"]
    assert all(value in excerpts[0]["text"] for value in ("$302B", "4.1%", "3%"))

def test_findings_target_source_pages_infer_one_missing_label_from_page_sequence():
    from src.generators.evidence_pack_generator import _findings_target_source_pages

    target = {
        "id": "technology-media-growth",
        "title": "Technology media market growth",
        "pages": [3, 4, 5, 6],
        "key_point": "Market revenue adds $302B from 2017E to 2021E.",
    }
    source_spans = [
        {"id": "pdf:p4", "page": 4, "text": "3\nContents page."},
        {
            "id": "pdf:p5",
            "page": 5,
            "text": "Technology media revenue\n$302B growth\nACTIVATE",
        },
        {"id": "pdf:p6", "page": 6, "text": "5\nTechnology media segments."},
        {"id": "pdf:p7", "page": 7, "text": "6\nTechnology media revenue model."},
    ]

    excerpts = _findings_target_source_pages([target], source_spans)

    assert 5 in [excerpt["page"] for excerpt in excerpts]
    assert any("$302B" in excerpt["text"] for excerpt in excerpts)

def test_findings_target_source_pages_aggregate_spans_and_find_page_end_evidence():
    from src.generators.evidence_pack_generator import _findings_target_source_pages

    target = {
        "id": "gaming",
        "pages": [19],
        "key_point": "Casino installs +22% and sessions -5%.",
    }
    source_spans = [
        {"id": "pdf:p19:span1", "page": 19, "text": "Unrelated page header. " * 400},
        {
            "id": "pdf:p19:span2",
            "page": 19,
            "text": "Casino installs +22% and sessions -5% in 2024-2025. "
            "Table labels: installs; sessions.",
        },
    ]

    excerpts = _findings_target_source_pages([target], source_spans)

    assert len(excerpts) == 1
    assert excerpts[0]["page"] == 19
    assert "Casino installs +22% and sessions -5%" in excerpts[0]["text"]
    assert excerpts[0]["source_span_ids"] == ["pdf:p19:span1", "pdf:p19:span2"]

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

    assert target["key_point"] in target["key_points"]
    assert subvertical in target["key_points"]
    assert regional in target["key_points"]
    assert len(target["key_points"]) == 3

def test_findings_target_significance_does_not_boost_report_topics():
    from src.generators.evidence_pack_generator import _findings_target_key_point_score

    app_metrics = (
        "Casino installs +22% and sessions -5%; slots installs +46% and sessions -5%."
    )
    retail_metrics = (
        "Online orders +22% and visits -5%; stores orders +46% and visits -5%."
    )

    assert _findings_target_key_point_score(
        app_metrics
    ) == _findings_target_key_point_score(retail_metrics)

def test_findings_targets_skip_reader_metadata_but_keep_substantive_summaries():
    from src.generators.evidence_pack_generator import _findings_retrieval_targets

    targets = _findings_retrieval_targets(
        {
            "sections": [
                {
                    "id": "who-should-read",
                    "title": "Who should read this report and why?",
                    "summary": "The report serves leaders seeking market trends.",
                    "pages": [7],
                },
                {
                    "id": "authors",
                    "title": "Authors – Meet the experts",
                    "summary": "The report lists the research authors.",
                    "pages": [73],
                },
                {
                    "id": "market-outlook",
                    "title": "Market outlook",
                    "summary": "Demand grew 12% while supply fell 4% in 2025.",
                    "pages": [8],
                },
                {
                    "id": "executive-summary",
                    "title": "Executive summary",
                    "summary": "In 2025, revenue grew 12% while costs fell 4%.",
                    "pages": [4],
                },
            ]
        }
    )

    assert {target["id"] for target in targets} == {
        "market-outlook",
        "executive-summary",
    }

def test_findings_target_coverage_requires_each_numeric_relationship():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "gaming",
        "title": "Finding and keeping users",
        "pages": [19],
        "key_points": [
            "Casino installs +22% and sessions -5%; slots installs +46% "
            "and sessions -5%."
        ],
    }
    findings = [
        {
            "id": "only-casino-pair",
            "section_id": "gaming",
            "text": "Casino installs grew 22%; slots installs grew 46%.",
            "evidence": (
                "Casino installs +22%, sessions -5%; slots installs +46%, "
                "sessions -5%."
            ),
            "pages": [19],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"only-casino-pair"}, [target]
    )

def test_findings_target_coverage_allows_complete_relationships_across_findings():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "gaming",
        "title": "Finding and keeping users",
        "pages": [18],
        "key_points": [
            "Casino installs +22% and sessions -5%; slots installs +46% "
            "and sessions -5%."
        ],
    }
    findings = [
        {
            "id": "casino-pair",
            "section_id": "gaming",
            "text": "Casino installs grew 22% and sessions fell 5% in 2025.",
            "evidence": "Casino installs +22%; sessions -5% in 2025.",
            "pages": [19],
        },
        {
            "id": "slots-pair",
            "section_id": "gaming",
            "text": "Slots installs grew 46% and sessions fell 5% in 2025.",
            "evidence": "Slots installs +46%; sessions -5% in 2025.",
            "pages": [19],
        },
    ]

    assert _findings_target_is_covered(
        target, findings, {"casino-pair", "slots-pair"}, [target]
    )

def test_findings_target_coverage_accepts_equivalent_numeric_formatting():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "market-growth",
        "title": "Market growth",
        "pages": [4],
        "key_point": "Global revenue increased to $0.3T in 2025.",
    }
    findings = [
        {
            "id": "market-growth-2025",
            "section_id": "market-growth",
            "text": "Global revenue rose to $300 billion in 2025.",
            "evidence": "Global revenue reached $300 billion in 2025.",
            "pages": [5],
        }
    ]

    assert _findings_target_is_covered(
        target, findings, {"market-growth-2025"}, [target]
    )

def test_findings_target_coverage_accepts_supported_qualitative_paraphrase():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "portfolio-simplification",
        "title": "Portfolio simplification as a value creation strategy",
        "pages": [18],
        "key_point": (
            "Portfolio simplification can unlock value for buyers and sellers."
        ),
    }
    findings = [
        {
            "id": "carve-out-value",
            "section_id": "portfolio-simplification",
            "text": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "evidence": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "pages": [19],
        }
    ]

    assert _findings_target_is_covered(
        target, findings, {"carve-out-value"}, [target]
    )

def test_findings_target_coverage_does_not_compare_printed_and_physical_page_numbers():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "revenue-growth",
        "title": "Revenue growth",
        "pages": [4],  # DocMap printed label; source page is physical PDF page 5.
        "key_point": "Revenue increased 12% in 2025.",
    }
    findings = [
        {
            "id": "revenue-growth-2025",
            "section_id": "revenue-growth",
            "text": "Revenue increased 12% in 2025.",
            "evidence": "Revenue increased 12% in 2025.",
            "pages": [5],
        }
    ]

    assert _findings_target_is_covered(
        target, findings, {"revenue-growth-2025"}, [target]
    )

def test_findings_target_coverage_rejects_values_swapped_between_subjects():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "benchmarks",
        "title": "Growth by category",
        "pages": [19],
        "key_points": ["Casino 22%; Slots 46%."],
    }
    findings = [
        {
            "id": "swapped-categories",
            "section_id": "benchmarks",
            "text": "Casino 46%; Slots 22%.",
            "evidence": "Casino 22%; Slots 46%.",
            "pages": [19],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"swapped-categories"}, [target]
    )

def test_missing_findings_targets_checks_all_bounded_targets_and_returns_two():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    targets = [
        {
            "id": f"section-{index}",
            "title": f"Section {index}",
            "key_point": f"Section {index} has a source-backed result.",
            "pages": [index],
        }
        for index in range(1, 5)
    ]
    findings = [
        {
            "id": f"finding-{index}",
            "section_id": f"section-{index}",
            "text": f"Section {index} has a source-backed result.",
            "evidence": f"Section {index} has a source-backed result.",
            "pages": [index],
        }
        for index in (1, 2)
    ]

    assert _missing_findings_retrieval_targets(
        targets, findings, {"finding-1", "finding-2"}
    ) == targets[2:4]

def test_bounded_recovery_prioritizes_specific_strategy_over_broad_focus():
    from src.generators.evidence_pack_generator import (
        _findings_retrieval_targets,
        _missing_findings_retrieval_targets,
    )

    targets = _findings_retrieval_targets(
        {
            "sections": [
                {
                    "id": "buyer-activity",
                    "title": "Diverging risk appetites between buyers",
                    "summary": "Compares corporate and PE deal activity.",
                    "key_points": [
                        "Planned number of M&A deals in 2026: Corporate mean "
                        "5.2; Private Equity mean 7.3."
                    ],
                    "pages": [14, 15, 16, 17],
                },
                {
                    "id": "strategic-focus",
                    "title": "Strategic focus in a fragmented world",
                    "summary": "Contrasts opportunistic expansion and strategy.",
                    "key_points": [
                        "The report contrasts opportunistic expansion with "
                        "transactions that reinforce a clear strategic direction."
                    ],
                    "pages": [10, 11, 12, 13],
                },
                {
                    "id": "portfolio-simplification",
                    "title": "Portfolio simplification as a value creation strategy",
                    "summary": "Discusses simplification as a means of creating value.",
                    "key_points": [
                        "Positions portfolio simplification as a value-creation "
                        "strategy."
                    ],
                    "pages": [18, 19, 20, 21, 22],
                },
            ]
        }
    )

    missing = _missing_findings_retrieval_targets(targets, [], set())

    assert [target["id"] for target in missing] == [
        "buyer-activity",
        "portfolio-simplification",
    ]

def test_target_selection_keeps_section_lead_ahead_of_dense_charts():
    from src.generators.evidence_pack_generator import _findings_retrieval_targets

    targets = _findings_retrieval_targets(
        {
            "sections": [
                {
                    "id": "section-04",
                    "title": "Platform changes",
                    "summary": "Publishers are changing platform effort.",
                    "key_points": [
                        "Meta reported that friends-and-family content accounted "
                        "for 17% on Facebook and 7% on Instagram; referrals fell "
                        "43% from Facebook and 46% from X.",
                        "For 2026, YouTube +74, AI platforms +61, TikTok +56, "
                        "Instagram +41, LinkedIn +40, WhatsApp +26, Facebook -23, "
                        "Google Search -25, and X -52.",
                        "The section describes publisher platform choices.",
                    ],
                    "pages": [18, 19, 20, 21],
                },
                {
                    "id": "section-03",
                    "title": "Distinctive content",
                    "summary": "Publishers plan to invest in distinctive journalism.",
                    "key_points": [
                        "For newsroom focus, original investigations scored +91, "
                        "contextual analysis +82, community +76, human stories +72, "
                        "fact-checking +63, opinion +55, and breaking news +26; "
                        "Q&A scored -10, evergreen -32, general news -38, and "
                        "service journalism -42."
                    ],
                    "pages": [15, 16, 17],
                },
                {
                    "id": "section-02",
                    "title": "Search traffic outlook",
                    "summary": "Publishers expect search traffic to decline.",
                    "key_points": [
                        "Publishers expected search-engine traffic to fall by more "
                        "than 40% over the next three years.",
                        "Chartbeat referral changes, Nov 2024-Nov 2025: Google Search "
                        "Global -33%, US -38%, Europe -17%; Google Discover Global "
                        "-21%, US -29%, Europe -18%; Facebook Global +9%, US +23%, "
                        "Europe +5%; X Global +15%, US +29%, Europe -22%.",
                        "Chartbeat referral changes, May 2023-Nov 2025: Google Search "
                        "Global -21%, US -22%, Europe -17%; Facebook Global -43%, "
                        "US -35%, Europe -38%; X Global -46%, US -46%, Europe -66%.",
                        "On licensing revenue in three years, respondents expected "
                        "main source 0%, significant 20%, minor 49%, no income 20%, "
                        "and did not know 11%."
                    ],
                    "pages": [10, 11, 12, 13, 14],
                },
            ]
        }
    )

    search_target = next(target for target in targets if target["id"] == "section-02")
    assert targets.index(search_target) < 2
    assert any("more than 40%" in point for point in search_target["key_points"])

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
