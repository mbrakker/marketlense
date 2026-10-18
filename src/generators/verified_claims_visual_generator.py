"""Shadow-mode visual correction and independent verification for claims."""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from src.contracts.files import FileBundleHashRequest
from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_assets import CropRefinePageRenderRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimCorrectionAttempt,
    VisualClaimEvaluationRequest,
    VisualClaimEvaluationResponse,
    VisualClaimEvaluationResult,
    VisualClaimVerificationAttempt,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import llm_service
from src.services.file_service import hash_file_bundle as service_hash_file_bundle
from src.services.pdf_service import render_page_for_crop_refine
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

LOGGER = logging.getLogger("market_lense.verified_claims_visual_generator")

CORRECTION_NAMESPACE = "report_vs/validate/visual_claim_correction"
VERIFICATION_NAMESPACE = "report_vs/validate/visual_claim_verification"
_CORRECTION_STATUSES = frozenset({"corrected", "unresolved", "failed"})
_VERIFICATION_OUTCOMES = frozenset({"verified", "rejected", "unresolved"})
_PDF_SHA256_PATTERN = re.compile(
    r"(?:^|[|,; ])pdf-sha256[:=]([0-9a-f]{64})(?:$|[|,; ])", re.I
)


@dataclass(frozen=True)
class VerifiedClaimsVisualDependencies:
    """Injected existing boundaries used by the shadow evaluator."""

    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    render_page_for_crop_refine: Callable[
        [CropRefinePageRenderRequest, RunContext], Any
    ]
    openai_chat_json_with_images: Callable[
        [OpenAIJSONImagePromptRequest, RunContext], Any
    ]
    hash_file_bundle: Callable[[FileBundleHashRequest, RunContext], Any] = (
        service_hash_file_bundle
    )

    @classmethod
    def default(cls) -> "VerifiedClaimsVisualDependencies":
        return cls(
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            render_page_for_crop_refine=render_page_for_crop_refine,
            openai_chat_json_with_images=llm_service.openai_chat_json_with_images,
            hash_file_bundle=service_hash_file_bundle,
        )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_id(claim: Mapping[str, Any]) -> str:
    for key in ("stable_candidate_id", "candidate_id", "id"):
        value = _text(claim.get(key))
        if value:
            return value
    return ""


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _physical_pages(claim: Mapping[str, Any]) -> list[int]:
    explicit_pages: list[int] = []
    for key in ("physical_page", "physical_pdf_page"):
        page = _positive_int(claim.get(key))
        if page is not None:
            explicit_pages.append(page)
    pages = claim.get("pages")
    page_values = (
        [_positive_int(value) for value in pages] if isinstance(pages, list) else []
    )
    page_values = [value for value in page_values if value is not None]
    if page_values:
        return list(dict.fromkeys(page_values))
    if explicit_pages:
        return list(dict.fromkeys(explicit_pages))
    spans = claim.get("evidence_spans")
    span_pages = (
        [_positive_int(span.get("page")) for span in spans if isinstance(span, dict)]
        if isinstance(spans, list)
        else []
    )
    span_pages = [value for value in span_pages if value is not None]
    return list(dict.fromkeys(span_pages))


def _physical_page(claim: Mapping[str, Any]) -> int | None:
    pages = _physical_pages(claim)
    return pages[0] if pages else None


def _source_pdf_sha256(source_identity: str) -> str:
    matches = {
        match.group(1).lower()
        for match in _PDF_SHA256_PATTERN.finditer(_text(source_identity))
    }
    if len(matches) > 1:
        raise AppError(
            code="verified_claims_source_identity_ambiguous",
            message="Source identity contains conflicting PDF hashes",
            retryable=False,
        )
    return next(iter(matches), "")


def _verify_source_pdf_identity(
    *,
    request: VisualClaimEvaluationRequest,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
) -> None:
    expected_sha256 = _source_pdf_sha256(request.source_identity)
    if not expected_sha256:
        raise AppError(
            code="verified_claims_source_pdf_hash_missing",
            message="Visual evaluation requires an expected source PDF hash",
            retryable=False,
        )
    response = dependencies.hash_file_bundle(
        FileBundleHashRequest(schema_version="1.0", paths=[request.pdf_path]),
        ctx,
    )
    file_hashes = getattr(response, "file_sha256", None)
    if isinstance(response, dict):
        file_hashes = response.get("file_sha256")
    actual_sha256 = (
        _text(file_hashes.get(request.pdf_path))
        if isinstance(file_hashes, dict)
        else ""
    ).lower()
    if actual_sha256 != expected_sha256:
        raise AppError(
            code="verified_claims_source_pdf_hash_mismatch",
            message="Source PDF hash does not match the expected source identity",
            retryable=False,
            context={
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
            },
        )


