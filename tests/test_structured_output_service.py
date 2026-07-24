"""Regression coverage for shared recovery using retained failed artifacts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.services.schema_validator_service import provider_output_schema
from src.services.structured_output_service import execute_structured_output
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
