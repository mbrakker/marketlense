from pathlib import Path

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


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
                "claim_evidence_map": [{"claim": "Claim 1", "evidence": "Evidence 1"}],
            },
            "insights_final": [
                {"id": "i1", "text": "Artifact insight 1", "metric": {"value": "10", "unit": "%", "timeframe": "2024"}},
                {"id": "i2", "text": "Artifact insight 2", "metric": {"value": "", "unit": "", "timeframe": ""}},
            ],
            "quotes_final": [{"text": "Artifact quote", "speaker": "Speaker", "citation": "Report", "page": 2}],
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

    assert "Covered topics" in html
    assert "Artifact TLDR" in html
    assert "Artifact executive summary" in html
    assert "Key data insights" in html
    assert "Artifact insight 1" in html
    assert "Key metric:" not in html
    assert "Key quotes" in html
    assert "Artifact quote" in html
    assert "Expert comment (generated)" in html
    assert "LinkedIn post" in html


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
    assert "Key data insights" in html


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
