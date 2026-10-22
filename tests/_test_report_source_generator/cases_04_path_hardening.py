# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
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
from src.utils.errors import AppError

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


def test_ocr_generator_noncached_outputs_keep_source_and_run_identity(
    ingest_settings, run_context, tmp_path
):
    settings = replace(
        ingest_settings,
        pdf_text_ocr_cache_enabled=False,
        pdf_text_ocr_chunk_page_count=2,
    )
    base_runtime = replace(
        _runtime(settings, run_context, tmp_path),
        md5="",
        report_name="same-report",
        file_name="same-report.pdf",
    )
    first_runtime = replace(
        base_runtime,
        file=replace(base_runtime.file, file_id="drive-report-a"),
        local_pdf_path=str(tmp_path / "source-a.pdf"),
    )
    second_runtime = replace(
        base_runtime,
        file=replace(base_runtime.file, file_id="drive-report-b"),
        local_pdf_path=str(tmp_path / "source-b.pdf"),
    )
    provider_calls: list[str] = []

    def _ocr(request, _ctx):
        provider_calls.append(request.pdf_path)
        text = Path(request.pdf_path).stem
        return OpenAIPdfOcrResponse(
            schema_version="1.0",
            pages=[PdfOcrPageText(page_number=1, text=text)],
            raw_text=json.dumps({"pages": [{"page_number": 1, "text": text}]}),
            model=request.model,
            request_id=f"request-{text}",
        )

    dependencies = _deps(openai_ocr_pdf=_ocr)
    first_response = recover_pdf_text_with_ocr(
        first_runtime,
        page_count=1,
        dependencies=dependencies,
        llm_client=_ocr_client(dependencies),
    )
    second_response = recover_pdf_text_with_ocr(
        second_runtime,
        page_count=1,
        dependencies=dependencies,
        llm_client=_ocr_client(dependencies),
    )
    first_path = Path(first_response.render_response.output_path)
    second_path = Path(second_response.render_response.output_path)
    first_bytes = first_path.read_bytes()
    second_bytes = second_path.read_bytes()

    assert first_path != second_path
    assert first_path.name.casefold().endswith(".ocr.pdf")
    assert second_path.name.casefold().endswith(".ocr.pdf")
    assert first_path.name.casefold() != second_path.name.casefold()
    assert first_path.exists() and second_path.exists()
    assert first_bytes != second_bytes

    replay = recover_pdf_text_with_ocr(
        first_runtime,
        page_count=1,
        dependencies=dependencies,
        llm_client=_ocr_client(dependencies),
    )
    assert Path(replay.render_response.output_path) == first_path
    assert first_path.exists()
    assert second_path.read_bytes() == second_bytes

    different_run = replace(
        first_runtime,
        ctx=replace(run_context, run_id=f"{run_context.run_id}-other"),
    )
    different_run_response = recover_pdf_text_with_ocr(
        different_run,
        page_count=1,
        dependencies=dependencies,
        llm_client=_ocr_client(dependencies),
    )
    assert Path(different_run_response.render_response.output_path) != first_path
    assert len(provider_calls) == 4


def test_ocr_generator_rejects_impossible_noncached_root_before_provider_work(
    ingest_settings, run_context, tmp_path
):
    impossible_root = tmp_path / ("impossible-output-root-" * 20)
    runtime = replace(
        _runtime(
            replace(
                ingest_settings,
                cache_dir=str(impossible_root),
                pdf_text_ocr_cache_enabled=False,
            ),
            run_context,
            tmp_path,
        ),
        md5="",
    )
    provider_calls: list[str] = []

    def _ocr(request, _ctx):
        provider_calls.append(request.pdf_path)
        raise AssertionError("provider work must not begin")

    dependencies = _deps(openai_ocr_pdf=_ocr)

    with pytest.raises(AppError) as exc_info:
        recover_pdf_text_with_ocr(
            runtime,
            page_count=1,
            dependencies=dependencies,
            llm_client=_ocr_client(dependencies),
        )

    assert exc_info.value.code == "pdf_text_ocr_path_invalid"
    assert exc_info.value.retryable is False
    assert exc_info.value.context["path_role"] == "OCR output root"
    assert provider_calls == []


__all__ = [
    "test_ocr_generator_bounds_noncached_long_report_paths_without_extra_provider_work",
    "test_ocr_generator_noncached_outputs_keep_source_and_run_identity",
    "test_ocr_generator_rejects_impossible_noncached_root_before_provider_work",
]
