from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.remediation import RemediationListRequest
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators.artifact_normalization import (
    validate_substantive_editorial_theme_coverage,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.services.state_service import list_remediation_records
from src.services.structured_output_service import execute_structured_output
from src.utils.structured_output import StructuredOutputFailure
from tests._test_artifact_generator._shared import _ctx
from tests.test_verified_semantic_completeness_contract import (
    _incomplete_material_coverage_payload,
    _verified_material_gap_fixture,
)


def test_coverage_attempt_categories_survive_remediation_without_source_content(
    tmp_path,
):
    plan, candidates, final = _verified_material_gap_fixture()
    invalid_ids = _incomplete_material_coverage_payload(
        report_completeness="complete",
        diagnosis="planned_theme_execution",
        recovery_action="none",
        material_gaps=[],
    )
    invalid_ids["theme_coverage"][0]["supporting_insight_ids"] = ["unknown"]
    missing = deepcopy(invalid_ids)
    missing["theme_coverage"] = []
    responses = iter([invalid_ids, missing, invalid_ids])
    feedback = []

    def call_model(mode, original_response, schema_errors):
        feedback.append(schema_errors)
        return OpenAIResponseResult(
            schema_version="1.0", text=json.dumps(next(responses)), model="test"
        )

    def validate(payload):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=plan,
            final_insights=final,
            candidate_insights=candidates,
        )

    ctx = _ctx()
    request = StructuredOutputExecutionRequest(
        schema_version="1.0",
        report_id="report",
        artifact_family="theme_coverage",
        schema_name="editorial_theme_coverage_output",
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

    attempts = caught.value.context["attempt_diagnostics"]
    assert [item["coverage_failure_category"] for item in attempts] == [
        "unauthorized_supporting_insights",
        "missing_planned_themes",
        "unauthorized_supporting_insights",
    ]
    assert all("coverage failure category" not in item for item in feedback)
    attempts[0]["source_text"] = "private source prose"
    attempts[1]["provider_status"] = "private source prose"
    attempts[2]["coverage_failure_category"] = "private-source-prose"
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="coverage",
        error=caught.value,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    retained = records[0].diagnostics["error_context"]["attempt_diagnostics"]
    assert [(item["attempt"], item["mode"]) for item in retained] == [
        (0, "primary"),
        (1, "model_repair"),
        (2, "regeneration"),
    ]
    assert (
        retained[0]["coverage_failure_category"] == "unauthorized_supporting_insights"
    )
    assert retained[1]["coverage_failure_category"] == "missing_planned_themes"
    assert "coverage_failure_category" not in retained[2]
    assert "private" not in json.dumps(records[0].diagnostics)


def test_remediation_ignores_malformed_attempt_metadata(tmp_path):
    error = StructuredOutputFailure(
        code="artifact_structured_output_invalid",
        message="invalid",
        artifact_family="theme_coverage",
        response_text="private source prose",
        failure_context={
            "attempt_diagnostics": [
                {"attempt": 0, "mode": {"private": "source"}},
                {
                    "attempt": 1,
                    "mode": "model_repair",
                    "coverage_failure_category": ["private"],
                },
                {
                    "attempt": 2,
                    "mode": "regeneration",
                    "parse_status": {"private": "source"},
                },
                {"attempt": 0, "mode": "primary"},
            ]
        },
    )
    ctx = _ctx()
    state_db = str(tmp_path / "state.sqlite")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="coverage",
        error=error,
        ctx=ctx,
        report_id="report",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    attempts = records[0].diagnostics["error_context"]["attempt_diagnostics"]
    assert attempts == [
        {"attempt": 1, "mode": "model_repair"},
        {"attempt": 2, "mode": "regeneration"},
    ]
    assert "private" not in json.dumps(records[0].diagnostics)
