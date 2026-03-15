from __future__ import annotations

import io
import json
import logging
from pathlib import Path

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from PIL import Image, ImageDraw

from src.contracts.report_assets import ExtractCandidatesRequest, FigureExtractRequest
from src.contracts.run_context import RunContext
from src.services.pdf_service import collect_candidates, extract_best_figure


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _chart_image_bytes() -> bytes:
    image = Image.new("RGB", (480, 240), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 440, 200), outline="black", fill=(220, 230, 245))
    draw.text((60, 60), "Figure 1. Growth by quarter", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_candidates_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((72, 72), "Executive summary", fontsize=18)
    page.insert_image(fitz.Rect(70, 120, 550, 360), stream=_chart_image_bytes())
    page.insert_text((74, 382), "Figure 1. Synthetic chart", fontsize=14)
    page.insert_text((74, 402), "Source: synthetic data", fontsize=10)

    x0, y0, x1, y1 = 60, 480, 560, 780
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [180, 320, 450]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [540, 600, 660, 720]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))
    page.insert_text((72, 500), "Table 1. Synthetic projections", fontsize=14)
    for row, y in enumerate([560, 620, 680, 740], start=1):
        page.insert_text((80, y), f"R{row}", fontsize=11)
        page.insert_text((200, y), str(row * 10), fontsize=11)
        page.insert_text((340, y), str(row * 20), fontsize=11)
        page.insert_text((470, y), str(row * 30), fontsize=11)

    doc.save(path.as_posix())
    doc.close()


def test_collect_candidates_returns_chart_and_table_contracts(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "candidates.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.candidates
    kinds = {candidate.kind for candidate in response.candidates}
    assert "chart" in kinds
    assert "table" in kinds
    assert_no_defaulted_required_fields(response)
    for candidate in response.candidates:
        assert_no_defaulted_required_fields(candidate)

    events = _events(caplog, "market_lense.pdf_service.candidate_extraction")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"extract_candidates_start", "extract_candidates_complete"} <= event_names


def test_extract_best_figure_writes_asset_and_logs(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "figure.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.figure")

    response = extract_best_figure(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.image_path == "report/assets/report.png"
    assert response.caption == "Figure 1. Synthetic chart"
    assert response.page == 0
    assert (out_dir / response.image_path).exists()
    assert_no_defaulted_required_fields(response)

    events = _events(caplog, "market_lense.pdf_service.figure")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"figure_extract_start", "figure_extract_complete"} <= event_names