def _binding_conflict_reason(
    claim: Mapping[str, Any], source_identity: str
) -> str:
    claim_source_identity = _text(claim.get("source_identity"))
    if claim_source_identity and claim_source_identity != _text(source_identity):
        return "claim_source_identity_conflict"
    raw_pages = claim.get("pages")
    if raw_pages is not None and not isinstance(raw_pages, list):
        return "pages_not_a_list"
    if isinstance(raw_pages, list):
        parsed_pages = [_positive_int(value) for value in raw_pages]
        if any(value is None for value in parsed_pages):
            return "pages_invalid"
        declared_pages = set(parsed_pages)
    else:
        declared_pages = set()

    explicit_pages = [
        _positive_int(claim.get(key))
        for key in ("physical_page", "physical_pdf_page")
        if claim.get(key) is not None
    ]
    if any(page is None for page in explicit_pages):
        return "physical_page_invalid"
    if len(set(explicit_pages)) > 1:
        return "physical_page_conflict"
    if declared_pages and any(page not in declared_pages for page in explicit_pages):
        return "physical_page_not_in_pages"

    spans = claim.get("evidence_spans")
    if spans is not None and not isinstance(spans, list):
        return "evidence_spans_not_a_list"
    span_pages: set[int] = set()
    span_evidence_ids: set[str] = set()
    span_source_ids: set[str] = set()
    for span in spans or []:
        if not isinstance(span, dict):
            return "evidence_span_invalid"
        page = span.get("page")
        if page is not None:
            parsed_page = _positive_int(page)
            if parsed_page is None:
                return "evidence_span_page_invalid"
            span_pages.add(parsed_page)
        evidence_id = _text(span.get("evidence_id"))
        if evidence_id:
            span_evidence_ids.add(evidence_id)
        for key in ("source_identity", "source_id"):
            value = _text(span.get(key))
            if value:
                span_source_ids.add(value)

    if declared_pages and not span_pages.issubset(declared_pages):
        return "evidence_span_page_conflict"
    if not declared_pages and explicit_pages and span_pages and (
        explicit_pages[0] not in span_pages
    ):
        return "evidence_span_page_conflict"
    if span_source_ids and span_source_ids != {_text(source_identity)}:
        return "evidence_span_source_conflict"
    top_evidence_id = _text(claim.get("evidence_id"))
    if (
        top_evidence_id
        and span_evidence_ids
        and top_evidence_id not in span_evidence_ids
    ):
        return "evidence_id_conflict"
    return ""


