# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_publish_readiness_gate.py"
)

from ._split_support_test_publish_readiness_gate import *  # noqa: F401,F403


def test_publish_readiness_binds_rendered_html_and_publication_projection() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifact = _evaluate_readiness_for_test(
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


def test_publish_readiness_fails_without_a_report_card_manifest() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifact = _evaluate_readiness_for_test(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
        report_card_manifest_path="",
    )

    rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.report_card_manifest"
    )
    assert rule.status == "fail"
    assert artifact.status == "fail"


def test_current_supported_retained_claim_package_passes_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)

    readiness = _readiness_with_package(package)

    assert readiness.status == "pass"
    assert _retained_grounding_rule(readiness).status == "pass"
    assert (
        readiness.artifact_hashes["retained_claim_validation"]
        == package["package_hash"]
    )


def test_missing_required_retained_claim_package_blocks_readiness() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()

    readiness = _evaluate_readiness_for_test(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
        retained_claim_package=None,
        retained_claim_required=True,
        source_id="source:example",
        source_md5="b" * 32,
    )

    assert readiness.status == "fail"
    assert "package_missing" in _retained_grounding_rule(readiness).detail


def test_unsupported_retained_claim_blocks_readiness_with_separate_count() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html, unsupported=1)

    readiness = _readiness_with_package(package)
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert rule.status == "fail"
    assert "not_publishable" in rule.detail
    assert "unsupported_factual_count=1" in rule.detail
    assert "unresolved_factual_count=0" in rule.detail


def test_unresolved_retained_claim_blocks_readiness_as_incomplete_grounding() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html, unresolved=1)

    readiness = _readiness_with_package(package)
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert rule.status == "fail"
    assert "not_publishable" in rule.detail
    assert "unsupported_factual_count=0" in rule.detail
    assert "unresolved_factual_count=1" in rule.detail


def test_stale_final_artifact_hash_blocks_retained_grounding_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)
    package["lineage"]["final_artifact_hash"] = "f" * 64

    readiness = _readiness_with_package(_seal_claim_package(package))

    assert readiness.status == "fail"
    assert "package_invalid" in _retained_grounding_rule(readiness).detail
    assert "artifact_hash" in _retained_grounding_rule(readiness).detail


def test_stale_evidence_and_source_identity_block_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)
    package["lineage"]["evidence_pack_hash"] = "f" * 64
    package["lineage"]["source_id"] = "source:stale"
    package["lineage"]["source_md5"] = "stale-source-md5"
    package["validation_identity"]["source_id"] = "source:stale"
    package["validation_identity"]["source_md5"] = "stale-source-md5"

    readiness = _readiness_with_package(_seal_claim_package(package))
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert "package_invalid" in rule.detail
    assert "evidence_pack_hash" in rule.detail
    assert "source_id" in rule.detail
    assert "source_md5" in rule.detail


def test_stale_validator_and_configuration_identity_block_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)
    package["lineage"]["claim_validation_validator_version"] = "old-validator"
    package["lineage"]["grounding_validator_version"] = "old-grounding-validator"
    package["lineage"]["configuration_hash"] = "config-old"
    package["lineage"]["policy_hash"] = "policy-old"
    package["validation_identity"]["configuration_hash"] = "config-old"

    readiness = _readiness_with_package(_seal_claim_package(package))
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert "package_invalid" in rule.detail
    assert "claim_validation_validator_version" in rule.detail
    assert "grounding_validator_version" in rule.detail
    assert "configuration_hash" in rule.detail
    assert "policy_hash" in rule.detail


def test_missing_semantic_grounding_identity_blocks_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html, semantic=True)
    package["results"][0]["semantic_identity"] = None

    readiness = _readiness_with_package(_seal_claim_package(package))
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert "semantic_execution_identity_missing" in rule.detail


@pytest.mark.parametrize(
    ("configuration_hash", "policy_hash", "problem"),
    [
        ("", "policy-current", "current_configuration_identity_missing"),
        ("config-current", "", "current_policy_identity_missing"),
    ],
)
def test_missing_readiness_execution_identity_blocks_retained_grounding(
    configuration_hash: str, policy_hash: str, problem: str
) -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)

    readiness = _readiness_with_package(
        package,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )

    assert readiness.status == "fail"
    assert "package_invalid" in _retained_grounding_rule(readiness).detail
    assert problem in _retained_grounding_rule(readiness).detail


def test_candidate_only_package_cannot_satisfy_final_readiness() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    candidate = _retained_claim_package(artifacts, evidence_packs, html)
    candidate.pop("lineage")

    readiness = _readiness_with_package(_seal_claim_package(candidate))
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert rule.status == "fail"
    assert "package_invalid" in rule.detail
    assert "final_lineage_missing" in rule.detail


