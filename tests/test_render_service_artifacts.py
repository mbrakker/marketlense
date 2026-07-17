from pathlib import Path

from PIL import Image

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_render_removes_inline_internal_evidence_tokens_from_public_prose(
    tmp_path: Path,
) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Evidence Token Report",
                "insights": [],
                "quote": {"text": "", "author": ""},
                "artifacts": {
                    "summary": {
                        "tldr": "The retained signal is actionable (IC1).",
                        "executive_summary": "The action follows IC-02.",
                    },
                    "expert_comment": "Leaders should act on the signal (IC3).",
                },
            },
            doc_name="evidence-token.pdf",
            file_id="file-evidence-token",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "IC1" not in html
    assert "IC-02" not in html
    assert "IC3" not in html
    assert "The retained signal is actionable." in html


def test_render_includes_artifact_sections(tmp_path):
    data = {
        "title": "Sample Report",
        "tldr": "Original TLDR",
        "insights": ["legacy insight"] * 5,
        "quote": {"text": "Legacy quote", "author": "Author"},
        "commentary": "Legacy commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "artifacts": {
            "toc_topics": ["Topic A", "Topic B"],
            "summary": {
                "tldr": "Artifact TLDR",
                "executive_summary": "Artifact executive summary",
                "claim_evidence_map": [
                    {
                        "claim": "Claim 1",
                        "evidence_id": "f1",
                        "evidence": "Evidence 1",
                        "pages": [4],
                        "evidence_spans": [
                            {
                                "evidence_id": "f1",
                                "source_pack": "findings",
                                "page": 4,
                            }
                        ],
                    }
                ],
            },
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Artifact insight 1",
                    "evidence_id": "f1",
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings", "page": 4}
                    ],
                    "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
                },
                {
                    "id": "i2",
                    "text": "Artifact insight 2",
                    "evidence_id": "f2",
                    "evidence_spans": [
                        {"evidence_id": "f2", "source_pack": "findings", "page": 5}
                    ],
                    "metric": {"value": "", "unit": "", "timeframe": ""},
                },
            ],
            "quotes_final": [
                {
                    "text": "Artifact quote",
                    "speaker": "Speaker",
                    "citation": "Report",
                    "page": 2,
                    "evidence_id": "q1",
                    "evidence_spans": [
                        {
                            "evidence_id": "q1",
                            "source_pack": "quote_candidates",
                            "page": 2,
                        }
                    ],
                }
            ],
            "expert_comment": "Expert take",
            "linkedin_post": "LinkedIn summary",
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="sample.pdf",
        file_id="file_1",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Signals to watch after reading this report" in html
    assert "Artifact TLDR" in html
    assert "Artifact executive summary" in html
    assert "What leaders should take from the report" in html
    assert "Artifact insight 1" in html
    assert "Source language behind the read" in html
    assert "Artifact quote" in html
    assert "MarketBearing expert view" in html
    assert "LinkedIn-ready post" in html
    assert 'id="expert"' in html
    assert 'id="overview"' in html
    assert 'class="summary-panel summary-panel-executive"' in html
    assert 'class="claim-strip"' in html
    assert "Sample Report, page 4" in html
    assert "Sample Report, page 2 · Report" in html
    assert "f1 · report page" not in html
    assert "q1 · report page" not in html
    assert 'data-market-lense-publish-entity="true"' in html
    assert '"entity_type":"report"' in html
    assert '"canonical_route_intent":"wordpress:ml_report"' in html


def test_render_body_excludes_wordpress_owned_chrome_and_nested_main(tmp_path):
    data = {
        "title": "Chrome Contract Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Artifact TLDR",
                "executive_summary": "Artifact executive summary",
            },
            "insights_final": [{"id": "i1", "text": "Insight A"}],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="chrome.pdf",
        file_id="file_chrome",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")
    body = html.split("<body", 1)[1].split("</body>", 1)[0]

    assert '<header class="site-header"' not in body
    assert '<footer class="footer"' not in body
    assert "<main" not in body
    assert 'class="report-document"' in body


