from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.pdf_text import PdfTextSample, PdfTextSampleResponse
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_assets import RenderResponse
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetRequest
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.contracts.validation import ValidationReport
from src.generators import report_analysis_generator as rag
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.orchestrators import report_generation_orchestrator as rgo
from src.services.file_service import file_stat
from src.services.state_service import get as state_get, record as state_record
from src.utils.errors import AppError
from src.utils.slugify import slugify


def _ingest_settings(tmp_path: Path) -> IngestSettings:
    cover_style_path = (
        Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
    )
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(cover_style_path),
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=True,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={},
    )


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def _report_dependencies(**overrides) -> ReportGeneratorDependencies:
    return replace(ReportGeneratorDependencies.default(), **overrides)


def _batch_dependencies(**overrides) -> orch.IngestBatchDependencies:
    return replace(orch.IngestBatchDependencies.default(), **overrides)


def _make_ingest_process(*, generate_report):
    def _download(req, ctx):
        payload = _pdf_bytes()
        path = Path(req.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return SimpleNamespace(
            output_path=req.output_path,
            md5="md5",
            size=len(payload),
        )

    def _process_file(file, index, settings, root_ctx):
        file_dependencies = IngestFileDependencies(
            should_skip=lambda *_args: False,
            cache_pdf_path=lambda current_settings, current_file: str(
                Path(current_settings.cache_dir) / f"{current_file.file_id}.pdf"
            ),
            md5_sidecar_path=lambda cache_path: f"{cache_path}.md5.json",
            load_md5_sidecar=lambda *_args: None,
            sidecar_md5_for_stat=lambda *_args: None,
            ensure_file_name=lambda current_file, _settings, _ctx: current_file,
            write_md5_sidecar=lambda *_args: None,
            existing_report_html=lambda *_args: None,
            run_step_with_retry=lambda _step, _ctx, operation, _retries: operation(),
            file_stat=file_stat,
            download_pdf_to_path=_download,
            check_pdf_eof=lambda _request, _ctx: SimpleNamespace(has_eof=True),
            delete_file=lambda _request, _ctx: None,
            run_report_pipeline=generate_report,
            state_record=state_record,
            eof_retry_limit=0,
        )
        return run_ingest_file(
            file=file,
            index=index,
            settings=settings,
            root_ctx=root_ctx,
            dependencies=file_dependencies,
            logger_name=orch.logger.name,
        )

    return _process_file


def _decode_log_events(caplog, logger_name: str) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        try:
            payload = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _base_vector_report_dependencies(
    tmp_path: Path, **overrides
) -> ReportGeneratorDependencies:
    base = {
        "state_get": lambda req, ctx: None,
        "vector_store_create": lambda req, ctx: SimpleNamespace(
            vector_store_id="vs_new"
        ),
        "vector_store_upload_file": lambda req, ctx: SimpleNamespace(
            openai_file_id="file_upload"
        ),
        "vector_store_attach_file": lambda req, ctx: None,
        "vector_store_wait_until_indexed": lambda req, ctx: SimpleNamespace(
            status="completed",
            indexed_at_utc="2024-01-01T00:00:00Z",
            last_error=None,
        ),
        "extract_pdf_info": lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            page_count=1,
            metadata={"k": "v"},
        ),
        "build_pdf_context": lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            context=SimpleNamespace(
                fitz_doc=None,
                pypdf_reader=None,
                close=lambda: None,
            ),
            fitz_error=None,
            pypdf_error=None,
        ),
        "detect_contents_page": lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            has_contents=False,
            page_index=-1,
            page_number=0,
            heading="",
            confidence=0.0,
        ),
        "extract_pdf_text": lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            text="text",
            pages_extracted=1,
            char_count=4,
            text_density=4.0,
        ),
        "load_category_mappings": lambda req, ctx: SimpleNamespace(
            mappings=SimpleNamespace(
                schema_version="1.0",
                categories=[],
                uncategorized=[],
            )
        ),
        "categorize_taxonomy": lambda taxonomy, mappings, ctx: SimpleNamespace(
            categories=["cat"],
            category_labels=["Category"],
            unmapped_tags=[],
        ),
        "update_uncategorized_tags": lambda req, ctx: None,
        "extract_best_figure": lambda req, ctx: SimpleNamespace(
            image_path=None,
            caption=None,
        ),
        "collect_candidates": lambda req, ctx: SimpleNamespace(candidates=[]),
        "render_preview": lambda req, ctx: SimpleNamespace(
            schema_version="1.1",
            image_path=str(tmp_path / "preview.png"),
            page_number=0,
        ),
        "extract_taxonomy": lambda req, ctx: TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["tag"],
            region="US",
            time_period="2024",
        ),
        "vector_store_update_metadata": lambda req, ctx: None,
        "sample_pdf_text": lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(
                    page_index=0,
                    page_number=1,
                    char_count=12,
                    has_text=True,
                )
            ],
            any_text=True,
        ),
    }
    base.update(overrides)
    return _report_dependencies(**base)


