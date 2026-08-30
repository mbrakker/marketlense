from pathlib import Path

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services.render_service import render_report


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_render_surfaces_public_advisory_metric_spine_and_claim_support(tmp_path):
    data = {
        "title": "Advisory Report",
        "tldr": "TLDR",
        "insights": ["Legacy insight"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["strategy"],
        "region": "Global",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Advisory TLDR",
                "executive_summary": (
                    "The report frames pricing discipline as the near-term "
                    "executive choice."
                ),
                "claim_evidence_map": [
                    {
                        "claim": "Pricing discipline is the highest-leverage move.",
                        "evidence_id": "f1",
                        "pages": [6],
                    }
                ],
            },
            "insights_final": [
                {
                    "id": "i1",
                    "text": (
                        "Leaders should separate premium and value-led demand pools."
                    ),
                    "so_what": (
                        "The same market signal needs different margin playbooks."
                    ),
                    "now_what": (
                        "Segment the next planning cycle by demand pool before "
                        "setting price corridors."
                    ),
                    "evidence_id": "f1",
                    "pages": [6],
                }
            ],
            "metric_spine": [
                {
                    "metric_id": "m1",
                    "label": "Premium demand growth",
                    "value": "18",
                    "unit": "%",
                    "segment": "premium buyers",
                    "timeframe": "2026",
                    "evidence_id": "metric-internal-1",
                    "confidence": "source_backed",
                }
            ],
            "executive_advisory": {
                "schema_version": "1.0",
                "decision_brief": {
                    "status": "generated",
                    "strategic_context": "Pricing discipline is the core decision.",
                    "decision_implications": [
                        "Prioritize margin-safe growth rather than blanket discounting."
                    ],
                    "priority_moves": [
                        "Set separate price corridors for premium and value segments."
                    ],
                    "watchouts": [
                        (
                            "Do not treat blended category growth as a single "
                            "demand signal."
                        )
                    ],
                    "evidence_links": ["f1", "metric-internal-1"],
                    "confidence_note": "Metric spine available",
                },
                "recommendations": {
                    "status": "generated",
                    "items": [
                        {
                            "id": "r1",
                            "recommendation": (
                                "Use margin-safe pricing scenarios in the next "
                                "planning cycle."
                            ),
                            "evidence_id": "f1",
                        }
                    ],
                },
                "risks": {
                    "status": "generated",
                    "items": [
                        {
                            "id": "risk1",
                            "risk": (
                                "Blended growth metrics can hide value-segment "
                                "softness."
                            ),
                            "evidence_id": "metric-internal-1",
                        }
                    ],
                },
            },
            "claim_ledgers": [
                {
                    "schema_version": "1.0",
                    "canonical_claim_id": (
                        "report:executive_advisory.recommendations:r1"
                    ),
                    "claim_text": (
                        "Use margin-safe pricing scenarios in the next planning cycle."
                    ),
                    "artifact_section": "executive_advisory.recommendations",
                    "evidence_ids": ["f1"],
                    "support_type": "explicit_recommendation",
                    "confidence": "source_backed",
                    "risk": "medium",
                    "evidence_span_count": 1,
                }
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="advisory.pdf",
        file_id="file_advisory",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Decision brief" in html
    assert 'name="editorial-contract-version"' not in html
    assert 'name="drive-file-id"' not in html
    assert "Pricing discipline is the core decision." in html
    assert "Priority moves" in html
    assert "Use margin-safe pricing scenarios in the next planning cycle." in html
    assert "Watchouts" in html
    assert "Do not treat blended category growth as a single demand signal." in html
    assert "Blended growth metrics can hide value-segment softness." not in html
    assert "Metric spine" in html
    assert "Premium demand growth" in html
    assert "18%" in html
    assert "So what" in html
    assert "The same market signal needs different margin playbooks." in html
    assert "Now what" in html
    assert "Segment the next planning cycle by demand pool" in html
    assert "Claim support" in html
    assert "Explicit recommendation" in html
    assert "Source-backed" in html
    assert "canonical_claim_id" not in html
    assert "report:executive_advisory" not in html
    assert "metric-internal-1" not in html


def test_render_omits_empty_decision_brief_sections(tmp_path):
    data = {
        "title": "Sparse Advisory Report",
        "tldr": "TLDR",
        "insights": ["Legacy insight"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["strategy"],
        "region": "Global",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {"tldr": "Advisory TLDR"},
            "executive_advisory": {
                "decision_brief": {
                    "status": "generated",
                    "strategic_context": "",
                    "decision_implications": [],
                    "priority_moves": [],
                    "watchouts": [],
                    "confidence_note": "Evidence-linked insights available",
                },
                "recommendations": {
                    "status": "generated",
                    "items": [
                        {
                            "id": "r1",
                            "recommendation": "Unsupported recommendation.",
                        }
                    ],
                },
                "risks": {
                    "status": "generated",
                    "items": [{"id": "risk1", "risk": "Unsupported risk."}],
                },
            },
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="sparse-advisory.pdf",
        file_id="file_sparse_advisory",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Decision brief" in html
    assert "Priority moves" not in html
    assert "Watchouts" not in html
    assert "Unsupported recommendation." not in html
    assert "Unsupported risk." not in html


def test_render_surfaces_topics_key_figures_and_chart_insight_cards(tmp_path):
    data = {
        "title": "Evidence Cards Report",
        "tldr": "Decision makers should inspect quantified demand shifts.",
        "insights": ["Legacy insight"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["demand"],
        "region": "Global",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Demand shifts are measurable.",
                "executive_summary": "Demand shifts are measurable.",
            },
            "topics_covered": [
                {
                    "topic_id": "t1",
                    "topic": "Demand outlook",
                    "why_it_matters": "It frames where the report expects pressure.",
                    "subtopics": ["Premium demand", "Value demand"],
                    "source_pages": [2, 3],
                }
            ],
            "key_figures": [
                {
                    "figure": "42 percent",
                    "label": "premium buyers trading down",
                    "context": "Demand pressure in 2026",
                    "source_page": 4,
                    "confidence": "source_backed",
                }
            ],
            "chart_insight_cards": [
                {
                    "card_id": "chart-1",
                    "status": "generated",
                    "candidate_id": "candidate-1",
                    "crop_qa_accepted": True,
                    "evidence_id": "f1",
                    "insight_id": "i1",
                    "caption": "Premium demand weakens in the measured segment.",
                    "public_takeaway": "The chart points to sharper pressure among premium buyers.",
                    "title": "Premium demand weakens",
                    "insight": "The chart points to sharper pressure among premium buyers.",
                    "so_what": "Planning cannot rely on blended category averages.",
                    "avoid_reason_if_weak": "",
                    "source_page": 4,
                },
                {
                    "card_id": "chart-2",
                    "status": "weak_evidence",
                    "title": "Weak visual link",
                    "insight": "Do not publish as a claim.",
                    "avoid_reason_if_weak": "Chart link is too weak for a public implication.",
                    "source_page": 9,
                },
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="cards.pdf",
        file_id="file_cards",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert 'id="report-intelligence"' in html
    assert "Topics covered" in html
    assert "Demand outlook" in html
    assert "Premium demand" in html
    assert "Key figures" in html
    assert "42 percent" in html
    assert "premium buyers trading down" in html
    assert "Chart insight cards" in html
    assert "Premium demand weakens" in html
    assert "Planning cannot rely on blended category averages." in html
    assert "Chart link is too weak for a public implication." not in html
    assert "Do not publish as a claim." not in html


def test_render_omits_malformed_retained_key_figures_and_normalizes_currency_unit(
    tmp_path,
):
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "IAB key figure regression",
                "tldr": "The source report retains supporting metric evidence.",
                "publisher": "IAB",
                "artifacts": {
                    "key_figures": [
                        {
                            "figure": "19.2%; $62.1; $102.9; 39.8% growth; $ billion; $ billion; share",
                            "unit": "$ billion; $ billion; share",
                            "label": "Composite metric must not be public.",
                        },
                        {
                            "figure": "258.6 $ billion",
                            "unit": "$ billion",
                            "label": "U.S. internet advertising revenue",
                        },
                    ],
                    "metric_spine": [
                        {
                            "value": "19.2%; $62.1; $102.9; 39.8% growth",
                            "unit": "$ billion; $ billion; share",
                            "label": "Composite advisory metric must not be public.",
                        },
                        {
                            "value": "258.6",
                            "unit": "$ billion",
                            "label": "Advisory revenue metric",
                        },
                    ],
                },
            },
            doc_name="iab-key-figure-regression.pdf",
            file_id="iab-key-figure-regression",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "19.2%; $62.1" not in html
    assert "Composite metric must not be public." not in html
    assert "Composite advisory metric must not be public." not in html
    assert "258.6 $ billion" not in html
    assert "$258.6 billion" in html


def test_render_removes_mechanical_scaffolding_from_commentary(tmp_path):
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Commentary Safety Report",
                "tldr": "The report has a supported finding.",
                "insights": ["The report has a supported finding."],
                "quote": {"text": "Quote", "author": "Author"},
                "commentary": "Answer: The supported finding informs the next decision.",
                "publisher": "Publisher",
                "taxonomy": ["strategy"],
                "region": "Global",
                "time_period": "2026",
            },
            doc_name="commentary-safety.pdf",
            file_id="file_commentary_safety",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "Answer:" not in html
    assert "The supported finding informs the next decision." in html
