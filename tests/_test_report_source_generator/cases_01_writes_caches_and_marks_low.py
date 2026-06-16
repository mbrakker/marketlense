# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
        write_json_object_cache=lambda req, ctx: writes.append(req.path) or None,
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert state.text_validation_status == "fail"
    assert state.text_validation_reason == "text_density_below_threshold"
    assert state.payload._text_not_available is True
    assert state.text_status["ocr_recommended"] is True
    assert any("pdf_info_" in path for path in writes)
    assert any("contents_" in path for path in writes)
    assert any("text_" in path for path in writes)


def test_prepare_report_source_uses_cached_source_phase_payloads(
    ingest_settings, run_context, tmp_path
):
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    cache_root = Path(runtime.settings.cache_dir) / "pdf_cache" / str(runtime.md5)
    cache_root.mkdir(parents=True, exist_ok=True)

    info_key = pdf_info_cache_key(str(runtime.md5))
    contents_key = contents_cache_key(str(runtime.md5), runtime.settings)
    text_key = text_cache_key(str(runtime.md5), runtime.settings)

    (cache_root / f"pdf_info_{info_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": info_key,
                "page_count": 7,
                "metadata": {"Author": "Cached"},
            }
        ),
        encoding="utf-8",
    )
    (cache_root / f"contents_{contents_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": contents_key,
                "has_contents": False,
                "page_index": -1,
                "page_number": 0,
                "heading": "",
                "confidence": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (cache_root / f"text_{text_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": text_key,
                "text": "cached body",
                "pages_extracted": 2,
                "char_count": 11,
                "text_density": 5.5,
            }
        ),
        encoding="utf-8",
    )

    deps = _deps(
        extract_pdf_info=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("extract_pdf_info should be skipped on cache hit")
        ),
        detect_contents_page=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("detect_contents_page should be skipped on cache hit")
        ),
        extract_pdf_text=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("extract_pdf_text should be skipped on cache hit")
        ),
        write_json_object_cache=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("cache write should be skipped on cache hit")
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(
                    page_index=0,
                    page_number=1,
                    char_count=14,
                    has_text=True,
                )
            ],
            any_text=True,
        ),
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert state.info_response.page_count == 7
    assert state.info_response.metadata == {"Author": "Cached"}
    assert state.contents_page_number == 0
    assert state.text_response.text == "cached body"
    assert state.text_response.pages_extracted == 2
    assert state.text_response.char_count == 11


def test_prepare_report_source_ignores_stale_source_cache_keys(
    ingest_settings, run_context, tmp_path
):
    writes: list[str] = []
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    cache_root = Path(runtime.settings.cache_dir) / "pdf_cache" / str(runtime.md5)
    cache_root.mkdir(parents=True, exist_ok=True)

    info_key = pdf_info_cache_key(str(runtime.md5))
    contents_key = contents_cache_key(str(runtime.md5), runtime.settings)
    text_key = text_cache_key(str(runtime.md5), runtime.settings)

    (cache_root / f"pdf_info_{info_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": "stale-info",
                "page_count": 99,
                "metadata": {"Author": "Stale"},
            }
        ),
        encoding="utf-8",
    )
    (cache_root / f"contents_{contents_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": "stale-contents",
                "has_contents": True,
                "page_index": 4,
                "page_number": 5,
                "heading": "Stale contents",
                "confidence": 0.9,
            }
        ),
        encoding="utf-8",
    )
    (cache_root / f"text_{text_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "key": "stale-text",
                "text": "stale body",
                "pages_extracted": 9,
                "char_count": 999,
                "text_density": 99.0,
            }
        ),
        encoding="utf-8",
    )

    calls = {"info": 0, "contents": 0, "text": 0}

    deps = _deps(
        extract_pdf_info=lambda req, ctx: (
            calls.__setitem__("info", calls["info"] + 1)
            or PdfInfoResponse(
                schema_version="1.0",
                path=req.path,
                page_count=3,
                metadata={"Author": "Fresh"},
            )
        ),
        detect_contents_page=lambda req, ctx: (
            calls.__setitem__("contents", calls["contents"] + 1)
            or SimpleNamespace(
                schema_version="1.0",
                path=req.path,
                has_contents=False,
                page_index=-1,
                page_number=0,
                heading="",
                confidence=0.0,
            )
        ),
        extract_pdf_text=lambda req, ctx: (
            calls.__setitem__("text", calls["text"] + 1)
            or PdfTextExtractResponse(
                schema_version="1.0",
                text="fresh body",
                pages_extracted=1,
                char_count=10,
                text_density=10.0,
            )
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
        write_json_object_cache=lambda req, ctx: writes.append(req.path) or None,
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert calls == {"info": 1, "contents": 1, "text": 1}
    assert state.info_response.page_count == 3
    assert state.info_response.metadata == {"Author": "Fresh"}
    assert state.text_response.text == "fresh body"
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
        prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

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
        prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

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
        replace(
            ingest_settings, pdf_text_ocr_enabled=True, pdf_text_ocr_cache_enabled=False
        ),
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
                PdfTextSample(
                    page_index=0,
                    page_number=1,
                    char_count=120,
                    has_text=True,
                    word_count=18,
                    confidence_score=0.92,
                )
            ],
            any_text=True,
            document_confidence_score=0.92,
        ),
        extract_pdf_text=lambda req, ctx: PdfTextExtractResponse(
            schema_version="1.0",
            text="native text",
            pages_extracted=1,
            char_count=180,
            text_density=420.0,
        ),
        openai_ocr_pdf=lambda req, ctx: ocr_calls.__setitem__(
            "count", ocr_calls["count"] + 1
        ),
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert state.ocr_fallback_used is False
    assert state.analysis_pdf_path == runtime.local_pdf_path
    assert ocr_calls["count"] == 0


