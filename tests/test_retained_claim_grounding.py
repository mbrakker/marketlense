from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.claim_validation import ClaimValidationPackage
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.validation import ValidationRequest
from src.generators.validation.grounding import grounding_payload, run_grounding_check
from src.generators.validation.regeneration_candidate import (
    retained_claim_repair_issues,
)
from src.generators.validation_generator import validate_report
from tests._test_validation_generator._shared import (
    FakeAnalysisStore,
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _retained_request() -> ValidationRequest:
    claim = "Wallet use is becoming a common checkout method across retailers."
    return ValidationRequest(
        schema_version="1.0",
        report_id="retained-grounding",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {"id": "claim-1", "claim": claim, "evidence_id": "f1"}
                ]
            }
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Wallet use is becoming a common checkout method.",
                    }
                ]
            }
        },
        source_id="source-retained-grounding",
    )


def _grounding_check(item_id: str, text: str, outcome: str) -> dict:
    return {
        "item_id": item_id,
        "section": "summary.claim_evidence_map:claim-1.claim",
        "text": text,
        "classification": "factual_claim",
        "entailment_outcome": outcome,
        "proposition_status": "compatible",
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": "unknown",
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": f"semantic_{outcome}",
    }


def test_grounding_payload_attaches_only_unresolved_claims_to_exact_evidence() -> None:
    request = _retained_request()
    payload = grounding_payload(request, request.artifacts)
    items = payload["retained_claims_to_ground"]

    assert len(items) == 1
    assert items[0]["item_id"] == "summary_claim:claim-1"
    assert items[0]["text"] == (
        "Wallet use is becoming a common checkout method across retailers."
    )
    assert len(items[0]["text_hash"]) == 64
    assert items[0]["evidence_ids"] == ["f1"]
    assert len(items[0]["evidence_hash"]) == 64
    retained_evidence = items[0]["retained_evidence"]
    assert len(retained_evidence) == 1
    assert retained_evidence[0]["evidence_id"] == "f1"
    assert retained_evidence[0]["source_pack"] == "findings"
    assert retained_evidence[0]["page"] is None
    assert retained_evidence[0]["text"] == (
        "Wallet use is becoming a common checkout method."
    )
    assert len(retained_evidence[0]["text_hash"]) == 64


def test_semantic_fallback_payload_omits_proven_and_failed_claims() -> None:
    unresolved_text = (
        "Wallet use is becoming a common checkout method across retailers."
    )
    request = ValidationRequest(
        schema_version="1.0",
        report_id="retained-grounding-filter",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {
                        "id": "unresolved",
                        "claim": unresolved_text,
                        "evidence_id": "f2",
                    },
                    {
                        "id": "supported",
                        "claim": "Wallet adoption reached 42% in 2026.",
                        "evidence_id": "f1",
                    },
                    {
                        "id": "contradicted",
                        "claim": "Wallet adoption reached 43% in 2026.",
                        "evidence_id": "f1",
                    },
                    {
                        "id": "unknown-evidence",
                        "claim": "Wallet use reached a new milestone.",
                        "evidence_id": "missing-id",
                    },
                ]
            },
            "expert_comment": "An unbound factual statement remains.",
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "text": "Wallet adoption reached 42% in 2026."},
                    {
                        "id": "f2",
                        "text": "Wallet use is becoming a common checkout method.",
                    },
                ]
            }
        },
    )

    payload = grounding_payload(request, request.artifacts)

    assert [item["item_id"] for item in payload["retained_claims_to_ground"]] == [
        "summary_claim:unresolved"
    ]


def test_reused_report_grounding_maps_semantics_and_current_identity(tmp_path) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    reused_output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, text, "entailed")],
    }
    reuse_requests = []
    captured_packages: list[ClaimValidationPackage] = []
    model_client = FakeOpenAI(grounding_payload=reused_output)

    def reuse_reader(reuse_request, _ctx):
        reuse_requests.append(reuse_request)
        return SimpleNamespace(
            reusable=True,
            reason="compatible_retained_output",
            output_payload=reused_output,
        )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["General report evidence."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        source_id=request.source_id,
        prompt_family_reuse_reader=reuse_reader,
        prompt_family_materializer=lambda *_: None,
        retained_claim_validation_sink=captured_packages.append,
    )

    assert issues == []
    assert len(reuse_requests) == 1
    assert model_client.requests == []
    assert captured_packages[0].results[0].status == "supported"
    result = captured_packages[0].results[0]
    assert result.semantic_outcome == "entailed"
    assert result.semantic_identity is not None
    assert result.semantic_identity.claim_id == item_id
    assert result.semantic_identity.evidence_ids == ["f1"]
    assert result.semantic_identity.source_identity == request.source_id
    assert (
        result.semantic_identity.relevant_input_hash
        == reuse_requests[0].relevant_input_hash
    )
    assert (
        result.semantic_identity.configuration_policy_identity
        == reuse_requests[0].configuration_policy_hash
    )


def test_multiple_retained_claims_use_one_report_level_grounding_call(tmp_path) -> None:
    request = _retained_request()
    second_text = (
        "Wallet use is becoming a familiar checkout route in several retail categories."
    )
    request = replace(
        request,
        source_id="",
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    *request.artifacts["summary"]["claim_evidence_map"],
                    {"id": "claim-2", "claim": second_text, "evidence_id": "f1"},
                ]
            }
        },
    )
    checks = [
        _grounding_check(
            "summary_claim:claim-1",
            request.artifacts["summary"]["claim_evidence_map"][0]["claim"],
            "entailed",
        ),
        _grounding_check("summary_claim:claim-2", second_text, "entailed"),
    ]
    model_client = FakeOpenAI(grounding_payload={"unsupported": [], "checks": checks})
    captured_packages: list[ClaimValidationPackage] = []

    run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        retained_claim_validation_sink=captured_packages.append,
    )

    grounding_calls = [
        call for call in model_client.requests if call[2].endswith(":grounding")
    ]
    assert len(grounding_calls) == 1
    assert len(captured_packages[0].results) == 2
    assert {result.status for result in captured_packages[0].results} == {"supported"}


