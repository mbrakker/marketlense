from __future__ import annotations

from types import SimpleNamespace

from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from src.utils.errors import AppError

from .cases_01_visual import _claim, _ctx, _dependencies, _request, _settings


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
    assert item.source_binding_status == "retained"
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


def test_strict_policy_rejects_unrelated_corrected_metric(tmp_path):
    claim = _claim(
        "strict-drift",
        "40% of shoppers abandoned a cart after losing their preferred wallet method.",
    )
    claim["_visual_replacement_policy"] = "strict_original_direction"
    claim["evidence_id"] = "wallet-abandonment"
    claim["evidence_spans"] = [
        {
            "evidence_id": "wallet-abandonment",
            "page": 5,
            "text": (
                "40% of shoppers abandoned a cart after losing their preferred "
                "wallet method."
            ),
        }
    ]
    responses = iter(
        [
            {
                "claim": "63% abandoned carts when unable to check out as a guest.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports a different checkout metric and population."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports a different checkout metric and population."
                },
            },
            {
                "claim": "63% abandoned carts when unable to check out as a guest.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports a different checkout metric and population."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports a different checkout metric and population."
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
    assert item.outcome == "failed_verification"
    assert all(
        "verification_strict_direction_drift" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


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


def _strict_wallet_claim(candidate_id="strict-wallet", page=8):
    return {
        "candidate_id": candidate_id,
        "text": (
            "40% of shoppers abandoned a cart after finding they could not use "
            "their preferred wallet method."
        ),
        "evidence_id": "preferred-wallet-abandonment",
        "evidence": (
            "40% have abandoned a cart after finding they cannot use their "
            "preferred wallet method."
        ),
        "evidence_spans": [
            {
                "evidence_id": "preferred-wallet-abandonment",
                "source_pack": "findings",
                "page": page,
                "text": (
                    "40% have abandoned a cart after finding they cannot use "
                    "their preferred wallet method."
                ),
            }
        ],
        "pages": [page],
        "_visual_replacement_policy": "strict_original_direction",
    }


def _verified_wallet_response(page=8):
    note = (
        "The page reports the 40% wallet-abandonment response for the stated "
        "shopper population and checkout condition."
    )
    return {
        "outcome": "verified",
        "diagnostics": [],
        "source_truth_notes": note,
        "supporting_physical_pages": [page],
        "source_truth_notes_by_page": {str(page): note},
    }


def test_strict_wrong_page_excerpt_cannot_be_verified_from_another_page(tmp_path):
    claim = _strict_wallet_claim()
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        8: (
            "Digital Natives report that 63% abandoned a cart when unable to "
            "check out as a guest."
        ),
        4: (
            "40% have abandoned a cart after finding they cannot use their "
            "preferred wallet method."
        ),
    }
    responses = iter(
        [
            {"claim": claim["text"], "status": "corrected", "issues": []},
            _verified_wallet_response(),
            {"claim": claim["text"], "status": "corrected", "issues": []},
            _verified_wallet_response(),
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
    assert len(item.verification_attempts) == 2
    assert all(
        "verification_strict_source_page_mismatch" in attempt.diagnostics
        for attempt in item.verification_attempts
    )
    assert item.original_physical_pages == [8]
    assert item.evidence_spans == claim["evidence_spans"]
    assert item.supporting_physical_pages == []


def test_strict_verifier_rejection_remains_fail_closed_with_original_binding(
    tmp_path,
):
    claim = _strict_wallet_claim()
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        8: "63% abandoned a cart when unable to check out as a guest.",
        4: (
            "40% have abandoned a cart after finding they cannot use their "
            "preferred wallet method."
        ),
    }
    rejection_note = (
        "Page 8 supports guest checkout abandonment, while the retained wallet "
        "excerpt is located on page 4."
    )
    rejection = {
        "outcome": "rejected",
        "diagnostics": ["verification_strict_source_page_mismatch"],
        "source_truth_notes": rejection_note,
        "supporting_physical_pages": [8],
        "source_truth_notes_by_page": {
            "8": "Page 8 supports guest checkout abandonment, not wallet abandonment."
        },
    }
    responses = iter(
        [
            {"claim": claim["text"], "status": "corrected", "issues": []},
            rejection,
            {"claim": claim["text"], "status": "corrected", "issues": []},
            rejection,
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
    assert item.original_physical_pages == [8]
    assert item.evidence_ids == ["preferred-wallet-abandonment"]
    assert item.evidence_spans == claim["evidence_spans"]
    assert item.supporting_physical_pages == []
    assert all(
        not attempt.supporting_physical_pages and not attempt.source_truth_notes_by_page
        for attempt in item.verification_attempts
    )


def test_strict_claim_supported_on_retained_page_remains_verified(tmp_path):
    claim = _strict_wallet_claim()
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        8: (
            "40% have abandoned a cart after finding they cannot use their "
            "preferred wallet method."
        )
    }
    responses = iter(
        [
            {"claim": claim["text"], "status": "corrected", "issues": []},
            _verified_wallet_response(),
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].outcome == "verified"
    assert result.claims[0].supporting_physical_pages == [8]


def test_strict_page_mismatch_guard_is_conservative_when_native_text_is_incomplete(
    tmp_path,
):
    claim = _strict_wallet_claim()
    request = _request(tmp_path, [claim])
    request.source_page_text_by_physical_page = {
        4: (
            "40% have abandoned a cart after finding they cannot use their "
            "preferred wallet method."
        )
    }
    responses = iter(
        [
            {"claim": claim["text"], "status": "corrected", "issues": []},
            _verified_wallet_response(),
        ]
    )

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    assert result.claims[0].outcome == "verified"


def test_visual_prompts_do_not_present_retained_span_text_as_source_proof(tmp_path):
    claim = _claim("prompt-binding", "Original direction")
    claim["evidence_spans"] = [
        {
            "evidence_id": "f1",
            "source_pack": "findings",
            "page": 5,
            "start": 10,
            "end": 20,
            "text": "unverified retained excerpt must not be source proof",
        }
    ]
    requests = []
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The page reports the corrected value for the named cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The page reports the corrected value for the named cohort."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [claim]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    assert result.claims[0].outcome == "verified"
    assert result.claims[0].evidence_spans == claim["evidence_spans"]
    assert len(requests) == 2
    assert all(
        "unverified retained excerpt must not be source proof"
        not in request.user_prompt
        for request in requests
    )
    assert all('"evidence_id": "f1"' in request.user_prompt for request in requests)
