from __future__ import annotations

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
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import derive_title, report_slug
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
    assert (
        exc_info.value.context["text_validation_reason"] == "no_text_in_sampled_pages"
    )


def test_prepare_report_source_does_not_call_ocr_when_native_text_is_extractable(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(ingest_settings, pdf_text_ocr_enabled=True),
        run_context,
        tmp_path,
    )
    ocr_calls = {"count": 0}
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=3,
            metadata={},
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(page_index=0, page_number=1, char_count=12, has_text=True)
            ],
            any_text=True,
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="native text",
            pages_extracted=1,
            char_count=11,
            text_density=11.0,
        ),
        openai_ocr_pdf=lambda req, ctx: ocr_calls.__setitem__(
            "count", ocr_calls["count"] + 1
        ),
    )

    state = prepare_report_source(runtime, deps)

    assert state.ocr_fallback_used is False
    assert state.analysis_pdf_path == runtime.local_pdf_path
    assert ocr_calls["count"] == 0


def test_prepare_report_source_uses_ocr_fallback_and_keeps_original_preview_source(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=False,
        ),
        run_context,
        tmp_path,
    )
    ocr_pdf_path = str(tmp_path / "cached-ocr.pdf")
    preview_paths: list[str] = []
    detect_paths: list[str] = []
    extract_paths: list[str] = []

    def _sample(req, ctx):
        if req.path == runtime.local_pdf_path:
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
                PdfTextSample(page_index=0, page_number=1, char_count=25, has_text=True)
            ],
            any_text=True,
        )

    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=3,
            metadata={},
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
                    end_page_number=3,
                    page_count=3,
                )
            ],
        ),
        sample_pdf_text=_sample,
        openai_ocr_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            pages=[
                SimpleNamespace(
                    schema_version="1.0", page_number=1, text="OCR page one"
                ),
                SimpleNamespace(
                    schema_version="1.0", page_number=2, text="OCR page two"
                ),
                SimpleNamespace(
                    schema_version="1.0", page_number=3, text="OCR page three"
                ),
            ],
            raw_text='{"pages":[]}',
            model=req.model,
            request_id="req_1",
        ),
        render_text_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            output_path=ocr_pdf_path,
            rendered_page_count=len(req.pages),
        ),
        detect_contents_page=lambda req, ctx: (
            detect_paths.append(req.path)
            or SimpleNamespace(
                schema_version="1.0",
                path=req.path,
                has_contents=True,
                page_index=1,
                page_number=2,
                heading="contents",
                confidence=0.9,
            )
        ),
        render_preview=lambda req, ctx: (
            preview_paths.append(req.pdf_path)
            or SimpleNamespace(
                schema_version="1.1",
                image_path="preview.png",
                page_number=req.page_number,
            )
        ),
        extract_pdf_text=lambda req, ctx: (
            extract_paths.append(req.path)
            or PdfTextExtractResponse(
                schema_version="1.0",
                text="ocr extracted text",
                pages_extracted=3,
                char_count=80,
                text_density=26.6,
            )
        ),
    )

    state = prepare_report_source(runtime, deps)

    assert state.ocr_fallback_used is True
    assert state.analysis_pdf_path == ocr_pdf_path
    assert state.ocr_pdf_path == ocr_pdf_path
    assert detect_paths == [ocr_pdf_path]
    assert extract_paths == [ocr_pdf_path]
    assert preview_paths == [runtime.local_pdf_path]


