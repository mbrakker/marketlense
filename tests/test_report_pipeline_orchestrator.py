from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.report_generation import ReportGenerationClientBundle
from src.contracts.run_context import RunContext
from src.orchestrators import report_pipeline_orchestrator as orch
from src.orchestrators import retry_orchestrator as retry_orch
from src.orchestrators import workflow_control_orchestrator as workflow_control
from src.contracts.pipeline_preflight import (
    PipelinePreflightReport,
    PipelinePreflightCheck,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings() -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state/index.sqlite",
        reports_db="./state/reports.sqlite",
        category_mapping_path="./src/config/category-mappings.yaml",
        cover_style_path="./src/config/cover-styles.yaml",
        ingest_lock_path="./state/ingest.lock",
        ingest_lock_ttl_seconds=7200.0,
        temperature=1.0,
    )


def _events(caplog) -> list[dict]:
    parsed: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.report_pipeline_orchestrator":
            parsed.append(payload)
    return parsed


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


class _TrackingOpenAIClient:
    def __init__(self, sleep_seconds: float = 0.03) -> None:
        self.sleep_seconds = sleep_seconds
        self._lock = threading.Lock()
        self._active = {"vector": 0, "chat": 0}
        self.max_active = {"vector": 0, "chat": 0}

    def _mark_start(self, kind: str) -> None:
        with self._lock:
            self._active[kind] += 1
            if self._active[kind] > self.max_active[kind]:
                self.max_active[kind] = self._active[kind]

    def _mark_end(self, kind: str) -> None:
        with self._lock:
            self._active[kind] = max(0, self._active[kind] - 1)

    def openai_respond_with_vector_store(self, req, ctx):
        self._mark_start("vector")
        try:
            time.sleep(self.sleep_seconds)
        finally:
            self._mark_end("vector")
        return SimpleNamespace(schema_version="1.0", parsed_json={})

    def openai_chat_json(self, req, ctx):
        self._mark_start("chat")
        try:
            time.sleep(self.sleep_seconds)
        finally:
            self._mark_end("chat")
        return SimpleNamespace(schema_version="1.0", parsed_json={})


def test_run_report_pipeline_uses_orchestrator_rate_limiter() -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        _settings(),
        evidence_pack_global_max_in_flight=2,
        evidence_pack_global_min_interval_ms=0,
        artifact_global_max_in_flight=2,
        artifact_global_min_interval_ms=0,
    )
    tracking_client = _TrackingOpenAIClient(sleep_seconds=0.04)

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
        assert client_bundle is not None
        evidence_pack_openai_client = client_bundle.evidence_pack_client
        artifact_openai_client = client_bundle.artifact_client
        vector_req = SimpleNamespace(model="gpt-5", vector_store_id="vs_1")
        chat_req = SimpleNamespace(model="gpt-5")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(
                    evidence_pack_openai_client.openai_respond_with_vector_store,
                    vector_req,
                    ctx,
                )
                for _ in range(4)
            ]
            for future in futures:
                future.result()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(artifact_openai_client.openai_chat_json, chat_req, ctx)
                for _ in range(4)
            ]
            for future in futures:
                future.result()
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=settings,
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        openai_client_override=tracking_client,
    )
    assert response.status == "processed"
    assert tracking_client.max_active["vector"] <= 2
    assert tracking_client.max_active["chat"] <= 2


def test_run_report_pipeline_owns_retry_around_single_attempt_llm_service(
    external_boundary_mocks_only,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        _settings(),
        llm_retry_retries=0,
        llm_retry_base_delay_seconds=0.0,
        llm_retry_backoff_step_seconds=0.0,
        llm_retry_jitter_seconds=0.0,
        evidence_pack_global_min_interval_ms=0,
        artifact_global_min_interval_ms=0,
    )
    sleep_calls: list[float] = []
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds))
    )
    external_boundary_mocks_only.setattr(
        retry_orch.random, "uniform", lambda _low, _high: 0.0
    )

    class _RetryThenSucceedClient:
        def __init__(self) -> None:
            self.calls = 0

        def openai_chat_json(self, req, ctx):
            self.calls += 1
            if self.calls == 1:
                raise AppError(
                    code="openai_chat_failed",
                    message="retry model call",
                    retryable=True,
                )
            return SimpleNamespace(schema_version="1.0", parsed_json={"ok": True})

        def openai_respond_with_vector_store(self, req, ctx):
            return SimpleNamespace(schema_version="1.0", parsed_json={})

    base_client = _RetryThenSucceedClient()

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
        assert client_bundle is not None
        artifact_openai_client = client_bundle.artifact_client
        response = artifact_openai_client.openai_chat_json(
            SimpleNamespace(model="gpt-5-mini"),
            ctx,
        )
        assert response.parsed_json == {"ok": True}
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=settings,
        md5="md5",
        ctx=_ctx(),
        retries=1,
        generate_report_fn=_gen,
        openai_client_override=base_client,
    )

    assert response.status == "processed"
    assert base_client.calls == 2
    assert sleep_calls == [1.0]


def test_run_report_pipeline_forwards_resume_stage_to_report_generation() -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    captured: dict[str, str] = {}

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
        captured["resume_from_stage"] = str(resume_from_stage or "")
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        resume_from_stage="analysis_complete",
    )

    assert response.status == "processed"
    assert captured == {"resume_from_stage": "analysis_complete"}