def _evidence_ids(claim: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for value in (_text(claim.get("evidence_id")),):
        if value and value not in values:
            values.append(value)
    spans = claim.get("evidence_spans")
    if isinstance(spans, list):
        for span in spans:
            if not isinstance(span, dict):
                continue
            value = _text(span.get("evidence_id"))
            if value and value not in values:
                values.append(value)
    return values


def _evidence_spans(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
    spans = claim.get("evidence_spans")
    return (
        [copy.deepcopy(span) for span in spans if isinstance(span, dict)]
        if isinstance(spans, list)
        else []
    )


def _claim_binding(
    *, claim: Mapping[str, Any], source_identity: str, physical_page: int
) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(claim),
        "original_claim": _text(claim.get("text") or claim.get("claim")),
        "source_identity": source_identity,
        "physical_page": physical_page,
        "physical_pages": _physical_pages(claim),
        "evidence_ids": _evidence_ids(claim),
        "evidence_spans": _evidence_spans(claim),
    }


def _rendered_image_path(response: Any, output_dir: str) -> str:
    raw_path = (
        response.get("image_path")
        if isinstance(response, dict)
        else getattr(response, "image_path", "")
    )
    normalized_path = _text(raw_path)
    if not normalized_path:
        return ""
    path = Path(normalized_path)
    return str(path if path.is_absolute() else Path(output_dir) / path)


def _response_json(response: Any) -> dict[str, Any] | None:
    payload = (
        response.get("parsed_json")
        if isinstance(response, dict)
        else getattr(response, "parsed_json", None)
    )
    return payload if isinstance(payload, dict) else None


def _response_metadata(
    response: Any, request: OpenAIJSONImagePromptRequest
) -> tuple[str, str]:
    request_id = (
        _text(response.get("request_id"))
        if isinstance(response, dict)
        else _text(getattr(response, "request_id", ""))
    )
    model = (
        _text(response.get("model"))
        if isinstance(response, dict)
        else _text(getattr(response, "model", ""))
    )
    return request_id, model or request.model


def _strict_string_list(payload: Mapping[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        return None
    return [item.strip() for item in value]


def _provider_error_details(prefix: str, error: Exception) -> list[str]:
    if isinstance(error, AppError):
        return [
            prefix,
            f"error_code:{error.code}",
            f"retryable:{str(error.retryable).lower()}",
            f"severity:{error.severity}",
        ]
    return [prefix, f"error_type:{type(error).__name__}", "retryable:unknown"]


def _substantive_source_truth_notes(notes: str) -> bool:
    normalized = " ".join(notes.split()).casefold()
    return len(normalized.split()) >= 8 and normalized not in {
        "matches",
        "source matches",
        "the source matches",
    }


def _require_visual_policy(bundle: Any) -> None:
    model = _text(bundle.resolved_model).lower().removeprefix("openai/")
    effort = _text(bundle.effective_reasoning_effort).lower()
    if not model.startswith("gpt-6-luna") or effort != "high":
        raise AppError(
            code="verified_claims_visual_policy_invalid",
            message=(
                "Visual verified-claims evaluation requires GPT-6 Luna high reasoning"
            ),
            retryable=False,
            context={"model": model, "reasoning_effort": effort},
        )


def _bundle(
    *,
    namespace: str,
    variables: dict[str, Any],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
):
    bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=dependencies,
        system_variables={},
        user_variables=variables,
    )
    _require_visual_policy(bundle)
    return bundle


def _request(
    *,
    bundle: Any,
    settings: Any,
    image_paths: list[str],
    report_name: str,
    user_prompt: str,
    namespace: str,
) -> OpenAIJSONImagePromptRequest:
    return OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt=bundle.system_prompt,
        user_prompt=user_prompt,
        model=bundle.resolved_model,
        temperature=bundle.effective_temperature,
        api_key=_text(getattr(settings, "openai_api_key", "")),
        image_paths=image_paths,
        reasoning_effort=bundle.effective_reasoning_effort,
        seed=bundle.effective_seed,
        timeout_seconds=bundle.effective_timeout_seconds,
        max_output_tokens=bundle.effective_max_output_tokens,
        cost_ledger_path=_text(
            getattr(settings, "cost_ledger_path", "./out/cost-ledger.jsonl")
        ),
        cost_daily_path=_text(
            getattr(settings, "cost_daily_path", "./out/cost-daily.json")
        ),
        model_pricing=getattr(settings, "model_pricing", {}) or {},
        response_cache_enabled=True,
        response_cache_dir=_text(getattr(settings, "cache_dir", "./cache")),
        response_cache_ttl_seconds=604800.0,
        publisher_name="",
        report_name=report_name,
        source_url="",
        prompt_namespace=namespace,
        prompt_hash=bundle.prompt_content_hash,
        usage_db_path=_text(
            getattr(settings, "usage_db_path", "./state/llm_usage.sqlite")
        ),
        context_compaction_policy=LLMContextCompactionPolicy(
            schema_version="1.0",
            enabled=bundle.routing_decision.compaction_enabled,
            max_input_tokens=bundle.routing_decision.max_input_tokens or None,
        ),
    )


def _record_result(
    *,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    physical_page: int,
    outcome: str,
    failure_reason: str = "",
    final_claim: str = "",
    correction_attempts: list[VisualClaimCorrectionAttempt] | None = None,
    verification_attempts: list[VisualClaimVerificationAttempt] | None = None,
) -> VisualClaimEvaluationResult:
    return VisualClaimEvaluationResult(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        candidate_id=_candidate_id(claim),
        original_claim=_text(claim.get("text") or claim.get("claim")),
        source_identity=request.source_identity,
        physical_page=physical_page,
        physical_pages=_physical_pages(claim) if physical_page > 0 else [],
        outcome=outcome,
        evidence_ids=_evidence_ids(claim),
        evidence_spans=_evidence_spans(claim),
        correction_attempts=list(correction_attempts or []),
        verification_attempts=list(verification_attempts or []),
        final_claim=final_claim,
        failure_reason=failure_reason,
    )


def _correction_attempt(
    *,
    attempt: int,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    bundle: Any,
    retry_feedback: list[str],
) -> tuple[VisualClaimCorrectionAttempt, str]:
    binding = _claim_binding(
        claim=claim,
        source_identity=request.source_identity,
        physical_page=_physical_page(claim) or 0,
    )
    rendered = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=bundle.prompt_set.user,
            variables={
                "claim_json": json.dumps(binding, ensure_ascii=False, sort_keys=True),
                "attempt": attempt,
                "retry_feedback": json.dumps(retry_feedback, ensure_ascii=False),
            },
        ),
        ctx,
    )
    model_request = _request(
        bundle=bundle,
        settings=settings,
        image_paths=image_paths,
        report_name=request.report_name,
        user_prompt=rendered.text,
        namespace=CORRECTION_NAMESPACE,
    )
    try:
        response = dependencies.openai_chat_json_with_images(model_request, ctx)
        payload = _response_json(response)
        request_id, model = _response_metadata(response, model_request)
    except Exception as error:
        return (
            VisualClaimCorrectionAttempt(
                schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
                attempt=attempt,
                claim="",
                status="failed",
                issues=_provider_error_details("correction_provider_error", error),
            ),
            "",
        )
    if payload is None:
        return (
            VisualClaimCorrectionAttempt(
                schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
                attempt=attempt,
                claim="",
                status="failed",
                issues=["correction_response_invalid"],
                request_id=request_id,
                model=model,
            ),
            "",
        )
    if not isinstance(payload.get("claim"), str) or not isinstance(
        payload.get("status"), str
    ):
        status = "failed"
        corrected_claim = ""
        issues = ["correction_response_invalid"]
    else:
        corrected_claim = _text(payload.get("claim"))
        status = _text(payload.get("status")).lower()
        issues = _strict_string_list(payload, "issues")
    if issues is None:
        status = "failed"
        corrected_claim = ""
        issues = ["correction_response_invalid"]
    if status not in _CORRECTION_STATUSES or (
        status == "corrected" and not corrected_claim
    ) or (status != "corrected" and corrected_claim):
        status = "failed"
        issues = [*issues, "correction_response_invalid"]
        corrected_claim = ""
    return (
        VisualClaimCorrectionAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            claim=corrected_claim,
            status=status,
            issues=issues,
            request_id=request_id,
            model=model,
        ),
        corrected_claim if status == "corrected" else "",
    )


