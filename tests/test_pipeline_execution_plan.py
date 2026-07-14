from __future__ import annotations

import json
import logging

from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    PipelineExecutionAuthorizationRequest,
    RunIntent,
)
from src.orchestrators import workflow_control_orchestrator as workflow
from src.utils.errors import AppError


def test_pipeline_execution_plan_is_side_effect_free_and_complete(caplog) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    plan = workflow.build_pipeline_execution_plan(
        RunIntent(
            schema_version="1.0",
            intent="publish ready reports",
            subject="report-42",
            publisher="publisher",
            report_id="report-42",
            requested_side_effects=["wordpress"],
            dry_run=True,
            allow_automation=False,
            metadata={"source": "test"},
        ),
        workflow.default_workflow_control_settings(),
        ctx=RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )

    assert plan.executable is True
    assert plan.workflow == "publishing"
    assert plan.profile == "publishing"
    assert plan.ordered_steps == ["preflight", "execute", "complete", "fail"]
    assert plan.required_credentials == ["wordpress"]
    assert plan.planned_side_effects == ["wordpress", "publish"]
    assert plan.checkpoints == []
    assert plan.expected_artifacts == []
    assert len(plan.idempotency_key) == 64
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.workflow_control_orchestrator"
    ]
    assert events[-1]["event"] == "workflow_pipeline_execution_plan"


def test_pipeline_execution_authorization_rejects_unplanned_side_effects(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    plan = workflow.build_pipeline_execution_plan(
        RunIntent(
            schema_version="1.0",
            intent="publish ready reports",
            subject="report-42",
            publisher="publisher",
            report_id="report-42",
            requested_side_effects=["wordpress"],
            dry_run=True,
            allow_automation=False,
            metadata={"source": "test"},
        ),
        workflow.default_workflow_control_settings(),
        ctx=ctx,
    )

    try:
        workflow.authorize_pipeline_execution(
            PipelineExecutionAuthorizationRequest(
                schema_version="1.0",
                plan=plan,
                expected_workflow="publishing",
                requested_side_effects=["browser"],
            ),
            ctx=ctx,
        )
    except AppError as error:
        assert error.code == "workflow_execution_plan_denied"
        assert error.retryable is False
        assert error.severity == "warning"
        assert error.context["reason"] == "requested_side_effect_not_planned"
    else:
        raise AssertionError("Unplanned browser side effect must be denied")

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.workflow_control_orchestrator"
    ]
    assert events[-1]["event"] == "workflow_pipeline_execution_denied"
