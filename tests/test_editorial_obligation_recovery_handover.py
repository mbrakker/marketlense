import json
from copy import deepcopy

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.errors import AppError
from tests._test_pre_e2e_integrity.cases_01_public_surfaces_and_status import (
    _valid_report_review_payload,
)
from tests._test_validation_generator._shared import _ctx


def test_recovery_identifies_bound_alternative_for_rejected_review():
    items, scope, valid = _valid_report_review_payload()
    scope["authority"] = "canonical_verified_facts"
    obligation = scope["original_editorial_plan_coverage"][
        "original_essential_obligations"
    ][0]
    obligation.update(
        evidence_ids=["verified-fact:fact-1", "verified-fact:f03"],
        required_evidence_ids=[],
        alternative_evidence_groups=[["verified-fact:fact-1", "verified-fact:f03"]],
    )
    invalid = deepcopy(valid)
    invalid["original_essential_obligation_assessments"][0]["evidence_ids"].append(
        "verified-fact:f03"
    )
    feedback = []

    def call_model(mode, original_response, schema_errors):
        if mode == "primary":
            payload = invalid
        else:
            feedback.append(schema_errors)
            payload = (
                valid
                if "bound evidence ids: verified-fact:fact-1" in schema_errors
                else invalid
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            model="test-model",
        )

    result = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id="report",
            artifact_family="public_editorial_quality",
            schema_name="public_editorial_quality_review",
            model="test-model",
            terminal_failure_code="review_invalid",
        ),
        _ctx(),
        call_model=call_model,
        normalize_payload=lambda value: value,
        validate_payload=lambda value: _validate_public_editorial_review_payload(
            value, items, _ctx(), scope
        ),
        is_substantive=lambda value: bool(value),
        model_pricing={},
    )
    assert result.payload == valid
    assert "unbound evidence ids: verified-fact:f03" in feedback[0]
    assert "bound evidence ids: verified-fact:fact-1" in feedback[0]


def test_regeneration_receives_both_original_binding_and_latest_target_failure():
    items, scope, valid = _valid_report_review_payload()
    scope["authority"] = "canonical_verified_facts"
    obligation = scope["original_editorial_plan_coverage"][
        "original_essential_obligations"
    ][0]
    obligation.update(
        evidence_ids=["verified-fact:fact-1", "verified-fact:f03"],
        required_evidence_ids=[],
        alternative_evidence_groups=[["verified-fact:fact-1", "verified-fact:f03"]],
    )
    invalid = deepcopy(valid)
    invalid["original_essential_obligation_assessments"][0]["evidence_ids"].append(
        "verified-fact:f03"
    )
    wrong_target = deepcopy(valid)
    wrong_target["report_verdict"].update(
        status="fail",
        severity="error",
        rule_id="public_editorial_quality.semantic_analytical_depth",
        hard_fail_class="editorial_quality",
        repair_target="expert_comment",
        reason="The report needs more specific commercial analysis.",
    )
    wrong_target["report_verdict"]["dimensions"]["analytical_depth"] = {
        "status": "fail",
        "reason": "The analysis lacks distinct implications.",
    }
    with pytest.raises(AppError) as caught:
        _validate_public_editorial_review_payload(wrong_target, items, _ctx(), scope)
    assert caught.value.code == "public_editorial_quality_report_review_target_mismatch"
    feedback = []

    def call_model(mode, original_response, schema_errors):
        if mode == "primary":
            payload = invalid
        elif mode == "model_repair":
            payload = wrong_target
        else:
            feedback.append(schema_errors)
            payload = (
                valid
                if (
                    "unbound evidence ids: verified-fact:f03" in schema_errors
                    and "public_editorial_quality_report_review_target_mismatch"
                    in schema_errors
                )
                else invalid
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            model="test-model",
        )

    result = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id="report",
            artifact_family="public_editorial_quality",
            schema_name="public_editorial_quality_review",
            model="test-model",
            terminal_failure_code="review_invalid",
        ),
        _ctx(),
        call_model=call_model,
        normalize_payload=lambda value: value,
        validate_payload=lambda value: _validate_public_editorial_review_payload(
            value, items, _ctx(), scope
        ),
        is_substantive=lambda value: bool(value),
        model_pricing={},
    )
    assert result.payload == valid
    assert "unbound evidence ids: verified-fact:f03" in feedback[0]
    assert "public_editorial_quality_report_review_target_mismatch" in feedback[0]
