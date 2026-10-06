# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
        validation_grounding_global_max_in_flight=1,
        validation_grounding_global_min_interval_ms=0,
    )
    tracking_client = _TrackingOpenAIClient(sleep_seconds=0.04)
    validation_max_active: list[int] = []

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
        validation_openai_client = client_bundle.validation_client
        vector_req = SimpleNamespace(model="gpt-5", vector_store_id="vs_1")
        chat_req = SimpleNamespace(model="gpt-5")
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(
                    validation_openai_client.openai_chat_json,
                    chat_req,
                    ctx,
                )
                for _ in range(4)
            ]
            for future in futures:
                future.result()
        validation_max_active.append(tracking_client.max_active["chat"])
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
    assert validation_max_active == [1]
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