def _runtime_state(
    file: DriveFile,
    settings: IngestSettings,
    *,
    local_pdf_path: str,
    md5: str | None,
    ctx: RunContext,
) -> ReportRuntimeState:
    file_name = file.name or file.file_id
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=local_pdf_path,
        settings=settings,
        md5=md5,
        ctx=ctx,
        file_name=file_name,
        report_name=report_slug(file_name, file.file_id),
        report_title=derive_title(file_name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=int(getattr(settings, "report_worker_limit", 1) or 1),
        parallel_within_file=bool(int(getattr(settings, "report_worker_limit", 1) or 1) > 1),
    )


def test_ensure_vector_store_creates_and_waits(tmp_path):
    settings = _ingest_settings(tmp_path)
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    file = DriveFile(
        schema_version="1.0",
        file_id="file_1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls: list[str] = []

    deps = _report_dependencies(
        state_get=lambda req, ctx: None,
        vector_store_create=lambda req, ctx: (
            calls.append("create") or SimpleNamespace(vector_store_id="vs_123")
        ),
        vector_store_upload_file=lambda req, ctx: (
            calls.append("upload") or SimpleNamespace(openai_file_id="file_upload_1")
        ),
        vector_store_attach_file=lambda req, ctx: calls.append("attach") or None,
        vector_store_wait_until_indexed=lambda req, ctx: (
            calls.append("wait")
            or SimpleNamespace(
                status="completed",
                indexed_at_utc="2024-01-01T00:00:00Z",
                last_error=None,
            )
        ),
    )

    runtime = _runtime_state(
        file,
        settings,
        local_pdf_path="local.pdf",
        md5="md5",
        ctx=ctx,
    )
    vector_store_id, openai_file_id, status, indexed_at_utc, last_error = (
        rag.ensure_vector_store(runtime, deps)
    )

    assert calls == ["create", "upload", "attach", "wait"]
    assert vector_store_id == "vs_123"
    assert openai_file_id == "file_upload_1"
    assert status == "completed"
    assert indexed_at_utc == "2024-01-01T00:00:00Z"
    assert last_error is None


def test_ingest_orchestrator_records_vector_events(
    caplog,
    tmp_path,
    assert_logs_have_required_fields,
) -> None:
    settings = _ingest_settings(tmp_path)
    file = DriveFile(
        schema_version="1.0",
        file_id="file",
        name="name.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5="md5",
        html_path="out/name.html",
        status="processed",
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2024-01-01T00:00:00Z",
        openai_file_id="file_upload_1",
        evidence_packs={"doc_map": "path"},
        vector_store_last_error=None,
    )
    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        process_file=_make_ingest_process(
            generate_report=lambda current_file, cache_path, current_settings, md5, ctx: (
                outcome
            )
        ),
    )

    with caplog.at_level(logging.INFO, logger=orch.logger.name):
        results = orch.run_ingest(settings, limit=1, dependencies=deps)

    events = _decode_log_events(caplog, orch.logger.name)
    assert_logs_have_required_fields(events)
    assert results[0].vector_store_id == "vs_1"
    assert any(event.get("event") == "VECTOR_STORE_CREATED" for event in events)
    assert any(event.get("event") == "EVIDENCE_READY" for event in events)

    rec = state_get(
        StateGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=file.file_id,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    assert rec is not None
    assert rec.vector_store_id == "vs_1"
    assert rec.vector_store_status == "completed"
    assert rec.indexed_at_utc == "2024-01-01T00:00:00Z"
    assert rec.openai_file_id == "file_upload_1"


def test_ingest_orchestrator_records_doc_map_summary(tmp_path) -> None:
    settings = _ingest_settings(tmp_path)
    file = DriveFile(
        schema_version="1.0",
        file_id="file",
        name="name.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    summary = {"sections_count": 0, "not_found_reason": "model_returned_no_json"}
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:no_content",
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2024-01-01T00:00:00Z",
        openai_file_id="file_upload_1",
        evidence_packs=None,
        vector_store_last_error=None,
        doc_map_summary=summary,
    )
    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        process_file=_make_ingest_process(
            generate_report=lambda current_file, cache_path, current_settings, md5, ctx: (
                outcome
            )
        ),
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert results[0].status == "error"
    rec = state_get(
        StateGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=file.file_id,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    assert rec is not None
    assert rec.doc_map_summary == summary


def test_generate_report_vector_store_with_validation(
    tmp_path,
    assert_no_defaulted_required_fields,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{**settings.__dict__, "openai_timeout_seconds": 3600.0}
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    validation_calls: list[str] = []
    analysis_store: list[tuple[str, object]] = []
    metadata_upserts = []
    vector_calls: list[tuple[str, dict[str, object]]] = []
    execution_trace: list[str] = []
    taxonomy_started = threading.Event()
    evidence_started = threading.Event()
    overlap_flags = {
        "taxonomy_saw_evidence": False,
        "evidence_saw_taxonomy": False,
    }
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )

    def _create_vector_store(req, ctx):
        execution_trace.append("vector_create")
        vector_calls.append(
            (
                "create",
                {
                    "name": req.name,
                    "report_id": req.metadata.report_id,
                    "report_name": req.metadata.report_name,
                },
            )
        )
        return SimpleNamespace(vector_store_id="vs_new")

    def _upload_file(req, ctx):
        execution_trace.append("vector_upload")
        vector_calls.append(
            (
                "upload",
                {
                    "vector_store_id": req.vector_store_id,
                    "file_path": req.file_path,
                },
            )
        )
        return SimpleNamespace(openai_file_id="file_upload")

    def _attach_file(req, ctx):
        execution_trace.append("vector_attach")
        vector_calls.append(
            (
                "attach",
                {
                    "vector_store_id": req.vector_store_id,
                    "openai_file_id": req.openai_file_id,
                },
            )
        )

    def _wait_until_indexed(req, ctx):
        execution_trace.append("vector_wait")
        vector_calls.append(
            (
                "wait",
                {
                    "vector_store_id": req.vector_store_id,
                    "timeout_s": req.timeout_s,
                    "poll_interval_s": req.poll_interval_s,
                },
            )
        )
        return SimpleNamespace(
            status="completed",
            indexed_at_utc="2024-01-01T00:00:00Z",
            last_error=None,
        )

    def _extract_best_figure(req, ctx):
        execution_trace.append("pdf_figure")
        return SimpleNamespace(image_path=None, caption=None)

    def _collect_candidates(req, ctx):
        execution_trace.append("pdf_candidates")
        assert req.parallel_workers == settings.report_worker_limit
        return SimpleNamespace(candidates=[])

    def _render_preview(req, ctx):
        execution_trace.append("pdf_preview")
        return SimpleNamespace(
            schema_version="1.1",
            image_path=str(tmp_path / "preview.png"),
            page_number=0,
        )

    def _extract_taxonomy(req, ctx):
        execution_trace.append("taxonomy_start")
        taxonomy_started.set()
        overlap_flags["taxonomy_saw_evidence"] = evidence_started.wait(1.0)
        return TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["tag"],
            region="US",
            time_period="2024",
        )

    def _store_pack(request, ctx):
        analysis_store.append((request.pack_name, request.payload))
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

    def _fake_evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        execution_trace.append("evidence_start")
        evidence_started.set()
        overlap_flags["evidence_saw_taxonomy"] = taxonomy_started.wait(1.0)
        assert settings.openai_timeout_seconds == 3600.0
        return {
            "doc_map": {
                "docMap": {
                    "title": "DocMap Title",
                    "publisher": "DocMap Publisher",
                    "sections": [{"title": "Overview"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _fake_artifacts(
        report_id,
        doc_map,
        evidence_packs,
        settings,
        vector_store_id=None,
        source_status=None,
        ctx=None,
        report_name=None,
        **kwargs,
    ):
        payload = {
            "summary": {"tldr": "tldr", "executive_summary": "exec"},
            "insights_final": [{"text": "insight"}],
            "quotes_final": [{"text": "qt", "speaker": "sp"}],
        }
        _store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name="artifacts",
                payload=payload,
                report_slug=report_name,
            ),
            ctx,
        )
        return payload

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        validation_calls.append(req.report_id)
        slug = slugify(kwargs.get("report_name") or req.report_id)
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slug
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        assert req.data.get("_figure_section_enabled") is False
        assert req.data.get("_figure_gallery") in ([], None)
        assert req.data.get("_figure_top", "") == ""
        assert req.data.get("title") == "DB Title"
        assert req.data.get("publisher") == "DB Publisher"
        assert req.data.get("time_period") == "Q1-Q3 2026"
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        vector_store_create=_create_vector_store,
        vector_store_upload_file=_upload_file,
        vector_store_attach_file=_attach_file,
        vector_store_wait_until_indexed=_wait_until_indexed,
        extract_best_figure=_extract_best_figure,
        collect_candidates=_collect_candidates,
        render_preview=_render_preview,
        extract_taxonomy=_extract_taxonomy,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, ctx: metadata_upserts.append(req),
        get_report_metadata=lambda req, ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file_vs",
            title="DB Title",
            created_at=1,
            updated_at=2,
            file_name="vector.pdf",
            publisher="DB Publisher",
            taxonomy=["tag"],
            categories=[],
            region="US",
            time_period="Q1-Q3 2026",
            source_url=None,
            html_path=None,
            md5="md5",
            page_count=1,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id="vs_new",
            evidence_pack_paths={},
        ),
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "processed"
    assert outcome.vector_store_id == "vs_new"
    assert "doc_map" in outcome.evidence_packs
    assert "validation" in outcome.evidence_packs
    assert Path(outcome.html_path).exists()
    assert metadata_upserts[0].title == "DocMap Title"
    assert metadata_upserts[0].publisher == "DocMap Publisher"
    assert validation_calls == ["file_vs"]
    assert overlap_flags["taxonomy_saw_evidence"] is True
    assert overlap_flags["evidence_saw_taxonomy"] is True
    assert execution_trace.index("pdf_figure") < execution_trace.index("vector_wait")
    assert execution_trace.index("pdf_candidates") < execution_trace.index(
        "vector_wait"
    )
    assert execution_trace.index("pdf_preview") < execution_trace.index("vector_wait")
    assert vector_calls == [
        (
            "create",
            {
                "name": "file_vs",
                "report_id": "file_vs",
                "report_name": "vector.pdf",
            },
        ),
        (
            "upload",
            {
                "vector_store_id": "vs_new",
                "file_path": str(pdf_path),
            },
        ),
        (
            "attach",
            {
                "vector_store_id": "vs_new",
                "openai_file_id": "file_upload",
            },
        ),
        (
            "wait",
            {
                "vector_store_id": "vs_new",
                "timeout_s": 3600,
                "poll_interval_s": 5,
            },
        ),
    ]
    assert (
        "artifacts",
        {
            "summary": {"tldr": "tldr", "executive_summary": "exec"},
            "insights_final": [{"text": "insight"}],
            "quotes_final": [{"text": "qt", "speaker": "sp"}],
        },
    ) in analysis_store


def test_generate_report_doc_map_empty_halts(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{**settings.__dict__, "openai_timeout_seconds": 3600.0}
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )

    def _fake_evidence(*args, **kwargs):
        raise AppError(
            code="doc_map_empty",
            message="doc_map_empty:no_content",
            retryable=False,
            context={
                "sections_count": 0,
                "not_found_reason": "model_returned_no_json",
            },
        )

    def _unexpected(*args, **kwargs):
        pytest.fail("Unexpected downstream call after doc_map_empty")

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_unexpected,
        run_validation=_unexpected,
        render_report=_unexpected,
        upsert_report_metadata=_unexpected,
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert outcome.status == "error"
    assert "doc_map_empty" in (outcome.error or "")
    assert outcome.vector_store_id == "vs_new"
    assert outcome.doc_map_summary is not None
    assert outcome.doc_map_summary.get("sections_count") == 0
    assert outcome.doc_map_summary.get("not_found_reason") == "model_returned_no_json"