def test_render_expands_covered_topics_with_briefs(tmp_path):
    data = {
        "title": "Topic Brief Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "artifacts": {
            "toc_topics": ["Demand outlook", "Margin resilience"],
            "toc_topics_expanded": [
                {
                    "topic": "Demand outlook",
                    "summary": "Demand is strongest in APAC and improving in North America.",
                    "key_points": [
                        "APAC growth leads at +12%",
                        "North America recovered in Q4",
                    ],
                },
                {
                    "topic": "Margin resilience",
                    "summary": "Margins stabilized in H2 as input costs eased.",
                    "key_points": [],
                },
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="topics.pdf",
        file_id="file_topics",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Demand is strongest in APAC and improving in North America." in html
    assert "APAC growth leads at +12%" in html
    assert "North America recovered in Q4" in html
    assert "Margins stabilized in H2 as input costs eased." in html


def test_render_fallbacks_without_artifacts(tmp_path):
    data = {
        "title": "Legacy Report",
        "tldr": "Legacy TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Legacy quote", "author": "Legacy author"},
        "commentary": "Legacy commentary",
        "publisher": "",
        "taxonomy": [],
        "region": "",
        "time_period": "",
        "contents_page_number": 0,
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="legacy.pdf",
        file_id="file_legacy",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Legacy TLDR" in html
    assert "Insight A" in html and "Insight E" in html
    assert "Legacy quote" in html
    assert "Legacy commentary" in html
    assert "What leaders should take from the report" in html
    assert "Source URL was not available in the extracted report metadata." in html


def test_render_surfaces_report_quality_score_and_download_link(tmp_path):
    data = {
        "title": "Scored Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2026",
        "contents_page_number": 0,
        "_source_download_href": "../cache/scored.pdf",
        "_report_value_score": {
            "schema_version": "1.0",
            "overall_score": 87.0,
            "value_band": "high",
            "rationale": "Strong original market report.",
            "components": [
                {
                    "schema_version": "1.0",
                    "dimension": "market_insight_depth",
                    "score": 90.0,
                    "rationale": "Deep market lens.",
                },
                {
                    "schema_version": "1.0",
                    "dimension": "evidence_specificity",
                    "score": 82.0,
                    "rationale": "Specific evidence.",
                },
                {
                    "schema_version": "1.0",
                    "dimension": "decision_relevance",
                    "score": 88.0,
                    "rationale": "Decision relevant.",
                },
                {
                    "schema_version": "1.0",
                    "dimension": "recency_timeliness",
                    "score": 86.0,
                    "rationale": "Recent enough.",
                },
                {
                    "schema_version": "1.0",
                    "dimension": "source_authority_originality",
                    "score": 89.0,
                    "rationale": "Authoritative source.",
                },
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="scored.pdf",
        file_id="file_scored",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Report quality" in html
    assert ">87<" in html
    assert "High source value" in html
    assert 'data-dimension="market_insight_depth"' in html
    assert 'data-dimension="source_authority_originality"' in html
    assert 'href="../cache/scored.pdf" download' in html


def test_render_surfaces_explicit_abstain_notices(tmp_path):
    data = {
        "title": "Abstained Report",
        "tldr": "",
        "insights": ["", "", "", "", ""],
        "quote": {"text": "", "author": ""},
        "commentary": "",
        "publisher": "Publisher",
        "taxonomy": [],
        "region": "US",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "",
                "executive_summary": "",
                "claim_evidence_map": [],
            },
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "family_status": {
                "summary": {
                    "schema_version": "1.0",
                    "family": "summary",
                    "source": "artifact",
                    "status": "abstained",
                    "confidence_score": 0.4,
                    "policy_action": "regenerate",
                    "reason": "summary_missing_claim_evidence",
                },
                "insights_bundle": {
                    "schema_version": "1.0",
                    "family": "insights_bundle",
                    "source": "artifact",
                    "status": "abstained",
                    "confidence_score": 0.35,
                    "policy_action": "regenerate",
                    "reason": "insights_missing_required_count",
                },
                "quotes": {
                    "schema_version": "1.0",
                    "family": "quotes",
                    "source": "artifact",
                    "status": "abstained",
                    "confidence_score": 0.15,
                    "policy_action": "regenerate",
                    "reason": "quotes_missing",
                },
                "expert_comment": {
                    "schema_version": "1.0",
                    "family": "expert_comment",
                    "source": "artifact",
                    "status": "abstained",
                    "confidence_score": 0.2,
                    "policy_action": "abstain",
                    "reason": "generated_text_missing",
                },
                "linkedin_post": {
                    "schema_version": "1.0",
                    "family": "linkedin_post",
                    "source": "artifact",
                    "status": "abstained",
                    "confidence_score": 0.2,
                    "policy_action": "abstain",
                    "reason": "generated_text_missing",
                },
            },
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="abstained.pdf",
        file_id="file_abstained",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "TLDR omitted because evidence support was too weak" in html
    assert "Key findings omitted because evidence support was too weak" in html
    assert "Key quotes omitted because evidence support was too weak" in html
    assert "Expert comment omitted because evidence support was too weak" in html
    assert "LinkedIn post omitted because evidence support was too weak" in html
    assert 'id="expert"' in html


def test_render_surfaces_report_identity_line_and_source_note(tmp_path):
    data = {
        "title": "Retail trends 2026",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Capgemini",
        "report_identity_author": "Mark Ruston",
        "taxonomy": ["retail"],
        "region": "Global",
        "time_period": "2026",
        "contents_page_number": 0,
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="identity.pdf",
        file_id="file_identity",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Title: Retail trends 2026" in html
    assert "Publisher: Capgemini" in html
    assert "Year: 2026" in html
    assert "Author: Mark Ruston" in html
    assert "Source URL was not available in the extracted report metadata." in html


def test_render_relabels_unknown_quote_speakers_and_shows_citation_micro_lines(
    tmp_path,
):
    data = {
        "title": "Unknown speaker report",
        "tldr": "TLDR",
        "insights": ["legacy insight"] * 5,
        "quote": {"text": "Legacy quote", "author": "Unknown"},
        "commentary": "Commentary",
        "publisher": "Artlist",
        "taxonomy": [],
        "region": "US",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Artifact TLDR",
                "executive_summary": "Artifact executive summary",
                "claim_evidence_map": [
                    {
                        "claim": "Claim 1",
                        "evidence_id": "f1",
                        "evidence": "Evidence 1",
                        "pages": [7],
                        "evidence_spans": [
                            {
                                "evidence_id": "f1",
                                "source_pack": "findings",
                                "page": 7,
                            }
                        ],
                    }
                ],
            },
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Artifact insight 1",
                    "evidence_id": "f1",
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings", "page": 7}
                    ],
                    "metric": {},
                }
            ],
            "quotes_final": [
                {
                    "text": "Artifact quote",
                    "speaker": "Unknown",
                    "citation": "",
                    "page": 7,
                    "evidence_id": "q1",
                    "evidence_spans": [
                        {
                            "evidence_id": "q1",
                            "source_pack": "quote_candidates",
                            "page": 7,
                        }
                    ],
                }
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="unknown.pdf",
        file_id="file_unknown",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Artlist expert team" in html
    assert "Unknown speaker report, page 7" in html
    assert "q1 · report page" not in html


def test_render_surfaces_editorial_details_from_evidence_packs(tmp_path):
    data = {
        "title": "Editorial Report",
        "tldr": "Concise lead.",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "region": "Global",
        "time_period": "2026 (fieldwork Oct 2025)",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Concise lead.",
                "executive_summary": "Longer summary.",
            },
            "toc_entries": [
                {
                    "display_title": "Demand outlook",
                    "section_title": "Demand outlook",
                    "summary": "Demand shifts toward APAC.",
                    "pages": [4, 5],
                    "order": 1,
                }
            ],
        },
        "evidence_packs": {
            "doc_map": {
                "title": "Editorial Report",
                "publisher": "Publisher",
                "methodology": "Survey fielded in October 2025 across 12 markets.",
                "contributors": [
                    {
                        "name": "Alex Analyst",
                        "role": "Research lead",
                        "email": "alex@example.com",
                    }
                ],
            },
            "methods": {
                "methods": [
                    {
                        "name": "Market survey",
                        "description": "Survey fielded in October 2025 across 12 markets.",
                    }
                ]
            },
            "findings": {
                "findings": [
                    {"statement": "Demand is rebounding in APAC first."},
                ]
            },
            "limitations": {
                "limitations": [
                    {"message": "Sample is weighted toward enterprise respondents."},
                ]
            },
            "scope": {
                "scope": {
                    "jurisdictions": ["US", "UK"],
                    "sources": [{"title": "Editorial Report"}],
                    "contentTypes": ["application/pdf"],
                    "samplingRate": "100%",
                    "retentionDays": 365,
                }
            },
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="editorial.pdf",
        file_id="file_editorial",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Read the source and check provenance" in html
    assert "Methodology" in html
    assert "Survey fielded in October 2025 across 12 markets." in html
    assert "Coverage" in html
    assert "Jurisdictions: US, UK" in html
    assert "Findings" in html
    assert "Demand is rebounding in APAC first." in html
    assert "Limitations" in html
    assert "Sample is weighted toward enterprise respondents." in html
    assert "Contacts" in html
    assert "Alex Analyst — Research lead — alex@example.com" in html
    assert "Ordered chapters" in html
    assert "1. Demand outlook" in html
    assert "Pages: 4, 5" in html
    assert "Year: 2026" in html
    assert "2026" in html
    assert "Fieldwork: fieldwork Oct 2025" in html
    assert "fieldwork Oct 2025" in html


def test_render_hides_figure_sections_when_disabled(tmp_path):
    data = {
        "title": "No Figures Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Q", "author": "A"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 4,
        "_contents_image": "report/contents.png",
        "_figure_top": "report/slices/top.png",
        "_figure_gallery": [
            "report/slices/top.png",
            "report/slices/extra1.png",
            "report/slices/extra2.png",
        ],
        "_figure_section_enabled": False,
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="nofig.pdf",
        file_id="file_nofig",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert 'id="section-figures"' not in html
    assert 'id="section-contents-preview"' not in html


def test_render_uses_per_asset_figure_captions(tmp_path):
    data = {
        "title": "Figure Caption Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_top": "report/slices/primary.png",
        "_figure_gallery": [
            "report/slices/primary.png",
            "report/slices/secondary.png",
        ],
        "_figure_assets": [
            {
                "schema_version": "1.0",
                "image_path": "report/slices/primary.png",
                "page": 2,
                "candidate_id": "chart-1",
                "kind": "chart",
                "is_primary": True,
                "detected_caption": "Detected primary caption",
                "preview_text": "Primary preview",
                "generated_caption": "Primary generated caption",
                "display_caption": "Primary generated caption",
                "caption_source": "generated",
            },
            {
                "schema_version": "1.0",
                "image_path": "report/slices/secondary.png",
                "page": 3,
                "candidate_id": "table-2",
                "kind": "table",
                "is_primary": False,
                "detected_caption": "Detected secondary caption",
                "preview_text": "Secondary preview",
                "generated_caption": "",
                "display_caption": "Detected secondary caption",
                "caption_source": "detected",
            },
        ],
        "_figure_section_enabled": True,
        "figure": {"title": "Legacy caption", "evidence": "Legacy evidence"},
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="figures.pdf",
        file_id="file_figures",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Primary generated caption" in html
    assert "Detected secondary caption" in html
    assert (
        '<figcaption class="carousel-caption">Additional figure 2</figcaption>'
        not in html
    )


def test_render_keeps_legacy_figure_captions_without_figure_assets(tmp_path):
    data = {
        "title": "Legacy Figure Caption Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_top": "report/slices/primary.png",
        "_figure_gallery": [
            "report/slices/primary.png",
            "report/slices/secondary.png",
        ],
        "_figure_section_enabled": True,
        "figure": {"title": "Legacy figure caption", "evidence": "Legacy evidence"},
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="legacy-figures.pdf",
        file_id="file_legacy_figures",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert 'id="candidates"' not in html
    assert "Legacy figure caption" not in html


def test_render_formats_slug_chips_with_acronyms(tmp_path):
    data = {
        "title": "Chip Format Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "categories_display": ["ai-in-retail", "private_label"],
        "taxonomy": ["fmcg", "consumer_trends", "roi"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "artifacts": {"toc_topics": ["ai", "consumer_trends"]},
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="chips.pdf",
        file_id="file_chip",
        out_dir=str(tmp_path),
        preview_png=None,
        tag_acronyms=["AI", "FMCG", "ROI"],
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "AI in Retail" in html
    assert "Private Label" in html
    assert "FMCG" in html
    assert "Consumer Trends" in html
    assert "ROI" in html
    assert "ai-in-retail" not in html
    assert "private_label" not in html


def test_render_adds_responsive_srcset_when_variant_exists(tmp_path):
    assets_dir = tmp_path / "report" / "slices"
    assets_dir.mkdir(parents=True, exist_ok=True)
    base_path = assets_dir / "primary.png"
    variant_path = assets_dir / "primary@2x.png"
    Image.new("RGB", (800, 450), color="navy").save(base_path)
    Image.new("RGB", (1600, 900), color="navy").save(variant_path)

    data = {
        "title": "Responsive Figure Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_assets": [
            {
                "schema_version": "1.0",
                "image_path": "report/slices/primary.png",
                "page": 2,
                "candidate_id": "chart-1",
                "kind": "chart",
                "is_primary": True,
                "display_caption": "Primary generated caption",
            }
        ],
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="responsive.pdf",
        file_id="file_responsive",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert (
        'srcset="report/slices/primary.png 1x, report/slices/primary@2x.png 2x"' in html
    )
    assert 'sizes="(max-width: 800px) 100vw, 980px"' in html
    assert 'width="800"' in html
    assert 'height="450"' in html
    assert 'loading="lazy"' in html


def test_render_is_deterministic_across_calls(tmp_path):
    data = {
        "title": "Deterministic Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["roi"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="deterministic.pdf",
        file_id="file_deterministic",
        out_dir=str(tmp_path),
        preview_png=None,
        tag_acronyms=["ROI"],
    )

    first = render_report(req, _ctx())
    second = render_report(req, _ctx())

    first_html = Path(first.html_path).read_text(encoding="utf-8")
    second_html = Path(second.html_path).read_text(encoding="utf-8")
    assert first.html_path == second.html_path
    assert first_html == second_html


def test_render_creates_missing_nested_output_directory(tmp_path):
    out_dir = tmp_path / "missing" / "nested"
    req = RenderRequest(
        schema_version="1.0",
        data={
            "title": "Nested Output Report",
            "tldr": "TLDR",
            "insights": [
                "Insight A",
                "Insight B",
                "Insight C",
                "Insight D",
                "Insight E",
            ],
            "quote": {"text": "Quote", "author": "Author"},
            "commentary": "Commentary",
            "publisher": "Publisher",
            "taxonomy": ["tag"],
            "region": "US",
            "time_period": "2024",
            "contents_page_number": 0,
        },
        doc_name="nested.pdf",
        file_id="file_nested",
        out_dir=str(out_dir),
        preview_png=None,
    )

    response = render_report(req, _ctx())

    assert out_dir.exists()
    assert Path(response.html_path).exists()


def test_render_overwrites_existing_html_atomically(tmp_path):
    first = RenderRequest(
        schema_version="1.0",
        data={
            "title": "First Title",
            "tldr": "TLDR",
            "insights": [
                "Insight A",
                "Insight B",
                "Insight C",
                "Insight D",
                "Insight E",
            ],
            "quote": {"text": "Quote", "author": "Author"},
            "commentary": "Commentary",
            "publisher": "Publisher",
            "taxonomy": ["tag"],
            "region": "US",
            "time_period": "2024",
            "contents_page_number": 0,
        },
        doc_name="overwrite.pdf",
        file_id="file_overwrite",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    second = RenderRequest(
        schema_version="1.0",
        data={
            "title": "Second Title",
            "tldr": "TLDR",
            "insights": [
                "Insight A",
                "Insight B",
                "Insight C",
                "Insight D",
                "Insight E",
            ],
            "quote": {"text": "Quote", "author": "Author"},
            "commentary": "Commentary",
            "publisher": "Publisher",
            "taxonomy": ["tag"],
            "region": "US",
            "time_period": "2024",
            "contents_page_number": 0,
        },
        doc_name="overwrite.pdf",
        file_id="file_overwrite",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    first_response = render_report(first, _ctx())
    second_response = render_report(second, _ctx())

    html = Path(second_response.html_path).read_text(encoding="utf-8")
    assert first_response.html_path == second_response.html_path
    assert "Second Title" in html
    assert "First Title" not in html
