from __future__ import annotations

import copy
from types import SimpleNamespace

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import VisualClaimEvaluationResult
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.services.prompt_service import load_prompt_set, render_prompt


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_shadow_result_preserves_source_binding_and_terminal_outcome():
    result = VisualClaimEvaluationResult(
        schema_version="1.0",
        candidate_id="candidate-1",
        original_claim="Original",
        source_identity="pdf-sha256",
        physical_page=5,
        evidence_ids=["f1"],
        evidence_spans=[{"evidence_id": "f1", "page": 5}],
        correction_attempts=[],
        verification_attempts=[],
        final_claim="",
        outcome="failed_verification",
        failure_reason="verification_failed_twice",
    )

    assert result.candidate_id == "candidate-1"
    assert result.physical_page == 5
    assert result.outcome == "failed_verification"


def test_visual_prompts_require_complete_page_and_separate_source_authority():
    correction = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/visual_claim_correction",
        ),
        _ctx(),
    )
    verification = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/visual_claim_verification",
        ),
        _ctx(),
    )

    assert "complete original PDF page" in correction.system.text
    assert "independently" in verification.system.text.lower()
    assert "original claim" in correction.user.text.lower()


def _settings(tmp_path):
    policy = {
        "schema_version": "1.0",
        "provider": "openai",
        "model": "gpt-6-luna",
        "reasoning_effort": "high",
        "max_output_tokens": 2048,
        "retrieval_mode": "chat_json",
        "timeout_seconds": 60,
        "fallback_policy": "same_provider_only",
        "pricing_key": "gpt-6-luna",
    }
    return SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-6-luna",
        openai_seed=None,
        temperature=1.0,
        openai_timeout_seconds=60,
        openai_models={},
        llm_routing={
            "report_vs/validate": {
                "model": "gpt-6-luna",
                "tier": "evidence_sensitive",
                "max_input_tokens": 64000,
                "compaction_enabled": True,
                "quality_threshold": 0.9,
                "same_provider_fallback": True,
            }
        },
        llm_execution_policies={"report_vs/validate": policy},
        output_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        cost_ledger_path=str(tmp_path / "cost.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
        usage_db_path=str(tmp_path / "usage.sqlite"),
    )


def _request(tmp_path, claims):
    return SimpleNamespace(
        schema_version="1.0",
        pdf_path=str(tmp_path / "source.pdf"),
        output_dir=str(tmp_path),
        report_name="report",
        source_identity="pdf-sha256",
        claims=claims,
        shadow_mode=True,
        dpi=180,
    )


def _claim(candidate_id, text, page=5):
    return {
        "candidate_id": candidate_id,
        "text": text,
        "evidence_id": "f1",
        "evidence_spans": [{"evidence_id": "f1", "page": page, "start": 10, "end": 20}],
        "pages": [page],
        "metric": {"value": "61%", "cohort": "video users"},
    }


def _dependencies(responses, render_calls, requests):
    def render_page(request, _ctx):
        render_calls.append(request)
        return SimpleNamespace(
            image_path=f"report/crop_refine_pages/page-{request.page}.png"
        )

    def call_model(request: OpenAIJSONImagePromptRequest, _ctx):
        requests.append(request)
        return SimpleNamespace(
            parsed_json=next(responses),
            request_id=f"request-{len(requests)}",
            model=request.model,
        )

    return VerifiedClaimsVisualDependencies(
        load_prompt_set=load_prompt_set,
        render_prompt=render_prompt,
        render_page_for_crop_refine=render_page,
        openai_chat_json_with_images=call_model,
    )


def test_first_verification_failure_is_repaired_once_and_then_verified(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    original = copy.deepcopy(claims)
    responses = iter(
        [
            {
                "claim": "Corrected 61% for video users",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "rejected",
                "diagnostics": ["wrong cohort"],
                "source_truth_notes": "",
            },
            {
                "claim": "Corrected 61% for the stated video-user cohort",
                "status": "corrected",
                "issues": ["added cohort"],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "source matches",
            },
        ]
    )
    render_calls = []
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, render_calls, requests),
    )

    item = result.claims[0]
    assert item.outcome == "verified_after_retry"
    assert item.final_claim == "Corrected 61% for the stated video-user cohort"
    assert len(item.correction_attempts) == 2
    assert len(item.verification_attempts) == 2
    assert len(render_calls) == 1
    assert [request.image_paths for request in requests] == [
        [str(tmp_path / "report/crop_refine_pages/page-4.png")]
    ] * 4
    assert claims == original
    assert all(request.reasoning_effort == "high" for request in requests)
    assert all(request.response_cache_enabled for request in requests)


