from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_ocr import (
    PdfOcrPageText,
    PdfOcrSplitRequest,
    PdfTextRenderRequest,
)
from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextSampleRequest
from src.contracts.pdf_utils import (
    PdfEofCheckRequest,
    PdfInfoRequest,
    PdfIntegrityCheckRequest,
)
from src.contracts.run_context import RunContext
from src.services.pdf_service import (
    build_pdf_context,
    check_pdf_eof,
    check_pdf_integrity,
    extract_pdf_info,
    extract_pdf_text,
    render_text_pdf,
    sample_pdf_text,
    split_pdf_for_ocr,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _service_events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _build_text_pdf(path: Path) -> None:
    doc = fitz.open()
    first_page = doc.new_page(width=595, height=842)
    first_page.insert_text((72, 72), "Synthetic title page", fontsize=18)
    first_page.insert_textbox(
        fitz.Rect(72, 120, 520, 320),
        "Market Lense synthetic PDF text for extraction coverage. " * 8,
        fontsize=12,
    )
    second_page = doc.new_page(width=595, height=842)
    second_page.insert_text((72, 72), "Second page sample text", fontsize=16)
    second_page.insert_textbox(
        fitz.Rect(72, 120, 520, 320),
        "Second page content keeps sample extraction deterministic. " * 6,
        fontsize=12,
    )
    doc.set_metadata({"title": "Synthetic Title", "author": "Synthetic Author"})
    doc.save(path.as_posix())
    doc.close()


def _build_multi_page_text_pdf(path: Path, page_count: int) -> None:
    doc = fitz.open()
    for page_number in range(1, page_count + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {page_number}", fontsize=18)
        page.insert_textbox(
            fitz.Rect(72, 120, 520, 320),
            f"Synthetic OCR split test content for page {page_number}. " * 6,
            fontsize=12,
        )
    doc.save(path.as_posix())
    doc.close()


def test_integrity_check_accepts_retained_golden_pdf_without_provider_io() -> None:
    pdf_path = (
        Path(__file__).parent
        / "fixtures"
        / "pdf_benchmark"
        / "golden"
        / "CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"
    )

    response = check_pdf_integrity(
        PdfIntegrityCheckRequest(schema_version="1.0", path=str(pdf_path)), _ctx()
    )

    assert response.failure_code == ""
    assert response.retryable is False
    assert response.has_pdf_header is True
    assert response.has_eof is True
    assert response.parser_opened is True
    assert response.page_count > 0
    assert len(response.sha256) == 64
    assert len(response.md5) == 32


def test_pdf_text_service_facade_preserves_contracts_and_logs(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "text.pdf"
    _build_text_pdf(pdf_path)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    context_response = build_pdf_context(
        PdfContextBuildRequest(schema_version="1.0", path=pdf_path.as_posix()),
        _ctx(),
    )
    try:
        eof_response = check_pdf_eof(
            PdfEofCheckRequest(schema_version="1.0", path=pdf_path.as_posix()),
            _ctx(),
        )
        info_response = extract_pdf_info(
            PdfInfoRequest(
                schema_version="1.0",
                path=pdf_path.as_posix(),
                pdf_context=context_response.context,
            ),
            _ctx(),
        )
        text_response = extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=pdf_path.as_posix(),
                max_pages=2,
                max_chars=5_000,
                pdf_context=context_response.context,
            ),
            _ctx(),
        )
        sample_response = sample_pdf_text(
            PdfTextSampleRequest(
                schema_version="1.0",
                path=pdf_path.as_posix(),
                page_indices=[0, 1],
                pdf_context=context_response.context,
            ),
            _ctx(),
        )
    finally:
        context_response.context.close()

    assert context_response.context.fitz_doc is not None
    assert context_response.context.pypdf_reader is not None
    assert eof_response.has_eof is True
    assert info_response.page_count == 2
    assert info_response.metadata["Title"] == "Synthetic Title"
    assert "Market Lense synthetic PDF text" in text_response.text
    assert text_response.pages_extracted == 2
    assert text_response.text_density > 0
    assert sample_response.any_text is True
    assert [sample.page_number for sample in sample_response.samples] == [1, 2]
    assert all(sample.word_count > 0 for sample in sample_response.samples)
    assert all(sample.confidence_score > 0.5 for sample in sample_response.samples)
    assert sample_response.document_confidence_score > 0.5

    for response in (eof_response, info_response, text_response, sample_response):
        assert_no_defaulted_required_fields(response)

    events = _service_events(caplog, "market_lense.pdf_service")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {
        "pdf_context_build_start",
        "pdf_context_build_complete",
        "pdf_eof_check_start",
        "pdf_eof_check_complete",
        "pdf_info_extract_start",
        "pdf_info_extract_complete",
        "pdf_text_extract_start",
        "pdf_text_extract_complete",
        "pdf_text_sample_start",
        "pdf_text_sample_complete",
    }.issubset(event_names)


def test_pdf_text_service_missing_file_raises_typed_error(assert_app_error) -> None:
    missing_path = "C:/definitely-missing/market-lense-missing.pdf"

    with pytest.raises(AppError) as exc_info:
        extract_pdf_info(
            PdfInfoRequest(schema_version="1.0", path=missing_path),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="pdf_not_found",
        retryable=False,
    )


def test_pdf_text_render_roundtrip_produces_extractable_pdf(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    rendered_pdf = tmp_path / "ocr.pdf"
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    render_response = render_text_pdf(
        PdfTextRenderRequest(
            schema_version="1.0",
            output_path=rendered_pdf.as_posix(),
            pages=[
                PdfOcrPageText(page_number=1, text="OCR page one"),
                PdfOcrPageText(page_number=2, text="OCR page two"),
            ],
        ),
        _ctx(),
    )
    extracted = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=render_response.output_path,
            max_pages=2,
            max_chars=2_000,
        ),
        _ctx(),
    )

    assert render_response.rendered_page_count == 2
    assert "OCR page one" in extracted.text
    assert "OCR page two" in extracted.text

    events = _service_events(caplog, "market_lense.pdf_service")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"pdf_text_render_start", "pdf_text_render_complete"}.issubset(event_names)


def test_pdf_ocr_split_creates_page_aligned_chunks(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    source_pdf = tmp_path / "source.pdf"
    _build_multi_page_text_pdf(source_pdf, page_count=5)
    output_dir = tmp_path / "chunks"
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    split_response = split_pdf_for_ocr(
        PdfOcrSplitRequest(
            schema_version="1.0",
            source_pdf_path=source_pdf.as_posix(),
            output_dir=output_dir.as_posix(),
            chunk_page_count=2,
        ),
        _ctx(),
    )

    assert [chunk.page_count for chunk in split_response.chunks] == [2, 2, 1]
    assert [chunk.start_page_number for chunk in split_response.chunks] == [1, 3, 5]
    assert [chunk.end_page_number for chunk in split_response.chunks] == [2, 4, 5]
    for chunk in split_response.chunks:
        chunk_info = extract_pdf_info(
            PdfInfoRequest(schema_version="1.0", path=chunk.chunk_pdf_path),
            _ctx(),
        )
        assert chunk_info.page_count == chunk.page_count

    events = _service_events(caplog, "market_lense.pdf_service")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"pdf_ocr_split_start", "pdf_ocr_split_complete"}.issubset(event_names)
