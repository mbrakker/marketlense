from __future__ import annotations

import json

from src.orchestrators.retry_telemetry_orchestrator import (
    build_retry_decision_telemetry,
)


def test_retry_telemetry_groups_decisions_and_accounts_success_after_retry(
    assert_no_defaulted_required_fields,
) -> None:
    report = build_retry_decision_telemetry(
        [
            {
                "run_id": "run-1",
                "event": "report_pipeline_retry",
                "fields": {
                    "step": "report_pipeline",
                    "decision": "retry",
                    "reason": "retryable_error",
                    "error_code": "openai_request_failed",
                    "decision_attempt": 1,
                    "delay_seconds": 1.0,
                    "publisher": "IAS",
                    "workflow": "report_generation",
                },
            },
            {
                "run_id": "run-1",
                "event": "report_pipeline_complete",
                "fields": {
                    "step": "report_pipeline",
                    "status": "processed",
                    "publisher": "IAS",
                    "workflow": "report_generation",
                },
            },
        ]
    )

    assert_no_defaulted_required_fields(report)
    assert report.decision_count == 1
    assert report.retry_count == 1
    assert report.deferred_count == 0
    assert report.successful_after_retry_count == 1
    assert report.retry_exhaustion_rate == 0.0
    assert report.cumulative_retry_delay_seconds == 1.0
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.step_name == "report_pipeline"
    assert row.publisher == "IAS"
    assert row.workflow == "report_generation"
    assert row.action == "retry"
    assert row.reason == "retryable_error"
    assert row.error_code == "openai_request_failed"
    assert row.decision_count == 1
    assert row.successful_after_retry_count == 1
    assert row.cumulative_delay_seconds == 1.0
    assert row.final_outcomes == {"processed": 1}


def test_retry_telemetry_handles_missing_optional_publisher_workflow_and_actions() -> (
    None
):
    report = build_retry_decision_telemetry(
        [
            {
                "run_id": "run-1",
                "event": "step_failed",
                "fields": {
                    "step": "drive_preflight",
                    "decision": "user_action_required",
                    "reason": "missing_credential",
                    "error_code": "drive_oauth_token_missing",
                    "decision_attempt": 1,
                    "delay_seconds": 0.0,
                },
            },
            {
                "run_id": "run-1",
                "event": "step_failed",
                "fields": {
                    "step": "wordpress_preflight",
                    "decision": "user_action_required",
                    "reason": "missing_credential",
                    "error_code": "wordpress_credentials_missing",
                    "decision_attempt": 1,
                    "delay_seconds": 0.0,
                },
            },
            {
                "run_id": "run-1",
                "event": "quota_defer",
                "fields": {
                    "step": "quota_guard",
                    "decision": "defer",
                    "reason": "defer_requested",
                    "error_code": "provider_quota_exhausted",
                    "decision_attempt": 1,
                    "delay_seconds": 120.0,
                },
            },
        ]
    )

    assert report.user_action_required_count == 2
    assert report.deferred_count == 1
    assert report.cumulative_retry_delay_seconds == 120.0
    assert [row.publisher for row in report.rows] == ["", "", ""]
    assert [row.workflow for row in report.rows] == ["", "", ""]
    assert [row.action for row in report.rows] == [
        "defer",
        "user_action_required",
        "user_action_required",
    ]


def test_retry_telemetry_json_output_is_deterministic() -> None:
    report = build_retry_decision_telemetry(
        [
            {
                "run_id": "run-2",
                "event": "failed",
                "fields": {
                    "step": "state_write",
                    "decision": "abort",
                    "reason": "retry_attempts_exhausted",
                    "error_code": "sqlite_database_locked",
                    "decision_attempt": 3,
                    "delay_seconds": 0,
                    "workflow": "ingest",
                },
            }
        ]
    )

    encoded = report.to_json()
    assert encoded == json.dumps(
        json.loads(encoded), ensure_ascii=True, indent=2, sort_keys=True
    )
    assert '"retry_exhaustion_count": 1' in encoded
    assert '"estimated_wasted_calls": 1' in encoded


def test_retry_telemetry_ignores_events_without_action_reason_or_step() -> None:
    report = build_retry_decision_telemetry(
        [
            {"run_id": "r", "event": "bad", "fields": {"reason": "retryable_error"}},
            {"run_id": "r", "event": "bad", "fields": {"decision": "retry"}},
            {
                "run_id": "r",
                "event": "bad",
                "fields": {"step": "model_call", "reason": "retryable_error"},
            },
            {
                "run_id": "r",
                "event": "bad",
                "fields": {"step": "model_call", "decision": "retry"},
            },
            {
                "run_id": "r",
                "event": "bad",
                "fields": {"decision": "retry", "reason": "retryable_error"},
            },
            {
                "run_id": "r",
                "event": "good",
                "fields": {
                    "step_name": "model_call",
                    "decision": "retry",
                    "reason": "retryable_error",
                    "error_code": "openai_request_failed",
                },
            },
        ]
    )

    assert report.decision_count == 1
    assert report.rows[0].step_name == "model_call"
    assert report.rows[0].reason == "retryable_error"
