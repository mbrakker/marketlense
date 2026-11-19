from copy import deepcopy
from dataclasses import replace

from src.generators.claim_validation_generator import (
    attach_claim_validation_execution_identity,
    materialize_retained_claim_package,
    retained_claim_semantic_inputs,
    reuse_retained_claim_semantic_results,
    validate_retained_claims,
)
from tests._test_claim_validation_generator._split_support_cases_03_hybrid_grounding import (  # noqa: E501
    _semantic_result,
)
from tests._test_claim_validation_generator.cases_04_incremental_validation import (
    _CONTEXT,
    _inputs,
    _validated_prior,
)
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _fact,
    _insight,
    _packs_for_facts,
    _verified_artifacts,
)


def test_verified_finalization_does_not_reuse_verdict_after_context_changes():
    fact = _fact()
    insight = _insight(metric=fact["metric"])
    insight["so_what"] = "Original surrounding interpretation."
    artifacts = _verified_artifacts(insight=insight, fact=fact)
    packs = _packs_for_facts([fact])

    def semantic_validator(inputs):
        results = []
        for item in inputs:
            result = _semantic_result(item, "entailed")
            results.append(
                replace(
                    result,
                    identity=replace(
                        result.identity,
                        schema_version="1.1",
                        prompt_content_hash="a" * 64,
                        retrieval_identity="b" * 64,
                    ),
                )
            )
        return results

    validated = validate_retained_claims(
        artifacts,
        packs,
        source_identity=SOURCE_IDENTITY,
        verified_facts_only=True,
        semantic_batch_validator=semantic_validator,
    )
    package = attach_claim_validation_execution_identity(
        validated,
        report_id="report",
        source_id=SOURCE_IDENTITY,
        source_md5="",
        configuration_hash="config",
        policy_hash="policy",
    )
    changed = deepcopy(artifacts)
    changed["insights_final"][0]["so_what"] = "Changed surrounding interpretation."

    def materialize(current):
        return materialize_retained_claim_package(
            package,
            report_id="report",
            artifacts=current,
            evidence_packs=packs,
            final_html="",
            source_id=SOURCE_IDENTITY,
            configuration_hash="config",
            policy_hash="policy",
            verified_facts_only=True,
        )

    unchanged, error = materialize(artifacts)
    assert error == ""
    assert unchanged["readiness_status"] == "awaiting_review"
    changed_package, error = materialize(changed)
    assert error == ""
    assert changed_package["readiness_status"] == "not_publishable"
    assert all(
        result["status"] == "unresolved" for result in changed_package["results"]
    )


def test_reuse_does_not_stamp_a_changed_snapshot_with_old_semantic_verdict():
    artifacts, evidence, initial, inputs = _inputs()
    prior = _validated_prior(initial, inputs)
    _, unchanged_inputs, unchanged_telemetry = reuse_retained_claim_semantic_results(
        initial,
        inputs,
        prior,
        expected_prior_artifact_hash=prior["artifact_hash"],
        prompt_content_hash_by_claim_id={
            item.candidate.claim_id: "f" * 64 for item in inputs
        },
        **_CONTEXT,
    )
    assert unchanged_inputs == []
    assert unchanged_telemetry["reused_validation_results"] == 1
    changed = deepcopy(artifacts)
    changed["summary"]["editorial_context"] = "A changed interpretation."
    current = validate_retained_claims(
        changed, evidence, source_identity=_CONTEXT["source_id"]
    )
    current_inputs = retained_claim_semantic_inputs(
        current, evidence, source_identity=_CONTEXT["source_id"]
    )
    merged, remaining, telemetry = reuse_retained_claim_semantic_results(
        current,
        current_inputs,
        prior,
        expected_prior_artifact_hash=prior["artifact_hash"],
        prompt_content_hash_by_claim_id={
            item.candidate.claim_id: "f" * 64 for item in current_inputs
        },
        **_CONTEXT,
    )

    assert remaining == current_inputs
    assert merged.results[0].status == "unresolved"
    assert telemetry["reused_validation_results"] == 0
