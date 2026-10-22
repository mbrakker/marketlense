"""Phase 2 semantic-authority and wrong-page visual regressions."""

from __future__ import annotations

import hashlib

from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims

from .cases_01_visual import _claim, _ctx, _dependencies, _request, _settings


def test_strict_policy_uses_visual_verification_for_relevance(tmp_path):
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
                "outcome": "rejected",
                "diagnostics": ["visual_relevance_conflict"],
                "source_truth_notes": (
                    "The page reports a different checkout metric and population."
                ),
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
            },
            {
                "claim": "63% abandoned carts when unable to check out as a guest.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "rejected",
                "diagnostics": ["visual_relevance_conflict"],
                "source_truth_notes": (
                    "The page reports a different checkout metric and population."
                ),
                "supporting_physical_pages": [],
                "source_truth_notes_by_page": {},
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
        "verification_strict_direction_drift" not in attempt.diagnostics
        for attempt in item.verification_attempts
    )


def test_visual_verifier_decides_strict_claim_relevance(tmp_path):
    """A Luna verification pass is not replaced by token-overlap scoring."""

    claim = _claim("strict-visual-authority", "Retained analytical direction")
    claim["_visual_replacement_policy"] = "strict_original_direction"
    claim["evidence_spans"] = [
        {
            "evidence_id": "f1",
            "page": 5,
            "text": "The retained source describes a market transition.",
        }
    ]
    responses = iter(
        [
            {
                "claim": (
                    "The source-supported market transition creates a focused action."
                ),
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The complete page shows the market transition and the stated "
                    "relationship supports the corrected analytical conclusion."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "The complete page shows the market transition and the "
                        "stated relationship supports the conclusion."
                    )
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
    assert item.final_claim == (
        "The source-supported market transition creates a focused action."
    )
    assert all(
        "verification_strict_direction_drift" not in attempt.diagnostics
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


def test_materially_rewritten_claim_does_not_retain_original_metric_binding(tmp_path):
    claim = _claim(
        "revenue-incentive-58",
        "The platform receives 58% of revenue from incentive-driven activity.",
    )
    claim["evidence_id"] = "ch2-revenue-incentive"
    claim["evidence_spans"] = [
        {
            "evidence_id": "ch2-revenue-incentive",
            "page": 5,
            "start": 10,
            "end": 20,
        }
    ]
    claim["metric"] = {
        "label": "Revenue share",
        "value": "58%",
        "unit": "%",
        "subject": "Platform revenue",
        "cohort": "Incentive-driven activity",
        "timeframe": "Observed period",
        "observation_status": "observed",
    }
    responses = iter(
        [
            {
                "claim": (
                    "Investment represented 53% of the mix, while 39% was "
                    "allocated to growth."
                ),
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Physical page 5 reports the investment and growth shares for "
                    "the named mix; the original revenue proposition is not the "
                    "page's metric."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "Physical page 5 reports the investment and growth shares "
                        "for the named mix."
                    )
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
    assert item.final_claim.startswith("Investment represented 53%")
    assert item.evidence_ids == ["ch2-revenue-incentive"]
    assert item.original_metric_binding["value"] == "58%"
    assert item.corrected_evidence_ids == []
    assert item.corrected_evidence_spans == []
    assert item.corrected_metric_binding == {}
    assert item.corrected_source_binding_status == "unbound"


def test_identical_verified_claim_retains_authoritative_corrected_binding(tmp_path):
    claim = _claim("candidate-1", "The source reports 61% adoption among video users.")
    claim["metric"] = {
        "label": "Adoption",
        "value": "61%",
        "unit": "%",
        "cohort": "Video users",
    }
    responses = iter(
        [
            {
                "claim": "The source reports 61% adoption among video users.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Physical page 5 reports the 61% adoption result for the "
                    "named video-user cohort."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "Physical page 5 reports the 61% adoption result for the "
                        "named video-user cohort."
                    )
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
    assert item.corrected_source_binding_status == "retained"
    assert item.corrected_evidence_ids == ["f1"]
    assert item.corrected_evidence_spans == item.evidence_spans
    assert item.corrected_metric_binding == item.original_metric_binding


def test_verified_result_carries_independent_fact_after_metric_replacement(tmp_path):
    claim = _claim(
        "candidate-1",
        "The source reports 58% revenue share for incentive-driven activity.",
    )
    claim["metric"] = {
        "label": "Revenue share",
        "value": "58%",
        "unit": "%",
        "cohort": "Incentive-driven activity",
    }
    verified_metric = {
        "label": "Investment mix",
        "value": "53%",
        "unit": "%",
        "trend": "",
        "timeframe": "2026",
        "geography": "global",
        "segment": "investment mix",
        "sample_size": "",
        "confidence": "source_backed",
        "subject": "investment",
        "cohort": "reported mix",
        "denominator": "reported mix",
        "observation_status": "observed",
    }
    responses = iter(
        [
            {
                "claim": "Investment represented 53% of the mix.",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Physical page 5 reports 53% for investment in the named "
                    "reported mix, not the original revenue-share metric."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "Physical page 5 reports 53% for investment in the named "
                        "reported mix."
                    )
                },
                "verified_fact": {
                    "statement": "Investment represented 53% of the mix.",
                    "metric": verified_metric,
                    "qualifiers": ["Observed reported mix."],
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
    assert item.verified_fact["statement"] == "Investment represented 53% of the mix."
    assert item.verified_fact["metric"] == verified_metric
    assert item.verified_fact["metric"] != item.original_metric_binding
    assert (
        item.verified_fact["source_pdf_sha256"]
        == hashlib.sha256((tmp_path / "source.pdf").read_bytes()).hexdigest()
    )
    assert item.verified_fact["supporting_physical_pages"] == [5]


def test_malformed_verification_response_can_use_one_bounded_retry(tmp_path):
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            None,
            {
                "claim": "Corrected claim after retry",
                "status": "corrected",
                "issues": [],
            },
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "Physical page 5 confirms the corrected value and the named "
                    "cohort relationship."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "Physical page 5 confirms the corrected value and the "
                        "named cohort relationship."
                    )
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [_claim("candidate-1", "Original claim")]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "verified_after_retry"
    assert len(item.correction_attempts) == 2
    assert len(item.verification_attempts) == 2
    assert "verification_response_invalid" in item.verification_attempts[0].diagnostics
    assert (
        "verification_response_malformed" in item.verification_attempts[0].diagnostics
    )


def test_generic_verification_explanation_is_not_substantive(tmp_path):
    responses = iter(
        [
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "The claim is supported by the source.",
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The claim is supported by the source."
                },
            },
            {"claim": "Corrected claim", "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "The claim is supported by the source.",
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": "The claim is supported by the source."
                },
            },
        ]
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, [_claim("candidate-1", "Original claim")]),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], []),
    )

    item = result.claims[0]
    assert item.outcome == "failed_verification"
    assert all(
        "verification_explanation_insubstantial" in attempt.diagnostics
        for attempt in item.verification_attempts
    )


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


def test_visual_verifier_rejects_wrong_page_without_native_text_veto(tmp_path):
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
    rejection = {
        "outcome": "rejected",
        "diagnostics": ["visual_source_page_conflict"],
        "source_truth_notes": (
            "The inspected page supports guest checkout abandonment, not the "
            "retained preferred-wallet finding."
        ),
        "supporting_physical_pages": [],
        "source_truth_notes_by_page": {},
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
    assert item.failure_reason == "verification_failed_twice"
    assert all(
        "verification_strict_source_page_mismatch" not in attempt.diagnostics
        for attempt in item.verification_attempts
    )
    assert item.original_physical_pages == [8]
    assert item.evidence_spans == claim["evidence_spans"]


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
        "diagnostics": ["visual_source_page_conflict"],
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