def test_prepare_report_source_uses_ocr_for_weak_native_text_even_when_any_text_exists(
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
    ocr_calls = {"count": 0}
    deps = _deps(
        extract_pdf_info=lambda req, ctx: PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=2,
            metadata={},
        ),
        sample_pdf_text=lambda req, ctx: (
            PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0,
                        page_number=1,
                        char_count=14,
                        has_text=True,
                        word_count=2,
                        confidence_score=0.18,
                    )
                ],
                any_text=True,
                document_confidence_score=0.18,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0,
                        page_number=1,
                        char_count=120,
                        has_text=True,
                        word_count=18,
                        confidence_score=0.9,
                    )
                ],
                any_text=True,
                document_confidence_score=0.9,
            )
        ),
        extract_pdf_text=lambda req, ctx: (
            PdfTextExtractResponse(
                schema_version="1.0",
                text="tiny native",
                pages_extracted=1,
                char_count=11,
                text_density=18.0,
            )
            if req.path == runtime.local_pdf_path
            else PdfTextExtractResponse(
                schema_version="1.0",
                text="ocr recovered text",
                pages_extracted=2,
                char_count=220,
                text_density=320.0,
            )
        ),
        openai_ocr_pdf=lambda req, ctx: (
            ocr_calls.__setitem__("count", ocr_calls["count"] + 1)
            or SimpleNamespace(
                schema_version="1.0",
                pages=[
                    SimpleNamespace(
                        schema_version="1.0",
                        page_number=1,
                        text="ocr recovered text",
                    ),
                    SimpleNamespace(
                        schema_version="1.0",
                        page_number=2,
                        text="ocr recovered text two",
                    ),
                ],
                raw_text='{"pages":[{"page_number":1,"text":"ocr recovered text"},{"page_number":2,"text":"ocr recovered text two"}]}',
                model=req.model,
                request_id="req_weak_native",
            )
        ),
        render_text_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            output_path=str(tmp_path / "weak-native-ocr.pdf"),
            rendered_page_count=len(req.pages),
        ),
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert state.ocr_fallback_used is True
    assert state.text_status["ocr_recommendation_reason"] in {
        "native_page_confidence_below_threshold",
        "native_text_confidence_below_threshold",
        "text_density_below_threshold",
    }
    assert float(state.text_status["native_confidence_score"]) < float(
        runtime.settings.pdf_text_native_confidence_threshold
    )
    assert ocr_calls["count"] == 1


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

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert state.ocr_fallback_used is True
    assert state.analysis_pdf_path == ocr_pdf_path
    assert state.ocr_pdf_path == ocr_pdf_path
    assert detect_paths == [ocr_pdf_path]
    assert extract_paths == [runtime.local_pdf_path, ocr_pdf_path]
    assert preview_paths == [runtime.local_pdf_path]


__all__ = [
    "test_prepare_report_source_writes_caches_and_marks_low_density",
    "test_prepare_report_source_uses_cached_source_phase_payloads",
    "test_prepare_report_source_ignores_stale_source_cache_keys",
    "test_prepare_report_source_halts_when_no_pages_to_sample",
    "test_prepare_report_source_halts_when_sample_pages_have_no_text",
    "test_prepare_report_source_does_not_call_ocr_when_native_text_is_extractable",
    "test_prepare_report_source_uses_ocr_for_weak_native_text_even_when_any_text_exists",
    "test_prepare_report_source_uses_ocr_fallback_and_keeps_original_preview_source",
]
