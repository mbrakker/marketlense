from __future__ import annotations

from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness,
    parse_publish_readiness_payload,
    publish_readiness_payload,
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
        "categories": ["markets"],
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


def test_publish_readiness_allows_non_fatal_grounding_interpretation() -> None:
    """Informational grounding feedback must agree with a passing validation report."""
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifact = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    rule_id="grounding",
                    message="Interpretation is not directly established.",
                    severity="info",
                    affected_section="summary",
                )
            ],
        ),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    assert artifact.status == "pass"


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


def test_publish_readiness_allows_public_evidence_quality_language() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = html.replace(
        "<p>Revenue grew in the measured market.</p>",
        (
            "<p>Evidence-linked analysis supports evidence-backed and "
            "evidence-aligned planning.</p>"
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

    identifier_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.public_identifier_leak"
    )
    assert identifier_rule.status == "pass"


def test_publish_readiness_allows_public_source_url_path_segments() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = html.replace(
        "https://publisher.example/reports/revenue-outlook",
        "https://web-assets.publisher.example/a3/f0/report.pdf",
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

    identifier_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.public_identifier_leak"
    )
    assert identifier_rule.status == "pass"


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


def test_publish_readiness_ignores_quarantined_evidence_absent_from_final_html() -> (
    None
):
    """Private audit failures cannot block a public artifact that never uses them."""
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    evidence_packs["evidence_fidelity"] = {
        "readiness_status": "blocked",
        "unsupported_factual_count": 1,
        "unresolved_factual_count": 0,
        "results": [
            {
                "candidate": {
                    "claim_id": "evidence:findings:F2",
                    "factual": True,
                },
                "status": "unsupported",
            }
        ],
    }

    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    fidelity = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.evidence_fidelity"
    )
    assert readiness.status == "pass"
    assert fidelity.status == "pass"
    assert fidelity.detail == "audit_untrusted=1; rendered_untrusted=0"


def test_publish_readiness_blocks_quarantined_evidence_rendered_in_final_html() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    quarantined_claim = "Unverified revenue is forecast to double."
    artifacts["insights_final"].append(
        {
            "id": "I2",
            "text": quarantined_claim,
            "evidence_id": "F2",
            "evidence": quarantined_claim,
        }
    )
    evidence_packs["findings"]["findings"].append(
        {"id": "F2", "snippet": quarantined_claim, "page": 2}
    )
    evidence_packs["evidence_fidelity"] = {
        "readiness_status": "blocked",
        "unsupported_factual_count": 1,
        "unresolved_factual_count": 0,
        "results": [
            {
                "candidate": {
                    "claim_id": "evidence:findings:F2",
                    "factual": True,
                },
                "status": "unsupported",
            }
        ],
    }
    html = html.replace("</body>", f"<p>{quarantined_claim}</p></body>")

    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    fidelity = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.evidence_fidelity"
    )
    assert readiness.status == "fail"
    assert fidelity.status == "fail"
    assert fidelity.surfaces == ["rendered_html:evidence:F2"]


def test_publish_readiness_payload_round_trips_and_rejects_malformed_surfaces() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    assert (
        parse_publish_readiness_payload(publish_readiness_payload(readiness))
        == readiness
    )
    for surfaces in (None, "categories", {"category": True}, ["categories", 1]):
        malformed = publish_readiness_payload(readiness)
        malformed["rule_results"][0]["surfaces"] = surfaces
        parsed = parse_publish_readiness_payload(malformed)
        verification = verify_publish_readiness(
            artifact=parsed, report_id="report-1", final_html=html
        )
        assert "publish_readiness.schema_unsupported" in verification.issues


def test_publish_readiness_category_consistency_fails_for_missing_side() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    cases = [([], ["markets"]), (["markets"], []), ([], []), (["other"], ["markets"])]
    for retained, canonical in cases:
        artifacts["categories"] = retained
        readiness = evaluate_publish_readiness(
            report_id="report-1",
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            validation_report=ValidationReport(schema_version="1.1", status="pass"),
            final_html=html,
            final_html_path="",
            category_ids=canonical,
            provenance=provenance,
        )
        rule = next(
            item
            for item in readiness.rule_results
            if item.rule_id == "publish_readiness.category_consistency"
        )
        assert rule.status == "fail"


def test_publish_readiness_accepts_an_explicit_uncategorized_abstention() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["categories"] = []
    evidence_packs["context_category_fit"] = {
        "selected_category_ids": [],
        "category_fits": [
            {
                "category_id": "payments",
                "decision": "reject",
                "semantic_rule_status": "rejected",
                "remediation_signal": "topic_semantics_unresolved_abstained",
            }
        ],
    }

    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=[],
        provenance=provenance,
    )

    category_rule = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.category_consistency"
    )
    assert category_rule.status == "pass"


def test_publish_readiness_rejects_malformed_plural_evidence_references() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    for invalid in (1, {"id": "F1"}, "F1", ["F1", None], [["F1"]]):
        artifacts["claim_ledgers"] = [
            {"claim_text": "Revenue grew.", "evidence_ids": invalid}
        ]
        readiness = evaluate_publish_readiness(
            report_id="report-1",
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            validation_report=ValidationReport(schema_version="1.1", status="pass"),
            final_html=html,
            final_html_path="",
            category_ids=["markets"],
            provenance=provenance,
        )
        rule = next(
            item
            for item in readiness.rule_results
            if item.rule_id == "publish_readiness.material_claim_evidence"
        )
        assert rule.status == "fail"
        assert "invalid evidence reference shape" in rule.detail


def test_publish_readiness_hard_blocks_unresolved_public_source_fidelity() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["insights_final"][0].update(
        {
            "id": "activate-2021-spend",
            "text": "23% of users account for 77% of ecommerce spend.",
            "evidence": "22% of users account for 77% of ecommerce spend.",
            "evidence_id": "activate-2021-spend-evidence",
        }
    )

    readiness = evaluate_publish_readiness(
        report_id="activate-2021",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    fidelity = next(
        result
        for result in readiness.rule_results
        if result.rule_id == "publish_readiness.source_fidelity"
    )
    assert readiness.status == "fail"
    assert fidelity.status == "fail"
    assert "insight:activate-2021-spend:text" in fidelity.surfaces


def test_publish_readiness_blocks_generic_title_and_wrong_publisher_identity() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = html.replace(
        "<h1>Revenue outlook 2026</h1>",
        "<h1 id='report-title'>PowerPoint Presentation</h1>",
    )
    html = html.replace(
        "</body>",
        (
            "<ul class='meta-row'><li class='meta-pill'>Publisher: Wrong "
            "Publisher</li></ul></body>"
        ),
    )

    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
        metadata_evidence={
            "title": "Activate Technology & Media Outlook 2025: Social Video",
            "publisher": "Activate Consulting",
        },
    )

    fidelity = next(
        result
        for result in readiness.rule_results
        if result.rule_id == "publish_readiness.source_fidelity"
    )
    assert readiness.status == "fail"
    assert fidelity.status == "fail"
    assert fidelity.surfaces == [
        "rendered_html:metadata:publisher",
        "rendered_html:metadata:title",
    ]
    assert "incorrect_publisher_author_attribution" in fidelity.detail
    assert "incorrect_report_identity" in fidelity.detail
