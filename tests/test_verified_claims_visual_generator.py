from __future__ import annotations

import copy
import hashlib
import re
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import VisualClaimEvaluationResult
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.errors import AppError


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
    assert "different topic" in correction.system.text.lower()
    assert "different, relevant" in correction.system.text.lower()
    assert "qualitative conclusion" in correction.system.text.lower()
    assert "relevant source-supported metric" in correction.system.text.lower()
    assert "replacement_policy" in correction.system.text
    assert "report_level_replacement_allowed" in correction.system.text
    assert "bounded pattern" in verification.system.text.lower()
    assert "nested cohort" in verification.system.text.lower()
    assert "recovery_sources" in verification.system.text
    assert "recovered physical pages" in verification.system.text
    assert "component totals" in correction.system.text.lower()
    assert "image-to-page" in verification.user.text.lower()


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
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"test-pdf")
    pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return SimpleNamespace(
        schema_version="1.0",
        pdf_path=str(pdf_path),
        output_dir=str(tmp_path),
        report_name="report",
        source_identity=f"report|pdf-sha256:{pdf_sha256}",
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
        payload = next(responses)
        if (
            isinstance(payload, dict)
            and payload.get("outcome") == "verified"
            and isinstance(payload.get("source_truth_notes"), str)
            and payload.get("source_truth_notes").strip()
            and "supporting_physical_pages" not in payload
            and "source_truth_notes_by_page" not in payload
        ):
            pages = [
                int(match.group(1)) + 1
                for match in re.finditer(
                    r"page-(\d+)\.png", " ".join(request.image_paths)
                )
            ]
            payload = {
                **payload,
                "supporting_physical_pages": pages,
                "source_truth_notes_by_page": {
                    str(page): payload["source_truth_notes"] for page in pages
                },
            }
        return SimpleNamespace(
            parsed_json=payload,
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
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
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
    assert "Original claim" in requests[1].user_prompt


def test_first_unresolved_correction_receives_one_bounded_retry(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "", "status": "unresolved", "issues": ["ambiguous"]},
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
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
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
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


def test_verifier_receives_original_direction_and_keeps_authoritative_binding(
    tmp_path,
):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
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
    assert item.outcome == "verified"
    assert item.final_claim == "Corrected claim"
    assert item.candidate_id == "candidate-1"
    assert item.source_identity.startswith("report|pdf-sha256:")
    assert item.physical_page == 5
    assert item.evidence_ids == ["f1"]
    assert item.evidence_spans == claims[0]["evidence_spans"]
    assert "Original claim" in requests[0].user_prompt
    assert "Original claim" in requests[1].user_prompt
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
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
            },
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


def test_visual_prompt_labels_each_image_with_one_based_physical_page(tmp_path):
    claim = _claim("candidate-1", "Original claim")
    claim["pages"] = [14, 15]
    claim["evidence_spans"] = [
        {"evidence_id": "f1", "page": 14, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 15, "start": 10, "end": 20},
    ]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart page confirms the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [15],
                "source_truth_notes_by_page": {
                    "15": (
                        "The chart page confirms the corrected value and cohort "
                        "relationship."
                    )
                },
            },
        ]
    )
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    assert result.claims[0].outcome == "verified"
    assert "image 1 = physical PDF page 14" in requests[0].user_prompt
    assert "image 2 = physical PDF page 15" in requests[0].user_prompt
    assert "image 1 = physical PDF page 14" in requests[1].user_prompt
    assert "image 2 = physical PDF page 15" in requests[1].user_prompt


