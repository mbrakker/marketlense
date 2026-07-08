from __future__ import annotations

import json
import logging

from dataclasses import asdict

import pytest

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.mailbox_acquisition import (
    MailReportAcquisitionResult,
    MailboxAcquisitionSettings,
)
from src.contracts.retry_telemetry import (
    RetryDecisionTelemetryReport,
    RetryDecisionTelemetryRow,
)
from src.contracts.run_context import RunContext
from src.contracts.state import MailDeliveryRequestUpsertRequest
from src.contracts.pipeline_preflight import (
    PipelinePreflightCheck,
    PipelinePreflightReport,
)
from src.orchestrators import workflow_control_orchestrator as workflow
from src.services import config_service
from src.services.state_service import upsert_mail_delivery_request
from src.utils.errors import AppError


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


def _mailbox_settings(tmp_path) -> MailboxAcquisitionSettings:
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=0.0,
        poll_interval_seconds=0.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="",
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="reports@example.com",
        imap_password="secret",
        imap_mailbox="INBOX",
    )


def _browser_settings(tmp_path) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=8,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "identity.yaml"),
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        drive_upload_enabled=False,
        drive_upload_required=False,
        retry_retries=0,
    )


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


def test_workflow_control_dispatches_due_mail_delivery_requests(
    tmp_path,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    state_db = tmp_path / "state.sqlite"
    reports_db = tmp_path / "reports.sqlite"
    upsert = upsert_mail_delivery_request(
        MailDeliveryRequestUpsertRequest(
            schema_version="1.0",
            state_db=str(state_db),
            idempotency_key="mail:https://example.com/report:reports@example.com",
            source_url="https://example.com/report",
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            delivery_email="reports@example.com",
            requested_after_utc="2026-07-04T11:08:00Z",
            route_family="browser_email_form",
        ),
        _ctx(),
    )
    calls = []

    def acquire(req, ctx):
        calls.append(req)
        return MailReportAcquisitionResult(
            schema_version="1.0",
            source_url=req.source_url,
            outcome="downloaded_attachment",
            mailbox_poll_count=1,
            selected_report_url=None,
            selected_message_id="msg-1",
            downloaded_file_path=str(tmp_path / "report.pdf"),
            report_download_result=None,
            acquisition_result_taxonomy="mailbox_attachment_pdf",
            seen_provider_message_ids=["msg-1"],
        )

    result = workflow.run_due_mail_delivery_requests(
        workflow.MailDeliveryWorkflowRunRequest(
            schema_version="1.0",
            state_db=str(state_db),
            reports_db=str(reports_db),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
            now_utc="2026-07-04T11:09:00Z",
            limit=10,
        ),
        ctx=_ctx(),
        run_mail_report_acquisition_fn=acquire,
    )

    assert result.processed_count == 1
    assert result.succeeded_count == 1
    assert result.deferred_count == 0
    assert result.failed_count == 0
    assert result.results[0].request_id == upsert.request.request_id
    assert result.results[0].status == "succeeded"
    assert calls[0].seen_provider_message_ids == []
    events = _events(caplog)
    assert events[-1]["event"] == "workflow_mail_delivery_run_complete"
    assert events[-1]["fields"]["succeeded_count"] == 1


def test_project_workflow_control_config_resolves_publish_intent() -> None:
    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        _ctx(),
    )

    resolved = workflow.resolve_run_intent(
        workflow.RunIntent(
            schema_version="1.0",
            intent="publish ready reports",
            subject="",
            publisher="",
            report_id="",
            requested_side_effects=["wordpress", "publish"],
            dry_run=True,
            allow_automation=False,
            metadata={},
        ),
        settings,
        ctx=_ctx(),
    )

    assert resolved.status == "resolved"
    assert resolved.workflow == "publishing"


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


def test_adaptive_concurrency_reduces_on_rate_limits_and_increases_on_stable_runs() -> (
    None
):
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


