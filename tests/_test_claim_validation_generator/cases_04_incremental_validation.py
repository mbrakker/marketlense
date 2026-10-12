from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticValidationIdentity,
)
from src.contracts.protected_facts import ProtectedFactComparison
from src.generators.claim_validation_generator import (
    apply_retained_claim_semantic_results,
    attach_claim_validation_execution_identity,
    claim_validation_package_hash,
    retained_claim_semantic_inputs,
    validate_retained_claims,
)

_CONTEXT = {
    "report_id": "report-1",
    "source_id": "source-1",
    "source_md5": "a" * 32,
    "configuration_hash": "b" * 64,
    "policy_hash": "c" * 64,
    "prompt_family": "report_vs/validate/grounding",
    "prompt_execution_identity": "d" * 64,
    "model_provider": "openai",
    "model_name": "gpt-test",
    "configuration_policy_identity": "e" * 64,
    "retrieval_identity": "2" * 64,
}


def _inputs(
    *,
    claims: tuple[str, ...] = (
        "Wallet use is becoming a common checkout method across retailers.",
    ),
    evidence_text: str = "Wallet use is becoming a common checkout method.",
    provenance: str = "source-span-1",
    claim_ids: tuple[str, ...] | None = None,
):
    evidence_packs = {
        "findings": {
            "findings": [{"id": "evidence-1", "text": evidence_text, "page": 4}]
        }
    }
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": (
                        claim_ids[index - 1]
                        if claim_ids is not None
                        else f"claim-{index}"
                    ),
                    "claim": claim,
                    "evidence_id": "evidence-1",
                    "evidence_spans": [
                        {
                            "evidence_id": "evidence-1",
                            "page": 4,
                            "text": provenance,
                        }
                    ],
                }
                for index, claim in enumerate(claims, start=1)
            ]
        }
    }
    package = validate_retained_claims(
        artifacts, evidence_packs, source_identity=_CONTEXT["source_id"]
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package, evidence_packs, source_identity=_CONTEXT["source_id"]
    )
    return artifacts, evidence_packs, package, semantic_inputs


def _semantic_result(semantic_input, *, outcome: str = "entailed"):
    candidate = semantic_input.candidate
    identity = ClaimSemanticValidationIdentity(
        schema_version="1.1",
        claim_id=candidate.claim_id,
        claim_text_hash=candidate.text_hash,
        evidence_ids=[ref.evidence_id for ref in candidate.evidence_references],
        evidence_hash=semantic_input.evidence_hash,
        source_identity=_CONTEXT["source_id"],
        prompt_family=_CONTEXT["prompt_family"],
        prompt_content_hash="f" * 64,
        execution_identity=_CONTEXT["prompt_execution_identity"],
        validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        model_provider=_CONTEXT["model_provider"],
        model_name=_CONTEXT["model_name"],
        configuration_policy_identity=_CONTEXT["configuration_policy_identity"],
        relevant_input_hash="1" * 64,
        retrieval_identity=_CONTEXT["retrieval_identity"],
    )
    return ClaimSemanticGroundingResult(
        schema_version="1.0",
        outcome=outcome,
        reason="test_result",
        identity=identity,
        protected_facts=ProtectedFactComparison.from_payload(None),
    )


def _validated_prior(package, semantic_inputs):
    grounded = apply_retained_claim_semantic_results(
        package,
        semantic_inputs,
        [_semantic_result(item) for item in semantic_inputs],
    )
    return attach_claim_validation_execution_identity(
        grounded,
        report_id=_CONTEXT["report_id"],
        source_id=_CONTEXT["source_id"],
        source_md5=_CONTEXT["source_md5"],
        configuration_hash=_CONTEXT["configuration_hash"],
        policy_hash=_CONTEXT["policy_hash"],
    )


def _reuse(
    current_package,
    current_inputs,
    prior,
    *,
    prompt_content_hash: str = "f" * 64,
):
    from src.generators.claim_validation_generator import (
        reuse_retained_claim_semantic_results,
    )

    return reuse_retained_claim_semantic_results(
        current_package,
        current_inputs,
        prior,
        expected_prior_artifact_hash=prior["artifact_hash"],
        prompt_content_hash_by_claim_id={
            item.candidate.claim_id: prompt_content_hash for item in current_inputs
        },
        **_CONTEXT,
    )


def test_unchanged_claim_and_evidence_reuse_supported_semantic_result() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs()

    merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert not remaining
    assert merged.results[0].status == "supported"
    assert (
        asdict(merged.results[0].semantic_identity)
        == prior["results"][0]["semantic_identity"]
    )
    assert telemetry["reused_validation_results"] == 1
    assert telemetry["newly_validated_claims"] == 0
    assert telemetry["semantic_validation_calls_avoided"] == 1