def _verification_attempt(
    *,
    attempt: int,
    corrected_claim: str,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    bundle: Any,
) -> VisualClaimVerificationAttempt:
    source_payload = {
        "source_identity": request.source_identity,
        "physical_page": _physical_page(claim),
        "physical_pages": _physical_pages(claim),
        "evidence_ids": _evidence_ids(claim),
        "evidence_spans": _evidence_spans(claim),
    }
    rendered = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=bundle.prompt_set.user,
            variables={
                "source_json": json.dumps(
                    source_payload, ensure_ascii=False, sort_keys=True
                ),
                "original_claim": _text(claim.get("text") or claim.get("claim")),
                "corrected_claim": corrected_claim,
            },
        ),
        ctx,
    )
    model_request = _request(
        bundle=bundle,
        settings=settings,
        image_paths=image_paths,
        report_name=request.report_name,
        user_prompt=rendered.text,
        namespace=VERIFICATION_NAMESPACE,
    )
    try:
        response = dependencies.openai_chat_json_with_images(model_request, ctx)
        payload = _response_json(response)
        request_id, model = _response_metadata(response, model_request)
    except Exception as error:
        return VisualClaimVerificationAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            outcome="rejected",
            diagnostics=_provider_error_details("verification_provider_error", error),
        )
    if payload is None:
        return VisualClaimVerificationAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            outcome="rejected",
            diagnostics=["verification_response_invalid"],
            request_id=request_id,
            model=model,
        )
    if not isinstance(payload.get("outcome"), str) or not isinstance(
        payload.get("source_truth_notes"), str
    ):
        outcome = "rejected"
        diagnostics = ["verification_response_invalid"]
        notes = ""
    else:
        outcome = _text(payload.get("outcome")).lower()
        diagnostics = _strict_string_list(payload, "diagnostics")
        notes = _text(payload.get("source_truth_notes"))
    if diagnostics is None:
        outcome = "rejected"
        diagnostics = ["verification_response_invalid"]
    if outcome not in _VERIFICATION_OUTCOMES:
        outcome = "rejected"
        diagnostics = [*diagnostics, "verification_response_invalid"]
    elif outcome == "verified" and not _substantive_source_truth_notes(notes):
        outcome = "rejected"
        diagnostics = [*diagnostics, "verification_explanation_missing"]
    elif outcome in {"rejected", "unresolved"} and not diagnostics:
        outcome = "rejected"
        diagnostics = ["verification_diagnostics_missing"]
    return VisualClaimVerificationAttempt(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        attempt=attempt,
        outcome=outcome,
        diagnostics=diagnostics,
        source_truth_notes=notes,
        request_id=request_id,
        model=model,
    )