def test_preflight_next_actions_are_converted_to_safe_remediation_artifact(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    report = PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_generation",
        planned_side_effects=["pdf", "model"],
        passed=True,
        expensive_side_effects_allowed=True,
        blocker_count=0,
        warning_count=1,
        auto_fixed_count=1,
        checks=[
            PipelinePreflightCheck(
                schema_version="1.0",
                check_name="path_writable:output_dir",
                status="auto_fixed",
                code="output_dir_created",
                message="Path is writable for output_dir",
                next_action="continue",
                auto_fix_applied=True,
                metadata={"path": "out"},
            ),
            PipelinePreflightCheck(
                schema_version="1.0",
                check_name="drive_live_preflight",
                status="warning",
                code="drive_live_preflight_skipped",
                message="Drive live endpoint preflight was skipped",
                next_action="run_live_preflight_before_drive_side_effects",
                auto_fix_applied=False,
                metadata={"folder_id": "folder"},
            ),
        ],
        blockers=[],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=[
            "run_live_preflight_before_drive_side_effects",
            "continue_pipeline",
        ],
    )

    artifact = workflow.build_preflight_remediation_artifact(report, _ctx())

    assert artifact.workflow == "report_generation"
    assert [action.action for action in artifact.actions] == [
        "create_local_path",
        "user_action_required",
    ]
    assert artifact.actions[0].result == "already_applied"
    assert artifact.actions[0].safe_to_auto_apply is True
    assert artifact.actions[1].result == "blocked"
    assert artifact.actions[1].safe_to_auto_apply is False
    assert artifact.user_action_required_count == 1
    assert _events(caplog)[-1]["event"] == "workflow_preflight_remediation_artifact"


def test_run_intent_resolves_workflow_and_reports_ambiguity() -> None:
    catalog = workflow.default_workflow_control_settings()

    resolved = workflow.resolve_run_intent(
        workflow.RunIntent(
            schema_version="1.0",
            intent="publish ready reports",
            subject="",
            publisher="",
            report_id="",
            requested_side_effects=["wordpress"],
            dry_run=True,
            allow_automation=False,
            metadata={},
        ),
        catalog,
        ctx=_ctx(),
    )
    ambiguous = workflow.resolve_run_intent(
        workflow.RunIntent(
            schema_version="1.0",
            intent="run",
            subject="",
            publisher="",
            report_id="",
            requested_side_effects=[],
            dry_run=True,
            allow_automation=False,
            metadata={},
        ),
        catalog,
        ctx=_ctx(),
    )

    assert resolved.status == "resolved"
    assert resolved.workflow == "publishing"
    assert resolved.preflight_profile == "publishing"
    assert "wordpress" in resolved.side_effect_plan
    assert ambiguous.status == "ambiguous"
    assert "publish_ready_reports" in ambiguous.alternatives
    assert ambiguous.workflow == ""


def test_publish_policy_fails_closed_with_confidence_gates() -> None:
    publish = workflow.evaluate_publish_policy(
        workflow.PublishPolicyInput(
            schema_version="1.0",
            validation_status="pass",
            family_confidence={"summary": 0.94, "quotes": 0.90},
            warnings=[],
            missing_metadata=[],
            editorial_risk="low",
            override=False,
            automation_enabled=True,
        ),
        ctx=_ctx(),
    )
    repair = workflow.evaluate_publish_policy(
        workflow.PublishPolicyInput(
            schema_version="1.0",
            validation_status="pass",
            family_confidence={"summary": 0.48},
            warnings=[],
            missing_metadata=[],
            editorial_risk="low",
            override=False,
            automation_enabled=True,
        ),
        ctx=_ctx(),
    )
    draft = workflow.evaluate_publish_policy(
        workflow.PublishPolicyInput(
            schema_version="1.0",
            validation_status="pass",
            family_confidence={"summary": 0.90},
            warnings=["minor_validation_warning"],
            missing_metadata=[],
            editorial_risk="low",
            override=False,
            automation_enabled=True,
        ),
        ctx=_ctx(),
    )

    assert publish.action == "publish"
    assert repair.action == "repair"
    assert repair.repair_supported is True
    assert draft.action == "draft"


