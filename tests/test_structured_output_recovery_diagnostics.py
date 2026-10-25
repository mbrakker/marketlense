from __future__ import annotations

import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="diag", task_id="t", span_id="s")


def _response(payload: dict) -> OpenAIResponseResult:
    return OpenAIResponseResult(
        schema_version="1.0",
        text=json.dumps(payload),
        parsed_json=payload,
        model="gpt-5-mini",
        request_id="diagnostic-request",
    )


def _request() -> StructuredOutputExecutionRequest:
    return StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="diagnostic-report",
        artifact_family="validation_grounding",
        schema_name="grounding_validation_output",
        model="gpt-5-mini",
        terminal_failure_code="validation_grounding_invalid_json",
    )


def test_exhaustion_merges_primary_and_terminal_identifier_contexts() -> None:
    calls: list[str] = []
    primary_id = "insight:primary:so_what"
    shared_id = "insight:shared:so_what"
    terminal_id = "insight:terminal:so_what"

    def validate_payload(candidate: dict) -> None:
        stage = str(candidate.get("stage") or "")
        if stage == "primary":
            raise AppError(
                code="primary_grounding_invalid",
                message="Primary grounding coverage is incomplete",
                context={
                    "missing_or_ambiguous_public_item_ids": [
                        primary_id,
                        shared_id,
                        shared_id,
                    ]
                },
            )
        if stage == "regeneration":
            raise AppError(
                code="terminal_grounding_invalid",
                message="Regenerated grounding coverage is incomplete",
                context={
                    "missing_or_ambiguous_public_item_ids": [
                        shared_id,
                        terminal_id,
                    ]
                },
            )

    def call_model(mode: str, original_response: str, schema_errors: str):
        del original_response, schema_errors
        calls.append(mode)
        if mode == "primary":
            return _response({"stage": "primary"})
        if mode == "model_repair":
            return OpenAIResponseResult(
                schema_version="1.0", text="", model="gpt-5-mini"
            )
        return _response({"stage": "regeneration"})

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            _request(),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=validate_payload,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    assert calls == ["primary", "model_repair", "regeneration"]
    assert exc_info.value.context["error_class"] == "terminal_grounding_invalid"
    assert exc_info.value.context["original_error_class"] == (
        "primary_grounding_invalid"
    )
    assert exc_info.value.context["missing_or_ambiguous_public_item_ids"] == [
        primary_id,
        shared_id,
        terminal_id,
    ]


def test_exhaustion_preserves_primary_priority_when_merged_context_is_full() -> None:
    primary_ids = [
        "insight:primary:one",
        "insight:primary:two",
        "insight:primary:three",
        "insight:primary:four",
    ]
    terminal_id = "insight:terminal:one"
    unsafe_id = "source text with spaces"
    oversized_id = "x" * 129

    def validate_payload(candidate: dict) -> None:
        stage = str(candidate.get("stage") or "")
        if stage == "primary":
            raise AppError(
                code="primary_grounding_invalid",
                message="Primary grounding failed",
                context={"item_ids": [*primary_ids, unsafe_id, oversized_id]},
            )
        if stage == "regeneration":
            raise AppError(
                code="terminal_grounding_invalid",
                message="Terminal grounding failed",
                context={"item_ids": [terminal_id]},
            )

    def call_model(mode: str, original_response: str, schema_errors: str):
        del original_response, schema_errors
        if mode == "primary":
            return _response({"stage": "primary"})
        if mode == "model_repair":
            return OpenAIResponseResult(
                schema_version="1.0", text="", model="gpt-5-mini"
            )
        return _response({"stage": "regeneration"})

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            _request(),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=validate_payload,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    assert exc_info.value.context["item_ids"] == primary_ids[:3]
    assert unsafe_id not in exc_info.value.context["item_ids"]
    assert oversized_id not in exc_info.value.context["item_ids"]


def test_exhaustion_keeps_primary_context_when_later_failures_have_none() -> None:
    primary_id = "verified-fact:fact_1"

    def validate_payload(candidate: dict) -> None:
        if candidate.get("stage") == "primary":
            raise AppError(
                code="primary_grounding_invalid",
                message="Primary grounding failed",
                context={"missing_evidence_ids": [primary_id]},
            )
        raise AppError(
            code="terminal_grounding_invalid",
            message="Later grounding failed without identifiers",
        )

    def call_model(mode: str, original_response: str, schema_errors: str):
        del original_response, schema_errors
        if mode == "primary":
            return _response({"stage": "primary"})
        if mode == "model_repair":
            return OpenAIResponseResult(
                schema_version="1.0", text="", model="gpt-5-mini"
            )
        return _response({"stage": "regeneration"})

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            _request(),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=validate_payload,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    assert exc_info.value.context["missing_evidence_ids"] == [primary_id]
