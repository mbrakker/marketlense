from __future__ import annotations

import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators._artifact_generator.rendering import (
    _normalize_artifact_response,
)
from src.generators.artifact_normalization import (
    editorial_plan_theme_bindings,
    fallback_artifact_insights_from_findings,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure
from src.utils.text_normalization import normalize_text


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="candidate-diag", task_id="t", span_id="s"
    )


def _request() -> StructuredOutputExecutionRequest:
    return StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="candidate-diag",
        artifact_family="insights_candidates",
        schema_name="artifacts",
        schema_root_key="insights_candidates",
        model="gpt-5-mini",
        terminal_failure_code="artifact_structured_output_invalid",
    )


def test_missing_candidate_root_is_not_normalized_to_an_empty_selection() -> None:
    normalized = _normalize_artifact_response(
        {"unrelated": "payload"}, "insights_candidates"
    )

    assert "insights_candidates" not in normalized
    assert normalized["_artifact_response_structure"] == {
        "expected_root_present": False,
        "root_value_type": "missing",
        "raw_candidate_count": 0,
        "normalized_candidate_count": 0,
        "location_only_candidates_removed": 0,
        "invalid_evidence_reference_candidates_rejected": 0,
    }


def test_explicit_empty_candidate_root_remains_distinct_from_missing_root() -> None:
    normalized = _normalize_artifact_response(
        {"insights_candidates": []}, "insights_candidates"
    )

    assert normalized["insights_candidates"] == []
    assert normalized["_artifact_response_structure"] == {
        "expected_root_present": True,
        "root_value_type": "list",
        "raw_candidate_count": 0,
        "normalized_candidate_count": 0,
        "location_only_candidates_removed": 0,
        "invalid_evidence_reference_candidates_rejected": 0,
    }


def test_fallback_theme_matching_canonicalizes_finding_id_forms() -> None:
    findings = {
        "findings": [
            {
                "id": "priority-finding",
                "text": "A priority source finding.",
                "evidence": "The source supports the priority finding.",
                "pages": [4],
                "confidence": "high",
            },
            {
                "id": "other-finding",
                "text": "Another source finding.",
                "evidence": "The source supports another finding.",
                "pages": [5],
                "confidence": "high",
            },
        ]
    }
    plan = {
        "themes": [
            {
                "theme": "Priority theme",
                "priority": 1,
                "evidence_ids": [
                    "evidence:findings:priority-finding",
                    "priority-finding",
                ],
            }
        ]
    }
    fidelity = {
        "results": [
            {
                "status": "supported",
                "candidate": {
                    "claim_id": "evidence:findings:priority-finding"
                },
            },
            {
                "status": "supported",
                "candidate": {"claim_id": "evidence:findings:other-finding"},
            },
        ]
    }

    bindings = editorial_plan_theme_bindings(
        plan,
        source_findings=findings,
        eligible_finding_ids={
            "priority-finding",
            "evidence:findings:priority-finding",
        },
    )
    selected = fallback_artifact_insights_from_findings(
        findings,
        limit=1,
        editorial_plan=plan,
        evidence_fidelity=fidelity,
    )

    assert bindings[0]["direct_finding_ids"] == {normalize_text("priority-finding")}
    assert [item["evidence_id"] for item in selected] == ["priority-finding"]


def test_exhausted_candidate_recovery_retains_bounded_attempt_structure() -> None:
    responses = [{"unrelated": "payload"}] * 3
    modes: list[str] = []

    def call_model(mode: str, original_response: str, schema_errors: str):
        del original_response, schema_errors
        payload = responses[len(modes)]
        modes.append(mode)
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            model="gpt-5-mini",
        )

    def validate_payload(payload: dict[str, object]) -> None:
        structure = payload.get("_artifact_response_structure")
        if isinstance(structure, dict) and not structure.get("expected_root_present"):
            raise AppError(
                code="artifact_response_root_missing",
                message="The candidate response omitted its required root.",
                context=structure,
            )

    with pytest.raises(StructuredOutputFailure) as exc_info:
        execute_structured_output(
            _request(),
            _ctx(),
            call_model=call_model,
            normalize_payload=lambda payload: _normalize_artifact_response(
                payload, "insights_candidates"
            ),
            validate_payload=validate_payload,
            is_substantive=lambda payload: bool(payload),
            model_pricing={},
        )

    assert modes == ["primary", "model_repair", "regeneration"]
    diagnostics = exc_info.value.context["attempt_diagnostics"]
    assert [item["mode"] for item in diagnostics] == modes
    assert [item["error_class"] for item in diagnostics] == [
        "artifact_response_root_missing"
    ] * 3
    assert all(item["expected_root_present"] is False for item in diagnostics)
    assert all(item["root_value_type"] == "missing" for item in diagnostics)
    assert all(item["raw_candidate_count"] == 0 for item in diagnostics)
    assert all(item["response_chars"] > 0 for item in diagnostics)
