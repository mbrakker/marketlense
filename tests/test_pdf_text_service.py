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
from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextSampleRequest
from src.contracts.pdf_utils import PdfEofCheckRequest, PdfInfoRequest
from src.contracts.run_context import RunContext
from src.services.pdf_service import (
    build_pdf_context,
    check_pdf_eof,
    extract_pdf_info,
    extract_pdf_text,
    sample_pdf_text,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


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