def _evaluate_claim(
    *,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    correction_bundle: Any,
    verification_bundle: Any,
) -> VisualClaimEvaluationResult:
    physical_page = _physical_page(claim)
    if not _candidate_id(claim):
        return _record_result(
            claim=claim,
            request=request,
            physical_page=physical_page or 0,
            outcome="skipped",
            failure_reason="candidate_id_missing",
        )
    if physical_page is None:
        return _record_result(
            claim=claim,
            request=request,
            physical_page=0,
            outcome="skipped",
            failure_reason="physical_page_missing",
        )
    original_claim = _text(claim.get("text") or claim.get("claim"))
    if not original_claim:
        return _record_result(
            claim=claim,
            request=request,
            physical_page=physical_page,
            outcome="skipped",
            failure_reason="claim_text_missing",
        )
    correction_attempts: list[VisualClaimCorrectionAttempt] = []
    verification_attempts: list[VisualClaimVerificationAttempt] = []
    retry_feedback: list[str] = []
    for correction_number in (1, 2):
        correction_ctx = child_context(
            ctx,
            task_id=f"{ctx.task_id}:correction:{_candidate_id(claim)}:{correction_number}",
        )
        correction, corrected_claim = _correction_attempt(
            attempt=correction_number,
            claim=claim,
            request=request,
            image_paths=image_paths,
            settings=settings,
            ctx=correction_ctx,
            dependencies=dependencies,
            bundle=correction_bundle,
            retry_feedback=retry_feedback,
        )
        correction_attempts.append(correction)
        if not corrected_claim:
            if correction_number == 1:
                retry_feedback = correction.issues
                continue
            return _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page,
                outcome="unresolved",
                failure_reason="correction_unresolved",
                correction_attempts=correction_attempts,
                verification_attempts=verification_attempts,
            )
        verification_ctx = child_context(
            ctx,
            task_id=f"{ctx.task_id}:verification:{_candidate_id(claim)}:{correction_number}",
        )
        verification = _verification_attempt(
            attempt=correction_number,
            corrected_claim=corrected_claim,
            claim=claim,
            request=request,
            image_paths=image_paths,
            settings=settings,
            ctx=verification_ctx,
            dependencies=dependencies,
            bundle=verification_bundle,
        )
        verification_attempts.append(verification)
        if verification.outcome == "verified":
            return _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page,
                outcome="verified"
                if correction_number == 1
                else "verified_after_retry",
                final_claim=corrected_claim,
                correction_attempts=correction_attempts,
                verification_attempts=verification_attempts,
            )
        retry_feedback = verification.diagnostics
    return _record_result(
        claim=claim,
        request=request,
        physical_page=physical_page,
        outcome="failed_verification",
        failure_reason="verification_failed_twice",
        correction_attempts=correction_attempts,
        verification_attempts=verification_attempts,
    )