def test_prepare_report_source_uses_cached_ocr_pdf_without_calling_openai_ocr(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=True,
        ),
        run_context,
        tmp_path,
    )
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace="pdf_text/ocr_fallback"),
        run_context,
    )
    cache_key = sha256_json(
        {
            "schema_version": "1.0",
            "md5": runtime.md5,
            "model": runtime.settings.pdf_text_ocr_model,
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "chunk_page_count": runtime.settings.pdf_text_ocr_chunk_page_count,
        }
    )
    cached_pdf_path = (
        tmp_path / "cache" / "pdf_cache" / runtime.md5 / f"ocr_text_{cache_key}.pdf"
    )
    cached_json_path = (
        tmp_path
        / "cache"
        / "pdf_cache"
        / runtime.md5
        / f"ocr_response_{cache_key}.json"
    )
    cached_payload = {
        "schema_version": "1.0",
        "key": cache_key,
        "ocr_response": {
            "schema_version": "1.0",
            "pages": [
                {"schema_version": "1.0", "page_number": 1, "text": "cached ocr text"}
            ],
            "raw_text": '{"pages":[{"page_number":1,"text":"cached ocr text"}]}',
            "model": "gpt-5-mini",
            "request_id": "req_cached",
        },
        "render_response": {
            "schema_version": "1.0",
            "output_path": str(cached_pdf_path),
            "rendered_page_count": 1,
        },
    }
    ocr_calls = {"count": 0}

    def _read_text(req, ctx):
        if req.path == str(cached_json_path):
            return SimpleNamespace(content=json.dumps(cached_payload))
        raise AppError(code="file_not_found", message="missing", retryable=False)

    def _file_stat(req, ctx):
        if req.path == str(cached_pdf_path):
            return SimpleNamespace(exists=True, size_bytes=100, mtime_utc=1.0, md5=None)
        return SimpleNamespace(exists=False, size_bytes=None, mtime_utc=None, md5=None)

    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=1,
            metadata={},
        ),
        sample_pdf_text=lambda req, ctx: (
            PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=0, has_text=False
                    )
                ],
                any_text=False,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=14, has_text=True
                    )
                ],
                any_text=True,
            )
        ),
        read_text=_read_text,
        file_stat=_file_stat,
        openai_ocr_pdf=lambda req, ctx: ocr_calls.__setitem__(
            "count", ocr_calls["count"] + 1
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="cached ocr text",
            pages_extracted=1,
            char_count=14,
            text_density=14.0,
        ),
    )

    state = prepare_report_source(runtime, deps)

    assert state.ocr_fallback_used is True
    assert state.analysis_pdf_path == str(cached_pdf_path)
    assert ocr_calls["count"] == 0


def test_prepare_report_source_runs_single_openai_ocr_model(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=False,
            pdf_text_ocr_model="gpt-5-mini",
        ),
        run_context,
        tmp_path,
    )
    attempted_models: list[str] = []

    def _openai_ocr_pdf(req, ctx):
        attempted_models.append(req.model)
        return SimpleNamespace(
            schema_version="1.0",
            pages=[
                SimpleNamespace(
                    schema_version="1.0",
                    page_number=1,
                    text="fallback ocr text",
                )
            ],
            raw_text='{"pages":[{"page_number":1,"text":"fallback ocr text"}]}',
            model=req.model,
            request_id="req_fallback",
        )

    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=1,
            metadata={},
        ),
        sample_pdf_text=lambda req, ctx: (
            PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=0, has_text=False
                    )
                ],
                any_text=False,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=18, has_text=True
                    )
                ],
                any_text=True,
            )
        ),
        openai_ocr_pdf=_openai_ocr_pdf,
        render_text_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            output_path=str(tmp_path / "fallback-ocr.pdf"),
            rendered_page_count=len(req.pages),
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="fallback ocr text",
            pages_extracted=1,
            char_count=18,
            text_density=18.0,
        ),
    )

    state = prepare_report_source(runtime, deps)

    assert attempted_models == ["gpt-5-mini"]
    assert state.ocr_fallback_used is True
    assert state.analysis_pdf_path == str(tmp_path / "fallback-ocr.pdf")


