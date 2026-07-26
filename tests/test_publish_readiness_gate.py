from __future__ import annotations

from src.contracts.validation import ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness,
    verify_publish_readiness,
)


def _ready_inputs() -> tuple[dict, dict, str, dict]:
    html = """<!doctype html><html><head>
<title>Revenue outlook 2026 | MarketLense</title>
<link rel="canonical" href="https://marketlense.example/reports/revenue-outlook">
<meta property="og:title" content="Revenue outlook 2026">
</head><body><h1>Revenue outlook 2026</h1>
<p>Revenue grew in the measured market.</p>
<section id="source"><a href="https://publisher.example/reports/revenue-outlook">
Open original source</a></section>
<script type="application/ld+json">{"@context":"https://schema.org",
"headline":"Revenue outlook 2026"}</script>
</body></html>"""
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "Revenue grew in the measured market.",
                    "evidence_id": "F1",
                    "evidence": "Revenue grew in the measured market.",
                }
            ]
        },
        "insights_final": [
            {
                "id": "I1",
                "text": "Revenue grew in the measured market.",
                "evidence_id": "F1",
                "evidence": "Revenue grew in the measured market.",
            }
        ],
        "quotes_final": [],
        "chart_insight_cards": [],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "F1",
                    "snippet": "Revenue grew in the measured market.",
                    "page": 1,
                }
            ]
        }
    }
    provenance = {
        "publisher_landing_page_url": "https://publisher.example/reports/revenue-outlook",
        "original_report_url": "",
        "marketlense_article_url": "https://marketlense.example/reports/revenue-outlook",
    }
    return artifacts, evidence_packs, html, provenance


def test_publish_readiness_binds_rendered_html_and_publication_projection() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifact = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    assert artifact.status == "pass"
    assert artifact.artifact_hash
    assert (
        verify_publish_readiness(
            artifact=artifact, report_id="report-1", final_html=html
        ).status
        == "pass"
    )
    assert verify_publish_readiness(
        artifact=artifact,
        report_id="report-1",
        final_html=html.replace("measured market", "unverified market"),
    ).issues == [
        "publish_readiness.final_html_changed",
        "publish_readiness.publication_projection_changed",
    ]


def test_publish_readiness_rejects_public_identifier_and_private_source_leaks() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    leaked_html = html.replace(
        "</head>",
        '<meta name="drive-file-id" content="F1"><meta property="og:url" content="https://drive.google.com/file/d/F1"></head>',
    )
    artifact = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=leaked_html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    failed = {item.rule_id for item in artifact.rule_results if item.status == "fail"}
    assert artifact.status == "fail"
    assert "publish_readiness.public_identifier_leak" in failed


def test_publish_readiness_requires_an_accepted_crop_for_each_rendered_chart_card() -> (
    None
):
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    takeaway = "Revenue growth is concentrated in the measured market."
    artifacts["chart_insight_cards"] = [
        {
            "status": "generated",
            "candidate_id": "chart-1",
            "crop_qa_accepted": True,
            "source_page": 1,
            "evidence_id": "F1",
            "insight_id": "I1",
            "caption": "Measured revenue growth by market.",
            "public_takeaway": takeaway,
        }
    ]
    evidence_packs["visuals"] = {
        "chart_candidates": [
            {
                "candidate_id": "chart-1",
                "crop_qa_accepted": True,
                "source_page": 1,
                "evidence_id": "F1",
            }
        ]
    }
    html = html.replace(
        "</body>",
        (
            '<div class="chart-insight-grid"><article><p>'
            f"{takeaway}</p></article></div></body>"
        ),
    )

    artifact = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    assert artifact.status == "pass"
    figure_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.figure_linkage"
    )
    assert figure_rule.status == "pass"


def test_publish_readiness_ignores_absent_scalar_evidence_id_in_claim_ledger() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["claim_ledgers"] = [
        {
            "claim_text": "Revenue grew in the measured market.",
            "evidence_id": None,
            "evidence_ids": ["F1"],
        }
    ]

    artifact = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    material_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.material_claim_evidence"
    )
    assert material_rule.status == "pass"
