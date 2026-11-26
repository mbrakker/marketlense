from __future__ import annotations

import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.remediation import RemediationListRequest
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators.artifact_normalization import (
    validate_final_insight_editorial_coverage,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.services.schema_validator_service import validate_output_schema
from src.services.state_service import list_remediation_records
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from src.utils.structured_output import StructuredOutputFailure
from tests._test_artifact_generator._shared import _ctx


@pytest.mark.parametrize(
    ("changed_paths", "extra", "expected_path", "expected_validator"),
    [
        (["same", "same"], {}, "repair_decision.changed_paths", "uniqueItems"),
        (
            ["safe"],
            {"private_customer_key": "private_customer_value"},
            "repair_decision",
            "additionalProperties",
        ),
    ],
)
def test_schema_diagnostics_survive_remediation_without_private_response(
    tmp_path, changed_paths, extra, expected_path, expected_validator
):
    payload = {
        "repair_decision": {
            "schema_version": "1.0",
            "repair_action": "replace",
            "repair_strategy": "current",
            "evidence_ids_used": [],
            "changed_paths": changed_paths,
            "minimal_patch": [
                {"op": "replace", "path": "safe", "value": "private response text"}
            ],
            **extra,
        }
    }
    ctx = _ctx()
    with pytest.raises(StructuredOutputFailure) as caught:
        execute_structured_output(
            StructuredOutputExecutionRequest(
                schema_version="1.0",
                report_id="report",
                artifact_family="insights_final",
                schema_name="regeneration_repair_decision",
                allow_model_recovery=False,
                terminal_failure_code="artifact_structured_output_invalid",
            ),
            ctx,
            call_model=lambda *args: OpenAIResponseResult(
                schema_version="1.0", text=json.dumps(payload), parsed_json=payload
            ),
            normalize_payload=lambda candidate: candidate,
            validate_payload=lambda candidate: validate_output_schema(
                payload=candidate,
                schema_name="regeneration_repair_decision",
                root_key="",
                ctx=ctx,
            ),
            is_substantive=lambda candidate: bool(candidate),
            model_pricing={},
        )
    assert caught.value.code == "artifact_structured_output_invalid"
    assert caught.value.context["schema_path"] == expected_path
    assert caught.value.context["schema_validator"] == expected_validator
    assert "private response text" not in json.dumps(caught.value.context)
    assert "private_customer" not in json.dumps(caught.value.context)
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="insights_final",
        error=caught.value,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    diagnostic = records[0].diagnostics["error_context"]
    assert diagnostic["schema_path"] == expected_path
    assert diagnostic["schema_validator"] == expected_validator
    assert "private response text" not in json.dumps(records[0].diagnostics)
    assert "private_customer" not in json.dumps(records[0].diagnostics)


def test_missing_essential_theme_reason_survives_attempt_remediation(tmp_path):
    private_theme = "Private source theme that must not be retained"
    plan = {
        "themes": [
            {
                "theme": private_theme,
                "priority": 1,
                "importance": "essential",
                "evidence_ids": ["f1"],
                "required_evidence_ids": ["f1"],
                "alternative_evidence_groups": [],
            }
        ]
    }
    candidates = [{"id": "c1", "evidence_id": "f1"}, {"id": "c2", "evidence_id": "f2"}]

    def call_model(mode, original_response, schema_errors):
        return OpenAIResponseResult(
            schema_version="1.0",
            model="test",
            text=json.dumps({"insights_final": [candidates[1]]}),
        )

    def validate(payload):
        validate_final_insight_editorial_coverage(
            final_insights=payload["insights_final"],
            candidate_insights=candidates,
            editorial_plan=plan,
        )

    ctx = _ctx()
    request = StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="report",
        artifact_family="insights_final",
        schema_name="artifacts",
        model="test",
        terminal_failure_code="artifact_structured_output_invalid",
    )
    with pytest.raises(StructuredOutputFailure) as caught:
        execute_structured_output(
            request,
            ctx,
            call_model=call_model,
            normalize_payload=lambda p: p,
            validate_payload=validate,
            is_substantive=lambda p: bool(p),
            model_pricing={},
        )
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="insights_final",
        error=caught.value,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    attempts = records[0].diagnostics["error_context"]["attempt_diagnostics"]
    assert [attempt["coverage_failure_category"] for attempt in attempts] == [
        "missing_planned_themes",
        "missing_planned_themes",
        "missing_planned_themes",
    ]
    assert private_theme not in json.dumps(records[0].diagnostics)


