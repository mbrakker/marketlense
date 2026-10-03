# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_03_hybrid_grounding import *  # noqa: F401,F403


def test_promoted_repair_candidate_materializes_against_promoted_artifact() -> None:
    unchanged_claim = (
        "Wallet use is becoming a common checkout method across retailers."
    )
    candidate_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-1",
                    "claim": unchanged_claim,
                    "evidence_id": "f1",
                },
                {
                    "id": "claim-2",
                    "claim": "Wallet adoption reached 45% in 2026.",
                    "evidence_id": "f2",
                },
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Wallet use is becoming a common checkout method.",
                },
                {"id": "f2", "text": "Wallet adoption reached 42% in 2026."},
            ]
        }
    }
    semantic_calls = 0

    def ground(claims):
        nonlocal semantic_calls
        semantic_calls += 1
        return [_semantic_result(claim, "entailed") for claim in claims]

    candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(
            candidate_artifacts,
            evidence,
            semantic_batch_validator=ground,
            source_identity="source-1",
        ),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    promoted_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-1",
                    "claim": unchanged_claim,
                    "evidence_id": "f1",
                },
                {
                    "id": "claim-2",
                    "claim": "Wallet adoption reached 42% in 2026.",
                    "evidence_id": "f2",
                },
            ]
        }
    }

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        candidate,
        report_id="report-1",
        artifacts=promoted_artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Wallet adoption reached 42%.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert semantic_calls == 1
    assert retained["lineage"]["report_id"] == "report-1"
    assert retained["lineage"]["final_artifact_hash"] == sha256_json(promoted_artifacts)
    assert retained["lineage"]["final_artifact_hash"] != candidate["artifact_hash"]
    assert retained["results"][0]["status"] == "supported"
    assert retained["results"][0]["semantic_validator_used"] is True
    assert retained["results"][1]["candidate"]["text"] == (
        "Wallet adoption reached 42% in 2026."
    )
    assert retained["results"][1]["status"] == "supported"
    assert retained["results"][1]["semantic_validator_used"] is False
    assert retained["semantic_validation_count"] == 1
    assert retained["readiness_status"] == "awaiting_review"


def test_rolled_back_candidate_cannot_become_the_final_package() -> None:
    final_claim = "Wallet adoption reached 42% in 2026."
    repair_claim = "Wallet adoption reached 45% in 2026."
    final_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"id": "claim-1", "claim": final_claim, "evidence_id": "f1"}
            ]
        }
    }
    repair_candidate_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"id": "claim-1", "claim": repair_claim, "evidence_id": "f1"}
            ]
        }
    }
    evidence = {"findings": {"findings": [{"id": "f1", "text": final_claim}]}}
    rolled_back_candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(
            repair_candidate_artifacts, evidence, source_identity="source-1"
        ),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        rolled_back_candidate,
        report_id="report-1",
        artifacts=final_artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Wallet adoption reached 42%.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["lineage"]["final_artifact_hash"] == sha256_json(final_artifacts)
    assert retained["results"][0]["candidate"]["text"] == (
        "Wallet adoption reached 42% in 2026."
    )
    assert retained["results"][0]["status"] == "supported"


def test_merchant_risk_council_final_figures_survive_candidate_projection_drift():
    candidate_artifacts = {
        "key_figures": [
            {
                "id": "1",
                "label": "Merchant acceptance of real-time payments",
                "evidence_id": "f1",
            }
        ]
    }
    final_artifacts = {
        "key_figures": [
            {
                "id": "1",
                "label": "Merchant acceptance of real-time payments",
                "value": "43%",
                "evidence_id": "f1",
            }
        ]
    }
    evidence = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "43% of merchants accept real-time payments.",
                    "page": 2,
                }
            ]
        }
    }
    candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(
            candidate_artifacts, evidence, source_identity="source:mrc"
        ),
        report_id="merchant-risk-council-2026",
        source_id="source:mrc",
        source_md5="11b0b55157f7d0636815ad72435e1cf5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        candidate,
        report_id="merchant-risk-council-2026",
        artifacts=final_artifacts,
        evidence_packs=evidence,
        final_html="<html><body>43% accept real-time payments.</body></html>",
        source_id="source:mrc",
        source_md5="11b0b55157f7d0636815ad72435e1cf5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["lineage"]["report_id"] == "merchant-risk-council-2026"
    assert retained["lineage"]["final_artifact_hash"] != candidate["artifact_hash"]
    assert retained["results"][0]["candidate"]["text"] == (
        "Merchant acceptance of real-time payments 43%"
    )
    assert retained["results"][0]["status"] == "supported"


def test_final_package_materialization_is_idempotent() -> None:
    artifacts, evidence = _ambiguous_claim("Wallet adoption reached 42% in 2026.")
    candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(artifacts, evidence, source_identity="source-1"),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    inputs = {
        "report_id": "report-1",
        "artifacts": artifacts,
        "evidence_packs": evidence,
        "final_html": "<html><body>Wallet adoption reached 42%.</body></html>",
        "source_id": "source-1",
        "source_md5": "source-md5",
        "configuration_hash": "config-1",
        "policy_hash": "policy-1",
    }

    first, first_error = claim_validation.materialize_retained_claim_package(
        candidate, **inputs
    )
    second, second_error = claim_validation.materialize_retained_claim_package(
        first, **inputs
    )

    assert first_error == second_error == ""
    assert first is not None and second is not None
    assert second["package_hash"] == first["package_hash"]


def test_publish_readiness_reuses_retained_semantic_result_without_provider_call():
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    calls = []

    def ground(claims):
        calls.append(claims)
        return [_semantic_result(claims[0], "entailed")]

    candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(
            artifacts,
            evidence,
            semantic_batch_validator=ground,
            source_identity="source-1",
        ),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    html = "<html><body>Wallet use is common.</body></html>"
    final_package, failure_code = claim_validation.materialize_retained_claim_package(
        candidate,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html=html,
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    assert final_package is not None
    assert failure_code == ""
    assert len(calls) == 1

    readiness = evaluate_publish_readiness(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        report_card_manifest_path="report-card-manifest.json",
        retained_claim_package=final_package,
        retained_claim_required=True,
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    grounding = next(
        rule
        for rule in readiness.rule_results
        if rule.rule_id == "publish_readiness.retained_claim_grounding"
    )

    assert grounding.status == "pass"
    assert len(calls) == 1