def test_wrong_support_page_fails_closed_when_another_inspected_page_has_claim_values(
    tmp_path,
):
    claim = _claim("candidate-1", "Original claim", page=14)
    claim["pages"] = [14, 15]
    claim["evidence_spans"] = [
        {"evidence_id": "f1", "page": 14, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 15, "start": 10, "end": 20},
    ]
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        14: "Targeting Super Users will be critical to growth strategies.",
        15: (
            "Video time and spend relative to share of users, U.S., 2017. "
            "Top 25% of users 61% of time and 34% of consumer spend. "
            "All other users 39% of time and 66% of consumer spend."
        ),
    }
    responses = iter(
        [
            {
                "claim": "The top 25% account for 61% of time and 34% of spend.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart values support the corrected cohort comparison."
                ),
                "supporting_physical_pages": [14],
                "source_truth_notes_by_page": {
                    "14": "The chart values support the corrected cohort comparison."
                },
            },
            {
                "claim": "The top 25% account for 61% of time and 34% of spend.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart values support the corrected cohort comparison."
                ),
                "supporting_physical_pages": [14],
                "source_truth_notes_by_page": {
                    "14": "The chart values support the corrected cohort comparison."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "unresolved"
    assert item.failure_reason == "verification_supporting_page_attribution_conflict"
    assert len(item.verification_attempts) == 2
    assert all(
        "verification_supporting_page_attribution_conflict" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_partial_numeric_overlap_does_not_bypass_page_attribution_conflict(tmp_path):
    claim = _claim("candidate-1", "Original claim", page=14)
    claim["pages"] = [14, 15]
    claim["evidence_spans"] = [
        {"evidence_id": "f1", "page": 14, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 15, "start": 10, "end": 20},
    ]
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        14: "Top users account for 61% of time, while the page omits the spend split.",
        15: "Top users account for 61% of time and 34% of consumer spend.",
    }
    responses = iter(
        [
            {
                "claim": "The top users account for 61% of time and 34% of spend.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart supports the corrected time and spend relationship "
                    "for the identified top-user cohort."
                ),
                "supporting_physical_pages": [14],
                "source_truth_notes_by_page": {
                    "14": (
                        "The chart supports the corrected time and spend relationship "
                        "for the identified top-user cohort."
                    )
                },
            },
            {
                "claim": "The top users account for 61% of time and 34% of spend.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart supports the corrected time and spend relationship "
                    "for the identified top-user cohort."
                ),
                "supporting_physical_pages": [14],
                "source_truth_notes_by_page": {
                    "14": (
                        "The chart supports the corrected time and spend relationship "
                        "for the identified top-user cohort."
                    )
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "unresolved"
    assert item.failure_reason == "verification_supporting_page_attribution_conflict"


def test_multi_page_numeric_attribution_uses_combined_cited_pages(tmp_path):
    claim = _claim("candidate-1", "Original claim", page=14)
    claim["pages"] = [14, 15]
    claim["evidence_spans"] = [
        {"evidence_id": "f1", "page": 14, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 15, "start": 10, "end": 20},
    ]
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        14: "Top users account for 61% of time.",
        15: "Top users account for 34% of consumer spend.",
    }
    responses = iter(
        [
            {
                "claim": "The top users account for 61% of time and 34% of spend.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The two chart pages together support the corrected time and "
                    "spend relationship for the identified top-user cohort."
                ),
                "supporting_physical_pages": [14, 15],
                "source_truth_notes_by_page": {
                    "14": "The time share is shown on this page.",
                    "15": "The spend share is shown on this page.",
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].outcome == "verified"


def test_empty_render_path_fails_closed_without_model_call(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    requests = []
    base = _dependencies(iter(()), [], requests)
    dependencies = base.__class__(
        load_prompt_set=base.load_prompt_set,
        render_prompt=base.render_prompt,
        render_page_for_crop_refine=lambda _request, _ctx: SimpleNamespace(
            image_path=""
        ),
        openai_chat_json_with_images=base.openai_chat_json_with_images,
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=dependencies,
    )

    assert result.claims[0].outcome == "skipped"
    assert result.claims[0].failure_reason == "page_render_failed"
    assert requests == []


def test_pdf_hash_mismatch_fails_closed_before_visual_calls(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    requests = []
    request = _request(tmp_path, claims)
    request.source_identity = f"report|pdf-sha256:{'0' * 64}"

    with pytest.raises(AppError, match="(?i)source PDF hash") as error:
        evaluate_shortlisted_claims(
            request=request,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            dependencies=_dependencies(iter(()), [], requests),
        )

    assert error.value.code == "verified_claims_source_pdf_hash_mismatch"
    assert requests == []


def test_conflicting_span_page_is_skipped_and_next_claim_continues(tmp_path):
    first = _claim("candidate-1", "First claim", page=5)
    first["pages"] = [5]
    first["evidence_spans"][0]["page"] = 6
    second = _claim("candidate-2", "Second claim", page=5)
    responses = iter(
        [
            {"claim": "Second corrected", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page and chart labels support the corrected claim."
                ),
            },
        ]
    )
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [first, second]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    assert result.claims[0].outcome == "skipped"
    assert result.claims[0].failure_reason == "source_binding_conflict"
    assert result.claims[1].outcome == "verified"


def test_conflicting_claim_source_identity_fails_closed(tmp_path):
    claim = _claim("candidate-1", "Original claim")
    claim["source_identity"] = "other-report|pdf-sha256:" + "1" * 64
    requests = []

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(iter(()), [], requests),
    )

    assert result.claims[0].outcome == "skipped"
    assert result.claims[0].failure_reason == "source_binding_conflict"
    assert requests == []


def test_doc_map_only_claim_page_is_eligible_for_provisional_visual_inspection(
    tmp_path,
):
    claim = _claim("doc-map-only", "Original claim")
    claim["evidence_spans"][0]["source_pack"] = "doc_map"
    requests = []
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page shows the corrected metric and cohort relationship."
                ),
            },
        ]
    )
    dependencies = _dependencies(responses, [], requests)

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=dependencies,
    )

    assert result.claims[0].outcome == "verified"
    assert result.claims[0].evidence_ids == ["f1"]
    assert result.claims[0].evidence_spans == claim["evidence_spans"]
    assert len(requests) == 2