def test_insight_attempt_error_classes_survive_remediation_without_response_text(
    tmp_path,
):
    codes = {
        "primary": "artifact_final_insight_lineage_invalid",
        "model_repair": "schema_reference_missing",
        "regeneration": "artifact_final_insight_coverage_invalid",
    }

    def call_model(mode, original_response, schema_errors):
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"phase": mode, "source": "private source prose"}),
            model="test",
        )

    def validate(payload):
        ids = {
            "primary": [
                "candidate-1",
                "private source prose",
                "x" * 129,
                "candidate-2",
                "candidate-3",
                "candidate-4",
            ],
            "model_repair": ["candidate-9"],
            "regeneration": ["candidate-2"],
        }
        raise AppError(
            code=codes[payload["phase"]],
            message="invalid",
            context={"invalid_insight_ids": ids[payload["phase"]]},
        )

    ctx = _ctx()
    request = StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="report",
        artifact_family="insights_final",
        schema_name="artifacts",
        model="test",
        terminal_failure_code="artifact_structured_output_invalid",
    )
    with pytest.raises(StructuredOutputFailure) as caught:
        execute_structured_output(
            request,
            ctx,
            call_model=call_model,
            normalize_payload=lambda p: p,
            validate_payload=validate,
            is_substantive=lambda p: bool(p),
            model_pricing={},
        )
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="insights_final",
        error=caught.value,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    diagnostics = records[0].diagnostics
    attempts = diagnostics["error_context"]["attempt_diagnostics"]
    assert [(a["mode"], a["error_class"]) for a in attempts] == [
        ("primary", "artifact_final_insight_lineage_invalid"),
        ("model_repair", "schema_reference_missing"),
        ("regeneration", "artifact_final_insight_coverage_invalid"),
    ]
    assert all(a["parse_status"] == "valid" for a in attempts)
    assert [a["invalid_insight_ids"] for a in attempts] == [
        ["candidate-1", "candidate-2", "candidate-3"],
        ["candidate-9"],
        ["candidate-2"],
    ]
    assert diagnostics["error_context"]["invalid_insight_ids"] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert "private source prose" not in json.dumps(diagnostics)


def test_unrecognized_attempt_error_class_is_not_persisted(tmp_path):
    ctx = _ctx()
    error = StructuredOutputFailure(
        code="artifact_structured_output_invalid",
        message="invalid",
        artifact_family="insights_final",
        response_text="private response",
        failure_context={
            "attempt_diagnostics": [
                {
                    "attempt": 0,
                    "mode": "primary",
                    "error_class": "private_source_prose",
                    "invalid_insight_ids": [
                        "private source prose",
                        "x" * 129,
                        "safe-1",
                    ],
                },
                {
                    "attempt": 1,
                    "mode": "model_repair",
                    "error_class": ["private"],
                    "invalid_insight_ids": {"private": "source"},
                },
            ]
        },
    )
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="insights_final",
        error=error,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    attempts = records[0].diagnostics["error_context"]["attempt_diagnostics"]
    assert all("error_class" not in item for item in attempts)
    assert attempts[0]["invalid_insight_ids"] == ["safe-1"]
    assert "invalid_insight_ids" not in attempts[1]
    assert "private" not in json.dumps(records[0].diagnostics)
