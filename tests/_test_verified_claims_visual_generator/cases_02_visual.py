from __future__ import annotations

from types import SimpleNamespace

from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from src.utils.errors import AppError

from .cases_01_visual import _claim, _ctx, _dependencies, _request, _settings


def test_verified_outcome_requires_structural_source_truth_notes(tmp_path):
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
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            },
            {"claim": "Corrected claim again", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "",
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            },
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
    assert result.claims[0].failure_reason == "verification_failed_twice"
    assert (
        "verification_supporting_pages_invalid"
        in result.claims[0].verification_attempts[0].diagnostics
    )
    assert (
        "verification_explanation_missing"
        in result.claims[0].verification_attempts[1].diagnostics
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
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
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
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
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
    assert item.failure_reason == "verification_failed_twice"
    assert item.inspected_physical_pages == [5, 7]
    assert item.recovered_physical_pages == [7]
    assert item.source_binding_status == "retained"
    assert len(item.verification_attempts) == 2
    assert all(
        "verification_supporting_pages_invalid" in attempt.diagnostics
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


def test_recovery_accepts_visually_supported_original_page_with_irrelevant_candidate(
    tmp_path,
):
    claims = [
        _claim(
            "mobile-wallet-cart-abandonment",
            "40% of shoppers abandoned a cart when their preferred wallet method "
            "was unavailable.",
            page=4,
        )
    ]
    claims[0]["_visual_replacement_policy"] = "report_level_replacement_allowed"
    claims[0]["metric"] = {"value": "40%", "cohort": "shoppers"}
    request = _request(tmp_path, claims)
    request.recovery_enabled = True
    request.recovery_candidates = {
        "mobile-wallet-cart-abandonment": [
            {
                "physical_page": 2,
                "source_identity": request.source_identity,
                "reason": "retained_page_irrelevant_or_insufficient",
                "evidence_id": "provisional-methodology",
            }
        ]
    }
    request.source_page_text_by_physical_page = {
        4: "4",
        2: "Methodology and respondent segments.",
    }
    responses = iter(
        [
            {
                "claim": claims[0]["text"],
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Physical page 4 reports the 40% cart-abandonment result for "
                    "shoppers who could not use their preferred wallet method."
                ),
                "supporting_physical_pages": [4],
                "source_truth_notes_by_page": {
                    "4": (
                        "Physical page 4 reports the 40% cart-abandonment result "
                        "for shoppers who could not use their preferred wallet method."
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
    assert item.outcome == "verified"
    assert item.supporting_physical_pages == [4]
    assert item.original_physical_pages == [4]
    assert item.recovered_physical_pages == [2]
    assert all(
        "verification_supporting_page_not_recovery_candidate" not in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_recovery_rejects_uninspected_support_page(tmp_path):
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
                    "An uninspected page reports the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [6],
                "source_truth_notes_by_page": {
                    "6": "Page 6 reports the corrected value and cohort relationship."
                },
            },
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "An uninspected page reports the corrected value and cohort "
                    "relationship."
                ),
                "supporting_physical_pages": [6],
                "source_truth_notes_by_page": {
                    "6": "Page 6 reports the corrected value and cohort relationship."
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
        "verification_supporting_pages_invalid" in attempt.diagnostics
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
