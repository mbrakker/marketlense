from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from src.contracts.drive import DriveFile
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateBatch,
    SignalCandidateExtractionOutcome,
    SignalCandidateStoreResponse,
)
from src.contracts.context_category_fit import (
    CategoryFitCandidate,
    ContextCategoryFitResponse,
    ReportCategoryContext,
)
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.pdf_text import PdfTextSample, PdfTextSampleResponse
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_assets import RenderResponse
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.report_store import ReportSourceDiscoveryRecordRequest
from src.contracts.report_store import ReportSourceQualityHistoryRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetRequest
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.contracts.validation import ValidationReport
from src.generators import report_analysis_generator as rag
from src.generators.report_generation_dependencies import (
    FigureCaptionDependencies,
    ReportAnalysisDependencies,
    ReportGenerationDependencies,
    ReportRenderDependencies,
    ReportSignalDependencies,
    ReportSelectionDependencies,
    ReportSourceDependencies,
    ReportSourceScoringDependencies,
)
from src.generators.report_generation_shared import derive_title, report_slug
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.orchestrators import report_generation_orchestrator as rgo
from src.services.file_service import file_stat
from src.services.report_store_service import (
    list_report_source_quality_history,
    record_discovered_report_source,
)
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
        signal_store_db=str(tmp_path / "signals.sqlite"),
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


def _analysis_artifacts(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "tldr",
            "executive_summary": "exec",
            "claim_evidence_map": [],
        },
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Candidate 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
                "score": 0.9,
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Insight 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Insight 2",
                "evidence_id": "f2",
                "evidence": "Evidence 2",
                "metric": {},
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Insight 3",
                "evidence_id": "f3",
                "evidence": "Evidence 3",
                "metric": {},
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Insight 4",
                "evidence_id": "f4",
                "evidence": "Evidence 4",
                "metric": {},
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Insight 5",
                "evidence_id": "f5",
                "evidence": "Evidence 5",
                "metric": {},
                "pages": [5],
            },
        ],
        "quotes_final": [
            {
                "text": "Quote",
                "speaker": "Author",
                "citation": "p. 1",
                "page": 1,
                "evidence_id": "q1",
            }
        ],
        "expert_comment": "Expert comment",
        "linkedin_post": "LinkedIn post",
        "source_status": {
            "schema_version": "1.0",
            "not_available": False,
            "reason": "",
        },
    }
    payload.update(overrides)
    return payload


def _analysis_dependencies(**overrides) -> ReportAnalysisDependencies:
    return replace(ReportAnalysisDependencies.default(), **overrides)


