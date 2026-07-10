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
                        "Use margin-safe pricing scenarios in the next planning "
                        "cycle."
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
    assert (
        'name="editorial-contract-version" content="public-report-editorial-v1"'
        in html
    )
    assert "Pricing discipline is the core decision." in html
    assert "Priority moves" in html
    assert "Use margin-safe pricing scenarios in the next planning cycle." in html
    assert "Watchouts" in html
    assert "Blended growth metrics can hide value-segment softness." in html
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