def test_changed_claim_text_requires_semantic_revalidation() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=("Wallet use is becoming a more common checkout method for shoppers.",)
    )

    _merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert [item.candidate.claim_id for item in remaining] == ["summary_claim:claim-1"]
    assert telemetry["reuse_fallback_reason_counts"]["claim_identity_changed"] == 1


def test_changed_evidence_requires_semantic_revalidation() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        evidence_text="Wallets are deployed throughout online banking."
    )

    _merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert len(remaining) == 1
    assert telemetry["reuse_fallback_reason_counts"]["evidence_identity_changed"] == 1


def test_changed_source_provenance_requires_semantic_revalidation() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        provenance="different source span"
    )

    _merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert len(remaining) == 1
    assert telemetry["reuse_fallback_reason_counts"]["provenance_identity_changed"] == 1


def test_changed_rendered_prompt_context_requires_semantic_revalidation() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs()

    _merged, remaining, telemetry = _reuse(
        current_package,
        current_inputs,
        prior,
        prompt_content_hash="9" * 64,
    )

    assert len(remaining) == 1
    assert telemetry["reuse_fallback_reason_counts"]["prompt_context_changed"] == 1


def test_new_claim_is_validated_and_removed_claim_is_not_carried_forward() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet use is becoming a more common checkout method for shoppers.",
        )
    )
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet adoption is increasing across online banking.",
        ),
        claim_ids=("claim-1", "claim-3"),
    )

    merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert len(merged.results) == 2
    assert [item.candidate.claim_id for item in remaining] == ["summary_claim:claim-3"]
    assert {item.candidate.claim_id for item in merged.results} == {
        "summary_claim:claim-1",
        "summary_claim:claim-3",
    }
    assert "summary_claim:claim-2" not in {
        item.candidate.claim_id for item in merged.results
    }
    assert telemetry["reuse_fallback_reason_counts"]["new_claim"] == 1


def test_ambiguous_prior_claim_mapping_fails_closed() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    prior["results"].append(deepcopy(prior["results"][0]))
    prior["semantic_validation_count"] = 2
    prior["package_hash"] = ""
    prior["package_hash"] = claim_validation_package_hash(prior)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs()

    _merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert len(remaining) == 1
    assert telemetry["reuse_fallback_reason_counts"]["claim_identity_ambiguous"] == 1


def test_prior_unresolved_package_is_never_reused_as_a_pass() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    prior["readiness_status"] = "not_publishable"
    prior["unresolved_factual_count"] = 1
    prior["package_hash"] = ""
    prior["package_hash"] = claim_validation_package_hash(prior)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs()

    _merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert len(remaining) == 1
    assert telemetry["reused_validation_results"] == 0
    assert telemetry["reuse_fallback_reason_counts"]["prior_validation_not_pass"] == 1


def test_mixed_candidate_reuses_only_the_unchanged_claim() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet use is becoming a more common checkout method for shoppers.",
        )
    )
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet adoption is increasing across online banking.",
        )
    )

    merged, remaining, telemetry = _reuse(current_package, current_inputs, prior)

    assert telemetry["total_candidate_claims"] == 2
    assert telemetry["reused_validation_results"] == 1
    assert telemetry["newly_validated_claims"] == 1
    assert [item.candidate.claim_id for item in remaining] == ["summary_claim:claim-2"]
    assert merged.results[0].status == "supported"


def test_reused_and_fresh_results_have_full_validation_semantics() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet use is becoming a more common checkout method for shoppers.",
        )
    )
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet adoption is increasing across online banking.",
        )
    )
    merged, remaining, _telemetry = _reuse(current_package, current_inputs, prior)
    merged = apply_retained_claim_semantic_results(
        merged, remaining, [_semantic_result(item) for item in remaining]
    )
    full = apply_retained_claim_semantic_results(
        current_package,
        current_inputs,
        [_semantic_result(item) for item in current_inputs],
    )

    assert [asdict(item.candidate) for item in merged.results] == [
        asdict(item.candidate) for item in full.results
    ]
    assert [(item.status, item.semantic_outcome) for item in merged.results] == [
        (item.status, item.semantic_outcome) for item in full.results
    ]
    assert merged.readiness_status == full.readiness_status == "awaiting_review"