def test_prepare_report_source_maps_chunk_local_ocr_pages_to_original_page_numbers(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=False,
            pdf_text_ocr_chunk_page_count=2,
        ),
        run_context,
        tmp_path,
    )
    rendered_pages: list[tuple[int, str]] = []
    chunk_paths: list[str] = []

    def _openai_ocr_pdf(req, ctx):
        chunk_paths.append(req.pdf_path)
        if req.pdf_path.endswith("0001-0002.pdf"):
            return SimpleNamespace(
                schema_version="1.0",
                pages=[
                    SimpleNamespace(schema_version="1.0", page_number=1, text="page 1"),
                    SimpleNamespace(schema_version="1.0", page_number=2, text="page 2"),
                ],
                raw_text='{"pages":[{"page_number":1,"text":"page 1"},{"page_number":2,"text":"page 2"}]}',
                model=req.model,
                request_id="req_chunk_1",
            )
        return SimpleNamespace(
            schema_version="1.0",
            pages=[SimpleNamespace(schema_version="1.0", page_number=1, text="page 3")],
            raw_text='{"pages":[{"page_number":1,"text":"page 3"}]}',
            model=req.model,
            request_id="req_chunk_2",
        )

    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=3,
            metadata={},
        ),
        split_pdf_for_ocr=lambda req, ctx: PdfOcrSplitResponse(
            schema_version="1.0",
            chunks=[
                PdfOcrChunk(
                    schema_version="1.0",
                    chunk_index=1,
                    source_pdf_path=req.source_pdf_path,
                    chunk_pdf_path=str(tmp_path / "report.ocr-pages-0001-0002.pdf"),
                    start_page_number=1,
                    end_page_number=2,
                    page_count=2,
                ),
                PdfOcrChunk(
                    schema_version="1.0",
                    chunk_index=2,
                    source_pdf_path=req.source_pdf_path,
                    chunk_pdf_path=str(tmp_path / "report.ocr-pages-0003-0003.pdf"),
                    start_page_number=3,
                    end_page_number=3,
                    page_count=1,
                ),
            ],
        ),
        sample_pdf_text=lambda req, ctx: (
            PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=0, has_text=False
                    )
                ],
                any_text=False,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=18, has_text=True
                    )
                ],
                any_text=True,
            )
        ),
        openai_ocr_pdf=_openai_ocr_pdf,
        render_text_pdf=lambda req, ctx: (
            rendered_pages.extend([(page.page_number, page.text) for page in req.pages])
            or SimpleNamespace(
                schema_version="1.0",
                output_path=str(tmp_path / "chunked-ocr.pdf"),
                rendered_page_count=len(req.pages),
            )
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="page 1\npage 2\npage 3",
            pages_extracted=3,
            char_count=18,
            text_density=6.0,
        ),
    )

    state = prepare_report_source(runtime, deps)

    assert chunk_paths == [
        str(tmp_path / "report.ocr-pages-0001-0002.pdf"),
        str(tmp_path / "report.ocr-pages-0003-0003.pdf"),
    ]
    assert rendered_pages == [(1, "page 1"), (2, "page 2"), (3, "page 3")]
    assert state.analysis_pdf_path == str(tmp_path / "chunked-ocr.pdf")


def test_prepare_report_source_surfaces_pdf_text_ocr_failed(
    ingest_settings, run_context, tmp_path, assert_app_error
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=False,
        ),
        run_context,
        tmp_path,
    )
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=2,
            metadata={},
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(page_index=0, page_number=1, char_count=0, has_text=False)
            ],
            any_text=False,
        ),
        openai_ocr_pdf=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="openai_ocr_request_failed",
                message="boom",
                retryable=True,
            )
        ),
    )

    with pytest.raises(AppError) as exc_info:
        prepare_report_source(runtime, deps)

    assert_app_error(
        exc_info.value,
        code="pdf_text_ocr_failed",
        retryable=True,
    )
    assert exc_info.value.context["attempted_models"] == [
        runtime.settings.pdf_text_ocr_model,
    ]
