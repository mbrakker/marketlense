from __future__ import annotations

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import UiRunRecord
from src.utils.ui_run_dead_letter import (
    build_dead_letter_record,
    classify_ui_run_failure,
)


def _failed_record(
    *,
    error_code: str,
    error_message: str = "",
    retryable: bool | None = None,
    run_type: str = "ingest",
    result_summary: dict[str, object] | None = None,
) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id=RunId("run-failed"),
        run_type=run_type,
        display_name="Failed run",
        status="failed",
        request_payload={"limit": 1},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-06-29T00:00:00+00:00",
        updated_at_utc="2026-06-29T00:01:00+00:00",
        finished_at_utc="2026-06-29T00:01:00+00:00",
        output_path="out.log",
        request_path="request.json",
        result_summary=dict(result_summary or {}),
        exit_code=1,
        error_code=error_code,
        error_message=error_message,
        error_retryable=retryable,
        error_severity="error",
    )


def test_classifies_process_launch_failure_as_cleanup_then_retry() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="ui_run_launch_failed",
            error_message="Output log path is locked",
            retryable=False,
        ),
        structured_events=[],
        output_tail="PermissionError: output.log is locked",
        checkpoints=[],
        preflight_state={},
    )

    assert classification.action == "cleanup_transient_resource"
    assert "worker launch" in classification.reason
    assert classification.side_effect_warning


def test_classifies_retryable_app_error_as_retry_now() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="openai_request_failed",
            error_message="temporary provider failure",
            retryable=True,
        )
    )

    assert classification.action == "retry_now"
    assert classification.retryable is True


def test_classifies_missing_credential_as_request_credential() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="pipeline_preflight_blocked",
            error_message="OpenAI API key is missing",
            retryable=False,
        ),
        preflight_state={
            "blockers": [
                {
                    "code": "openai_missing_api_key",
                    "next_action": "set_OPENAI_API_KEY",
                }
            ]
        },
    )

    assert classification.action == "request_credential"
    assert classification.suggested_command == "set_OPENAI_API_KEY"


def test_classifies_checkpoint_failure_as_resume_from_checkpoint() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="openai_request_failed",
            retryable=True,
            result_summary={"latest_safe_resume_stage": "analysis_complete"},
        ),
        checkpoints=["analysis_complete"],
    )

    assert classification.action == "resume_from_checkpoint"
    assert classification.resume_stage == "analysis_complete"
    assert "completed checkpoint" in classification.reason


def test_classifies_report_card_date_failure_as_targeted_repair() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="card_publication_date_invalid",
            retryable=False,
            result_summary={"latest_safe_resume_stage": "analysis_complete"},
        ),
        checkpoints=["analysis_complete"],
    )

    assert classification.action == "repair_report_card_publication_date"
    assert classification.retryable is False
    assert classification.resume_stage == "analysis_complete"
    assert "typed registry artifacts" in classification.side_effect_warning


def test_classifies_permanent_validation_failure_as_mark_permanent() -> None:
    classification = classify_ui_run_failure(
        record=_failed_record(
            error_code="validation_failed",
            error_message="Generated artifact failed semantic validation",
            retryable=False,
        )
    )

    assert classification.action == "mark_permanent"
    assert classification.retryable is False


def test_dead_letter_auto_triage_records_recommended_action_note() -> None:
    dead_letter = build_dead_letter_record(
        registry_path="state/ui_runs.sqlite",
        record=_failed_record(
            error_code="openai_request_failed",
            error_message="temporary provider failure",
            retryable=True,
        ),
        failed_at_utc="2026-06-29T00:01:00+00:00",
        updated_at_utc="2026-06-29T00:02:00+00:00",
    )

    assert dead_letter.last_action == "auto_triaged"
    assert dead_letter.last_action_note.startswith("retry_now:")
    assert dead_letter.result_summary["failure_classification"]["action"] == "retry_now"
