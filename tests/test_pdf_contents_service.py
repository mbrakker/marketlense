from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from src.contracts.pdf_contents import PdfContentsDetectionRequest
from src.contracts.run_context import RunContext
from src.services.pdf_service import detect_contents_page
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.pdf_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _build_contents_pdf(path: Path, *, include_contents: bool) -> None:
    doc = fitz.open()
    for page_index in range(4):
        page = doc.new_page(width=595, height=842)
        if include_contents and page_index == 1:
            page.insert_text((72, 72), "Table of Contents", fontsize=18)
            page.insert_textbox(
                fitz.Rect(72, 120, 520, 360),
                "\n".join(
                    [
                        "1. Executive summary ............ 3",
                        "2. Market outlook ............... 5",
                        "3. Key findings ................. 9",
                        "4. Methodology .................. 12",
                    ]
                ),
                fontsize=12,
            )
        else:
            page.insert_text((72, 72), f"Body page {page_index + 1}", fontsize=16)
            page.insert_textbox(
                fitz.Rect(72, 120, 520, 420),
                "Narrative body text for table scanning coverage. " * 20,
                fontsize=11,
            )
    doc.save(path.as_posix())
    doc.close()


def test_detect_contents_page_matches_expected_page(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "with_contents.pdf"
    _build_contents_pdf(pdf_path, include_contents=True)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")

    response = detect_contents_page(
        PdfContentsDetectionRequest(
            schema_version="1.0",
            path=pdf_path.as_posix(),
            max_pages=4,
            min_headings=3,
            keywords=["table of contents", "contents", "index"],
        ),
        _ctx(),
    )

    assert response.has_contents is True
    assert response.page_index == 1
    assert response.page_number == 2
    assert response.heading == "table of contents"
    assert response.confidence >= 0.8
    assert_no_defaulted_required_fields(response)

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"pdf_contents_detect_start", "pdf_contents_detect_complete"} <= event_names


def test_detect_contents_page_returns_empty_when_not_found(tmp_path) -> None:
    pdf_path = tmp_path / "without_contents.pdf"
    _build_contents_pdf(pdf_path, include_contents=False)

    response = detect_contents_page(
        PdfContentsDetectionRequest(
            schema_version="1.0",
            path=pdf_path.as_posix(),
            max_pages=3,
            min_headings=3,
            keywords=["table of contents", "contents", "index"],
        ),
        _ctx(),
    )

    assert response.has_contents is False
    assert response.page_index == -1
    assert response.page_number == 0
    assert response.heading == ""
    assert response.confidence == 0.0


def test_detect_contents_page_missing_file_raises_typed_error(assert_app_error) -> None:
    with pytest.raises(AppError) as exc_info:
        detect_contents_page(
            PdfContentsDetectionRequest(
                schema_version="1.0",
                path="C:/definitely-missing/contents.pdf",
                max_pages=3,
                min_headings=3,
                keywords=["contents"],
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="pdf_not_found", retryable=False)
