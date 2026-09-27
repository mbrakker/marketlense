from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness,
    parse_publish_readiness_payload,
    publish_readiness_payload,
    verify_publish_readiness,
)
from src.utils.cache_utils import sha256_json
from src.utils.publication_projection import publication_projection_hash


def _ready_inputs() -> tuple[dict, dict, str, dict]:
    html = """<!doctype html>
<!--
marketbearing-build:
  git_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  generation_run_id: generation-run-1
  validation_run_id: validation-run-1
  source_id: source:example
  source_md5: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  artifact_hash: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
  generation_profile: safe_default
  generated_at_utc: 2026-09-09T12:00:00+00:00
-->
<html><head>
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


def _seal_claim_package(package: dict) -> dict:
    sealed = deepcopy(package)
    sealed["package_hash"] = ""
    sealed["package_hash"] = sha256_json(sealed)
    return sealed


def _retained_claim_package(
    artifacts: dict,
    evidence_packs: dict,
    html: str,
    *,
    source_id: str = "source:example",
    source_md5: str = "b" * 32,
    configuration_hash: str = "config-current",
    policy_hash: str = "policy-current",
    unsupported: int = 0,
    unresolved: int = 0,
    semantic: bool = False,
) -> dict:
    statuses = ["supported"] + ["unsupported"] * unsupported + [
        "unresolved"
    ] * unresolved
    results = []
    for index, status in enumerate(statuses, start=1):
        evidence_references = (
            [
                {
                    "schema_version": "1.3",
                    "evidence_id": "F1",
                    "source_pack": "findings",
                    "page": 1,
                    "text_hash": sha256_json(
                        "Revenue grew in the measured market."
                    ),
                }
            ]
            if semantic and index == 1
            else []
        )
        result = {
            "schema_version": "1.3",
            "candidate": {
                "schema_version": "1.3",
                "claim_id": f"claim:{index}",
                "source_family": "summary",
                "text": f"Retained factual claim {index}.",
                "text_hash": sha256_json(f"Retained factual claim {index}."),
                "kind": "descriptive",
                "factual": True,
                "evidence_references": evidence_references,
                "affected_section": "summary",
                "entity_id": "",
            },
            "checks": [],
            "status": status,
            "deterministic_status": (
                "unresolved"
                if semantic and index == 1
                else "supported"
                if status == "supported"
                else status
            ),
            "reasons": [],
            "protected_facts": None,
            "semantic_outcome": "entailed" if semantic and index == 1 else None,
            "semantic_reason": (
                "entailed from linked evidence" if semantic and index == 1 else ""
            ),
            "semantic_protected_facts": None,
            "semantic_identity": (
                {
                    "schema_version": "1.0",
                    "claim_id": f"claim:{index}",
                    "claim_text_hash": sha256_json(f"Retained factual claim {index}."),
                    "evidence_ids": ["F1"],
                    "evidence_hash": sha256_json(
                        [
                            {
                                "evidence_id": "F1",
                                "source_pack": "findings",
                                "page": 1,
                                "text_hash": sha256_json(
                                    "Revenue grew in the measured market."
                                ),
                            }
                        ]
                    ),
                    "source_identity": source_id,
                    "prompt_family": "report_vs/validate/grounding",
                    "prompt_content_hash": "prompt-content-hash",
                    "execution_identity": "grounding-execution-1",
                    "validator_version": "grounding_validation_output:1.2",
                    "model_provider": "openai",
                    "model_name": "gpt-4.1-mini",
                    "configuration_policy_identity": "grounding-policy-hash",
                    "relevant_input_hash": "grounding-input-hash",
                }
                if semantic and index == 1
                else None
            ),
            "semantic_disagreement": "",
            "semantic_validator_used": semantic and index == 1,
            "semantic_execution_identity": "grounding-execution-1"
            if semantic and index == 1
            else "",
        }
        results.append(result)
    package = {
        "schema_version": "1.3",
        "artifact_hash": sha256_json(artifacts),
        "package_hash": "",
        "results": results,
        "readiness_status": (
            "not_publishable" if unsupported or unresolved else "awaiting_review"
        ),
        "unsupported_factual_count": unsupported,
        "unresolved_factual_count": unresolved,
        "deterministic_pass_count": 0 if semantic else 1,
        "semantic_validation_count": 1 if semantic else 0,
        "semantic_execution_identities": ["grounding-execution-1"] if semantic else [],
        "validation_identity": {
            "schema_version": "1.1",
            "report_id": "report-1",
            "source_id": source_id,
            "source_md5": source_md5,
            "claim_validation_validator_version": "retained_claim_validation:v2",
            "grounding_validator_version": "grounding_validation_output:1.2",
            "configuration_hash": configuration_hash,
            "policy_hash": policy_hash,
        },
        "lineage": {
            "schema_version": "1.1",
            "report_id": "report-1",
            "final_artifact_hash": sha256_json(artifacts),
            "publication_projection_hash": publication_projection_hash(html),
            "evidence_pack_hash": sha256_json(evidence_packs),
            "source_id": source_id,
            "source_md5": source_md5,
            "claim_validation_validator_version": "retained_claim_validation:v2",
            "grounding_validator_version": "grounding_validation_output:1.2",
            "semantic_execution_identities": (
                ["grounding-execution-1"] if semantic else []
            ),
            "semantic_prompt_content_hashes": (
                ["prompt-content-hash"] if semantic else []
            ),
            "semantic_model_identities": ["openai/gpt-4.1-mini"] if semantic else [],
            "configuration_hash": configuration_hash,
            "policy_hash": policy_hash,
        },
    }
    return _seal_claim_package(package)


def _readiness_with_package(
    package: dict,
    *,
    configuration_hash: str = "config-current",
    policy_hash: str = "policy-current",
) -> object:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    return evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
        retained_claim_package=package,
        retained_claim_required=True,
        source_id="source:example",
        source_md5="b" * 32,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )


def _retained_grounding_rule(readiness):
    return next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.retained_claim_grounding"
    )


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

    readiness = evaluate_publish_readiness(
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
    package = _retained_claim_package(
        artifacts, evidence_packs, html, unsupported=1
    )

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
    package = _retained_claim_package(
        artifacts, evidence_packs, html, semantic=True
    )
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
    package = _retained_claim_package(
        artifacts, evidence_packs, html, semantic=True
    )

    readiness = _readiness_with_package(package)

    assert readiness.status == "pass"
    assert _retained_grounding_rule(readiness).status == "pass"
    assert package["semantic_execution_identities"] == ["grounding-execution-1"]


def test_publish_readiness_rejects_html_without_build_traceability() -> None:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = re.sub(r"<!--.*?-->\s*", "", html, count=1, flags=re.DOTALL)

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


def test_mintel_rendered_heading_passes_all_three_original_readiness_rules() -> None:
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures/public_editorial/mintel_2026_readiness_ellipsis.json"
        ).read_text(encoding="utf-8")
    )
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    html = html.replace("</body>", fixture["rendered_html"] + "</body>")

    readiness = evaluate_publish_readiness(
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
        readiness = evaluate_publish_readiness(
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
