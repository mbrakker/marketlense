# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_run_report_pipeline_retries_retryable(
    caplog, external_boundary_mocks_only, assert_logs_have_required_fields
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path="./out/a.html",
        status="processed",
    )
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        if calls["count"] < 3:
            raise AppError(
                code="openai_request_failed", message="retry", retryable=True
            )
        return outcome

    external_boundary_mocks_only.setattr(
        retry_orch.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds))
    )
    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=2,
        generate_report_fn=_gen,
    )
    assert calls["count"] == 3
    assert sleep_calls == [1.0, 2.0]
    assert response.status == "processed"

    events = _events(caplog)
    retry_events = [
        event for event in events if event.get("event") == "report_pipeline_retry"
    ]
    complete_events = [
        event for event in events if event.get("event") == "report_pipeline_complete"
    ]
    start_events = [
        event for event in events if event.get("event") == "report_pipeline_start"
    ]
    transition_events = [
        event
        for event in events
        if event.get("event") == "report_pipeline_doc_map_retry_transition"
    ]

    assert len(start_events) == 1
    assert len(retry_events) == 2
    assert len(complete_events) == 1
    assert len(transition_events) == 0
    assert_logs_have_required_fields(start_events + retry_events + complete_events)

    retry_fields = [event["fields"] for event in retry_events]
    assert [fields["attempt"] for fields in retry_fields] == [1, 2]
    assert all(fields["code"] == "openai_request_failed" for fields in retry_fields)

    complete_fields = complete_events[0]["fields"]
    assert complete_fields["attempt"] == 2
    assert complete_fields["status"] == "processed"
    assert complete_fields["retry_transition"] is False


def test_run_report_pipeline_surfaces_retryable_error_after_retry_exhaustion(
    caplog,
    external_boundary_mocks_only,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        raise AppError(code="openai_request_failed", message="retry", retryable=True)

    external_boundary_mocks_only.setattr(
        retry_orch.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds))
    )

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/a.pdf",
            settings=_settings(),
            md5="md5",
            ctx=_ctx(),
            retries=1,
            generate_report_fn=_gen,
        )
    assert_app_error(
        exc_info.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )
    assert calls["count"] == 2
    assert sleep_calls == [1.0]

    events = _events(caplog)
    retry_events = [
        event for event in events if event.get("event") == "report_pipeline_retry"
    ]
    failure_events = [
        event for event in events if event.get("event") == "report_pipeline_failed"
    ]
    complete_events = [
        event for event in events if event.get("event") == "report_pipeline_complete"
    ]

    assert len(retry_events) == 1
    assert len(failure_events) == 1
    assert len(complete_events) == 0
    assert_logs_have_required_fields(retry_events + failure_events)

    retry_fields = retry_events[0]["fields"]
    failure_fields = failure_events[0]["fields"]
    assert retry_fields["attempt"] == 1
    assert retry_fields["code"] == "openai_request_failed"
    assert failure_fields["attempt"] == 1
    assert failure_fields["code"] == "openai_request_failed"
    assert failure_fields["retryable"] is True
    assert failure_fields["error"] == "retry"


def test_run_report_pipeline_retries_transient_artifact_file_not_found(
    caplog,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path="./out/a.html",
        status="processed",
    )

    def _gen(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise FileNotFoundError(2, "artifact disappeared", "./out/a.png")
        return outcome

    external_boundary_mocks_only.setattr(
        retry_orch.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(orch.time, "sleep", lambda _seconds: None)

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=1,
        generate_report_fn=_gen,
    )

    assert response.status == "processed"
    assert calls["count"] == 2
    retry_events = [
        event
        for event in _events(caplog)
        if event.get("event") == "report_pipeline_retry"
    ]
    assert len(retry_events) == 1
    assert retry_events[0]["fields"]["code"] == "report_pipeline_artifact_missing"
    assert_logs_have_required_fields(retry_events)


def test_run_report_pipeline_retries_doc_map_transition_with_logs(
    caplog, external_boundary_mocks_only
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    retry_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:model_returned_no_json",
        doc_map_summary={"not_found_reason": "model_returned_no_json"},
    )
    success_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path="./out/a.html",
        status="processed",
    )

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        return retry_outcome if calls["count"] == 1 else success_outcome

    external_boundary_mocks_only.setattr(orch.time, "sleep", lambda _: None)
    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=2,
        generate_report_fn=_gen,
    )
    assert response.status == "processed"
    assert calls["count"] == 2
    events = _events(caplog)
    transition_events = [
        event
        for event in events
        if event.get("event") == "report_pipeline_doc_map_retry_transition"
    ]
    retry_events = [
        event for event in events if event.get("event") == "report_pipeline_retry"
    ]
    assert len(transition_events) == 1
    assert len(retry_events) == 1
    transition_fields = transition_events[0]["fields"]
    retry_fields = retry_events[0]["fields"]
    assert transition_fields["attempt"] == 1
    assert transition_fields["reason"] == "model_returned_no_json"
    assert retry_fields["attempt"] == 1
    assert retry_fields["code"] == "doc_map_generation_retry"
    assert transition_events[0]["run_id"] == "r"
    assert transition_events[0]["task_id"] == "t"
    assert transition_events[0]["role"] == "orchestrator"


def test_run_report_pipeline_retries_doc_map_no_content_with_valid_text(
    external_boundary_mocks_only,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    retry_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:no_content",
        text_validation_status="pass",
        doc_map_summary={"not_found_reason": "no_content"},
    )
    success_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path="./out/a.html",
        status="processed",
    )

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        return retry_outcome if calls["count"] == 1 else success_outcome

    external_boundary_mocks_only.setattr(orch.time, "sleep", lambda _: None)

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=2,
        generate_report_fn=_gen,
    )

    assert response.status == "processed"
    assert calls["count"] == 2


def test_run_report_pipeline_does_not_retry_doc_map_no_content_with_invalid_text(
    external_boundary_mocks_only,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    retry_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:no_content",
        text_validation_status="fail",
        doc_map_summary={"not_found_reason": "no_content"},
    )

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        return retry_outcome

    external_boundary_mocks_only.setattr(orch.time, "sleep", lambda _: None)

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=2,
        generate_report_fn=_gen,
    )

    assert response.status == "error"
    assert response.text_validation_status == "fail"
    assert calls["count"] == 1


def test_run_report_pipeline_doc_map_retry_is_bounded(
    external_boundary_mocks_only,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(_settings(), evidence_pack_doc_map_max_attempts=2)
    calls = {"count": 0}
    retry_outcome = IngestOutcome(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:model_returned_no_json",
        doc_map_summary={"not_found_reason": "model_returned_no_json"},
    )

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle=None,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        return retry_outcome

    external_boundary_mocks_only.setattr(orch.time, "sleep", lambda _: None)
    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=settings,
        md5="md5",
        ctx=_ctx(),
        retries=1,
        generate_report_fn=_gen,
    )
    assert response.status == "error"
    assert calls["count"] == 2
