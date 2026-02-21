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
from src.contracts.run_context import RunContext
from src.orchestrators import report_pipeline_orchestrator as orch
from src.orchestrators import retry_orchestrator as retry_orch
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
    caplog, monkeypatch, assert_logs_have_required_fields
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
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

    def _gen(file, local_pdf_path, settings, md5, ctx):
        calls["count"] += 1
        if calls["count"] < 3:
            raise AppError(code="openai_request_failed", message="retry", retryable=True)
        return outcome

    monkeypatch.setattr(retry_orch.random, "uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds)))
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
    retry_events = [event for event in events if event.get("event") == "report_pipeline_retry"]
    complete_events = [event for event in events if event.get("event") == "report_pipeline_complete"]
    start_events = [event for event in events if event.get("event") == "report_pipeline_start"]
    transition_events = [event for event in events if event.get("event") == "report_pipeline_doc_map_retry_transition"]

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
    monkeypatch,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def _gen(file, local_pdf_path, settings, md5, ctx):
        calls["count"] += 1
        raise AppError(code="openai_request_failed", message="retry", retryable=True)

    monkeypatch.setattr(retry_orch.random, "uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds)))

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
    retry_events = [event for event in events if event.get("event") == "report_pipeline_retry"]
    failure_events = [event for event in events if event.get("event") == "report_pipeline_failed"]
    complete_events = [event for event in events if event.get("event") == "report_pipeline_complete"]

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


def test_run_report_pipeline_retries_doc_map_transition_with_logs(caplog, monkeypatch) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
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

    def _gen(file, local_pdf_path, settings, md5, ctx):
        calls["count"] += 1
        return retry_outcome if calls["count"] == 1 else success_outcome

    monkeypatch.setattr(orch.time, "sleep", lambda _: None)
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
    transition_events = [event for event in events if event.get("event") == "report_pipeline_doc_map_retry_transition"]
    retry_events = [event for event in events if event.get("event") == "report_pipeline_retry"]
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


def test_run_report_pipeline_doc_map_retry_is_bounded(monkeypatch) -> None:
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
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

    def _gen(file, local_pdf_path, settings, md5, ctx):
        calls["count"] += 1
        return retry_outcome

    monkeypatch.setattr(orch.time, "sleep", lambda _: None)
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
    file = DriveFile(schema_version="1.0", file_id="f1", name="a.pdf", modified_time=None, md5_checksum="md5")
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
        evidence_pack_openai_client=None,
        artifact_openai_client=None,
    ):
        assert evidence_pack_openai_client is not None
        assert artifact_openai_client is not None
        vector_req = SimpleNamespace(model="gpt-5", vector_store_id="vs_1")
        chat_req = SimpleNamespace(model="gpt-5")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(evidence_pack_openai_client.openai_respond_with_vector_store, vector_req, ctx)
                for _ in range(4)
            ]
            for future in futures:
                future.result()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(artifact_openai_client.openai_chat_json, chat_req, ctx) for _ in range(4)]
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