def evaluate_shortlisted_claims(
    *,
    request: VisualClaimEvaluationRequest,
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies | None = None,
) -> VisualClaimEvaluationResponse:
    """Evaluate shortlisted claims in shadow mode without mutating the source artifact.

    The returned assessment is intentionally separate from the retained artifact.
    """

    if request.shadow_mode is not True:
        raise AppError(
            code="verified_claims_shadow_mode_required",
            message="Visual verified-claims evaluation is shadow-mode only",
            retryable=False,
        )
    dependencies = dependencies or VerifiedClaimsVisualDependencies.default()
    evaluation_ctx = child_context(ctx, task_id=f"{ctx.task_id}:verified_claims_visual")
    _verify_source_pdf_identity(
        request=request,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    correction_bundle = _bundle(
        namespace=CORRECTION_NAMESPACE,
        variables={"claim_json": "", "attempt": 1, "retry_feedback": "[]"},
        settings=settings,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    verification_bundle = _bundle(
        namespace=VERIFICATION_NAMESPACE,
        variables={"source_json": "{}", "corrected_claim": ""},
        settings=settings,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    rendered_pages: dict[int, str] = {}
    results: list[VisualClaimEvaluationResult] = []
    for index, raw_claim in enumerate(request.claims):
        claim = raw_claim if isinstance(raw_claim, Mapping) else {}
        physical_pages = _physical_pages(claim)
        physical_page = physical_pages[0] if physical_pages else None
        if not physical_pages:
            results.append(
                _record_result(
                    claim=claim,
                    request=request,
                    physical_page=0,
                    outcome="skipped",
                    failure_reason="physical_page_missing",
                )
            )
            continue
        binding_conflict = _binding_conflict_reason(claim, request.source_identity)
        if binding_conflict:
            results.append(
                _record_result(
                    claim=claim,
                    request=request,
                    physical_page=physical_page or 0,
                    outcome="skipped",
                    failure_reason="source_binding_conflict",
                )
            )
            continue
        missing_page = False
        for page in physical_pages:
            if page in rendered_pages:
                continue
            render_ctx = child_context(
                evaluation_ctx, task_id=f"{evaluation_ctx.task_id}:render:{page}"
            )
            try:
                render_response = dependencies.render_page_for_crop_refine(
                    CropRefinePageRenderRequest(
                        schema_version="1.1",
                        pdf_path=request.pdf_path,
                        out_dir=request.output_dir,
                        report_name=request.report_name,
                        page=page - 1,
                        dpi=request.dpi,
                    ),
                    render_ctx,
                )
                image_path = _rendered_image_path(render_response, request.output_dir)
            except Exception:
                image_path = ""
            if not image_path:
                missing_page = True
                break
            rendered_pages[page] = image_path
        if missing_page:
            results.append(
                _record_result(
                    claim=claim,
                    request=request,
                    physical_page=physical_page or 0,
                    outcome="skipped",
                    failure_reason="page_render_failed",
                )
            )
            continue
        image_paths = [rendered_pages[page] for page in physical_pages]
        claim_ctx = child_context(
            evaluation_ctx, task_id=f"{evaluation_ctx.task_id}:claim:{index}"
        )
        results.append(
            _evaluate_claim(
                claim=claim,
                request=request,
                image_paths=image_paths,
                settings=settings,
                ctx=claim_ctx,
                dependencies=dependencies,
                correction_bundle=correction_bundle,
                verification_bundle=verification_bundle,
            )
        )
    LOGGER.info(
        log_event(
            evaluation_ctx,
            role="generator",
            event="verified_claims_visual_shadow_complete",
            module=LOGGER.name,
            fields={
                "claim_count": len(results),
                "rendered_page_count": len(rendered_pages),
                "verified_count": sum(
                    item.outcome in {"verified", "verified_after_retry"}
                    for item in results
                ),
                "failed_verification_count": sum(
                    item.outcome == "failed_verification" for item in results
                ),
                "shadow_mode": True,
            },
        )
    )
    return VisualClaimEvaluationResponse(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        shadow_mode=True,
        claims=results,
        rendered_pages=rendered_pages,
    )


__all__ = [
    "CORRECTION_NAMESPACE",
    "VERIFICATION_NAMESPACE",
    "VerifiedClaimsVisualDependencies",
    "evaluate_shortlisted_claims",
]
