# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_vector_pipeline_wiring.py"
)

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

from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    ReportCardManifestWriteResponse,
)

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
        "publication_date": "2026-06-09",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "Complete standard TLDR.",
            "card_tldr_compact": "Complete compact TLDR.",
            "executive_summary": "exec",
            "claim_evidence_map": [],
        },
        "cover_semantics": {
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "country",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "selection_reason": "The report is organized around a rising trend.",
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
                "text": "Insight 1.",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Insight 2.",
                "evidence_id": "f2",
                "evidence": "Evidence 2",
                "metric": {},
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Insight 3.",
                "evidence_id": "f3",
                "evidence": "Evidence 3",
                "metric": {},
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Insight 4.",
                "evidence_id": "f4",
                "evidence": "Evidence 4",
                "metric": {},
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Insight 5.",
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

    def _process_file(file, index, settings, root_ctx, force_report_cards):
        del force_report_cards
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
    def _generate_cover_images(req, ctx):
        del ctx
        report = req.reports[0]
        asset_dir = Path(req.output_dir) / report.report_slug / "assets"
        return [
            SimpleNamespace(
                schema_version="2.0",
                file_id=report.file_id,
                title=report.title,
                status="generated",
                assets=CardCoverAssetSet(
                    schema_version="1.0",
                    small=CardCoverAsset(
                        schema_version="1.0",
                        size="small",
                        output_path=str(asset_dir / "report-card-small.png"),
                        width=1600,
                        height=900,
                    ),
                    medium=CardCoverAsset(
                        schema_version="1.0",
                        size="medium",
                        output_path=str(asset_dir / "report-card-medium.png"),
                        width=1200,
                        height=1500,
                    ),
                    large=CardCoverAsset(
                        schema_version="1.0",
                        size="large",
                        output_path=str(asset_dir / "report-card-large.png"),
                        width=1200,
                        height=1600,
                    ),
                ),
                error=None,
            )
        ]

    def _write_report_card_manifest(req, ctx):
        del ctx
        return ReportCardManifestWriteResponse(
            schema_version="1.0",
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json"),
            bytes_written=1024,
        )

    def _render_preview(req, ctx):
        del req, ctx
        preview_path = tmp_path / "preview.png"
        preview_path.write_bytes(b"preview")
        return SimpleNamespace(
            schema_version="1.1",
            image_path=str(preview_path),
            page_number=0,
        )

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
        "render_preview": _render_preview,
        "generate_cover_images": _generate_cover_images,
        "write_report_card_manifest": _write_report_card_manifest,
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


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
