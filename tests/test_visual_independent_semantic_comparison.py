from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from src.contracts.run_budget import RunBudget
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _claim,
    _ctx,
    _request,
    _settings,
)


@dataclass(frozen=True)
class ComparisonDependencies(VerifiedClaimsVisualDependencies):
    # The future evaluator must inject the canonical text-only service here.
    openai_chat_json: Callable[..., Any] | None = None


SOURCE_TEXT = "Among surveyed firms, 62% increased investment and 38% decreased it."
REVERSED_CLAIM = "Most surveyed firms decreased investment."
INTERPRETATION = (
    "Investment expansion was more common than retrenchment among surveyed firms."
)
ORIGINAL = "ORIGINAL CANDIDATE PRIVATE SENTINEL"


def _run(tmp_path, claim_text, verdict, *, run_budget=None):
    request = _request(tmp_path, [_claim("candidate", ORIGINAL)])
    reading = {
        "schema_version": "1.0",
        "source_identity": request.source_identity,
        "request_id": "reading-id",
        "model": "gpt-6-luna",
        "pages": [
            {"physical_page": 5, "observations": [SOURCE_TEXT], "uncertainties": []}
        ],
    }
    calls = []

    def render_page(render_request, _ctx):
        return SimpleNamespace(image_path=f"report/page-{render_request.page}.png")

    def image_model(model_request, _ctx):
        calls.append(("image", model_request))
        namespace = model_request.prompt_namespace
        if namespace.endswith("visual_source_reading"):
            payload = {"status": "read", "pages": reading["pages"]}
            request_id = "reading-id"
        elif namespace.endswith("visual_claim_correction"):
            payload = {"status": "corrected", "claim": claim_text, "issues": []}
            request_id = "correction-id"
        elif namespace.endswith("visual_claim_verification"):
            payload = {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The complete source page supports the corrected claim for the "
                    "surveyed firms and the stated investment direction."
                ),
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {
                    "5": (
                        "The complete source page supports the corrected claim for "
                        "the surveyed firms and the stated investment direction."
                    )
                },
                "verified_fact": {
                    "statement": claim_text,
                    "metric": {"methodology": {"scope": "FACT METHOD SENTINEL"}},
                    "qualifiers": ["FACT QUALIFIER SENTINEL"],
                },
                "source_reading_assessment": {
                    "outcome": "supported",
                    "supporting_physical_pages": [5],
                    "explanation": "The visual verifier accepted it.",
                },
            }
            request_id = "verifier-id"
        else:
            pytest.fail(f"Unexpected image model call: {namespace}")
        return SimpleNamespace(
            parsed_json=payload, request_id=request_id, model=model_request.model
        )

    def text_model(model_request, _ctx):
        calls.append(("text", model_request))
        if isinstance(verdict, AppError):
            raise verdict
        return SimpleNamespace(
            parsed_json=verdict, request_id="comparison-id", model=model_request.model
        )

    dependencies = ComparisonDependencies(
        load_prompt_set=load_prompt_set,
        render_prompt=render_prompt,
        render_page_for_crop_refine=render_page,
        openai_chat_json_with_images=image_model,
        openai_chat_json=text_model,
    )
    try:
        result = evaluate_shortlisted_claims(
            request=request,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            dependencies=dependencies,
            run_budget=run_budget,
        )
    except AppError as error:
        result = error
    return result, calls, sha256_json(reading)


def test_every_visual_provider_call_receives_scoped_run_budget(tmp_path):
    budget = RunBudget(
        schema_version="1.0",
        run_id="budget-test",
        publisher_name="publisher",
        max_calls=4,
    )
    _result, calls, _digest = _run(
        tmp_path, INTERPRETATION, _verdict("contradicted"), run_budget=budget
    )
    assert len(calls) == 4
    assert all(request.run_budget == budget for _kind, request in calls)


def _verdict(outcome, *, pages=None, digest=None):
    return {
        "outcome": outcome,
        "supporting_physical_pages": [5] if pages is None else pages,
        "source_reading_digest": digest,
        "explanation": "The independent text comparison assessed the relationship.",
    }


def _assert_not_verified(result):
    assert isinstance(result, AppError) or result.claims[0].outcome not in {
        "verified",
        "verified_after_retry",
    }


