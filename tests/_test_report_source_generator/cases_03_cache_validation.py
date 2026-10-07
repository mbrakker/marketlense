# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("case", "overrides", "legacy_without_pages"),
    [
        pytest.param(
            "negative_pages", {"pages_extracted": -1}, False, id="negative-pages"
        ),
        pytest.param("negative_chars", {"char_count": -1}, False, id="negative-chars"),
        pytest.param(
            "nonfinite_density", {"text_density": float("nan")}, False, id="nan-density"
        ),
        pytest.param(
            "infinite_density",
            {"text_density": float("inf")},
            False,
            id="infinite-density",
        ),
        pytest.param(
            "mismatched_char_count", {"char_count": 10}, False, id="char-count-mismatch"
        ),
        pytest.param(
            "duplicate_pages",
            {
                "pages": [
                    {"page_number": 1, "text": "first"},
                    {"page_number": 1, "text": "again"},
                ]
            },
            False,
            id="duplicate-pages",
        ),
        pytest.param(
            "negative_page",
            {
                "pages": [
                    {"page_number": 0, "text": "invalid"},
                    {"page_number": 2, "text": "valid"},
                ]
            },
            False,
            id="nonpositive-page",
        ),
        pytest.param(
            "out_of_range_page",
            {
                "pages": [
                    {"page_number": 1, "text": "valid"},
                    {"page_number": 4, "text": "outside source"},
                ]
            },
            False,
            id="page-outside-source",
        ),
        pytest.param(
            "unordered_pages",
            {
                "pages": [
                    {"page_number": 2, "text": "second"},
                    {"page_number": 1, "text": "first"},
                ]
            },
            False,
            id="unordered-pages",
        ),
        pytest.param(
            "malformed_page",
            {"pages": [{"page_number": 1, "text": "valid"}, "not-a-page"]},
            False,
            id="malformed-page-object",
        ),
        pytest.param(
            "page_count_mismatch",
            {"pages_extracted": 1},
            False,
            id="page-count-mismatch",
        ),
        pytest.param(
            "legacy_missing_pages",
            {"schema_version": "1.0"},
            True,
            id="legacy-without-pages",
        ),
    ],
)
def test_prepare_report_source_regenerates_inconsistent_text_cache(
    ingest_settings,
    run_context,
    tmp_path,
    case,
    overrides,
    legacy_without_pages,
):
    runtime = _runtime(
        replace(ingest_settings, pdf_text_min_density=1.0),
        run_context,
        tmp_path,
    )
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
                "page_count": 3,
                "metadata": {},
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
    cached_text_payload = {
        "schema_version": "2.0",
        "key": text_key,
        "text": "cached body",
        "pages_extracted": 2,
        "char_count": len("cached body"),
        "text_density": 5.5,
        "pages": [
            {"page_number": 1, "text": "cached"},
            {"page_number": 2, "text": "body"},
        ],
    }
    cached_text_payload.update(overrides)
    if legacy_without_pages:
        cached_text_payload.pop("pages")
    (cache_root / f"text_{text_key}.json").write_text(
        json.dumps(cached_text_payload),
        encoding="utf-8",
    )

    extract_calls: list[str] = []
    fresh_response = PdfTextExtractResponse(
        schema_version="1.0",
        text="fresh text",
        pages_extracted=2,
        char_count=len("fresh text"),
        text_density=5.0,
        pages=[
            PdfTextPage(page_number=1, text="fresh"),
            PdfTextPage(page_number=2, text="text"),
        ],
    )
    deps = _deps(
        extract_pdf_info=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("valid PDF-info cache should be reused")
        ),
        detect_contents_page=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("valid contents cache should be reused")
        ),
        extract_pdf_text=lambda req, ctx: (
            extract_calls.append(req.path) or fresh_response
        ),
        sample_pdf_text=lambda req, ctx: PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(
                    page_index=0,
                    page_number=1,
                    char_count=5,
                    has_text=True,
                    word_count=1,
                    confidence_score=1.0,
                )
            ],
            any_text=True,
        ),
    )

    state = prepare_report_source(runtime, deps, ocr_openai_client=_ocr_client(deps))

    assert extract_calls == [runtime.local_pdf_path], case
    assert state.text_response.text == "fresh text"
    assert [(page.page_number, page.text) for page in state.text_response.pages] == [
        (1, "fresh"),
        (2, "text"),
    ]
    rewritten = json.loads(
        (cache_root / f"text_{text_key}.json").read_text(encoding="utf-8")
    )
    assert rewritten["schema_version"] == "2.0"
    assert rewritten["pages_extracted"] == 2