def test_merged_package_readiness_covers_the_complete_current_claim_set() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet use is becoming a more common checkout method for shoppers.",
        )
    )
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=(
            "Wallet use is becoming a common checkout method across retailers.",
            "Wallet adoption is increasing across online banking.",
        )
    )
    merged, remaining, _telemetry = _reuse(current_package, current_inputs, prior)
    complete = apply_retained_claim_semantic_results(
        merged, remaining, [_semantic_result(item) for item in remaining]
    )

    assert len(complete.results) == len(current_package.results) == 2
    assert complete.unsupported_factual_count == 0
    assert complete.unresolved_factual_count == 0
    assert complete.readiness_status == "awaiting_review"


def test_unsupported_changed_claim_still_blocks_readiness() -> None:
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    prior = _validated_prior(prior_package, prior_inputs)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=("Wallet adoption is increasing across online banking.",)
    )
    merged, remaining, _telemetry = _reuse(current_package, current_inputs, prior)
    blocked = apply_retained_claim_semantic_results(
        merged,
        remaining,
        [_semantic_result(remaining[0], outcome="contradicted")],
    )

    assert blocked.unsupported_factual_count == 1
    assert blocked.readiness_status == "not_publishable"


def test_reuse_does_not_mutate_canonical_package_when_candidate_is_rolled_back():
    _artifacts, _evidence, prior_package, prior_inputs = _inputs()
    canonical = _validated_prior(prior_package, prior_inputs)
    original = deepcopy(canonical)
    _candidate_artifacts, _evidence, current_package, current_inputs = _inputs(
        claims=("Wallet adoption is increasing across online banking.",)
    )

    _candidate_package, _remaining, _telemetry = _reuse(
        current_package, current_inputs, canonical
    )

    assert canonical == original


