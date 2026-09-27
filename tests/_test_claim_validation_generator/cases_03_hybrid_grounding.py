from __future__ import annotations

from dataclasses import asdict, replace

import pytest

import src.generators.claim_validation_generator as claim_validation
from src.contracts.claim_validation import (
    ClaimSemanticGroundingResult,
    ClaimSemanticValidationIdentity,
)
from src.contracts.validation import ValidationReport
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.publish_readiness_generator import evaluate_publish_readiness
from src.utils.cache_utils import sha256_json


def _ambiguous_claim(
    text: str = "Wallet use is becoming a common checkout method across retailers.",
) -> tuple[dict, dict]:
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"id": "claim-1", "claim": text, "evidence_id": "f1"}
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common checkout method."}
            ]
        }
    }
    return artifacts, evidence


def _semantic_result(claim_input, outcome: str) -> ClaimSemanticGroundingResult:
    identity = ClaimSemanticValidationIdentity(
        schema_version="1.0",
        claim_id=claim_input.candidate.claim_id,
        claim_text_hash=claim_input.candidate.text_hash,
        evidence_ids=[
            ref.evidence_id for ref in claim_input.candidate.evidence_references
        ],
        evidence_hash=claim_input.evidence_hash,
        source_identity=claim_input.source_identity,
        prompt_family="report_vs/validate/grounding",
        prompt_content_hash="prompt-content-1",
        execution_identity="execution-1",
        validator_version="grounding_validation_output:1.2",
        model_provider="openai",
        model_name="test-model",
        configuration_policy_identity="policy-1",
        relevant_input_hash="input-1",
    )
    return ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome=outcome,
        reason=f"semantic_{outcome}",
        identity=identity,
    )


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("entailed", "supported"),
        ("contradicted", "unsupported"),
        ("not_established", "unresolved"),
    ],
)
def test_retained_claim_batch_grounding_preserves_three_semantic_outcomes(
    outcome: str, expected_status: str
) -> None:
    artifacts, evidence = _ambiguous_claim()
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, outcome) for claim in claims]

    package = validate_retained_claims(
        artifacts,
        evidence,
        source_identity="source-1",
        semantic_batch_validator=ground_batch,
    )

    result = package.results[0]
    assert len(calls) == 1
    assert len(calls[0]) == 1
    assert (
        calls[0][0].candidate.text
        == artifacts["summary"]["claim_evidence_map"][0]["claim"]
    )
    assert calls[0][0].evidence_texts == [
        "Wallet use is becoming a common checkout method."
    ]
    assert result.deterministic_status == "unresolved"
    assert result.semantic_outcome == outcome
    assert result.status == expected_status
    assert result.semantic_validator_used is True
    assert result.semantic_identity is not None
    assert result.semantic_identity.evidence_ids == ["f1"]


def test_retained_claim_batch_grounding_collects_unresolved_claims_once() -> None:
    first, evidence = _ambiguous_claim()
    second, _ = _ambiguous_claim(
        "Wallet use is becoming a more common checkout method for shoppers."
    )
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                *first["summary"]["claim_evidence_map"],
                {
                    **second["summary"]["claim_evidence_map"][0],
                    "id": "claim-2",
                },
            ]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, "not_established") for claim in claims]

    package = validate_retained_claims(
        artifacts, evidence, semantic_batch_validator=ground_batch
    )

    assert len(calls) == 1
    assert len(calls[0]) == 2
    assert {result.status for result in package.results} == {"unresolved"}
    assert {result.candidate.claim_id for result in package.results} == {
        "summary_claim:claim-1",
        "summary_claim:claim-2",
    }


def test_retained_claim_deterministic_support_and_contradiction_bypass_semantics() -> (
    None
):
    supported_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-supported",
                    "claim": "Wallet adoption reached 42% in 2026.",
                    "evidence_id": "f1",
                }
            ]
        }
    }
    contradictory_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-contradicted",
                    "claim": "Wallet adoption reached 43% in 2026.",
                    "evidence_id": "f1",
                }
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [{"id": "f1", "text": "Wallet adoption reached 42% in 2026."}]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        raise AssertionError("mechanically decided claims must bypass grounding")

    supported = validate_retained_claims(
        supported_artifacts, evidence, semantic_batch_validator=ground_batch
    )
    contradicted = validate_retained_claims(
        contradictory_artifacts, evidence, semantic_batch_validator=ground_batch
    )

    assert supported.results[0].status == "supported"
    assert supported.results[0].deterministic_status == "supported"
    assert contradicted.results[0].status == "unsupported"
    assert contradicted.results[0].deterministic_status == "unsupported"
    assert calls == []


def test_retained_claim_provenance_failure_bypasses_semantic_grounding() -> None:
    claim = "Wallet use is becoming a common checkout method across retailers."
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        raise AssertionError("invalid provenance must bypass semantic grounding")

    package = validate_retained_claims(
        {"expert_comment": claim},
        {
            "findings": {
                "findings": [{"id": "f1", "text": "Wallet use is becoming common."}]
            }
        },
        semantic_batch_validator=ground_batch,
    )

    assert package.results[0].status == "unsupported"
    assert package.results[0].reasons == ["soft_copy_provenance_missing"]
    assert calls == []