def test_comparison_is_separate_text_only_and_receives_exact_verified_inputs(tmp_path):
    result, calls, _ = _run(tmp_path, REVERSED_CLAIM, _verdict("contradicted"))
    text_calls = [request for kind, request in calls if kind == "text"]
    assert len(text_calls) == 1, (
        "a separate text-only comparison must follow visual verification"
    )
    assert calls.index(("text", text_calls[0])) > next(
        index
        for index, (kind, request) in enumerate(calls)
        if kind == "image"
        and request.prompt_namespace.endswith("visual_claim_verification")
    )
    comparison = text_calls[0]
    prompt = comparison.system_prompt + "\n" + comparison.user_prompt
    assert SOURCE_TEXT in prompt
    assert REVERSED_CLAIM in prompt
    assert "FACT METHOD SENTINEL" in prompt
    assert "FACT QUALIFIER SENTINEL" in prompt
    assert ORIGINAL not in prompt
    assert not getattr(comparison, "image_paths", None)
    _assert_not_verified(result)


@pytest.mark.parametrize(
    "case",
    [
        "contradicted",
        "unresolved",
        "malformed",
        "wrong-page",
        "wrong-digest",
        "provider-error",
    ],
)
def test_visual_acceptance_requires_bound_supported_independent_verdict(tmp_path, case):
    # Compute the expected digest from the identical request and source reading.
    probe_request = _request(tmp_path, [_claim("candidate", ORIGINAL)])
    reading = {
        "schema_version": "1.0",
        "source_identity": probe_request.source_identity,
        "request_id": "reading-id",
        "model": "gpt-6-luna",
        "pages": [
            {"physical_page": 5, "observations": [SOURCE_TEXT], "uncertainties": []}
        ],
    }
    digest = sha256_json(reading)
    verdicts = {
        "contradicted": _verdict("contradicted", digest=digest),
        "unresolved": _verdict("unresolved", digest=digest),
        "malformed": {
            "outcome": "supported",
            "supporting_physical_pages": "5",
            "source_reading_digest": digest,
        },
        "wrong-page": _verdict("supported", pages=[6], digest=digest),
        "wrong-digest": _verdict("supported", digest="wrong"),
        "provider-error": AppError(
            code="comparison_error", message="provider error", retryable=False
        ),
    }
    result, calls, _ = _run(tmp_path, REVERSED_CLAIM, verdicts[case])
    assert any(kind == "text" for kind, _ in calls), (
        "independent comparison was bypassed"
    )
    _assert_not_verified(result)


def test_supported_interpretation_is_accepted_with_matching_page_and_digest(tmp_path):
    probe_request = _request(tmp_path, [_claim("candidate", ORIGINAL)])
    reading = {
        "schema_version": "1.0",
        "source_identity": probe_request.source_identity,
        "request_id": "reading-id",
        "model": "gpt-6-luna",
        "pages": [
            {"physical_page": 5, "observations": [SOURCE_TEXT], "uncertainties": []}
        ],
    }
    result, calls, digest = _run(
        tmp_path, INTERPRETATION, _verdict("supported", digest=sha256_json(reading))
    )
    assert any(kind == "text" for kind, _ in calls), (
        "independent comparison was bypassed"
    )
    assert not isinstance(result, AppError)
    assert result.claims[0].outcome in {"verified", "verified_after_retry"}
    assert result.claims[0].final_claim == INTERPRETATION
    assert result.claims[0].source_reading_assessment["source_reading_digest"] == digest


@pytest.mark.parametrize("outcome", ["contradicted", "unresolved"])
def test_non_supported_comparison_preserves_terminal_reason(tmp_path, outcome):
    result, _, _ = _run(tmp_path, REVERSED_CLAIM, _verdict(outcome))
    assert not isinstance(result, AppError)
    assert result.claims[0].failure_reason == f"source_comparison_{outcome}"


def test_comparison_outcome_is_logged_without_source_or_claim_text(tmp_path, caplog):
    with caplog.at_level(
        "INFO", logger="market_lense.verified_claims_visual_generator"
    ):
        _run(tmp_path, REVERSED_CLAIM, _verdict("contradicted"))
    records = [record.getMessage() for record in caplog.records]
    assert any(
        "source_comparison_result" in record and "contradicted" in record
        for record in records
    )
    assert all(
        SOURCE_TEXT not in record and REVERSED_CLAIM not in record for record in records
    )