def test_grounding_revalidates_only_changed_claims_and_avoids_a_batch(tmp_path) -> None:
    from dataclasses import replace as dataclass_replace
    from types import SimpleNamespace

    from src.contracts.validation import ValidationRequest
    from src.generators.prompt_preparation import prepare_prompt_bundle
    from src.generators.validation.grounding import (
        _claim_prompt_content_hashes,
        _grounding_batches,
        grounding_payload,
        run_grounding_check,
    )
    from src.generators.validation.shared import grounding_retrieval_mode
    from src.utils.cache_utils import sha256_json
    from tests._test_retained_claim_grounding import (
        _split_support_test_retained_claim_grounding as retained_claim_grounding_cases,
    )
    from tests._test_validation_generator._shared import (
        FakeOpenAI,
        FakePromptClient,
        _ctx,
        _report,
        _settings,
    )

    _grounding_check = retained_claim_grounding_cases._grounding_check

    prior_texts = (
        "Wallet use is becoming a common checkout method across retailers.",
        "Wallet use is becoming a more common checkout method for shoppers.",
        "The report describes a common checkout method involving wallets.",
        "Wallets appear in payment workflows across retailers.",
        "The report discusses wallet use by retailers.",
    )
    prior_artifacts, evidence, prior_package, prior_inputs = _inputs(claims=prior_texts)
    candidate_artifacts = deepcopy(prior_artifacts)
    candidate_artifacts["summary"]["claim_evidence_map"][2]["provenance_id"] = (
        "changed-source-span"
    )
    candidate_package = validate_retained_claims(
        candidate_artifacts,
        evidence,
        source_identity=_CONTEXT["source_id"],
    )
    candidate_inputs = retained_claim_semantic_inputs(
        candidate_package,
        evidence,
        source_identity=_CONTEXT["source_id"],
    )
    prior = _validated_prior(prior_package, prior_inputs)
    report_id = _CONTEXT["report_id"]
    settings = _settings(tmp_path)
    ctx = _ctx()
    prompt_client = FakePromptClient()
    report = dataclass_replace(
        _report(),
        tldr="",
        title="",
        insights=[],
        quote=None,
        figure=None,
        commentary="",
        source="",
    )
    bundle = prepare_prompt_bundle(
        namespace=_CONTEXT["prompt_family"],
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={},
    )
    policy_identity = sha256_json(
        {
            "execution_policy_hash": bundle.execution_policy.policy_hash,
            "execution_policy": asdict(bundle.execution_policy.policy),
            "routing_policy": asdict(bundle.routing_decision),
        }
    )
    retrieval_identity = sha256_json(
        {
            "use_vector_store": False,
            "vector_store_id": "",
            "vector_store_content_hash": "",
            "retrieval_mode": grounding_retrieval_mode(False),
        }
    )
    prior_request = ValidationRequest(
        schema_version="1.1",
        report_id=report_id,
        report=report,
        artifacts=prior_artifacts,
        evidence_packs=evidence,
        source_id=_CONTEXT["source_id"],
    )
    prior_payload = grounding_payload(
        prior_request,
        prior_artifacts,
        retained_claim_inputs=prior_inputs,
    )
    prior_batches = _grounding_batches(prior_payload, prior_inputs)
    evidence_texts = ["Wallet use is becoming a common checkout method."]
    prior_prompt_bundles = [
        prepare_prompt_bundle(
            namespace=_CONTEXT["prompt_family"],
            settings=settings,
            ctx=ctx,
            prompt_client=prompt_client,
            system_variables={
                "report_json": json.dumps(batch_payload, ensure_ascii=False),
                "evidence_json": json.dumps(evidence_texts, ensure_ascii=False),
            },
            user_variables={
                "report_json": json.dumps(batch_payload, ensure_ascii=False),
                "evidence_json": json.dumps(evidence_texts, ensure_ascii=False),
            },
        )
        for batch_payload, _batch_inputs in prior_batches
    ]
    prior_prompt_hashes = _claim_prompt_content_hashes(
        prior_batches, prior_prompt_bundles
    )
    for result in prior["results"]:
        identity = result["semantic_identity"]
        identity.update(
            {
                "execution_identity": bundle.execution_identity.execution_identity,
                "model_provider": str(bundle.execution_policy.policy.provider),
                "model_name": bundle.resolved_model,
                "configuration_policy_identity": policy_identity,
                "retrieval_identity": retrieval_identity,
                "prompt_content_hash": prior_prompt_hashes[
                    result["candidate"]["claim_id"]
                ],
            }
        )
        result["semantic_execution_identity"] = (
            bundle.execution_identity.execution_identity
        )
    prior["semantic_execution_identities"] = [
        bundle.execution_identity.execution_identity
    ]
    prior["validation_identity"] = {
        "schema_version": "1.1",
        "report_id": report_id,
        "source_id": _CONTEXT["source_id"],
        "source_md5": "",
        "claim_validation_validator_version": "retained_claim_validation:v5",
        "grounding_validator_version": CLAIM_GROUNDING_VALIDATOR_VERSION,
        "configuration_hash": str(ctx.configuration_hash or ""),
        "policy_hash": str(ctx.policy_hash or ""),
    }
    prior["package_hash"] = ""
    prior["package_hash"] = claim_validation_package_hash(prior)

    request = ValidationRequest(
        schema_version="1.1",
        report_id=report_id,
        report=report,
        artifacts=candidate_artifacts,
        evidence_packs=evidence,
        source_id=_CONTEXT["source_id"],
        prior_claim_validation_package=prior,
        prior_claim_validation_artifact_hash=prior["artifact_hash"],
    )
    changed_item_id = "summary_claim:claim-3"
    changed_text = prior_texts[2]
    provider = FakeOpenAI(
        grounding_payload={
            "unsupported": [],
            "checks": [_grounding_check(changed_item_id, changed_text, "entailed")],
        }
    )
    retained_packages = []

    issues = run_grounding_check(
        request=request,
        settings=settings,
        grounding_use_vector_store=False,
        evidence_texts=evidence_texts,
        evidence_windows=[],
        prompt_client=prompt_client,
        openai_client=provider,
        ctx=ctx,
        source_id=_CONTEXT["source_id"],
        retained_claim_package=validate_retained_claims(
            candidate_artifacts,
            evidence,
            source_identity=_CONTEXT["source_id"],
        ),
        retained_claim_inputs=candidate_inputs,
        retained_claim_validation_sink=retained_packages.append,
        prompt_family_reuse_reader=lambda *_: SimpleNamespace(
            reusable=False, reason="not_found", output_payload={}
        ),
        prompt_family_materializer=lambda *_: None,
    )

    assert issues == []
    assert len(provider.requests) == 1
    assert len(retained_packages[0].results) == 5
    assert all(result.status == "supported" for result in retained_packages[0].results)
    by_id = {
        result.candidate.claim_id: result for result in retained_packages[0].results
    }
    prior_by_id = {
        result["candidate"]["claim_id"]: result for result in prior["results"]
    }
    assert by_id[changed_item_id].semantic_reason == "semantic_entailed"
    for index in (1, 2, 4, 5):
        assert (
            asdict(by_id[f"summary_claim:claim-{index}"].semantic_identity)
            == prior_by_id[f"summary_claim:claim-{index}"]["semantic_identity"]
        )
        assert by_id[f"summary_claim:claim-{index}"].semantic_reason == "test_result"
