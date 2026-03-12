from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveFile
from src.contracts.pdf_text import (
    PdfTextExtractResponse,
    PdfTextSample,
    PdfTextSampleResponse,
)
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.run_context import RunContext
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.generators.report_source_generator import prepare_report_source
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


def _deps(**overrides) -> ReportGeneratorDependencies:
    base = ReportGeneratorDependencies.default()
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
        read_text=lambda req, ctx: (_ for _ in ()).throw(
            AppError(code="file_not_found", message="missing", retryable=False)
        ),
    )
    return replace(seeded, **overrides)


def test_prepare_report_source_writes_caches_and_marks_low_density(
    ingest_settings, run_context, tmp_path
):
    writes: list[str] = []
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=5,
            metadata={"Author": "ACME"},
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="body",
            pages_extracted=1,
            char_count=4,
            text_density=4.0,
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
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
        write_bytes=lambda req, ctx: writes.append(req.path) or None,
    )

    state = prepare_report_source(runtime, deps)

    assert state.text_validation_status == "pass"
    assert state.payload._text_not_available is True
    assert any("pdf_info_" in path for path in writes)
    assert any("contents_" in path for path in writes)
    assert any("text_" in path for path in writes)


def test_prepare_report_source_halts_when_no_pages_to_sample(
    ingest_settings, run_context, tmp_path, assert_app_error
):
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=0,
            metadata={},
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="",
            pages_extracted=0,
            char_count=0,
            text_density=0.0,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        prepare_report_source(runtime, deps)

    assert_app_error(
        exc_info.value,
        code="pdf_text_unextractable",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["text_validation_reason"] == "no_pages_to_sample"


def test_prepare_report_source_halts_when_sample_pages_have_no_text(
    ingest_settings, run_context, tmp_path, assert_app_error
):
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=4,
            metadata={},
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="",
            pages_extracted=1,
            char_count=0,
            text_density=0.0,
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(
                    page_index=0,
                    page_number=1,
                    char_count=0,
                    has_text=False,
                ),
                PdfTextSample(
                    page_index=2,
                    page_number=3,
                    char_count=0,
                    has_text=False,
                ),
            ],
            any_text=False,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        prepare_report_source(runtime, deps)

    assert_app_error(
        exc_info.value,
        code="pdf_text_unextractable",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["text_validation_reason"] == "no_text_in_sampled_pages"
