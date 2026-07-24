"""Shared, bounded recovery for report model JSON artifacts.

Raw provider responses are deliberately retained only in local variables while
the one model repair is prepared.  Audit events carry metadata and hashes via
the normal bounded logger, never report text or rendered prompts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.contracts.structured_output import (
    StructuredOutputExecutionRequest,
    StructuredOutputExecutionResult,
)
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text, repair_json_once
from src.utils.logging import log_event
from src.utils.structured_output import StructuredOutputFailure

logger = logging.getLogger("market_lense.structured_output_service")

StructuredOutputCall = Callable[[str, str, str], OpenAIResponseResult]
PayloadNormalizer = Callable[[Any], Any]
PayloadValidator = Callable[[Any], None]
SubstantiveCheck = Callable[[Any], bool]
FormalAbstentionCheck = Callable[[Any], bool]


def execute_structured_output(
    request: StructuredOutputExecutionRequest,
    ctx: RunContext,
    *,
    call_model: StructuredOutputCall,
    normalize_payload: PayloadNormalizer,
    validate_payload: PayloadValidator,
    is_substantive: SubstantiveCheck,
    model_pricing: dict[str, dict],
    is_formal_abstention: FormalAbstentionCheck | None = None,
) -> StructuredOutputExecutionResult:
    """Execute the single required recovery sequence for one JSON artifact."""

    if request.allow_abstention and is_formal_abstention is None:
        raise AppError(
            code="structured_output_abstention_contract_missing",
            message="An abstainable output needs an explicit downstream contract check",
            retryable=False,
            context={"artifact_family": request.artifact_family},
        )

    primary = _call_model(
        request=request,
        ctx=ctx,
        call_model=call_model,
        mode="primary",
        original_response="",
        schema_errors="",
        attempt=0,
        model_pricing=model_pricing,
    )
    initial = _evaluate_response(
        response=primary,
        normalize_payload=normalize_payload,
        validate_payload=validate_payload,
        is_substantive=is_substantive,
        allow_abstention=request.allow_abstention,
        is_formal_abstention=is_formal_abstention,
    )
    if initial.payload is not None:
        disposition = initial.disposition or "generated"
        _record_attempt(
            request,
            ctx,
            response=primary,
            attempt=0,
            error_class="",
            disposition=disposition,
            model_pricing=model_pricing,
        )
        return _result(initial.payload, disposition, 1, response=primary)

    _record_attempt(
        request,
        ctx,
        response=primary,
        attempt=0,
        error_class=initial.error_class,
        disposition="recovery_started",
        model_pricing=model_pricing,
    )
    deterministic = _evaluate_deterministic_repair(
        response=primary,
        normalize_payload=normalize_payload,
        validate_payload=validate_payload,
        is_substantive=is_substantive,
        allow_abstention=request.allow_abstention,
        is_formal_abstention=is_formal_abstention,
    )
    if deterministic.payload is not None:
        _record_attempt(
            request,
            ctx,
            response=primary,
            attempt=0,
            error_class=initial.error_class,
            disposition="deterministic_repair",
            model_pricing=model_pricing,
        )
        return _result(
            deterministic.payload,
            "deterministic_repair",
            1,
            initial.error_class,
            primary,
        )
    _record_attempt(
        request,
        ctx,
        response=primary,
        attempt=0,
        error_class=deterministic.error_class,
        disposition="deterministic_repair_failed",
        model_pricing=model_pricing,
    )

    original_response = str(primary.text or "")
    exact_errors = _join_errors(initial.error_detail, deterministic.error_detail)
    repaired = _call_model(
        request=request,
        ctx=ctx,
        call_model=call_model,
        mode="model_repair",
        original_response=original_response,
        schema_errors=exact_errors,
        attempt=1,
        model_pricing=model_pricing,
    )
    repaired_evaluation = _evaluate_response(
        response=repaired,
        normalize_payload=normalize_payload,
        validate_payload=validate_payload,
        is_substantive=is_substantive,
        allow_abstention=request.allow_abstention,
        is_formal_abstention=is_formal_abstention,
    )
    if repaired_evaluation.payload is not None:
        disposition = repaired_evaluation.disposition or "model_repair"
        _record_attempt(
            request,
            ctx,
            response=repaired,
            attempt=1,
            error_class=initial.error_class,
            disposition=disposition,
            model_pricing=model_pricing,
        )
        return _result(
            repaired_evaluation.payload,
            disposition,
            2,
            initial.error_class,
            repaired,
        )
    _record_attempt(
        request,
        ctx,
        response=repaired,
        attempt=1,
        error_class=repaired_evaluation.error_class,
        disposition="model_repair_failed",
        model_pricing=model_pricing,
    )

    regenerated = _call_model(
        request=request,
        ctx=ctx,
        call_model=call_model,
        mode="regeneration",
        original_response="",
        schema_errors=repaired_evaluation.error_detail,
        attempt=2,
        model_pricing=model_pricing,
    )
    regenerated_evaluation = _evaluate_response(
        response=regenerated,
        normalize_payload=normalize_payload,
        validate_payload=validate_payload,
        is_substantive=is_substantive,
        allow_abstention=request.allow_abstention,
        is_formal_abstention=is_formal_abstention,
    )
    if regenerated_evaluation.payload is not None:
        disposition = regenerated_evaluation.disposition or "regeneration"
        _record_attempt(
            request,
            ctx,
            response=regenerated,
            attempt=2,
            error_class=repaired_evaluation.error_class,
            disposition=disposition,
            model_pricing=model_pricing,
        )
        return _result(
            regenerated_evaluation.payload,
            disposition,
            3,
            repaired_evaluation.error_class,
            regenerated,
        )
    final_error = regenerated_evaluation.error_class or repaired_evaluation.error_class
    _record_attempt(
        request,
        ctx,
        response=regenerated,
        attempt=2,
        error_class=final_error,
        disposition="recovery_exhausted",
        model_pricing=model_pricing,
    )
    raise StructuredOutputFailure(
        code=request.terminal_failure_code,
        message=(
            f"{request.artifact_family} did not produce a substantive "
            "schema-valid JSON artifact"
        ),
        artifact_family=request.artifact_family,
        response_text=str(regenerated.text or original_response),
        schema_errors=_join_errors(exact_errors, regenerated_evaluation.error_detail),
        repair_attempt=2,
    )


class _Evaluation:
    def __init__(
        self,
        payload: Any | None,
        error_class: str = "",
        error_detail: str = "",
        disposition: str = "",
    ) -> None:
        self.payload = payload
        self.error_class = error_class
        self.error_detail = error_detail
        self.disposition = disposition


def _evaluate_response(
    *,
    response: OpenAIResponseResult,
    normalize_payload: PayloadNormalizer,
    validate_payload: PayloadValidator,
    is_substantive: SubstantiveCheck,
    allow_abstention: bool,
    is_formal_abstention: FormalAbstentionCheck | None,
) -> _Evaluation:
    raw = str(response.text or "")
    parsed: Any = response.parsed_json
    parse_strategy = "provider_parsed"
    if parsed is None:
        parsed, parse_strategy = parse_json_from_text(raw, accepted_types=(dict, list))
    if parsed is None:
        error = "empty_response" if not raw.strip() else "invalid_json"
        return _Evaluation(None, error, f"{error}:{parse_strategy}")
    return _normalize_validate(
        parsed,
        normalize_payload,
        validate_payload,
        is_substantive,
        allow_abstention,
        is_formal_abstention,
    )


def _evaluate_deterministic_repair(
    *,
    response: OpenAIResponseResult,
    normalize_payload: PayloadNormalizer,
    validate_payload: PayloadValidator,
    is_substantive: SubstantiveCheck,
    allow_abstention: bool,
    is_formal_abstention: FormalAbstentionCheck | None,
) -> _Evaluation:
    repaired_text, strategy = repair_json_once(str(response.text or ""))
    parsed, parse_strategy = parse_json_from_text(
        repaired_text, accepted_types=(dict, list)
    )
    if parsed is None:
        return _Evaluation(
            None,
            "deterministic_repair_invalid",
            f"{strategy}:{parse_strategy}",
        )
    return _normalize_validate(
        parsed,
        normalize_payload,
        validate_payload,
        is_substantive,
        allow_abstention,
        is_formal_abstention,
    )


def _normalize_validate(
    payload: Any,
    normalize_payload: PayloadNormalizer,
    validate_payload: PayloadValidator,
    is_substantive: SubstantiveCheck,
    allow_abstention: bool,
    is_formal_abstention: FormalAbstentionCheck | None,
) -> _Evaluation:
    try:
        normalized = normalize_payload(payload)
        validate_payload(normalized)
    except AppError as exc:
        return _Evaluation(None, exc.code, f"{exc.code}:{exc.message}")
    except (TypeError, ValueError, KeyError) as exc:
        return _Evaluation(
            None, "schema_normalization_failed", f"schema_normalization_failed:{exc}"
        )
    if allow_abstention and is_formal_abstention is not None:
        try:
            if is_formal_abstention(normalized):
                return _Evaluation(normalized, disposition="abstained")
        except (TypeError, ValueError, KeyError) as exc:
            return _Evaluation(
                None,
                "abstention_normalization_failed",
                f"abstention_normalization_failed:{exc}",
            )
    if not is_substantive(normalized):
        return _Evaluation(
            None,
            "structured_output_empty",
            "structured_output_empty:normalized output is empty",
        )
    return _Evaluation(normalized)


def _call_model(
    *,
    request: StructuredOutputExecutionRequest,
    ctx: RunContext,
    call_model: StructuredOutputCall,
    mode: str,
    original_response: str,
    schema_errors: str,
    attempt: int,
    model_pricing: dict[str, dict],
) -> OpenAIResponseResult:
    try:
        return call_model(mode, original_response, schema_errors)
    except AppError as exc:
        _record_attempt(
            request,
            ctx,
            response=OpenAIResponseResult(
                schema_version="1.0", text="", model=request.model
            ),
            attempt=attempt,
            error_class=exc.code,
            disposition="provider_error",
            model_pricing=model_pricing,
        )
        raise


def _record_attempt(
    request: StructuredOutputExecutionRequest,
    ctx: RunContext,
    *,
    response: OpenAIResponseResult,
    attempt: int,
    error_class: str,
    disposition: str,
    model_pricing: dict[str, dict],
) -> None:
    model = str(response.model or "")
    input_tokens = int(response.input_tokens or 0)
    output_tokens = int(response.output_tokens or 0)
    tool_calls = int(response.tool_calls or 0)
    total_tokens = int(response.total_tokens or input_tokens + output_tokens)
    cost_usd = estimate_cost_usd(
        model, input_tokens, output_tokens, tool_calls, model_pricing
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="structured_output_attempt",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "artifact_family": request.artifact_family,
                "attempt": attempt,
                "error_class": error_class,
                "provider": request.provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tokens": total_tokens,
                "total_tokens": total_tokens,
                "cost": cost_usd,
                "cost_usd": cost_usd,
                "final_disposition": disposition,
                "request_id": str(response.request_id or ""),
            },
        )
    )


def _join_errors(*errors: str) -> str:
    return " | ".join(str(error).strip() for error in errors if str(error).strip())


def _result(
    payload: Any,
    disposition: str,
    attempts: int,
    error_class: str = "",
    response: OpenAIResponseResult | None = None,
) -> StructuredOutputExecutionResult:
    return StructuredOutputExecutionResult(
        schema_version="1.0",
        payload=payload,
        disposition=disposition,
        attempts=attempts,
        error_class=error_class,
        model=str(getattr(response, "model", "") or ""),
        request_id=str(getattr(response, "request_id", "") or ""),
    )