def test_run_report_pipeline_passes_explicit_report_client_bundle() -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    captured: dict[str, object] = {}

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle,
        resume_from_stage=None,
    ):
        captured["bundle"] = client_bundle
        captured["resume_from_stage"] = str(resume_from_stage or "")
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        resume_from_stage="selection_complete",
    )

    assert response.status == "processed"
    assert isinstance(captured["bundle"], ReportGenerationClientBundle)
    bundle = captured["bundle"]
    assert bundle.source_ocr_client is not None
    assert bundle.taxonomy_client is not None
    assert bundle.category_fit_client is not None
    assert bundle.evidence_pack_client is not None
    assert bundle.artifact_client is not None
    assert bundle.validation_client is not None
    assert bundle.regeneration_client is not None
    assert bundle.figure_caption_client is not None
    assert captured["resume_from_stage"] == "selection_complete"


def test_run_report_pipeline_auto_resume_uses_latest_safe_when_stage_not_explicit() -> (
    None
):
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    captured: dict[str, str] = {}

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle,
        resume_from_stage=None,
    ):
        captured["resume_from_stage"] = str(resume_from_stage or "")
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        auto_resume_from_latest_safe=True,
    )

    assert response.status == "processed"
    assert captured["resume_from_stage"] == "latest_safe"


def test_run_report_pipeline_uses_workflow_retry_policy(
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
    sleep_calls: list[float] = []
    catalog = workflow_control.default_workflow_control_settings()

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle,
        resume_from_stage=None,
    ):
        calls["count"] += 1
        if calls["count"] == 1:
            raise AppError(
                code="openai_request_failed",
                message="retry once",
                retryable=True,
            )
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

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
        retries=0,
        generate_report_fn=_gen,
        workflow_control_settings=catalog,
    )

    assert response.status == "processed"
    assert calls["count"] == 2
    assert sleep_calls == [1.0]
    events = _events(caplog)
    starts = [event for event in events if event["event"] == "report_pipeline_start"]
    assert starts[-1]["fields"]["retry_policy_id"] == (
        "report_generation.report_pipeline.v1"
    )


def test_report_pipeline_orchestrator_does_not_use_signature_reflection() -> None:
    source = orch.__loader__.get_source(orch.__name__)

    assert source is not None
    assert "inspect.signature" not in source


def test_report_generation_client_bundle_rejects_missing_client(
    assert_app_error,
) -> None:
    bundle = ReportGenerationClientBundle(
        schema_version="1.0",
        source_ocr_client=object(),
        taxonomy_client=object(),
        category_fit_client=object(),
        evidence_pack_client=object(),
        artifact_client=object(),
        validation_client=object(),
        regeneration_client=object(),
        figure_caption_client=None,
    )

    with pytest.raises(AppError) as exc_info:
        bundle.validate()

    assert_app_error(
        exc_info.value,
        code="report_generation_client_bundle_invalid",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["field"] == "figure_caption_client"


def test_run_report_pipeline_preflights_before_model_client_construction(
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    model_client_calls = {"count": 0}

    def _build_client(*_args, **_kwargs):
        model_client_calls["count"] += 1
        raise AssertionError("model clients must not be built after blocking preflight")

    blocking_check = PipelinePreflightCheck(
        schema_version="1.0",
        check_name="openai_api_key",
        status="blocker",
        code="openai_missing_api_key",
        message="OpenAI API key is missing",
        next_action="set_OPENAI_API_KEY",
        auto_fix_applied=False,
        metadata={},
    )
    blocking_report = PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_pipeline",
        planned_side_effects=["pdf", "model"],
        passed=False,
        expensive_side_effects_allowed=False,
        blocker_count=1,
        warning_count=0,
        auto_fixed_count=0,
        checks=[blocking_check],
        blockers=[blocking_check],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=["set_OPENAI_API_KEY", "rerun_preflight"],
    )

    external_boundary_mocks_only.setattr(
        orch.llm_service, "build_client_for_settings", _build_client
    )

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/a.pdf",
            settings=_settings(),
            md5="md5",
            ctx=_ctx(),
            retries=0,
            generate_report_fn=lambda *_args, **_kwargs: None,
            preflight_fn=lambda *_args, **_kwargs: blocking_report,
        )

    assert_app_error(
        exc_info.value,
        code="pipeline_preflight_blocked",
        retryable=False,
        severity="error",
    )
    assert model_client_calls["count"] == 0


def test_pdf_budget_stop_prevents_report_generation_call(tmp_path) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="budgeted-pdf",
        name="budgeted.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        _settings(),
        run_budget_max_pdfs=1,
        usage_db_path=str(tmp_path / "pdf_budget.sqlite"),
    )
    calls = {"count": 0}

    def _generate(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("PDF budget must stop before report generation")

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/budgeted.pdf",
            settings=settings,
            md5="md5",
            ctx=_ctx(),
            retries=0,
            generate_report_fn=_generate,
            execution_plan_mode="disabled",
        )

    assert exc_info.value.code == "report_pipeline_pdf_budget_stop"
    assert exc_info.value.retryable is False
    assert calls["count"] == 0
