# ruff: noqa: F401,F403,F405

from ._shared import *


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
                    "evidence_id": "quote_02",
                    "evidence_spans": [
                        {
                            "evidence_id": "quote_02",
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
    assert "MarketBearing analysis" in html
    assert "Focused on trust, operating model and commercial execution." not in html
    assert "LinkedIn-ready post" in html
    assert 'id="expert"' in html
    assert 'id="overview"' in html
    assert 'class="summary-panel summary-panel-executive"' in html
    assert 'class="claim-strip"' in html
    assert "Sample Report, page 4" in html
    assert "Sample Report, page 2 · Report" in html
    assert "f1 · report page" not in html
    assert "quote_02" not in html
    assert "quote_02 · report page" not in html
    assert 'data-market-lense-publish-entity="true"' not in html
    assert '"entity_type":"report"' not in html
    assert '"canonical_route_intent":"wordpress:ml_report"' not in html


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
                    "summary": (
                        "Demand is strongest in APAC and improving in North America."
                    ),
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
    assert "Source URL: Not available" in html


def test_render_surfaces_report_quality_score_and_verified_source_link(tmp_path):
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
        "source": "https://publisher.example/reports/scored.pdf",
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
    assert 'data-dimension="market-insight-depth"' in html
    assert 'data-dimension="source-authority-originality"' in html
    assert "evidence_specificity" not in html
    assert 'href="https://publisher.example/reports/scored.pdf"' in html
    assert "../cache/scored.pdf" not in html


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
    assert "Edition: 2026" in html
    assert "Author: Mark Ruston" in html
    assert "Source URL: Not available" in html
