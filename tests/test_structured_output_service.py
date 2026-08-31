"""Regression coverage for shared recovery using retained failed artifacts."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.services.schema_validator_service import provider_output_schema
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure

_FIXTURES = Path(__file__).parent / "fixtures" / "docpacks" / "golden"
_STOCKSY = _FIXTURES / "stocksy-visual-insights-report-2026-acig-pdf"
_AKIN = _FIXTURES / "the-akin-the-quarantine-cohort-exec-summary-pdf"


def _payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r1", task_id="t1", span_id="s1")


def _response(payload: dict, *, model: str = "gpt-5-mini") -> OpenAIResponseResult:
    return OpenAIResponseResult(
        schema_version="1.0",
        text=json.dumps(payload, ensure_ascii=False),
        parsed_json=payload,
        input_tokens=11,
        output_tokens=7,
        tool_calls=0,
        model=model,
        request_id="req_fixture",
    )


def test_recovery_repairs_retained_empty_document_map_and_records_attempts(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    """The historical Stocksy empty doc-map cannot remain an empty artifact."""

    stocksy = _payload(_STOCKSY / "report_analysis" / "doc_map.json")
    recovered = _payload(_AKIN / "report_analysis" / "doc_map.json")
    calls: list[tuple[str, str, str]] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        calls.append((mode, original_response, schema_errors))
        return _response(stocksy if mode == "primary" else recovered)

    caplog.set_level(logging.INFO, logger="market_lense.structured_output_service")
    result = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id="stocksy-2026",
            artifact_family="doc_map",
            schema_name="doc_map",
            model="gpt-5-mini",
            terminal_failure_code="doc_map_invalid_json",
        ),
        _ctx(),
        call_model=call_model,
        normalize_payload=lambda payload: payload,
        validate_payload=lambda payload: None,
        is_substantive=lambda payload: bool(
            isinstance(payload, dict)
            and str(payload.get("title") or "").strip()
            and payload.get("sections")
        ),
        model_pricing={
            "gpt-5-mini": {
                "input_tokens_per_1k_usd": 0.001,
                "output_tokens_per_1k_usd": 0.002,
                "tool_call_usd": 0.0,
            }
        },
    )

    assert result.disposition == "model_repair"
    assert result.attempts == 2
    assert result.payload == recovered
    assert [call[0] for call in calls] == ["primary", "model_repair"]
    assert stocksy["not_found_reason"] in calls[1][1]
    assert "structured_output_empty" in calls[1][2]

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.structured_output_service"
        and '"event": "structured_output_attempt"' in record.message
    ]
    assert_logs_have_required_fields(events)
    assert [event["fields"]["attempt"] for event in events] == [0, 0, 1]
    for event in events:
        fields = event["fields"]
        assert fields["report_id"] == "stocksy-2026"
        assert fields["artifact_family"] == "doc_map"
        assert fields["provider"] == "openai"
        assert fields["model"] == "gpt-5-mini"
        assert fields["tokens"] == 18
        assert "cost" in fields
        assert fields["final_disposition"]

    outcomes = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.structured_output_service"
        and '"event": "structured_output_recovery_outcome"' in record.message
    ]
    assert len(outcomes) == 1
    outcome = outcomes[0]["fields"]
    assert outcome["workflow"] == "report_analysis"
    assert outcome["artifact_family"] == "doc_map"
    assert outcome["schema_name"] == "doc_map"
    assert outcome["provider_model"] == "openai:gpt-5-mini"
    assert outcome["failure_reason"] == "structured_output_empty"
    assert outcome["repair_strategy"] == "model_repair"
    assert outcome["first_pass_valid"] is False
    assert outcome["deterministic_repair_attempted"] is True
    assert outcome["deterministic_repair_succeeded"] is False
    assert outcome["model_repair_attempted"] is True
    assert outcome["model_repair_succeeded"] is True
    assert outcome["retry_exhausted"] is False
    assert outcome["terminal_failure"] is False
    assert outcome["provider_attempts"] == 2
    assert outcome["repair_input_tokens"] == 11
    assert outcome["repair_output_tokens"] == 7
    assert outcome["repair_cost_usd"] > 0
    assert outcome["elapsed_repair_ms"] >= 0


def test_recovery_escapes_literal_newline_without_model_repair() -> None:
    """A transport-only JSON control character is repaired without inventing data."""

    responses: list[str] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        responses.append(mode)
        return OpenAIResponseResult(
            schema_version="1.0",
            text='{"title":"Line one\nLine two","sections":["s"]}',
            model="gpt-5-mini",
            input_tokens=11,
            output_tokens=7,
        )

    result = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id="newline-1",
            artifact_family="doc_map",
            schema_name="doc_map",
            model="gpt-5-mini",
        ),
        _ctx(),
        call_model=call_model,
        normalize_payload=lambda payload: payload,
        validate_payload=lambda payload: None,
        is_substantive=lambda payload: bool(
            isinstance(payload, dict)
            and payload.get("title")
            and payload.get("sections")
        ),
        model_pricing={},
    )

    assert result.disposition == "deterministic_repair"
    assert result.payload == {"title": "Line one\nLine two", "sections": ["s"]}
    assert responses == ["primary"]


@pytest.mark.parametrize("control_character", ["\r", "\t"])
def test_recovery_does_not_deterministically_escape_non_newline_controls(
    control_character: str,
) -> None:
    """Only literal newlines are an approved lossless transport repair."""

    modes: list[str] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        modes.append(mode)
        if mode == "primary":
            return OpenAIResponseResult(
                schema_version="1.0",
                text=(
                    '{"title":"Line one'
                    + control_character
                    + 'Line two","sections":["s"]}'
                ),
                model="gpt-5-mini",
            )
        return _response({"title": "recovered", "sections": ["s"]})

    result = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id="non-newline-control-1",
            artifact_family="doc_map",
            schema_name="doc_map",
            model="gpt-5-mini",
        ),
        _ctx(),
        call_model=call_model,
        normalize_payload=lambda payload: payload,
        validate_payload=lambda payload: None,
        is_substantive=lambda payload: bool(
            isinstance(payload, dict)
            and payload.get("title")
            and payload.get("sections")
        ),
        model_pricing={},
    )

    assert result.disposition == "model_repair"
    assert modes == ["primary", "model_repair"]


def test_retained_empty_taxonomy_terminally_fails_after_bounded_recovery() -> None:
    """The historical empty taxonomy never becomes a successful empty result."""

    stocksy = _payload(_STOCKSY / "report_analysis" / "analysis_vector_store.json")
    modes: list[str] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        modes.append(mode)
        return _response(stocksy)

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            StructuredOutputExecutionRequest(
                schema_version="1.0",
                report_id="stocksy-2026",
                artifact_family="taxonomy",
                schema_name="taxonomy",
                model="gpt-5-mini",
                terminal_failure_code="taxonomy_invalid_json",
            ),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=lambda payload: None,
            is_substantive=lambda payload: bool(
                isinstance(payload, dict) and payload.get("taxonomy")
            ),
            model_pricing={},
        )

    assert exc_info.value.code == "taxonomy_invalid_json"
    assert modes == ["primary", "model_repair", "regeneration"]


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        ({"title": "only title"}, "schema_missing_required"),
        ({"title": ["wrong"], "sections": ["s"]}, "schema_type_mismatch"),
        (
            {"title": "valid", "sections": ["s"], "unsupported": "field"},
            "schema_additional_properties",
        ),
        ({"title": "ungrounded", "sections": ["s"]}, "semantic_invalid"),
    ],
)
def test_recovery_fails_closed_for_parseable_invalid_payloads(
    payload: dict, error_code: str
) -> None:
    """JSON parsing never bypasses schema or semantic validation."""

    modes: list[str] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        modes.append(mode)
        return _response(payload)

    def validate_payload(candidate: dict) -> None:
        if "unsupported" in candidate:
            raise AppError(
                code="schema_additional_properties",
                message="unsupported property",
                retryable=False,
            )
        if "title" not in candidate or "sections" not in candidate:
            raise AppError(
                code="schema_missing_required", message="required", retryable=False
            )
        if not isinstance(candidate["title"], str):
            raise AppError(
                code="schema_type_mismatch", message="title", retryable=False
            )
        if candidate["title"] == "ungrounded":
            raise AppError(
                code="semantic_invalid", message="grounding", retryable=False
            )

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            StructuredOutputExecutionRequest(
                schema_version="1.0",
                report_id="invalid-1",
                artifact_family="doc_map",
                schema_name="doc_map",
            ),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda candidate: candidate,
            validate_payload=validate_payload,
            is_substantive=lambda candidate: bool(candidate),
            model_pricing={},
        )

    assert modes == ["primary", "model_repair", "regeneration"]
    assert error_code in exc_info.value.schema_errors


def test_provider_error_records_terminal_failure_outcome(caplog) -> None:
    """A provider exception is an explicit terminal outcome, never an implicit gap."""

    def call_model(mode: str, original_response: str, schema_errors: str):
        raise AppError(code="openai_request_failed", message="provider", retryable=True)

    caplog.set_level(logging.INFO, logger="market_lense.structured_output_service")
    with pytest.raises(AppError):
        execute_structured_output(
            StructuredOutputExecutionRequest(
                schema_version="1.0",
                report_id="provider-failure-1",
                artifact_family="doc_map",
                schema_name="doc_map",
            ),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=lambda payload: None,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    outcomes = [
        json.loads(record.message)["fields"]
        for record in caplog.records
        if '"event": "structured_output_recovery_outcome"' in record.message
    ]
    assert outcomes == [
        {
            "artifact_family": "doc_map",
            "deterministic_repair_attempted": False,
            "deterministic_repair_succeeded": False,
            "elapsed_repair_ms": 0.0,
            "failure_reason": "openai_request_failed",
            "first_pass_valid": False,
            "model": "",
            "model_repair_attempted": False,
            "model_repair_succeeded": False,
            "outcome_id": "r1:t1:s1:provider-failure-1:doc_map:doc_map",
            "outcome_schema_version": "1.0",
            "prompt_namespace": "doc_map",
            "provider": "openai",
            "provider_attempts": 1,
            "provider_model": "openai:",
            "repair_cost_usd": 0,
            "repair_input_tokens": 0,
            "repair_model_calls": 0,
            "repair_output_tokens": 0,
            "repair_strategy": "provider_error",
            "retry_exhausted": False,
            "retry_attempt": 0,
            "schema_name": "doc_map",
            "schema_root_key": "",
            "terminal": "failure",
            "terminal_failure": True,
            "workflow": "report_analysis",
        }
    ]


def test_regeneration_provider_error_keeps_prior_repair_usage_in_outcome(
    caplog,
) -> None:
    """A late provider error does not discard already attributed repair usage."""

    def call_model(mode: str, original_response: str, schema_errors: str):
        if mode == "regeneration":
            time.sleep(0.02)
            raise AppError(
                code="openai_request_failed", message="provider", retryable=True
            )
        return _response({"title": "", "sections": []})

    caplog.set_level(logging.INFO, logger="market_lense.structured_output_service")
    with pytest.raises(AppError):
        execute_structured_output(
            StructuredOutputExecutionRequest(
                schema_version="1.0",
                report_id="regeneration-provider-failure-1",
                artifact_family="doc_map",
                schema_name="doc_map",
                model="gpt-5-mini",
            ),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: payload,
            validate_payload=lambda payload: None,
            is_substantive=lambda payload: bool(
                payload.get("title") and payload.get("sections")
            ),
            model_pricing={
                "gpt-5-mini": {
                    "input_tokens_per_1k_usd": 0.001,
                    "output_tokens_per_1k_usd": 0.002,
                    "tool_call_usd": 0,
                }
            },
        )

    outcome = next(
        json.loads(record.message)["fields"]
        for record in caplog.records
        if '"event": "structured_output_recovery_outcome"' in record.message
    )
    assert outcome["provider_attempts"] == 3
    assert outcome["repair_model_calls"] == 1
    assert outcome["repair_input_tokens"] == 11
    assert outcome["repair_output_tokens"] == 7
    assert outcome["repair_cost_usd"] > 0
    assert outcome["elapsed_repair_ms"] >= 10


def test_provider_schema_projection_enforces_openai_strict_object_rules() -> None:
    schema = provider_output_schema("artifacts", "cover_semantics")

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["cover_semantics"]
    cover = schema["properties"]["cover_semantics"]
    assert cover["additionalProperties"] is False
    assert cover["required"] == list(cover["properties"])


def test_provider_schema_projection_uses_openai_supported_union_keyword() -> None:
    schema = provider_output_schema("scope_pack")
    scope = schema["properties"]["scope"]

    assert "_cache" not in schema["properties"]
    assert "family_status" not in schema["properties"]
    assert "oneOf" not in scope
    assert [branch["type"] for branch in scope["anyOf"]] == ["string", "object"]


def test_provider_schema_projection_omits_unsupported_conditional_keywords() -> None:
    schema = provider_output_schema("artifacts", "insights_candidates")
    metric = schema["properties"]["insights_candidates"]["items"]["properties"][
        "metric"
    ]

    assert "allOf" not in metric
    assert "if" not in metric
    assert "then" not in metric


def test_context_category_fit_provider_schema_allows_five_selected_categories() -> None:
    schema = provider_output_schema("context_category_fit")

    assert schema["properties"]["selected_category_ids"]["maxItems"] == 5