def _report_dependencies(**overrides) -> ReportGenerationDependencies:
    base = ReportGenerationDependencies.default()
    source_updates = {}
    selection_updates = {}
    analysis_updates = {}
    render_updates = {}
    figure_caption_updates = {}
    signal_updates = {}
    source_scoring_updates = {}
    source_fields = set(ReportSourceDependencies.__dataclass_fields__)
    selection_fields = set(ReportSelectionDependencies.__dataclass_fields__)
    analysis_fields = set(ReportAnalysisDependencies.__dataclass_fields__) - {
        "figure_caption"
    }
    render_fields = set(ReportRenderDependencies.__dataclass_fields__)
    figure_caption_fields = set(FigureCaptionDependencies.__dataclass_fields__)
    signal_fields = set(ReportSignalDependencies.__dataclass_fields__)
    source_scoring_fields = set(ReportSourceScoringDependencies.__dataclass_fields__)

    for key, value in overrides.items():
        applied = False
        if key in source_fields:
            source_updates[key] = value
            applied = True
        if key in selection_fields:
            selection_updates[key] = value
            applied = True
        if key in analysis_fields:
            analysis_updates[key] = value
            applied = True
        if key in render_fields:
            render_updates[key] = value
            applied = True
        if key in figure_caption_fields:
            figure_caption_updates[key] = value
            applied = True
        if key in signal_fields:
            signal_updates[key] = value
            applied = True
        if key in source_scoring_fields:
            source_scoring_updates[key] = value
            applied = True
        if not applied:
            raise AssertionError(f"Unknown report dependency override: {key}")

    analysis = replace(base.analysis, **analysis_updates)
    if figure_caption_updates:
        analysis = replace(
            analysis,
            figure_caption=replace(analysis.figure_caption, **figure_caption_updates),
        )
    return replace(
        base,
        source=replace(base.source, **source_updates),
        selection=replace(base.selection, **selection_updates),
        analysis=analysis,
        render=replace(base.render, **render_updates),
        signal=replace(base.signal, **signal_updates),
        source_scoring=replace(base.source_scoring, **source_scoring_updates),
    )


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
            resolve_md5_sidecar=lambda request, _ctx: (
                FileCacheMd5SidecarResolveResponse(
                    schema_version="1.0",
                    cache_path=request.cache_path,
                    sidecar_path=f"{request.cache_path}.md5.json",
                    sidecar_exists=False,
                    record=None,
                    resolved_md5=None,
                    hit=False,
                    reason="missing",
                )
            ),
            ensure_file_name=lambda current_file, _settings, _ctx: current_file,
            write_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
                schema_version="1.0",
                cache_path=request.cache_path,
                sidecar_path=f"{request.cache_path}.md5.json",
                record=None,
                written=False,
                reason="skipped",
            ),
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
) -> ReportGenerationDependencies:
    base = {
        "state_get": lambda req, ctx: None,
        "vector_store_get_status": lambda req, ctx: SimpleNamespace(
            status="completed",
            indexed_at_utc="2024-01-01T00:00:00Z",
            last_error=None,
        ),
        "vector_store_create": lambda req, ctx: SimpleNamespace(
            vector_store_id="vs_new"
        ),
        "vector_store_upload_file": lambda req, ctx: SimpleNamespace(
            openai_file_id="file_upload"
        ),
        "vector_store_attach_file": lambda req, ctx: None,
        "vector_store_delete": lambda req, ctx: SimpleNamespace(
            vector_store_id=req.vector_store_id,
            deleted=True,
            missing_remote=False,
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
        "build_report_category_context": lambda req, ctx: ReportCategoryContext(
            schema_version="1.0",
            report_id=req.report.file_id,
            title=req.report.title,
            publisher=req.report.publisher or "",
            region=req.report.region or "",
            time_period=req.report.time_period or "",
            overview="Context overview",
            methods=[],
            key_findings=[],
            limitations=[],
            sections=[],
        ),
        "fit_report_categories_from_context": lambda req, ctx: (
            ContextCategoryFitResponse(
                schema_version="1.0",
                report_id=req.context.report_id,
                categories=["cat"],
                category_labels=["Category"],
                fits=[
                    CategoryFitCandidate(
                        category_id="cat",
                        label="Category",
                        fit_score=0.91,
                        decision="primary",
                        why_fit="The report centers on Category.",
                        why_not_fit="",
                        evidence_sections=["Overview"],
                    )
                ],
                request_id="req-1",
                model="gpt-5-mini",
                raw_response="{}",
            )
        ),
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
        "split_pdf_for_ocr": lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            chunks=[
                SimpleNamespace(
                    schema_version="1.0",
                    chunk_index=1,
                    source_pdf_path=req.source_pdf_path,
                    chunk_pdf_path=req.source_pdf_path,
                    start_page_number=1,
                    end_page_number=1,
                    page_count=1,
                )
            ],
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
        parallel_within_file=bool(
            int(getattr(settings, "report_worker_limit", 1) or 1) > 1
        ),
    )


def test_start_vector_store_indexing_creates_without_wait_loop(tmp_path):
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

    deps = _analysis_dependencies(
        state_get=lambda req, ctx: None,
        vector_store_create=lambda req, ctx: (
            calls.append("create") or SimpleNamespace(vector_store_id="vs_123")
        ),
        vector_store_upload_file=lambda req, ctx: (
            calls.append("upload") or SimpleNamespace(openai_file_id="file_upload_1")
        ),
        vector_store_attach_file=lambda req, ctx: calls.append("attach") or None,
        vector_store_get_status=lambda req, ctx: (
            calls.append("status")
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
    state = rag.start_vector_store_indexing(runtime, None, deps)

    assert calls == ["create", "upload", "attach"]
    assert state.vector_store_id == "vs_123"
    assert state.openai_file_id == "file_upload_1"
    assert state.vector_store_status == "indexing"
    assert state.indexed_at_utc is None
    assert state.last_error is None


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
    caplog,
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

    def _get_vector_store_status(req, ctx):
        execution_trace.append("vector_status")
        vector_calls.append(
            (
                "status",
                {
                    "vector_store_id": req.vector_store_id,
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
        payload = _analysis_artifacts()
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
        vector_store_get_status=_get_vector_store_status,
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

    projection_requests = []

    def _failing_projection(req):
        projection_requests.append(req)
        raise AppError(
            code="analytics_projection_test_failure",
            message="projection failed",
            retryable=False,
            severity="error",
        )

    with caplog.at_level(logging.ERROR, logger=rgo.logger.name):
        outcome = rgo.run_report_generation(
            file,
            str(pdf_path),
            settings,
            md5="md5",
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=_failing_projection,
        )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "processed"
    assert projection_requests[0].rendered_html_path == outcome.html_path
    events = _decode_log_events(caplog, rgo.logger.name)
    assert any(
        event.get("event") == "analytics_projection_failed_nonblocking"
        and event.get("fields", {}).get("error_code")
        == "analytics_projection_test_failure"
        for event in events
    )
    assert outcome.vector_store_id == "vs_new"
    assert outcome.evidence_packs is not None
    assert "doc_map" in outcome.evidence_packs
    assert "validation" in outcome.evidence_packs
    assert outcome.html_path is not None
    assert Path(outcome.html_path).exists()
    assert metadata_upserts[0].title == "DocMap Title"
    assert metadata_upserts[0].publisher == "DocMap Publisher"
    assert validation_calls == ["file_vs"]
    assert overlap_flags["taxonomy_saw_evidence"] is True
    assert overlap_flags["evidence_saw_taxonomy"] is True
    assert execution_trace.index("pdf_figure") < execution_trace.index("vector_status")
    assert execution_trace.index("pdf_candidates") < execution_trace.index(
        "vector_status"
    )
    assert execution_trace.index("pdf_preview") < execution_trace.index("vector_status")
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
            "status",
            {
                "vector_store_id": "vs_new",
            },
        ),
    ]
    artifacts_entries = [
        payload for pack_name, payload in analysis_store if pack_name == "artifacts"
    ]
    assert len(artifacts_entries) == 1
    assert artifacts_entries[0]["summary"]["tldr"] == "tldr"
    assert len(artifacts_entries[0]["insights_final"]) == 5
    assert artifacts_entries[0]["quotes_final"][0]["text"] == "Quote"


def test_generate_report_adds_signal_artifact_pack_after_projection(tmp_path) -> None:
    settings = _ingest_settings(tmp_path)
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    file = DriveFile(
        schema_version="1.0",
        file_id="file_signal",
        name="signal.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-signal",
        task_id="task-signal",
        span_id="span-signal",
    )
    execution_trace: list[str] = []
    signal_requests = []

    def _store_pack(request, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or request.report_id)
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload), encoding="utf-8")
        return SimpleNamespace(output_path=str(path))

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
        payload = _analysis_artifacts()
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

    def _fake_evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        return {
            "doc_map": {
                "docMap": {
                    "title": "Signal Report",
                    "publisher": "Signal Publisher",
                    "sections": [{"title": "Market movement"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    def _projection(req):
        execution_trace.append("projection")
        return SimpleNamespace(rows_upserted=3)

    def _signal_extraction(request, ctx):
        execution_trace.append("signal_extraction")
        signal_requests.append(request)
        batch = SignalCandidateBatch(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            extraction_request_id=request.extraction_request_id,
            generated_at_utc="2026-06-02T00:00:00+00:00",
            candidates=[],
            groups=[],
        )
        stored = SignalCandidateStoreResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=request.db_path,
            extraction_request_id=request.extraction_request_id,
            candidate_count=0,
            group_count=0,
            stale_candidate_count=0,
            stale_group_count=0,
        )
        return SignalCandidateExtractionOutcome(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            extraction_request_id=request.extraction_request_id,
            status="stored",
            batch=batch,
            stored_response=stored,
            candidate_count=0,
            group_count=0,
            state_transitions=["started", "completed"],
        )

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        run_signal_candidate_extraction=_signal_extraction,
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
        analytics_projection_fn=_projection,
    )

    assert execution_trace == ["projection", "signal_extraction"]
    assert signal_requests
    signal_request = signal_requests[0]
    assert signal_request.projected_data_request.db_path == settings.reports_db
    assert signal_request.db_path == settings.signal_store_db
    assert signal_request.analysis_request.publisher_filters == ["Signal Publisher"]
    assert signal_request.analysis_request.max_source_reports == 1
    assert outcome.evidence_packs is not None
    signal_path = outcome.evidence_packs["signals"]
    assert Path(signal_path).exists()
    payload = json.loads(Path(signal_path).read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "signals"
    assert payload["source_report_id"] == "file_signal"
    assert payload["signal_store_db"] == settings.signal_store_db
    assert payload["candidate_count"] == 0


def test_report_generation_scores_two_ingested_reports_for_same_publisher(
    tmp_path,
) -> None:
    settings = replace(_ingest_settings(tmp_path), report_worker_limit=1)
    publisher_name = "Example Research"
    source_rows = [
        (
            "file_score_1",
            "2026 Global Retail Market Outlook Benchmark Survey",
            "https://research.example.com/reports/2026-retail-market-outlook",
        ),
        (
            "file_score_2",
            "2026 Consumer Commerce Trends Benchmark Survey",
            "https://research.example.com/reports/2026-commerce-trends-benchmark",
        ),
    ]
    seed_ctx = RunContext(
        schema_version="1.0",
        run_id="run-seed",
        task_id="seed-report-sources",
        span_id="span-seed",
    )
    for _file_id, title, url in source_rows:
        record_discovered_report_source(
            ReportSourceDiscoveryRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                publisher_name=publisher_name,
                source_domain="research.example.com",
                report_name=title,
                landing_page_url=url,
                source_page_url="https://research.example.com/research/reports",
                discovered_at_utc="2026-06-05T00:00:00Z",
                discovered_on_page_number=1,
            ),
            seed_ctx,
        )

    def _store_pack(request, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or request.report_id)
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload), encoding="utf-8")
        return SimpleNamespace(output_path=str(path))

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _render_report(req, ctx):
        html_path = Path(settings.output_dir) / f"{req.file_id}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    files = [
        DriveFile(
            schema_version="1.0",
            file_id=file_id,
            name=f"{title}.pdf",
            modified_time=None,
            md5_checksum=f"md5-{file_id}",
        )
        for file_id, title, _url in source_rows
    ]
    titles_by_file_id = {file_id: title for file_id, title, _url in source_rows}

    def _generate_report(current_file, cache_path, current_settings, md5, ctx):
        title = titles_by_file_id[current_file.file_id]

        def _evidence(report_id, vector_store_id, settings, ctx, **kwargs):
            return {
                "doc_map": {
                    "docMap": {
                        "title": title,
                        "publisher": publisher_name,
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

        def _artifacts(
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
            payload = _analysis_artifacts()
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

        deps = _base_vector_report_dependencies(
            tmp_path,
            generate_evidence_packs=_evidence,
            generate_artifacts=_artifacts,
            run_validation=_fake_validation,
            analysis_store_pack=_store_pack,
            render_report=_render_report,
        )
        return rgo.run_report_generation(
            current_file,
            cache_path,
            current_settings,
            md5=md5,
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=lambda req: None,
        )

    outcomes = orch.run_ingest(
        settings,
        limit=2,
        dependencies=_batch_dependencies(
            list_pdfs=lambda req, ctx: files,
            process_file=_make_ingest_process(generate_report=_generate_report),
        ),
    )

    assert [outcome.status for outcome in outcomes] == ["processed", "processed"]

    history = list_report_source_quality_history(
        ReportSourceQualityHistoryRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            publisher_name=publisher_name,
            limit=10,
        ),
        seed_ctx,
    )

    assert len(history.items) == 2
    assert {item.report_name for item in history.items} == {
        title for _file_id, title, _url in source_rows
    }
    assert {item.source_page_url for item in history.items} == {
        "https://research.example.com/research/reports"
    }
    assert all(item.source_status == "downloaded" for item in history.items)
    assert all(item.overall_score >= 78.0 for item in history.items)

    with sqlite3.connect(settings.reports_db) as conn:
        scored_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM report_sources
            WHERE publisher_name=?
              AND report_value_score IS NOT NULL
              AND report_value_score_json IS NOT NULL
            """,
            (publisher_name,),
        ).fetchone()[0]
    assert scored_rows == 2


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


def test_generate_report_resumes_from_analysis_checkpoint_without_upstream_rerun(
    tmp_path,
) -> None:
    settings = replace(_ingest_settings(tmp_path), report_worker_limit=1)
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
    upstream_calls = {"evidence": 0, "artifacts": 0, "validation": 0}
    rendered_payloads: list[dict] = []

    def _store_pack(request: AnalysisStorePackRequest, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or str(request.report_id))
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(request.payload, ensure_ascii=True), encoding="utf-8"
        )
        return SimpleNamespace(output_path=str(path))

    def _fake_evidence(*args, **kwargs):
        upstream_calls["evidence"] += 1
        return {
            "doc_map": {
                "docMap": {
                    "title": "Checkpoint Title",
                    "publisher": "Checkpoint Publisher",
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

    def _fake_artifacts(*args, **kwargs):
        upstream_calls["artifacts"] += 1
        return _analysis_artifacts()

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        upstream_calls["validation"] += 1
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or str(req.report_id))
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _render_report(req, ctx):
        rendered_payloads.append(dict(req.data))
        html_path = Path(req.out_dir) / f"{req.file_id}-{len(rendered_payloads)}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            json.dumps(req.data, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    full_deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
        generate_cover_images=lambda req, ctx: [],
    )

    full_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=full_deps,
    )
    full_render_payload = rendered_payloads[-1]

    def _unexpected_upstream(*args, **kwargs):
        pytest.fail("resume from analysis checkpoint reran an upstream stage")

    resume_deps = _base_vector_report_dependencies(
        tmp_path,
        build_pdf_context=_unexpected_upstream,
        extract_pdf_info=_unexpected_upstream,
        extract_best_figure=_unexpected_upstream,
        collect_candidates=_unexpected_upstream,
        vector_store_create=_unexpected_upstream,
        generate_evidence_packs=_unexpected_upstream,
        generate_artifacts=_unexpected_upstream,
        run_validation=_unexpected_upstream,
        render_report=_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: None,
        generate_cover_images=lambda req, ctx: [],
    )

    resumed_outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=resume_deps,
        resume_from_stage="analysis_complete",
    )
    resumed_render_payload = rendered_payloads[-1]

    assert full_outcome.status == "processed"
    assert resumed_outcome.status == "processed"
    assert full_render_payload == resumed_render_payload
    assert resumed_outcome.evidence_packs == full_outcome.evidence_packs
    assert upstream_calls == {"evidence": 1, "artifacts": 1, "validation": 1}


def test_generate_report_deletes_vector_store_when_retention_disabled(
    tmp_path,
) -> None:
    settings = replace(_ingest_settings(tmp_path), vector_store_keep=False)
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
    delete_calls = []

    def _store_pack(request, ctx):
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=lambda **kwargs: {
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
        },
        generate_artifacts=lambda **kwargs: _analysis_artifacts(),
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, ctx: None,
        vector_store_delete=lambda req, ctx: (
            delete_calls.append(req.vector_store_id)
            or SimpleNamespace(
                vector_store_id=req.vector_store_id,
                deleted=True,
                missing_remote=False,
            )
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

    assert delete_calls == ["vs_new"]
    assert outcome.status == "processed"
    assert outcome.vector_store_id is None
    assert outcome.vector_store_status == "deleted"


def test_generate_report_ocr_fallback_uses_ocr_pdf_for_vector_and_original_for_visuals(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "openai_timeout_seconds": 3600.0,
            "pdf_text_ocr_enabled": True,
            "pdf_text_ocr_cache_enabled": False,
        }
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
    ocr_pdf_path = str(tmp_path / "ocr.pdf")
    preview_paths: list[str] = []
    figure_paths: list[str] = []
    candidate_paths: list[str] = []
    vector_upload_paths: list[str] = []

    def _sample(req, ctx):
        if req.path == str(pdf_path):
            return PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=0, has_text=False
                    )
                ],
                any_text=False,
            )
        return PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(page_index=0, page_number=1, char_count=18, has_text=True)
            ],
            any_text=True,
        )

    def _render_preview(req, ctx):
        preview_paths.append(req.pdf_path)
        return SimpleNamespace(
            schema_version="1.1",
            image_path=str(tmp_path / "preview.png"),
            page_number=0,
        )

    def _extract_best_figure(req, ctx):
        figure_paths.append(req.pdf_path)
        return SimpleNamespace(image_path=None, caption=None)

    def _collect_candidates(req, ctx):
        candidate_paths.append(req.pdf_path)
        return SimpleNamespace(candidates=[])

    def _vector_store_upload_file(req, ctx):
        vector_upload_paths.append(req.file_path)
        return SimpleNamespace(openai_file_id="file_upload")

    deps = _base_vector_report_dependencies(
        tmp_path,
        sample_pdf_text=_sample,
        openai_ocr_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            pages=[
                SimpleNamespace(schema_version="1.0", page_number=1, text="ocr text")
            ],
            raw_text='{"pages":[{"page_number":1,"text":"ocr text"}]}',
            model=req.model,
            request_id="req_ocr",
        ),
        render_text_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            output_path=ocr_pdf_path,
            rendered_page_count=len(req.pages),
        ),
        extract_pdf_text=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            text="ocr text",
            pages_extracted=1,
            char_count=8,
            text_density=8.0,
        ),
        detect_contents_page=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            has_contents=False,
            page_index=-1,
            page_number=0,
            heading="",
            confidence=0.0,
        ),
        render_preview=_render_preview,
        extract_best_figure=_extract_best_figure,
        collect_candidates=_collect_candidates,
        vector_store_upload_file=_vector_store_upload_file,
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _analysis_artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(tmp_path / "validation.json"),
        ),
        render_report=lambda req, ctx: RenderResponse(
            schema_version="1.0",
            html_path=str(tmp_path / "out.html"),
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

    assert outcome.status == "processed"
    assert outcome.ocr_fallback_used is True
    assert outcome.ocr_pdf_path == ocr_pdf_path
    assert vector_upload_paths == [ocr_pdf_path]
    assert preview_paths == [str(pdf_path)]
    assert figure_paths == [str(pdf_path)]
    assert candidate_paths == [str(pdf_path)]


def test_generate_report_vector_store_figure_caption_fail_open_runs_before_validation(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "figure_caption_enabled": True,
            "figure_caption_prompt_namespace": "report_vs/figure_caption",
            "figure_caption_max_chars": 120,
            "openai_models": {"report_vs/figure_caption": "gpt-5-caption"},
        }
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
    execution_trace: list[str] = []
    analysis_store: list[tuple[str, object]] = []

    def _extract_best_figure(req, _ctx):
        execution_trace.append("figure_select")
        return SimpleNamespace(
            image_path="vector/assets/figure.png",
            caption="Detected figure caption",
            page=0,
        )

    def _store_pack(request, _ctx):
        analysis_store.append((request.pack_name, request.payload))
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

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
        execution_trace.append("artifacts")
        payload = _analysis_artifacts()
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

    def _fake_load_prompt_set(request, _ctx):
        execution_trace.append("caption_prompt")
        return SimpleNamespace(
            system=SimpleNamespace(
                path="src/prompts/report_vs/figure_caption/system.yaml",
                text='{"instruction":"limit {{ max_chars }}"}',
                sha256="system-sha",
            ),
            user=SimpleNamespace(
                path="src/prompts/report_vs/figure_caption/user.yaml",
                text='{"context": {{ context_json }}, "limit": {{ max_chars }}}',
                sha256="user-sha",
            ),
        )

    def _fake_render_prompt(request, _ctx):
        text = request.template.text
        for key, value in request.variables.items():
            text = text.replace("{{ " + key + " }}", str(value))
        return SimpleNamespace(schema_version="1.0", text=text)

    def _fake_openai_chat_json_with_images(request, _ctx):
        execution_trace.append("figure_caption")
        raise RuntimeError("caption_provider_down")

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        execution_trace.append("validation")
        assert req.report.figure.title == "Detected figure caption"
        assert req.report._figure_assets[0].display_caption == "Detected figure caption"
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

    def _fake_render_report(req, _ctx):
        execution_trace.append("render")
        assert (
            req.data["_figure_assets"][0]["display_caption"]
            == "Detected figure caption"
        )
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        extract_best_figure=_extract_best_figure,
        collect_candidates=lambda req, _ctx: SimpleNamespace(candidates=[]),
        load_prompt_set=_fake_load_prompt_set,
        render_prompt=_fake_render_prompt,
        openai_chat_json_with_images=_fake_openai_chat_json_with_images,
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "docMap": {
                    "title": "Doc Title",
                    "publisher": "Doc Publisher",
                    "sections": [
                        {"title": "Overview", "summary": "Summary", "pages": [1]}
                    ],
                }
            },
            "findings": {"findings": []},
        },
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, _ctx: None,
        get_report_metadata=lambda req, _ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file_vs",
            title="Doc Title",
            created_at=1,
            updated_at=2,
            file_name="vector.pdf",
            publisher="Doc Publisher",
            taxonomy=["tag"],
            categories=[],
            region="US",
            time_period="2024",
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

    assert outcome.status == "processed"
    assert outcome.evidence_packs is not None
    assert "figure_captions" in outcome.evidence_packs
    assert execution_trace.index("artifacts") < execution_trace.index("figure_caption")
    assert execution_trace.index("figure_caption") < execution_trace.index("validation")
    assert execution_trace.index("validation") < execution_trace.index("render")
    pack_names = [name for name, _payload in analysis_store]
    assert "figure_captions" in pack_names