def test_final_package_from_another_report_is_rejected() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html)
    package["lineage"]["report_id"] = "report-2"
    package["validation_identity"]["report_id"] = "report-2"

    readiness = _readiness_with_package(_seal_claim_package(package))

    assert readiness.status == "fail"
    assert "package_invalid" in _retained_grounding_rule(readiness).detail
    assert "report_id_stale" in _retained_grounding_rule(readiness).detail


def test_semantically_grounded_package_is_consumed_without_regrounding() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html, semantic=True)

    readiness = _readiness_with_package(package)

    assert readiness.status == "pass"
    assert _retained_grounding_rule(readiness).status == "pass"
    assert package["semantic_execution_identities"] == ["grounding-execution-1"]


def test_invalid_semantic_outcome_type_blocks_readiness_without_crashing() -> None:
    artifacts, evidence_packs, html, _ = _ready_inputs()
    package = _retained_claim_package(artifacts, evidence_packs, html, semantic=True)
    package["results"][0]["semantic_outcome"] = []

    readiness = _readiness_with_package(_seal_claim_package(package))
    rule = _retained_grounding_rule(readiness)

    assert readiness.status == "fail"
    assert "semantic_disposition_mismatch" in rule.detail


def test_publish_readiness_rejects_html_without_build_traceability() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = re.sub(r"<!--.*?-->\s*", "", html, count=1, flags=re.DOTALL)

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

    traceability = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.build_traceability"
    )
    assert readiness.status == "fail"
    assert traceability.status == "fail"


def test_publish_readiness_allows_non_fatal_grounding_interpretation() -> None:
    """Informational grounding feedback must agree with a passing validation report."""
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifact = _evaluate_readiness_for_test(
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
    artifact = _evaluate_readiness_for_test(
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

    artifact = _evaluate_readiness_for_test(
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

    artifact = _evaluate_readiness_for_test(
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

    artifact = _evaluate_readiness_for_test(
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


def test_publish_readiness_matches_sanitized_chart_card_projection() -> None:
    marker = "\ue200filecite\ue202turn0file2\ue202turnfile4\ue201"
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
            "caption": f"Measured revenue growth by market. {marker}",
            "public_takeaway": f"{takeaway} {marker}",
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

    artifact = _evaluate_readiness_for_test(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
    )

    figure_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.figure_linkage"
    )
    identifier_rule = next(
        item
        for item in artifact.rule_results
        if item.rule_id == "publish_readiness.public_identifier_leak"
    )
    assert artifact.status == "pass"
    assert figure_rule.status == "pass"
    assert identifier_rule.status == "pass"


def test_publish_readiness_ignores_absent_scalar_evidence_id_in_claim_ledger() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    artifacts["claim_ledgers"] = [
        {
            "claim_text": "Revenue grew in the measured market.",
            "evidence_id": None,
            "evidence_ids": ["F1"],
        }
    ]

    artifact = _evaluate_readiness_for_test(
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

    fidelity = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.evidence_fidelity"
    )
    assert readiness.status == "fail"
    assert fidelity.status == "fail"
    assert fidelity.surfaces == ["rendered_html:evidence:F2"]


@pytest.mark.parametrize(
    ("source_pack", "expected_status", "expected_rendered_untrusted"),
    [("doc_map", "pass", 0), ("findings", "fail", 1)],
)
def test_publish_readiness_matches_untrusted_evidence_by_source_pack(
    source_pack: str,
    expected_status: str,
    expected_rendered_untrusted: int,
) -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    public_claim = "Revenue grew in the measured market."
    artifacts["insights_final"][0].update(
        {
            "evidence_id": "F2",
            "evidence_spans": [
                {
                    "evidence_id": "F2",
                    "source_pack": source_pack,
                    "page": 20,
                    "text": public_claim,
                }
            ],
        }
    )
    evidence_packs["findings"]["findings"].append(
        {"id": "F2", "snippet": public_claim, "page": 4}
    )
    evidence_packs["doc_map"] = {
        "sections": [{"id": "F2", "text": public_claim, "page": 20}]
    }
    evidence_packs["evidence_fidelity"] = {
        "readiness_status": "blocked",
        "unsupported_factual_count": 1,
        "unresolved_factual_count": 0,
        "results": [
            {
                "candidate": {
                    "claim_id": "evidence:findings:F2",
                    "source_family": "evidence_pack:findings",
                    "factual": True,
                },
                "status": "unsupported",
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
        category_ids=["markets"],
        provenance=provenance,
    )

    fidelity = next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.evidence_fidelity"
    )
    assert fidelity.status == expected_status
    assert f"rendered_untrusted={expected_rendered_untrusted}" in fidelity.detail
    if source_pack == "doc_map":
        assert readiness.status == "pass", [
            (item.rule_id, item.status, item.detail)
            for item in readiness.rule_results
            if item.status != "pass"
        ]
    else:
        assert readiness.status == "fail"
    if expected_status == "fail":
        assert fidelity.surfaces == ["rendered_html:evidence:F2"]


def test_publish_readiness_payload_round_trips_and_rejects_malformed_surfaces() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
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
