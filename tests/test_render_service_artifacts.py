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
                {
                    "id": "i1",
                    "text": "Artifact insight 1",
                    "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
                },
                {
                    "id": "i2",
                    "text": "Artifact insight 2",
                    "metric": {"value": "", "unit": "", "timeframe": ""},
                },
            ],
            "quotes_final": [
                {
                    "text": "Artifact quote",
                    "speaker": "Speaker",
                    "citation": "Report",
                    "page": 2,
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
    assert 'id="section-appendix"' in html
    assert 'id="section-expert"' not in html
    assert 'id="section-linkedin"' not in html
    assert '<p class="summary-copy" style="max-width:none">Artifact TLDR</p>' in html
    assert (
        '<p class="summary-copy" style="max-width:none">Artifact executive summary</p>'
        in html
    )
    assert '<ul class="claim-list" style="max-width:none">' in html
    assert 'style="max-width:none"' in html


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
    assert "Source URL was not available in the extracted report metadata." in html


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

    assert (
        '<p class="report-identity">Title: Retail trends 2026 · Publisher: Capgemini · Year: 2026 · Author: Mark Ruston</p>'
        in html
    )
    assert "Publisher:</span> Capgemini" in html
    assert "Source URL was not available in the extracted report metadata." in html


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

    assert "Legacy figure caption" in html
    assert "Additional figure 2" in html


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
            "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
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
