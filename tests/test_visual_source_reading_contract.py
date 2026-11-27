from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.contracts.verified_claims import VisualClaimEvaluationResult
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError

SOURCE = "report_vs/validate/visual_source_reading"
CORRECTION = "report_vs/validate/visual_claim_correction"
VERIFICATION = "report_vs/validate/visual_claim_verification"
OBSERVATION = "The chart shows a blue bar for the northern region."
MISSING = object()


def _evaluate(tmp_path, assessment, verifier_assessment=MISSING):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test-pdf")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    claim = {
        "candidate_id": "candidate-secret-id",
        "text": "Candidate secret proposition 73 percent",
        "evidence_id": "evidence-secret-id",
        "evidence_spans": [
            {
                "evidence_id": "evidence-secret-id",
                "page": 5,
                "start": 10,
                "end": 20,
                "text": "Evidence secret excerpt",
            }
        ],
        "pages": [5],
        "metric": {"value": "73%", "cohort": "metric-secret-cohort"},
    }
    request = SimpleNamespace(
        schema_version="1.0",
        pdf_path=str(pdf),
        output_dir=str(tmp_path),
        report_name="report",
        source_identity=f"report|pdf-sha256:{digest}",
        claims=[claim],
        shadow_mode=True,
        dpi=180,
    )
    policy = {
        "schema_version": "1.0",
        "provider": "openai",
        "model": "gpt-6-luna",
        "reasoning_effort": "high",
        "max_output_tokens": 16384,
        "retrieval_mode": "chat_json",
        "timeout_seconds": 60,
        "fallback_policy": "same_provider_only",
        "pricing_key": "gpt-6-luna",
    }
    settings = SimpleNamespace(
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
    calls = []

    def render_page(render_request, _ctx):
        return SimpleNamespace(image_path=f"report/page-{render_request.page}.png")

    def call_model(model_request, _ctx):
        calls.append(model_request)
        if model_request.prompt_namespace == SOURCE:
            if isinstance(assessment, Exception):
                raise assessment
            if isinstance(assessment, SimpleNamespace):
                return assessment
            payload = assessment
        elif model_request.prompt_namespace == CORRECTION:
            payload = {"status": "corrected", "claim": "Corrected claim", "issues": []}
        elif model_request.prompt_namespace == VERIFICATION:
            payload = {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": "The page supports the corrected claim.",
                "supporting_physical_pages": [5],
                "source_truth_notes_by_page": {"5": "The page supports the claim."},
                "verified_fact": {
                    "statement": "Corrected claim",
                    "metric": {},
                    "qualifiers": [],
                },
            }
            if verifier_assessment is MISSING:
                payload["source_reading_assessment"] = {
                    "outcome": "supported",
                    "supporting_physical_pages": [5],
                    "explanation": "The independent observation supports the claim on page 5.",
                }
            elif verifier_assessment is not None:
                payload["source_reading_assessment"] = verifier_assessment
        else:
            pytest.fail(f"Unexpected model namespace: {model_request.prompt_namespace}")
        return SimpleNamespace(
            parsed_json=payload, request_id="fake-request", model=model_request.model
        )

    def compare_source(model_request, _ctx):
        calls.append(model_request)
        reading = {
            "schema_version": "1.0",
            "source_identity": request.source_identity,
            "request_id": "fake-request",
            "model": "gpt-6-luna",
            "pages": assessment["pages"],
        }
        return SimpleNamespace(
            parsed_json={
                "outcome": "supported",
                "supporting_physical_pages": [5],
                "source_reading_digest": sha256_json(reading),
                "explanation": "The source reading supports the claim and proposed fact.",
            },
            request_id="comparison-id",
            model=model_request.model,
        )

    dependencies = VerifiedClaimsVisualDependencies(
        load_prompt_set=load_prompt_set,
        render_prompt=render_prompt,
        render_page_for_crop_refine=render_page,
        openai_chat_json_with_images=call_model,
        openai_chat_json=compare_source,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    try:
        result = evaluate_shortlisted_claims(
            request=request,
            settings=settings,
            ctx=ctx,
            dependencies=dependencies,
        )
    except AppError as error:
        result = error
    return result, calls


def _read_assessment():
    return {
        "status": "read",
        "pages": [
            {"physical_page": 5, "observations": [OBSERVATION], "uncertainties": []}
        ],
    }


def test_source_reader_is_claim_blind_and_sees_the_verified_page(tmp_path):
    result, calls = _evaluate(tmp_path, _read_assessment())
    namespaces = [call.prompt_namespace for call in calls]
    assert SOURCE in namespaces, "source reading must occur before claim verification"
    assert namespaces.index(SOURCE) < namespaces.index(CORRECTION)
    assert namespaces.index(SOURCE) < namespaces.index(VERIFICATION)
    source = calls[namespaces.index(SOURCE)]
    verifier = calls[namespaces.index(VERIFICATION)]
    assert (
        source.image_paths
        == verifier.image_paths
        == [str(tmp_path / "report/page-4.png")]
    )
    prompt = source.system_prompt + "\n" + source.user_prompt
    for secret in (
        "candidate-secret-id",
        "Candidate secret proposition",
        "73%",
        "metric-secret-cohort",
        "evidence-secret-id",
        "Evidence secret excerpt",
    ):
        assert secret not in prompt
    assert not isinstance(result, AppError)
    assert result.claims[0].outcome == "verified"
    assert result.claims[0].source_reading["request_id"] == "fake-request"
    assert result.claims[0].source_reading["model"] == "gpt-6-luna"


@pytest.mark.parametrize(
    "assessment",
    [
        {"status": "read", "pages": "malformed"},
        {
            "status": "read",
            "pages": [
                {"physical_page": 6, "observations": [OBSERVATION], "uncertainties": []}
            ],
        },
        {"status": "unresolved", "pages": []},
    ],
    ids=["malformed", "wrong-page", "unresolved"],
)
def test_invalid_source_reading_fails_closed_before_verification(tmp_path, assessment):
    result, calls = _evaluate(tmp_path, assessment)
    namespaces = [call.prompt_namespace for call in calls]
    assert SOURCE in namespaces, "source assessment must be requested"
    assert VERIFICATION not in namespaces
    assert isinstance(result, AppError) or result.claims[0].outcome != "verified"


def test_verifier_receives_source_observation_bound_to_physical_page(tmp_path):
    result, calls = _evaluate(tmp_path, _read_assessment())
    namespaces = [call.prompt_namespace for call in calls]
    assert SOURCE in namespaces, "source assessment must precede verification"
    verifier = calls[namespaces.index(VERIFICATION)]
    prompt = verifier.system_prompt + "\n" + verifier.user_prompt
    assert re.search(
        rf"(?:physical[_ ]page[^\n]{{0,30}}5[\s\S]{{0,200}}{re.escape(OBSERVATION)}|"
        rf"{re.escape(OBSERVATION)}[\s\S]{{0,200}}physical[_ ]page[^\n]{{0,30}}5)",
        prompt,
        re.IGNORECASE,
    ), "the observation must be associated with physical page 5"
    assert not isinstance(result, AppError)
    assert result.claims[0].outcome == "verified"


@pytest.mark.parametrize(
    "verifier_assessment",
    [
        None,
        "malformed",
        {
            "outcome": "supported",
            "supporting_physical_pages": "5",
            "explanation": "Supported.",
        },
        {
            "outcome": "supported",
            "supporting_physical_pages": [6],
            "explanation": "Supported.",
        },
        {"outcome": "supported", "supporting_physical_pages": [5], "explanation": ""},
        {
            "outcome": "unresolved",
            "supporting_physical_pages": [5],
            "explanation": "Cannot compare.",
        },
        {
            "outcome": "disagreement",
            "supporting_physical_pages": [5],
            "explanation": "The reading contradicts the claim.",
        },
    ],
    ids=[
        "missing",
        "malformed-object",
        "malformed-pages",
        "wrong-page",
        "empty-explanation",
        "unresolved",
        "disagreement",
    ],
)
def test_verifier_requires_supported_source_reading_comparison(
    tmp_path, verifier_assessment
):
    result, calls = _evaluate(tmp_path, _read_assessment(), verifier_assessment)
    assert VERIFICATION in [call.prompt_namespace for call in calls]
    assert isinstance(result, AppError) or result.claims[0].outcome != "verified"


def test_nonretryable_source_provider_error_is_a_typed_unresolved_result(tmp_path):
    result, calls = _evaluate(
        tmp_path,
        AppError(
            code="source_provider_budget_exceeded",
            message="Budget exhausted",
            retryable=False,
        ),
    )
    assert not isinstance(result, AppError)
    assert result.claims[0].outcome == "unresolved"
    assert "source_provider_budget_exceeded" in result.claims[0].failure_reason
    assert VERIFICATION not in [call.prompt_namespace for call in calls]


def test_retryable_source_provider_error_reaches_recovery_owner(tmp_path):
    result, calls = _evaluate(
        tmp_path,
        AppError(code="source_provider_timeout", message="Timeout", retryable=True),
    )
    assert isinstance(result, AppError)
    assert result.code == "source_provider_timeout"
    assert result.retryable is True
    assert VERIFICATION not in [call.prompt_namespace for call in calls]


def test_incomplete_source_reader_response_preserves_typed_retryable_reason(tmp_path):
    result, calls = _evaluate(
        tmp_path,
        SimpleNamespace(
            parsed_json=None,
            provider_status="incomplete",
            incomplete_reason="max_output_tokens",
            request_id="incomplete-id",
            model="gpt-6-luna",
        ),
    )
    assert isinstance(result, AppError)
    assert result.code == "source_reading_output_incomplete"
    assert result.retryable is True
    assert VERIFICATION not in [call.prompt_namespace for call in calls]


def test_unresolved_source_reading_is_not_placed_in_semantic_response_cache(tmp_path):
    _, calls = _evaluate(tmp_path, {"status": "unresolved", "pages": []})
    source = next(call for call in calls if call.prompt_namespace == SOURCE)
    assert source.response_cache_enabled is False


def test_legacy_positional_result_preserves_physical_pages():
    result = VisualClaimEvaluationResult(
        "1.1", "candidate", "claim", "source", 5, "skipped", [5]
    )
    assert result.physical_pages == [5]