def test_stale_report_grounding_is_not_reused_for_current_retained_claim(
    tmp_path,
) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    new_output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, text, "not_established")],
    }
    reuse_requests = []
    model_client = FakeOpenAI(grounding_payload=new_output)
    captured_packages: list[ClaimValidationPackage] = []

    def stale_reader(reuse_request, _ctx):
        reuse_requests.append(reuse_request)
        return SimpleNamespace(
            reusable=False,
            reason="input_identity_mismatch",
            output_payload={
                "unsupported": [],
                "checks": [_grounding_check(item_id, text, "entailed")],
            },
        )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["General report evidence."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        source_id=request.source_id,
        prompt_family_reuse_reader=stale_reader,
        prompt_family_materializer=lambda *_: None,
        retained_claim_validation_sink=captured_packages.append,
    )

    assert len(reuse_requests) == 1
    assert len(model_client.requests) == 1
    assert any(
        issue.severity == "warning"
        and "[factual_claim|not_established]" in issue.message
        for issue in issues
    )
    assert captured_packages[0].results[0].status == "unresolved"
    assert captured_packages[0].results[0].semantic_outcome == "not_established"


def test_initial_and_regenerated_candidate_share_grounding_identity_and_cache(
    tmp_path,
) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    claim_text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, claim_text, "entailed")],
    }
    settings = _settings(tmp_path)
    initial_store = FakeAnalysisStore()
    initial_client = FakeOpenAI(grounding_payload=output)
    validate_report(
        request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=initial_client,
        analysis_store=initial_store,
    )

    candidate_request = replace(request, artifacts=dict(request.artifacts))
    assert not retained_claim_repair_issues(
        candidate_request.artifacts,
        candidate_request.evidence_packs,
        previous_artifacts=request.artifacts,
    )
    candidate_store = FakeAnalysisStore()
    candidate_client = FakeOpenAI(grounding_payload=output)
    validate_report(
        candidate_request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=candidate_client,
        analysis_store=candidate_store,
        pack_name="validation_regen_candidate_1",
    )

    initial_package = next(
        item[3]
        for item in initial_store.stored
        if item[2] == "validation_retained_claim_validation_candidate"
    )
    candidate_package = next(
        item[3]
        for item in candidate_store.stored
        if item[2] == "validation_regen_candidate_1_retained_claim_validation_candidate"
    )
    initial_result = initial_package["results"][0]
    candidate_result = candidate_package["results"][0]
    initial_grounding_calls = [
        call for call in initial_client.requests if call[2].endswith(":grounding")
    ]
    candidate_grounding_calls = [
        call for call in candidate_client.requests if call[2].endswith(":grounding")
    ]
    assert len(initial_grounding_calls) == 1
    assert candidate_grounding_calls == []
    assert initial_result["status"] == candidate_result["status"] == "supported"
    assert initial_result["semantic_identity"] == candidate_result["semantic_identity"]


def test_unresolved_claim_candidate_is_persisted_for_final_readiness_materialization(
    tmp_path,
) -> None:
    request = _retained_request()
    request = replace(
        request,
        source_id="",
        validation_mode="deferred_grounding",
    )
    analysis_store = FakeAnalysisStore()
    claim_text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    report = validate_report(
        request,
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                "unsupported": [
                    {
                        "item_id": "summary_claim:claim-1",
                        "section": "summary.claim_evidence_map:claim-1.claim",
                        "text": claim_text,
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "reason": "Evidence does not establish the claim.",
                    }
                ],
                "checks": [
                    _grounding_check(
                        "summary_claim:claim-1",
                        claim_text,
                        "not_established",
                    )
                ],
            }
        ),
        analysis_store=analysis_store,
    )

    assert report.status == "pass"
    package_entry = next(
        item
        for item in analysis_store.stored
        if item[2] == "validation_retained_claim_validation_candidate"
    )
    package = package_entry[3]
    assert not any(
        item[2] == "retained_claim_validation" for item in analysis_store.stored
    )
    assert package["unresolved_factual_count"] == 1
    assert package["readiness_status"] == "not_publishable"
    assert package["validation_identity"]["grounding_validator_version"] == (
        "grounding_validation_output:1.2"
    )
    result = package["results"][0]
    assert result["status"] == "unresolved"
    assert result["semantic_outcome"] == "not_established"
    identity = result["semantic_identity"]
    assert identity["claim_id"] == "summary_claim:claim-1"
    assert identity["claim_text_hash"] == result["candidate"]["text_hash"]
    assert identity["evidence_ids"] == ["f1"]
    assert len(identity["evidence_hash"]) == 64
    assert identity["source_identity"] == ""
    assert identity["prompt_family"] == "report_vs/validate/grounding"
    assert identity["prompt_content_hash"]
    assert identity["execution_identity"]
    assert identity["validator_version"] == "grounding_validation_output:1.2"
    assert identity["model_provider"]
    assert identity["model_name"]
    assert identity["configuration_policy_identity"]
    assert identity["relevant_input_hash"]