def test_stale_retained_claim_grounding_identity_is_ignored() -> None:
    artifacts, evidence = _ambiguous_claim()

    def ground_batch(claims):
        stale = _semantic_result(claims[0], "entailed")
        return [
            replace(
                stale,
                identity=replace(stale.identity, claim_text_hash="stale-claim-hash"),
            )
        ]

    package = validate_retained_claims(
        artifacts, evidence, semantic_batch_validator=ground_batch
    )

    result = package.results[0]
    assert result.status == "unresolved"
    assert result.semantic_validator_used is False
    assert result.semantic_disagreement == "semantic_result_identity_mismatch"


def test_missing_semantic_batch_result_is_explicitly_diagnostic() -> None:
    artifacts, evidence = _ambiguous_claim()

    package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=lambda _claims: [],
    )

    result = package.results[0]
    assert result.status == "unresolved"
    assert result.semantic_outcome is None
    assert result.semantic_disagreement == "semantic_result_missing"


def test_final_claim_package_binds_current_artifact_evidence_and_source_lineage():
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    semantic_calls = 0

    def ground(claims):
        nonlocal semantic_calls
        semantic_calls += 1
        return [_semantic_result(claims[0], "entailed")]

    validation_package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=ground,
        source_identity="source-1",
    )
    assert semantic_calls == 1
    package = claim_validation.attach_claim_validation_execution_identity(
        validation_package,
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    materialize = getattr(
        claim_validation, "materialize_retained_claim_package", None
    )
    assert callable(materialize)

    final_html = "<html><body>Current report.</body></html>"
    retained, failure_code = materialize(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html=final_html,
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert semantic_calls == 1
    assert (
        retained["lineage"]["final_artifact_hash"]
        == validation_package.artifact_hash
    )
    assert retained["lineage"]["publication_projection_hash"]
    assert retained["lineage"]["evidence_pack_hash"]
    assert retained["lineage"]["source_id"] == "source-1"
    assert retained["lineage"]["report_id"] == "report-1"
    assert retained["lineage"]["source_md5"] == "source-md5"
    assert retained["lineage"]["configuration_hash"] == "config-1"
    assert retained["lineage"]["policy_hash"] == "policy-1"
    assert retained["lineage"]["claim_validation_validator_version"]
    assert retained["lineage"]["grounding_validator_version"]
    assert retained["lineage"]["semantic_execution_identities"] == [
        "execution-1"
    ]
    assert retained["lineage"]["semantic_prompt_content_hashes"] == [
        "prompt-content-1"
    ]
    assert retained["lineage"]["semantic_model_identities"]


def test_final_claim_package_materialization_rejects_stale_evidence() -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(artifacts, evidence, source_identity="source-1"),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    evidence["findings"]["findings"][0]["text"] = "A different source fact."
    materialize = getattr(
        claim_validation, "materialize_retained_claim_package", None
    )
    assert callable(materialize)

    retained, failure_code = materialize(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["lineage"]["evidence_pack_hash"] == sha256_json(evidence)
    assert retained["lineage"]["semantic_execution_identities"] == []
    assert retained["readiness_status"] == "not_publishable"


def test_final_claim_package_rejects_changed_deterministic_disposition() -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(artifacts, evidence, source_identity="source-1"),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    package["results"][0]["status"] = "supported"
    package["results"][0]["deterministic_status"] = "supported"
    package["package_hash"] = ""
    package["package_hash"] = claim_validation.claim_validation_package_hash(package)

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["readiness_status"] == "not_publishable"
    assert retained["results"][0]["status"] == "unresolved"


@pytest.mark.parametrize(
    ("identity_field", "stale_value"),
    [
        ("source_id", "source:old"),
        ("source_md5", "source-md5-old"),
        ("configuration_hash", "config-old"),
        ("policy_hash", "policy-old"),
    ],
)
def test_final_claim_package_rejects_stale_validation_identity(
    identity_field: str, stale_value: str
) -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = asdict(
        validate_retained_claims(artifacts, evidence, source_identity="source-1")
    )
    package["validation_identity"] = {
        "schema_version": "1.1",
        "report_id": "report-1",
        "source_id": "source-1",
        "source_md5": "source-md5",
        "claim_validation_validator_version": "retained_claim_validation:v2",
        "grounding_validator_version": "grounding_validation_output:1.2",
        "configuration_hash": "config-1",
        "policy_hash": "policy-1",
    }
    package["validation_identity"][identity_field] = stale_value
    package["package_hash"] = ""
    package["package_hash"] = claim_validation.claim_validation_package_hash(package)

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["validation_identity"][identity_field] != stale_value


def test_missing_validation_candidate_materializes_deterministic_final_package():
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        None,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["lineage"]["report_id"] == "report-1"
    assert retained["lineage"]["final_artifact_hash"] == sha256_json(artifacts)
    assert retained["semantic_validation_count"] == 0
    assert retained["unresolved_factual_count"] == 1
    assert retained["readiness_status"] == "not_publishable"


def test_promoted_repair_candidate_materializes_against_promoted_artifact() -> None:
    unchanged_claim = "Wallet use is becoming a common checkout method across retailers."
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
                }
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common checkout method."},
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
                }
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
    evidence = {
        "findings": {
            "findings": [{"id": "f1", "text": final_claim}]
        }
    }
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
    artifacts, evidence = _ambiguous_claim(
        "Wallet adoption reached 42% in 2026."
    )
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
