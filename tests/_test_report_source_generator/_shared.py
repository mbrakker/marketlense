# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_report_source_generator.py")

import json

from dataclasses import replace

from pathlib import Path

from types import SimpleNamespace

import pytest

from src.contracts.prompts import PromptLoadRequest

from src.contracts.drive import DriveFile

from src.contracts.pdf_ocr import PdfOcrChunk, PdfOcrSplitResponse

from src.contracts.pdf_text import (
    PdfTextExtractResponse,
    PdfTextSample,
    PdfTextSampleResponse,
)

from src.contracts.pdf_utils import PdfInfoResponse

from src.contracts.report_generation import ReportRuntimeState

from src.contracts.run_context import RunContext

from src.generators.report_generation_dependencies import ReportSourceDependencies

from src.generators.report_generation_shared import (
    contents_cache_key,
    derive_title,
    pdf_info_cache_key,
    report_slug,
    text_cache_key,
)

from src.generators.report_source_generator import prepare_report_source

from src.services import prompt_service

from src.utils.cache_utils import sha256_json

from src.utils.errors import AppError

def _runtime(
    ingest_settings,
    run_context: RunContext,
    tmp_path: Path,
) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(ingest_settings, pdf_text_sample_pages=2, report_worker_limit=1)
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / "report.pdf"),
        settings=settings,
        md5="md5",
        ctx=run_context,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )

def _deps(**overrides) -> ReportSourceDependencies:
    base = ReportSourceDependencies.default()
    seeded = replace(
        base,
        build_pdf_context=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            context=SimpleNamespace(
                fitz_doc=None,
                pypdf_reader=None,
                close=lambda: None,
            ),
            fitz_error=None,
            pypdf_error=None,
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
        render_preview=lambda req, ctx: SimpleNamespace(
            schema_version="1.1",
            image_path="preview.png",
            page_number=0,
        ),
        split_pdf_for_ocr=lambda req, ctx: PdfOcrSplitResponse(
            schema_version="1.0",
            chunks=[
                PdfOcrChunk(
                    schema_version="1.0",
                    chunk_index=1,
                    source_pdf_path=req.source_pdf_path,
                    chunk_pdf_path=req.source_pdf_path,
                    start_page_number=1,
                    end_page_number=2,
                    page_count=2,
                )
            ],
        ),
        read_text=lambda req, ctx: (_ for _ in ()).throw(
            AppError(code="file_not_found", message="missing", retryable=False)
        ),
    )
    return replace(seeded, **overrides)



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
