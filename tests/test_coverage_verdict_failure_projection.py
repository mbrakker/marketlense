from __future__ import annotations

import json
import logging
from copy import deepcopy

import pytest

from src.contracts.remediation import RemediationListRequest
from src.orchestrators.remediation_orchestrator import (
    _bounded_failure_context,
    record_workflow_failure,
)
from src.services.state_service import list_remediation_records
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _context() -> dict:
    return {
        "coverage_diagnostics": {
            "stage": "semantic_repair",
            "current_plan_identity": "a" * 64,
            "planned_theme_ids": ["fact-1", "fact-2"],
            "selected_candidate_ids": ["insight-1", "insight-2"],
            "planned_themes": [
                {"theme": "private theme one", "fact_ids": ["fact-1"]},
                {"theme": "private theme two", "fact_ids": ["fact-2"]},
            ],
            "theme_verdicts": [
                {
                    "theme": "private theme two",
                    "status": "partial",
                    "resolution": "unresolved",
                    "importance": "essential",
                    "supporting_insight_ids": ["insight-2"],
                    "reason": "private model explanation",
                },
                {
                    "theme": "private theme one",
                    "status": "covered",
                    "resolution": "retained",
                    "importance": "optional",
                    "supporting_insight_ids": ["insight-1"],
                    "reason": "private source excerpt",
                },
            ],
        }
    }


def test_bound_decisions_survive_reprojection_without_prose():
    projected = _bounded_failure_context(_context())
    assert projected["coverage_diagnostics"]["theme_verdict_projection"] == {
        "schema_version": "1.0",
        "status": "complete",
        "verdicts": [
            {
                "plan_index": 1,
                "fact_ids": ["fact-2"],
                "status": "partial",
                "resolution": "unresolved",
                "importance": "essential",
                "supporting_insight_ids": ["insight-2"],
            },
            {
                "plan_index": 0,
                "fact_ids": ["fact-1"],
                "status": "covered",
                "resolution": "retained",
                "importance": "optional",
                "supporting_insight_ids": ["insight-1"],
            },
        ],
    }
    assert "private" not in str(projected)
    assert _bounded_failure_context(projected) == projected


def test_schema_valid_verdicts_do_not_require_fields_absent_from_response():
    context = _context()
    for verdict in context["coverage_diagnostics"]["theme_verdicts"]:
        # The producer projects absent response fields as empty strings.
        verdict["resolution"] = ""
        verdict["importance"] = ""
    context["coverage_diagnostics"]["theme_verdicts"][0]["status"] = (
        "redundant_optional"
    )
    projected = _bounded_failure_context(context)
    projection = projected["coverage_diagnostics"]["theme_verdict_projection"]
    assert projection["status"] == "complete"
    assert projection["verdicts"][0] == {
        "plan_index": 1,
        "fact_ids": ["fact-2"],
        "status": "redundant_optional",
        "supporting_insight_ids": ["insight-2"],
    }
    assert _bounded_failure_context(projected) == projected
    assert "private" not in str(projected)


@pytest.mark.parametrize(
    "defect",
    [
        "unknown_theme",
        "duplicate_theme",
        "unknown_status",
        "unknown_support",
        "malformed",
        "missing_verdict",
        "too_many",
        "missing_plan_hash",
        "empty_fact_binding",
    ],
)
def test_invalid_verdicts_are_explicitly_incomplete_and_never_exported(defect):
    context = _context()
    diagnostic = context["coverage_diagnostics"]
    verdicts = diagnostic["theme_verdicts"]
    if defect == "unknown_theme":
        verdicts[0]["theme"] = "untrusted private content"
    elif defect == "duplicate_theme":
        verdicts[0]["theme"] = verdicts[1]["theme"]
    elif defect == "unknown_status":
        verdicts[0]["status"] = "private-status"
    elif defect == "unknown_support":
        verdicts[0]["supporting_insight_ids"] = ["private-id"]
    elif defect == "malformed":
        verdicts[0] = "private response"
    elif defect == "missing_verdict":
        verdicts.pop()
    elif defect == "too_many":
        verdicts.extend(deepcopy(verdicts) * 17)
    elif defect == "empty_fact_binding":
        diagnostic["planned_themes"][0]["fact_ids"] = []
    else:
        diagnostic.pop("current_plan_identity")
    projected = _bounded_failure_context(context)
    assert projected["coverage_diagnostics"]["theme_verdict_projection"] == {
        "schema_version": "1.0",
        "status": "incomplete",
        "verdicts": [],
    }
    assert "private" not in str(projected)
    assert _bounded_failure_context(projected) == projected


def test_failure_record_and_export_retain_verdicts_without_private_text(
    tmp_path, caplog
):
    ctx = new_run_context(task_id="coverage-test")
    state_db = str(tmp_path / "state.sqlite")
    caplog.set_level(logging.INFO, logger="market_lense.remediation_orchestrator")
    record_workflow_failure(
        state_db=state_db,
        workflow="report_generation",
        stage="artifact_generation",
        operation="editorial_theme_coverage",
        error=AppError(
            code="artifact_final_insight_coverage_invalid",
            message="coverage failed",
            retryable=False,
            context=_context(),
        ),
        ctx=ctx,
        report_id="report-1",
    )
    records = list_remediation_records(
        RemediationListRequest(schema_version="1.0", state_db=state_db), ctx
    ).records
    diagnostics = records[0].diagnostics
    context = diagnostics["error_context"]
    assert (
        context["coverage_diagnostics"]["theme_verdict_projection"]["status"]
        == "complete"
    )
    assert _bounded_failure_context(context) == context
    assert "private" not in json.dumps(diagnostics)
    assert "remediation_failure_recorded" in caplog.text
    assert "private" not in caplog.text


def test_reprojection_rejects_unknown_version_and_unbound_ids():
    context = _bounded_failure_context(_context())
    projection = context["coverage_diagnostics"]["theme_verdict_projection"]
    projection["schema_version"] = "2.0"
    assert (
        _bounded_failure_context(context)["coverage_diagnostics"][
            "theme_verdict_projection"
        ]["status"]
        == "incomplete"
    )
    projection["schema_version"] = "1.0"
    projection["verdicts"][0]["fact_ids"] = ["private-id"]
    assert _bounded_failure_context(context)["coverage_diagnostics"][
        "theme_verdict_projection"
    ] == {"schema_version": "1.0", "status": "incomplete", "verdicts": []}