def test_verified_outcome_requires_substantive_source_truth_notes(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The claim is plausible and supported by the source page."
                ),
            },
            {"claim": "Corrected claim again", "status": "corrected", "issues": []},
            {"outcome": "verified", "diagnostics": [], "source_truth_notes": ""},
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].outcome == "failed_verification"
    assert len(result.claims[0].verification_attempts) == 2
    assert all(
        "verification_explanation_missing" in attempt.diagnostics
        for attempt in result.claims[0].verification_attempts
    )


def test_heading_only_qualitative_rewrite_is_not_verified(tmp_path):
    claims = [_claim("candidate-1", "Original qualitative claim")]
    claims[0]["_visual_replacement_policy"] = "report_level_replacement_allowed"
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [
            {
                "physical_page": 7,
                "source_identity": request.source_identity,
                "reason": "retained_page_is_section_divider",
                "score": 10,
            }
        ]
    }
    responses = iter(
        [
            {
                "claim": "The page frames this as a strategic priority.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page is only a section divider with no explanatory text."
                ),
            },
            {
                "claim": "The page frames this as a strategic priority.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page is only a section divider with no explanatory text."
                ),
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "unresolved"
    assert item.failure_reason == "verification_claim_not_substantive"
    assert item.inspected_physical_pages == [5, 7]
    assert item.recovered_physical_pages == [7]
    assert item.source_binding_status == "provisional_recovered"
    assert len(item.verification_attempts) == 2
    assert all(
        "verification_claim_not_substantive" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_typed_provider_error_details_are_retained(tmp_path):
    claims = [_claim("candidate-1", "Original claim")]

    def raising_model(request, _ctx):
        raise AppError(
            code="llm_budget_exceeded",
            message="budget exceeded",
            retryable=False,
            severity="warning",
        )

    base = _dependencies(iter(()), [], [])
    dependencies = base.__class__(
        load_prompt_set=base.load_prompt_set,
        render_prompt=base.render_prompt,
        render_page_for_crop_refine=base.render_page_for_crop_refine,
        openai_chat_json_with_images=raising_model,
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=dependencies,
    )

    assert result.claims[0].outcome == "unresolved"
    assert len(result.claims[0].correction_attempts) == 1
    assert (
        "error_code:llm_budget_exceeded"
        in result.claims[0].correction_attempts[0].issues
    )
    assert "retryable:false" in result.claims[0].correction_attempts[0].issues


def test_non_retryable_verification_error_does_not_retry_and_next_claim_runs(tmp_path):
    claims = [_claim("candidate-1", "First"), _claim("candidate-2", "Second")]
    base = _dependencies(iter(()), [], [])
    calls = 0

    def model(request, _ctx):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppError(
                code="llm_provider_configuration_invalid",
                message="invalid provider configuration",
                retryable=False,
                severity="error",
            )
        if calls in {1, 3}:
            return SimpleNamespace(
                parsed_json={"claim": "Corrected", "status": "corrected", "issues": []},
                request_id=f"request-{calls}",
                model=request.model,
            )
        return SimpleNamespace(
            parsed_json={
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The source page confirms the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "The source page confirms the corrected value and cohort "
                        "relationship."
                    )
                },
            },
            request_id=f"request-{calls}",
            model=request.model,
        )

    dependencies = base.__class__(
        load_prompt_set=base.load_prompt_set,
        render_prompt=base.render_prompt,
        render_page_for_crop_refine=base.render_page_for_crop_refine,
        openai_chat_json_with_images=model,
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=dependencies,
    )

    assert [item.outcome for item in result.claims] == ["unresolved", "verified"]
    assert result.claims[0].failure_reason == "verification_non_retryable"
    assert len(result.claims[0].correction_attempts) == 1
    assert len(result.claims[0].verification_attempts) == 1
    assert len(result.claims[1].correction_attempts) == 1
    assert len(result.claims[1].verification_attempts) == 1
    assert calls == 4