def test_first_unresolved_correction_receives_one_bounded_retry(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "", "status": "unresolved", "issues": ["ambiguous"]},
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "source matches",
            },
        ]
    )
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    item = result.claims[0]
    assert item.outcome == "verified_after_retry"
    assert item.final_claim == "Corrected claim"
    assert [attempt.status for attempt in item.correction_attempts] == [
        "unresolved",
        "corrected",
    ]
    assert len(item.verification_attempts) == 1


def test_two_verification_failures_do_not_block_the_next_claim(tmp_path):
    claims = [_claim("candidate-1", "First"), _claim("candidate-2", "Second")]
    responses = iter(
        [
            {"claim": "First corrected", "status": "corrected", "issues": []},
            {
                "outcome": "rejected",
                "diagnostics": ["unsupported"],
                "source_truth_notes": "",
            },
            {"claim": "First corrected again", "status": "corrected", "issues": []},
            {
                "outcome": "rejected",
                "diagnostics": ["still unsupported"],
                "source_truth_notes": "",
            },
            {"claim": "Second corrected", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "source matches",
            },
        ]
    )
    render_calls = []
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, render_calls, requests),
    )

    assert [item.outcome for item in result.claims] == [
        "failed_verification",
        "verified",
    ]
    assert result.claims[0].final_claim == ""
    assert len(result.claims[0].verification_attempts) == 2
    assert result.claims[1].final_claim == "Second corrected"
    assert len(render_calls) == 1


def test_missing_physical_page_is_skipped_without_model_call(tmp_path):
    requests = []
    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [{"candidate_id": "missing-page", "text": "Claim"}]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(iter(()), [], requests),
    )

    assert result.claims[0].outcome == "skipped"
    assert result.claims[0].failure_reason == "physical_page_missing"
    assert requests == []


def test_verifier_receives_no_original_claim_and_result_keeps_authoritative_binding(
    tmp_path,
):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {"outcome": "verified", "diagnostics": [], "source_truth_notes": "matches"},
        ]
    )
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    item = result.claims[0]
    assert item.outcome == "verified"
    assert item.final_claim == "Corrected claim"
    assert item.candidate_id == "candidate-1"
    assert item.source_identity == "pdf-sha256"
    assert item.physical_page == 5
    assert item.evidence_ids == ["f1"]
    assert item.evidence_spans == claims[0]["evidence_spans"]
    assert "Original claim" in requests[0].user_prompt
    assert "Original claim" not in requests[1].user_prompt
    assert "pdf-sha256" in requests[1].user_prompt
    assert "f1" in requests[1].user_prompt


def test_invalid_correction_and_verification_outputs_fail_closed(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "unsupported", "status": "not-a-status", "issues": []},
            {"claim": "still unsupported", "status": "corrected", "issues": []},
            {"outcome": "not-a-verdict", "diagnostics": [], "source_truth_notes": ""},
        ]
    )
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    item = result.claims[0]
    assert item.outcome == "failed_verification"
    assert item.final_claim == ""
    assert len(item.correction_attempts) == 2
    assert len(item.verification_attempts) == 1


def test_multi_page_binding_renders_and_sends_each_complete_page(tmp_path):
    claim = _claim("candidate-1", "Original claim")
    claim["pages"] = [5, 6]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {"outcome": "verified", "diagnostics": [], "source_truth_notes": "matches"},
        ]
    )
    render_calls = []
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, render_calls, requests),
    )

    assert result.claims[0].outcome == "verified"
    assert result.claims[0].physical_pages == [5, 6]
    assert [call.page for call in render_calls] == [4, 5]
    assert requests[0].image_paths == [
        str(tmp_path / "report/crop_refine_pages/page-4.png"),
        str(tmp_path / "report/crop_refine_pages/page-5.png"),
    ]
    assert requests[1].image_paths == requests[0].image_paths