@pytest.mark.parametrize(
    ("phase", "overrides"),
    [
        pytest.param("pdf_info", {"page_count": -1}, id="negative-pdf-page-count"),
        pytest.param("pdf_info", {"page_count": 3.0}, id="noninteger-pdf-page-count"),
        pytest.param("contents", {"confidence": float("nan")}, id="nan-confidence"),
        pytest.param("contents", {"confidence": 1.01}, id="confidence-over-one"),
        pytest.param(
            "contents",
            {"has_contents": True, "page_index": 3, "page_number": 4},
            id="contents-outside-source",
        ),
        pytest.param(
            "contents",
            {"has_contents": True, "page_index": 0, "page_number": 2},
            id="contents-page-mismatch",
        ),
        pytest.param(
            "contents",
            {"has_contents": False, "page_index": 0, "page_number": 1},
            id="invalid-not-found-sentinel",
        ),
    ],
)
def test_prepare_report_source_regenerates_invalid_pdf_metadata_cache(
    ingest_settings,
    run_context,
    tmp_path,
    phase,
    overrides,
):
    runtime = _runtime(ingest_settings, run_context, tmp_path)
    cache_root = Path(runtime.settings.cache_dir) / "pdf_cache" / str(runtime.md5)
    cache_root.mkdir(parents=True, exist_ok=True)
    info_key = pdf_info_cache_key(str(runtime.md5))
    contents_key = contents_cache_key(str(runtime.md5), runtime.settings)
    text_key = text_cache_key(str(runtime.md5), runtime.settings)
    info_payload = {
        "schema_version": "1.0",
        "key": info_key,
        "page_count": 3,
        "metadata": {},
    }
    contents_payload = {
        "schema_version": "1.0",
        "key": contents_key,
        "has_contents": False,
        "page_index": -1,
        "page_number": 0,
        "heading": "",
        "confidence": 0.0,
    }
    if phase == "pdf_info":
        info_payload.update(overrides)
    else:
        contents_payload.update(overrides)
    (cache_root / f"pdf_info_{info_key}.json").write_text(
        json.dumps(info_payload),
        encoding="utf-8",
    )
    (cache_root / f"contents_{contents_key}.json").write_text(
        json.dumps(contents_payload),
        encoding="utf-8",
    )
    (cache_root / f"text_{text_key}.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "key": text_key,
                "text": "cached body",
                "pages_extracted": 2,
                "char_count": len("cached body"),
                "text_density": 5.5,
                "pages": [
                    {"page_number": 1, "text": "cached"},
                    {"page_number": 2, "text": "body"},
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = {"pdf_info": 0, "contents": 0}

    def _extract_pdf_info(req, ctx):
        calls["pdf_info"] += 1
        return PdfInfoResponse(
            schema_version="1.0",
            path=req.path,
            page_count=3,
            metadata={},
        )

    def _detect_contents_page(req, ctx):
        calls["contents"] += 1
        return SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            has_contents=False,
            page_index=-1,
            page_number=0,
            heading="",
            confidence=0.0,
        )

    deps = _deps(
        extract_pdf_info=_extract_pdf_info,
        detect_contents_page=_detect_contents_page,
        extract_pdf_text=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("valid text cache should be reused")
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

    assert calls["pdf_info"] == (1 if phase == "pdf_info" else 0)
    assert calls["contents"] == (1 if phase == "contents" else 0)
    assert state.info_response.page_count == 3
    assert state.contents_page_number == 0


__all__ = [
    "test_prepare_report_source_regenerates_inconsistent_text_cache",
    "test_prepare_report_source_regenerates_invalid_pdf_metadata_cache",
]