def test_real_recovery_inspects_new_pages_but_keeps_original_binding(tmp_path):
    claims = [_claim("candidate-1", "Original direction")]
    claims[0]["_visual_replacement_policy"] = "report_level_replacement_allowed"
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [
            {
                "physical_page": 7,
                "source_identity": request.source_identity,
                "reason": "retained_page_is_section_divider",
                "evidence_id": "recovered-finding",
                "text": "The source reports a supported 73% adoption measure.",
            }
        ]
    }
    responses = iter(
        [
            {
                "claim": "Supported 73% adoption result",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The recovered page reports the 73% adoption measure for the "
                    "named population and supports the corrected conclusion."
                ),
                "supporting_physical_pages": [7],
                "source_truth_notes_by_page": {
                    "7": (
                        "Page 7 reports the 73% adoption measure for the named "
                        "population and supports the corrected conclusion."
                    )
                },
            },
        ]
    )
    render_calls = []
    requests = []

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, render_calls, requests),
    )

    item = result.claims[0]
    assert item.outcome == "verified"
    assert item.original_physical_pages == [5]
    assert item.physical_pages == [5]
    assert item.inspected_physical_pages == [5, 7]
    assert item.recovered_physical_pages == [7]
    assert item.recovery_reason == "retained_page_is_section_divider"
    assert item.source_binding_status == "provisional_recovered"
    assert item.evidence_ids == ["f1"]
    assert item.evidence_spans == claims[0]["evidence_spans"]
    assert [call.page for call in render_calls] == [4, 6]
    assert requests[0].image_paths == [
        str(tmp_path / "report/crop_refine_pages/page-4.png"),
        str(tmp_path / "report/crop_refine_pages/page-6.png"),
    ]


