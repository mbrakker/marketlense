from __future__ import annotations

from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationReport
from src.orchestrators import workflow_control_orchestrator as workflow


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_inline_validation_report_promotes_publish_remediation_payload() -> None:
    report = ValidationReport(
        schema_version="1.1",
        status="pass",
        severity="warning",
        source_path="out/report/validation.inline.json",
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="Generic artifact wording detected: valuable insights",
                severity="warning",
                affected_section="artifacts.summary",
                rule_id="artifact_quality.generic_wording",
                repair_target="summary",
                entity_id="summary",
            ),
            ValidationIssue(
                schema_version="1.0",
                message="LLM grounding validation is deferred and must run before final publish.",
                severity="info",
                affected_section="validation",
                rule_id="deferred_grounding_required",
                repair_target="validation_grounding",
                entity_id="report-1",
            ),
        ],
    )

    remediation = workflow.build_publish_remediation_from_validation(
        report,
        value_band="high",
        policy_mode="hold_high_value_warnings",
        ctx=_ctx(),
    )

    assert remediation.decision == "hold"
    assert remediation.warning_count == 1
    assert remediation.deferred_grounding_count == 1
    assert remediation.targets[0].rule_id == "artifact_quality.generic_wording"
    assert remediation.targets[0].repair_action == "regenerate_artifact"
    assert remediation.targets[0].sample_text == "Generic artifact wording detected"
    assert remediation.targets[1].repair_action == "run_deferred_grounding"


def test_supervisor_plan_uses_scorecard_gate_for_publish_ready_run() -> None:
    passing_scorecard = {
        "schema_version": "1.0",
        "run_id": "run-1",
        "warnings": [],
        "error_count": 0,
        "retry_count": 1,
        "validation_failure_count": 0,
        "cost_usd": 0.12,
    }
    failing_scorecard = {
        **passing_scorecard,
        "warnings": ["validation_failure_count 1 exceeds 0"],
        "validation_failure_count": 1,
    }

    allowed_gate = workflow.evaluate_run_health_gate(
        workflow.RunHealthGateInput(
            schema_version="1.0",
            workflow="publishing",
            scorecard=passing_scorecard,
            max_warnings=0,
            allow_threshold_override=False,
            policy_version="run-health-gate-v1",
        ),
        ctx=_ctx(),
    )
    failed_gate = workflow.evaluate_run_health_gate(
        workflow.RunHealthGateInput(
            schema_version="1.0",
            workflow="publishing",
            scorecard=failing_scorecard,
            max_warnings=0,
            allow_threshold_override=False,
            policy_version="run-health-gate-v1",
        ),
        ctx=_ctx(),
    )

    plan = workflow.plan_autonomous_run(
        workflow.AutonomousRunSupervisorInput(
            schema_version="1.0",
            workflow="publishing",
            run_id="run-1",
            current_state="publish_ready",
            latest_safe_checkpoint="render_complete",
            idempotency_scope="publish",
            idempotency_key="publish:file-1",
            preflight_passed=True,
            duplicate=False,
            validation_status="pass",
            retry_action="",
            health_gate=allowed_gate,
            publish_allowed=True,
            blockers=[],
        ),
        ctx=_ctx(),
    )
    held = workflow.plan_autonomous_run(
        workflow.AutonomousRunSupervisorInput(
            schema_version="1.0",
            workflow="publishing",
            run_id="run-2",
            current_state="publish_ready",
            latest_safe_checkpoint="render_complete",
            idempotency_scope="publish",
            idempotency_key="publish:file-2",
            preflight_passed=True,
            duplicate=False,
            validation_status="pass",
            retry_action="",
            health_gate=failed_gate,
            publish_allowed=True,
            blockers=[],
        ),
        ctx=_ctx(),
    )

    assert allowed_gate.outcome == "pass"
    assert failed_gate.outcome == "fail"
    assert plan.selected_action == "publish"
    assert plan.expected_side_effects == ["wordpress_publish"]
    assert held.selected_action == "notify"
    assert held.blockers == ["run_health_gate_failed"]


def test_supervisor_dispatch_persists_registered_handler_outcome(tmp_path) -> None:
    gate = workflow.evaluate_run_health_gate(
        workflow.RunHealthGateInput(
            schema_version="1.0",
            workflow="publishing",
            scorecard={"run_id": "run-dispatch", "warnings": []},
        ),
        ctx=_ctx(),
    )
    plan = workflow.plan_autonomous_run(
        workflow.AutonomousRunSupervisorInput(
            schema_version="1.0",
            workflow="publishing",
            run_id="run-dispatch",
            current_state="publish_ready",
            latest_safe_checkpoint="render_complete",
            idempotency_scope="publish",
            idempotency_key="publish:dispatch",
            preflight_passed=True,
            validation_status="pass",
            health_gate=gate,
            publish_allowed=True,
        ),
        ctx=_ctx(),
    )

    execution = workflow.dispatch_autonomous_run(
        plan,
        state_db=str(tmp_path / "state.sqlite"),
        action_handlers={"publish": lambda _plan, _ctx: "wordpress_draft_created"},
        ctx=_ctx(),
    )

    assert execution.status == "completed"
    assert execution.outcome == "wordpress_draft_created"
    from src.services.state_service import list_workflow_control_observations
    from src.contracts.state import WorkflowControlObservationListRequest

    persisted = list_workflow_control_observations(
        WorkflowControlObservationListRequest(
            schema_version="1.0",
            state_db=str(tmp_path / "state.sqlite"),
            workflow="publishing",
        ),
        _ctx(),
    )
    assert persisted.observations[0].step_name == "supervisor:publish"


def test_run_health_gate_blocks_configured_operational_breaches() -> None:
    decision = workflow.evaluate_run_health_gate(
        workflow.RunHealthGateInput(
            schema_version="1.0",
            workflow="ingest",
            scorecard={
                "run_id": "run-health",
                "warnings": [],
                "cost_usd": 4.0,
                "retry_exhaustion_rate": 0.3,
                "crop_rejection_rate": 0.4,
                "evidence_complete": False,
            },
            thresholds={
                "max_cost_usd": 3.0,
                "max_retry_exhaustion_rate": 0.2,
                "max_crop_rejection_rate": 0.3,
            },
        ),
        ctx=_ctx(),
    )

    assert decision.outcome == "fail"
    assert decision.action == "notify"
    assert "run_health_cost_usd_exceeded" in decision.blockers
