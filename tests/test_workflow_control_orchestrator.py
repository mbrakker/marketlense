from __future__ import annotations

import json
import logging

from dataclasses import asdict

import pytest

from src.contracts.config import ConfigLoadRequest
from src.contracts.retry_telemetry import (
    RetryDecisionTelemetryReport,
    RetryDecisionTelemetryRow,
)
from src.contracts.run_context import RunContext
from src.orchestrators import workflow_control_orchestrator as workflow
from src.services import config_service


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _events(caplog) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.workflow_control_orchestrator":
            events.append(payload)
    return events


def test_workflow_control_config_loads_yaml_profiles_and_policy_map(
    tmp_path,
    assert_no_defaulted_required_fields,
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
workflow_control:
  schema_version: "1.0"
  preflight_profiles:
    report_generation:
      workflow: "report_generation"
      planned_side_effects: ["pdf", "model"]
      require_llm: true
      require_drive: false
      require_publish: false
      require_browser: false
      prompt_namespaces: ["report_vs/doc_map"]
    report_download:
      workflow: "report_download"
      planned_side_effects: ["browser", "drive"]
      require_llm: true
      require_drive: true
      require_publish: false
      require_browser: true
      prompt_namespaces: ["browser_report_download/browser_route"]
  retry_policies:
    report_generation:
      report_pipeline:
        policy_id: "report_generation.report_pipeline.v1"
        retries: 2
        base_delay_seconds: 1.0
        backoff_step_seconds: 1.0
        jitter_seconds: 0.25
  concurrency:
    model:
      min_limit: 1
      max_limit: 4
      default_limit: 2
      high_retry_rate: 0.25
      high_latency_ms: 5000
      low_retry_rate: 0.05
      low_latency_ms: 1500
  operational_memory:
    ttl_days: 30
    min_observations: 2
""",
        encoding="utf-8",
    )

    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
        _ctx(),
    )

    assert settings.schema_version == "1.0"
    assert set(settings.preflight_profiles) >= {
        "report_generation",
        "report_download",
    }
    report_download = settings.preflight_profiles["report_download"]
    assert report_download.require_drive is True
    assert report_download.require_browser is True
    retry_policy = settings.retry_policies["report_generation"]["report_pipeline"]
    assert retry_policy.policy_id == "report_generation.report_pipeline.v1"
    assert retry_policy.retries == 2
    assert settings.concurrency["model"].max_limit == 4
    assert_no_defaulted_required_fields(report_download)
    assert_no_defaulted_required_fields(retry_policy)


def test_workflow_preflight_profile_builds_pipeline_request(
    ingest_settings,
    publish_settings_factory,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    catalog = workflow.default_workflow_control_settings()

    request = workflow.build_workflow_preflight_request(
        catalog,
        workflow_name="publishing",
        settings=ingest_settings,
        publish_settings=publish_settings_factory(),
        require_live_endpoints=True,
        ctx=_ctx(),
    )

    assert request.workflow == "publishing"
    assert request.require_publish is True
    assert request.require_drive is False
    assert request.require_live_endpoints is True
    assert "publish" in request.planned_side_effects
    assert "report_vs/doc_map" not in request.prompt_namespaces
    events = _events(caplog)
    assert events[-1]["event"] == "workflow_preflight_profile_resolved"
    assert events[-1]["fields"]["workflow"] == "publishing"
    assert events[-1]["fields"]["require_live_endpoints"] is True
    assert "report_vs/doc_map" not in events[-1]["fields"]["prompt_namespaces"]


def test_workflow_control_config_rejects_invalid_retry_policy(
    tmp_path,
    assert_app_error,
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
workflow_control:
  retry_policies:
    report_generation:
      report_pipeline:
        policy_id: "report_generation.report_pipeline.v1"
        retries: -1
        base_delay_seconds: 1.0
        backoff_step_seconds: 1.0
        jitter_seconds: 0.25
""",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        config_service.load_workflow_control_settings(
            ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="workflow_retry_policy_invalid",
        retryable=False,
        severity="error",
    )


def test_report_generation_preflight_expands_required_prompt_namespaces(
    ingest_settings,
) -> None:
    catalog = workflow.default_workflow_control_settings()

    request = workflow.build_workflow_preflight_request(
        catalog,
        workflow_name="report_generation",
        settings=ingest_settings,
        require_live_endpoints=False,
    )

    assert request.workflow == "report_generation"
    assert request.require_llm is True
    assert "report_vs/taxonomy" in request.prompt_namespaces
    assert "report_vs/doc_map" in request.prompt_namespaces
    assert "rank_candidates" in request.prompt_namespaces


def test_machine_readable_workflow_dag_validates_state_transitions(
    assert_no_defaulted_required_fields,
) -> None:
    catalog = workflow.default_workflow_control_settings()

    contract = workflow.resolve_workflow_contract(catalog, "report_generation")

    assert contract.workflow == "report_generation"
    assert contract.version == "1.0"
    assert workflow.is_valid_transition(
        contract, from_state="preflighted", to_state="source_prepared"
    )
    assert not workflow.is_valid_transition(
        contract, from_state="render_complete", to_state="source_prepared"
    )
    assert "analysis_complete" in contract.checkpoint_outputs
    assert "processed" in contract.terminal_outcomes
    assert_no_defaulted_required_fields(contract)


def test_machine_readable_workflow_dag_rejects_unknown_transition_state(
    assert_app_error,
) -> None:
    contract = workflow.WorkflowContract(
        schema_version="1.0",
        workflow="broken",
        version="1.0",
        states=["pending", "done"],
        initial_state="pending",
        transitions=[
            workflow.WorkflowTransition(
                schema_version="1.0",
                from_state="pending",
                to_state="missing",
                step_name="bad_step",
                retry_policy_ref="default.v1",
                side_effects=[],
            )
        ],
        prerequisites={},
        checkpoint_outputs=[],
        validation_gates=["preflight"],
        terminal_outcomes=["done"],
    )
    catalog = workflow.WorkflowControlSettings(
        schema_version="1.0",
        preflight_profiles={},
        retry_policies={},
        workflow_contracts={"broken": contract},
        concurrency={},
        operational_memory_ttl_days=30,
        operational_memory_min_observations=2,
    )

    with pytest.raises(Exception) as exc_info:
        workflow.resolve_workflow_contract(catalog, "broken")

    assert_app_error(
        exc_info.value,
        code="workflow_contract_invalid",
        retryable=False,
        severity="error",
    )


def test_retry_policy_resolves_by_workflow_and_step(caplog) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    catalog = workflow.default_workflow_control_settings()

    resolved = workflow.resolve_retry_policy(
        catalog,
        workflow_name="report_generation",
        step_name="report_pipeline",
        ctx=_ctx(),
    )

    assert resolved.policy_id == "report_generation.report_pipeline.v1"
    assert resolved.policy.retries >= 1
    assert resolved.workflow == "report_generation"
    assert resolved.step_name == "report_pipeline"
    events = _events(caplog)
    assert events[-1]["event"] == "workflow_retry_policy_resolved"
    assert events[-1]["fields"]["policy_id"] == resolved.policy_id


def test_operational_memory_recommends_fastest_successful_route() -> None:
    telemetry = RetryDecisionTelemetryReport(
        schema_version="1.0",
        decision_count=1,
        retry_count=1,
        deferred_count=0,
        user_action_required_count=0,
        retry_exhaustion_count=0,
        successful_after_retry_count=1,
        successful_after_retry_rate=1.0,
        retry_exhaustion_rate=0.0,
        cumulative_retry_delay_seconds=2.0,
        estimated_wasted_calls=0,
        estimated_avoided_calls=0,
        rows=[
            RetryDecisionTelemetryRow(
                schema_version="1.0",
                step_name="browser_acquisition",
                error_code="browser_timeout",
                publisher="Example Publisher",
                workflow="report_download",
                action="retry",
                reason="retryable_error",
                decision_count=1,
                max_attempt=2,
                cumulative_delay_seconds=2.0,
                successful_after_retry_count=1,
                retry_exhaustion_count=0,
                deferred_count=0,
                user_action_required_count=0,
                estimated_wasted_calls=0,
                estimated_avoided_calls=0,
                final_outcomes={"downloaded": 1},
            )
        ],
    )

    memory = workflow.build_operational_memory(
        [
            workflow.OperationalObservation(
                schema_version="1.0",
                publisher="Example Publisher",
                workflow="report_download",
                route="browser_render",
                success=True,
                runtime_seconds=42.0,
                cost_usd=0.40,
                failure_signature="",
                pdf_extractable=True,
                credential_required=False,
            ),
            workflow.OperationalObservation(
                schema_version="1.0",
                publisher="Example Publisher",
                workflow="report_download",
                route="http_pdf",
                success=True,
                runtime_seconds=7.0,
                cost_usd=0.05,
                failure_signature="",
                pdf_extractable=True,
                credential_required=False,
            ),
            workflow.OperationalObservation(
                schema_version="1.0",
                publisher="Example Publisher",
                workflow="report_download",
                route="http_pdf",
                success=False,
                runtime_seconds=5.0,
                cost_usd=0.02,
                failure_signature="http_403",
                pdf_extractable=False,
                credential_required=False,
            ),
        ],
        retry_telemetry=telemetry,
    )

    recommendation = workflow.recommend_from_operational_memory(
        memory,
        publisher="Example Publisher",
        workflow_name="report_download",
    )

    assert recommendation.recommended_route == "http_pdf"
    assert recommendation.confidence > 0.0
    assert recommendation.failure_signatures == ["http_403", "browser_timeout"]
    assert recommendation.recommended_retry_policy == "report_download.http_pdf.v1"


def test_operational_memory_ignores_incomplete_retry_telemetry_rows() -> None:
    telemetry = RetryDecisionTelemetryReport(
        schema_version="1.0",
        decision_count=3,
        retry_count=3,
        deferred_count=0,
        user_action_required_count=0,
        retry_exhaustion_count=0,
        successful_after_retry_count=0,
        successful_after_retry_rate=0.0,
        retry_exhaustion_rate=0.0,
        cumulative_retry_delay_seconds=0.0,
        estimated_wasted_calls=0,
        estimated_avoided_calls=0,
        rows=[
            RetryDecisionTelemetryRow(
                schema_version="1.0",
                step_name="browser_acquisition",
                error_code="",
                publisher="Example Publisher",
                workflow="report_download",
                action="retry",
                reason="retryable_error",
                decision_count=1,
                max_attempt=1,
                cumulative_delay_seconds=0.0,
                successful_after_retry_count=0,
                retry_exhaustion_count=0,
                deferred_count=0,
                user_action_required_count=0,
                estimated_wasted_calls=0,
                estimated_avoided_calls=0,
                final_outcomes={},
            ),
            RetryDecisionTelemetryRow(
                schema_version="1.0",
                step_name="browser_acquisition",
                error_code="browser_timeout",
                publisher="",
                workflow="report_download",
                action="retry",
                reason="retryable_error",
                decision_count=1,
                max_attempt=1,
                cumulative_delay_seconds=0.0,
                successful_after_retry_count=0,
                retry_exhaustion_count=0,
                deferred_count=0,
                user_action_required_count=0,
                estimated_wasted_calls=0,
                estimated_avoided_calls=0,
                final_outcomes={},
            ),
            RetryDecisionTelemetryRow(
                schema_version="1.0",
                step_name="browser_acquisition",
                error_code="rate_limit",
                publisher="Example Publisher",
                workflow="",
                action="retry",
                reason="retryable_error",
                decision_count=1,
                max_attempt=1,
                cumulative_delay_seconds=0.0,
                successful_after_retry_count=0,
                retry_exhaustion_count=0,
                deferred_count=0,
                user_action_required_count=0,
                estimated_wasted_calls=0,
                estimated_avoided_calls=0,
                final_outcomes={},
            ),
        ],
    )

    memory = workflow.build_operational_memory(
        [
            workflow.OperationalObservation(
                schema_version="1.0",
                publisher="Example Publisher",
                workflow="report_download",
                route="http_pdf",
                success=False,
                runtime_seconds=3.0,
                cost_usd=0.0,
                failure_signature="http_403",
                pdf_extractable=False,
                credential_required=False,
            )
        ],
        retry_telemetry=telemetry,
    )

    assert memory[0].failure_signatures == ["http_403"]


def test_adaptive_concurrency_reduces_on_rate_limits_and_increases_on_stable_runs() -> None:
    limit = workflow.ConcurrencyLimit(
        schema_version="1.0",
        resource="model",
        min_limit=1,
        max_limit=4,
        default_limit=2,
        high_retry_rate=0.25,
        high_latency_ms=5000,
        low_retry_rate=0.05,
        low_latency_ms=1500,
    )

    reduced = workflow.resolve_adaptive_concurrency(
        limit,
        workflow.ConcurrencyObservation(
            schema_version="1.0",
            resource="model",
            current_limit=3,
            retry_rate=0.50,
            p95_latency_ms=6000,
            sqlite_lock_count=0,
            browser_failure_rate=0.0,
            budget_burn_rate=0.5,
        ),
    )
    increased = workflow.resolve_adaptive_concurrency(
        limit,
        workflow.ConcurrencyObservation(
            schema_version="1.0",
            resource="model",
            current_limit=2,
            retry_rate=0.0,
            p95_latency_ms=700,
            sqlite_lock_count=0,
            browser_failure_rate=0.0,
            budget_burn_rate=0.2,
        ),
    )

    assert reduced.selected_limit == 2
    assert reduced.reason == "pressure_detected"
    assert increased.selected_limit == 3
    assert increased.reason == "stable_headroom"
    assert asdict(reduced)["resource"] == "model"
