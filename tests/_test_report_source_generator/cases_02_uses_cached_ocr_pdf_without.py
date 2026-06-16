# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
    cached_json_path.parent.mkdir(parents=True, exist_ok=True)
    cached_json_path.write_text(json.dumps(cached_payload), encoding="utf-8")
    ocr_calls = {"count": 0}

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

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

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

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

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
            pdf_text_min_density=5.0,
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

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert chunk_paths == [
        str(tmp_path / "report.ocr-pages-0001-0002.pdf"),
        str(tmp_path / "report.ocr-pages-0003-0003.pdf"),
    ]
    assert rendered_pages == [(1, "page 1"), (2, "page 2"), (3, "page 3")]
    assert state.analysis_pdf_path == str(tmp_path / "chunked-ocr.pdf")


def test_prepare_report_source_accepts_blank_trailing_ocr_chunk(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(
        replace(
            ingest_settings,
            pdf_text_ocr_enabled=True,
            pdf_text_ocr_cache_enabled=False,
            pdf_text_ocr_chunk_page_count=2,
            pdf_text_min_density=5.0,
        ),
        run_context,
        tmp_path,
    )
    rendered_pages: list[tuple[int, str]] = []

    def _openai_ocr_pdf(req, ctx):
        if req.pdf_path.endswith("0001-0002.pdf"):
            return SimpleNamespace(
                schema_version="1.0",
                pages=[
                    SimpleNamespace(
                        schema_version="1.0",
                        page_number=1,
                        text="ocr page one",
                    ),
                    SimpleNamespace(
                        schema_version="1.0",
                        page_number=2,
                        text="ocr page two",
                    ),
                ],
                raw_text='{"pages":[{"page_number":1,"text":"ocr page one"},{"page_number":2,"text":"ocr page two"}]}',
                model=req.model,
                request_id="req_chunk_1",
            )
        return SimpleNamespace(
            schema_version="1.0",
            pages=[SimpleNamespace(schema_version="1.0", page_number=1, text="")],
            raw_text='{"pages":[{"page_number":1,"text":""}]}',
            model=req.model,
            request_id="req_blank_chunk",
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
            else (_ for _ in ()).throw(
                AssertionError("OCR validation should use structured OCR pages")
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
        extract_pdf_text=lambda req, ctx: (
            PdfTextExtractResponse(
                schema_version="1.0",
                text="",
                pages_extracted=1,
                char_count=0,
                text_density=0.0,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextExtractResponse(
                schema_version="1.0",
                text="ocr page one\nocr page two",
                pages_extracted=3,
                char_count=25,
                text_density=8.3,
            )
        ),
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert rendered_pages == [(1, "ocr page one"), (2, "ocr page two"), (3, "")]
    assert state.ocr_fallback_used is True
    assert state.analysis_pdf_path == str(tmp_path / "chunked-ocr.pdf")
    assert state.text_validation_status == "pass"
    assert state.text_status["not_available"] is False
    assert "Source page 1" in state.text_response.text


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
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="",
            pages_extracted=1,
            char_count=0,
            text_density=0.0,
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
        prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert_app_error(
        exc_info.value,
        code="pdf_text_ocr_failed",
        retryable=True,
    )
    assert exc_info.value.context["attempted_models"] == [
        runtime.settings.pdf_text_ocr_model,
    ]


__all__ = [
    "test_prepare_report_source_uses_cached_ocr_pdf_without_calling_openai_ocr",
    "test_prepare_report_source_runs_single_openai_ocr_model",
    "test_prepare_report_source_maps_chunk_local_ocr_pages_to_original_page_numbers",
    "test_prepare_report_source_accepts_blank_trailing_ocr_chunk",
    "test_prepare_report_source_surfaces_pdf_text_ocr_failed",
]
