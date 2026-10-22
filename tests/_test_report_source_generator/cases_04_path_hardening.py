# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.contracts.openai import OpenAIPdfOcrResponse
from src.contracts.pdf_ocr import (
    PdfOcrChunk,
    PdfOcrPageText,
    PdfOcrSplitResponse,
    PdfTextRenderResponse,
)
from src.generators.pdf_text_ocr_generator import recover_pdf_text_with_ocr

from ._shared import *  # noqa: F401,F403


def _units(path: str) -> int:
    return len(str(Path(path).resolve()).encode("utf-16-le")) // 2


def test_ocr_generator_bounds_noncached_long_report_paths_without_extra_provider_work(
    ingest_settings, run_context, tmp_path
):
    runtime = replace(
        _runtime(
            replace(
                ingest_settings,
                pdf_text_ocr_cache_enabled=False,
                pdf_text_ocr_chunk_page_count=2,
            ),
            run_context,
            tmp_path,
        ),
        md5="",
        report_name="Очень-длинное-имя-отчёта-" * 20,
    )
    split_paths: list[str] = []
    render_paths: list[str] = []
    provider_calls: list[str] = []

    def _split(request, _ctx):
        split_paths.append(request.output_dir)
        return PdfOcrSplitResponse(
            schema_version="1.0",
            chunks=[
                PdfOcrChunk(
                    schema_version="1.0",
                    chunk_index=1,
                    source_pdf_path=request.source_pdf_path,
                    chunk_pdf_path=request.source_pdf_path,
                    start_page_number=1,
                    end_page_number=1,
                    page_count=1,
                )
            ],
        )

    def _ocr(request, _ctx):
        provider_calls.append(request.pdf_path)
        return OpenAIPdfOcrResponse(
            schema_version="1.0",
            pages=[PdfOcrPageText(page_number=1, text="OCR page")],
            raw_text='{"pages":[{"page_number":1,"text":"OCR page"}]}',
            model=request.model,
            request_id="request-1",
        )

    def _render(request, _ctx):
        render_paths.append(request.output_path)
        return PdfTextRenderResponse(
            schema_version="1.0",
            output_path=request.output_path,
            rendered_page_count=len(request.pages),
        )

    dependencies = _deps(
        split_pdf_for_ocr=_split,
        openai_ocr_pdf=_ocr,
        render_text_pdf=_render,
    )

    response = recover_pdf_text_with_ocr(
        runtime,
        page_count=1,
        dependencies=dependencies,
        llm_client=_ocr_client(dependencies),
    )

    assert response.cache_hit is False
    assert provider_calls == [runtime.local_pdf_path]
    assert split_paths and _units(split_paths[0]) <= 240
    assert render_paths and _units(render_paths[0]) <= 240
    assert Path(render_paths[0]).name.casefold().endswith(".ocr.pdf")


__all__ = [
    "test_ocr_generator_bounds_noncached_long_report_paths_without_extra_provider_work",
]