def test_recovery_cannot_verify_using_only_retained_page_support(tmp_path):
    claims = [_claim("candidate-1", "Original direction")]
    claims[0]["_visual_replacement_policy"] = "report_level_replacement_allowed"
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [
            {"physical_page": 7, "reason": "retained_page_is_section_divider"}
        ]
    }
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The retained page reports the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "Page 5 reports the corrected value and cohort relationship."
                },
            },
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The retained page reports the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "Page 5 reports the corrected value and cohort relationship."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "failed_verification"
    assert item.supporting_physical_pages == []
    assert all(
        "verification_supporting_page_not_recovery_candidate" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_recovery_preserves_source_supported_retained_page(tmp_path):
    claims = [_claim("candidate-1", "Original direction")]
    claims[0]["_visual_replacement_policy"] = "report_level_replacement_allowed"
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [
            {"physical_page": 7, "reason": "retained_page_is_section_divider"}
        ]
    }
    request.source_page_text_by_physical_page = {
        5: "The source reports a 61% adoption result for video users.",
        7: "Methodology and definitions.",
    }
    responses = iter(
        [
            {
                "claim": "The source reports a 61% adoption result for video users.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The retained physical page reports the 61% adoption result "
                    "for the named video-user cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports the 61% adoption result for video users."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "verified"
    assert item.supporting_physical_pages == [5]
    assert item.recovered_physical_pages == [7]
    assert all(
        "verification_supporting_page_not_recovery_candidate" not in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_recovery_is_disabled_for_reference_style_requests(tmp_path):
    claims = [_claim("candidate-1", "Original direction")]
    claims[0]["_visual_replacement_policy"] = "strict_original_direction"
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [{"physical_page": 7, "reason": "should_not_be_used"}]
    }
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The retained source page confirms the corrected relationship "
                    "for the stated population."
                ),
            },
        ]
    )
    render_calls = []
    requests = []

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, render_calls, requests),
    )

    assert result.claims[0].outcome == "verified"
    assert [call.page for call in render_calls] == [4]
    assert requests[0].image_paths == [
        str(tmp_path / "report/crop_refine_pages/page-4.png")
    ]


def test_verified_result_records_only_inspected_supporting_pages_and_page_notes(
    tmp_path,
):
    claims = [_claim("candidate-1", "Original direction")]
    request = _request(tmp_path, claims)
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Page 5 reports the corrected value for the named cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports the corrected value for the named cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "verified"
    assert item.supporting_physical_pages == [5]
    assert item.source_truth_notes_by_page == {
        "5": "The page reports the corrected value for the named cohort."
    }
    assert item.verification_attempts[0].supporting_physical_pages == [5]


def test_verified_result_can_attribute_one_support_page_from_multiple_inspected_pages(
    tmp_path,
):
    claim = _claim("candidate-1", "Original direction")
    claim["pages"] = [5, 6]
    claim["evidence_spans"] = [
        {"evidence_id": "f1", "page": 5, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 6, "start": 10, "end": 20},
    ]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Page 6 reports the corrected value for the named cohort."
                ),
                "supporting_physical_pages": [6],
                "source_truth_notes_by_page": {
                    "6": "The page reports the corrected value for the named cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "verified"
    assert item.inspected_physical_pages == [5, 6]
    assert item.supporting_physical_pages == [6]


def test_uninspected_supporting_page_fails_closed(tmp_path):
    claims = [_claim("candidate-1", "Original direction")]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports the corrected value and cohort."
                ),
                "supporting_physical_pages": [6],
                "source_truth_notes_by_page": {
                    "6": "The page reports the corrected value and cohort."
                },
            },
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports the corrected value and cohort."
                ),
                "supporting_physical_pages": [6],
                "source_truth_notes_by_page": {
                    "6": "The page reports the corrected value and cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "failed_verification"
    assert item.supporting_physical_pages == []
    assert all(
        "verification_supporting_pages_invalid" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_top_level_plural_evidence_ids_are_preserved(tmp_path):
    claim = _claim("candidate-1", "Original direction")
    claim.pop("evidence_id")
    claim["evidence_ids"] = ["f1", "f2"]
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports the corrected value and cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports the corrected value and cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].evidence_ids == ["f1", "f2"]


def test_recovery_requires_explicit_report_level_replacement_policy(tmp_path):
    claim = _claim("candidate-1", "Original direction")
    request = _request(tmp_path, [claim])
    request.recovery_enabled = True
    request.recovery_candidates = {
        "candidate-1": [
            {
                "physical_page": 7,
                "source_identity": request.source_identity,
                "reason": "retained_page_is_section_divider",
            }
        ]
    }
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The retained page reports the corrected value and cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The retained page reports the corrected value and cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].inspected_physical_pages == [5]