def test_pre_llm_quality_gates_block_expensive_model_call() -> None:
    calls = {"count": 0}

    def expensive_call() -> str:
        calls["count"] += 1
        return "called"

    decision = workflow.evaluate_pre_llm_data_quality(
        workflow.PreLlmDataQualityInput(
            schema_version="1.0",
            file_id="file-1",
            md5="md5",
            already_processed=True,
            duplicate_report=True,
            text_char_count=20_000,
            supported_file_type=True,
            report_like=True,
            stale_already_processed=False,
            publisher_matches=True,
            publication_date_evidence=True,
            visual_candidate_count=5,
            known_gated_lead_form=False,
        ),
        ctx=_ctx(),
    )

    result = workflow.run_after_pre_llm_gate(decision, expensive_call)

    assert decision.outcome == "skip_duplicate"
    assert decision.expensive_work_allowed is False
    assert result is None
    assert calls["count"] == 0


def test_resolve_all_adaptive_concurrency_covers_all_resource_classes() -> None:
    catalog = workflow.default_workflow_control_settings()

    decisions = workflow.resolve_all_adaptive_concurrency(
        catalog,
        {
            "model": workflow.ConcurrencyObservation(
                schema_version="1.0",
                resource="model",
                current_limit=2,
                retry_rate=0.0,
                p95_latency_ms=700,
                sqlite_lock_count=0,
                browser_failure_rate=0.0,
                budget_burn_rate=0.2,
            )
        },
    )

    assert set(decisions) >= {"model", "pdf", "browser", "drive", "wordpress"}
    assert decisions["model"].reason == "stable_headroom"
    assert decisions["pdf"].selected_limit == catalog.concurrency["pdf"].default_limit


def test_workflow_feedback_changes_operational_memory_recommendation() -> None:
    feedback = [
        workflow.WorkflowControlObservation(
            schema_version="1.0",
            observed_at_utc="2026-07-04T00:00:00Z",
            run_id="run-1",
            workflow="report_download",
            step_name="browser_acquisition",
            route="browser_render",
            publisher="Example Publisher",
            report_key="report-a",
            outcome="failed",
            error_code="browser_timeout",
            error_retryable=True,
            error_severity="warning",
            latency_ms=9000,
            cost_usd=0.20,
            retry_count=1,
            resource_pressure={"browser_failure_rate": 0.5},
        ),
        workflow.WorkflowControlObservation(
            schema_version="1.0",
            observed_at_utc="2026-07-04T00:01:00Z",
            run_id="run-2",
            workflow="report_download",
            step_name="http_pdf",
            route="http_pdf",
            publisher="Example Publisher",
            report_key="report-b",
            outcome="succeeded",
            error_code="",
            error_retryable=False,
            error_severity="",
            latency_ms=1500,
            cost_usd=0.01,
            retry_count=0,
            resource_pressure={},
        ),
        workflow.WorkflowControlObservation(
            schema_version="1.0",
            observed_at_utc="2026-07-04T00:02:00Z",
            run_id="run-3",
            workflow="report_download",
            step_name="http_pdf",
            route="http_pdf",
            publisher="Example Publisher",
            report_key="report-c",
            outcome="succeeded",
            error_code="",
            error_retryable=False,
            error_severity="",
            latency_ms=1300,
            cost_usd=0.01,
            retry_count=0,
            resource_pressure={},
        ),
    ]

    memory = workflow.build_operational_memory_from_feedback(feedback)
    recommendation = workflow.recommend_from_operational_memory(
        memory,
        publisher="Example Publisher",
        workflow_name="report_download",
    )

    assert recommendation.recommended_route == "http_pdf"
    assert recommendation.confidence == 1.0
    assert "browser_timeout" in recommendation.failure_signatures


def test_run_after_pre_llm_gate_raises_typed_error_for_user_action() -> None:
    decision = workflow.PreLlmDataQualityDecision(
        schema_version="1.0",
        outcome="user_action_required",
        expensive_work_allowed=False,
        reason="known_gated_lead_form",
        source_signals={"known_gated_lead_form": True},
        remediation="provide_credentials_or_skip",
    )

    with pytest.raises(AppError) as exc_info:
        workflow.run_after_pre_llm_gate(decision, lambda: "called")

    assert exc_info.value.code == "pre_llm_quality_gate_blocked"
    assert exc_info.value.retryable is False
