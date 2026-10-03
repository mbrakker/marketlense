# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_publish_readiness_gate.py"
)

from ._split_support_test_publish_readiness_gate import *  # noqa: F401,F403


def test_publish_readiness_category_consistency_fails_for_missing_side() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    cases = [([], ["markets"]), (["markets"], []), ([], []), (["other"], ["markets"])]
    for retained, canonical in cases:
        artifacts["categories"] = retained
        readiness = _evaluate_readiness_for_test(
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
                "why_not_fit": "The report does not support this category.",
            }
        ],
    }

    readiness = _evaluate_readiness_for_test(
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


def test_publish_readiness_accepts_all_rejected_category_abstention() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["categories"] = []
    evidence_packs["context_category_fit"] = {
        "selected_category_ids": [],
        "category_fits": [
            {
                "category_id": "payments",
                "decision": "reject",
                "semantic_rule_status": "rejected",
                "remediation_signal": "topic_semantics_all_rejected_abstained",
                "why_not_fit": "No retained evidence supports this category.",
            }
        ],
    }

    readiness = _evaluate_readiness_for_test(
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


def test_publish_readiness_rejects_uncategorized_fit_without_explanation() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["categories"] = []
    evidence_packs["context_category_fit"] = {
        "selected_category_ids": [],
        "category_fits": [
            {
                "category_id": "payments",
                "decision": "reject",
                "semantic_rule_status": "rejected",
                "remediation_signal": "topic_semantics_all_rejected_abstained",
                "why_not_fit": "",
            }
        ],
    }

    readiness = _evaluate_readiness_for_test(
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
    assert category_rule.status == "fail"


def test_publish_readiness_rejects_malformed_plural_evidence_references() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    for invalid in (1, {"id": "F1"}, "F1", ["F1", None], [["F1"]]):
        artifacts["claim_ledgers"] = [
            {"claim_text": "Revenue grew.", "evidence_ids": invalid}
        ]
        readiness = _evaluate_readiness_for_test(
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

    readiness = _evaluate_readiness_for_test(
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

    readiness = _evaluate_readiness_for_test(
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


def test_mintel_rendered_heading_passes_all_three_original_readiness_rules() -> None:
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures/public_editorial/mintel_2026_readiness_ellipsis.json"
        ).read_text(encoding="utf-8")
    )
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = html.replace("</body>", fixture["rendered_html"] + "</body>")

    readiness = _evaluate_readiness_for_test(
        report_id=fixture["report_id"],
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    assert readiness.status == "pass"
    assert all(
        result.status == "pass"
        for result in readiness.rule_results
        if result.rule_id in fixture["before_readiness_rule_ids"]
    )


def test_rendered_scaffolding_projects_canonical_html_issues() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    for bad_html in ("<p>Demand rose...</p>", "<p>Observation: demand rose.</p>"):
        readiness = _evaluate_readiness_for_test(
            report_id="report-1",
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            validation_report=ValidationReport(schema_version="1.1", status="pass"),
            final_html=html.replace("</body>", bad_html + "</body>"),
            final_html_path="",
            category_ids=["markets"],
            provenance=provenance,
        )
        failed = {
            result.rule_id
            for result in readiness.rule_results
            if result.status == "fail"
        }
        assert "publish_readiness.rendered_scaffolding" in failed
        assert "publish_readiness.editorial_quality" in failed
        assert ("publish_readiness.source_fidelity" in failed) == ("..." in bad_html)
