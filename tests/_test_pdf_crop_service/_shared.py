# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_pdf_crop_service.py")

import json

import logging

from pathlib import Path

import time

import pymupdf as fitz

import pytest

from PIL import Image

from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefinePageRenderRequest,
    CropRequest,
    PreviewRequest,
)

from src.contracts.report_models import CropItem

from src.contracts.run_context import RunContext

from src.services._pdf.crop import (
    _dominant_border_color,
    _legacy_chart_border_trim,
    _tighten_chart_crop_rect,
    _tighten_table_crop_rect,
)

from src.services.pdf_service import (
    apply_crop_refine_bbox,
    crop_regions,
    render_page_for_crop_refine,
    render_preview,
)

from src.utils.errors import AppError

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

def _build_basic_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=560)
    page.insert_text((40, 40), "Crop test page", fontsize=14)
    page.draw_rect(
        fitz.Rect(60, 90, 360, 280), color=(0, 0, 0), fill=(0.94, 0.94, 0.94)
    )
    doc.save(path.as_posix())
    doc.close()

def _build_partial_change_pdf(path: Path, *, first_page_label: str, second_page_label: str) -> None:
    doc = fitz.open()
    first_page = doc.new_page(width=420, height=560)
    first_page.insert_text((40, 40), first_page_label, fontsize=14)
    first_page.draw_rect(
        fitz.Rect(60, 90, 360, 280), color=(0, 0, 0), fill=(0.94, 0.94, 0.94)
    )
    second_page = doc.new_page(width=420, height=560)
    second_page.insert_text((40, 40), second_page_label, fontsize=14)
    second_page.draw_rect(
        fitz.Rect(70, 120, 340, 300), color=(0, 0, 0), fill=(0.88, 0.88, 0.88)
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_bottom_body_text(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.draw_rect(
        fitz.Rect(60, 90, 540, 420), color=(0, 0, 0), fill=(0.95, 0.95, 0.95)
    )
    page.insert_text((74, 125), "Figure 1. Synthetic chart", fontsize=16)
    page.insert_text((74, 405), "Source: synthetic data", fontsize=10)
    page.insert_textbox(
        fitz.Rect(60, 445, 540, 730),
        "This paragraph should stay outside the final chart crop. " * 40,
        fontsize=11,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_long_line_crossing_crop_edge(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=800)
    page.draw_rect(
        fitz.Rect(60, 90, 360, 420), color=(0, 0, 0), fill=(0.95, 0.95, 0.95)
    )
    page.insert_text((74, 130), "Figure 1. Edge trimming guard", fontsize=16)
    page.insert_textbox(
        fitz.Rect(255, 200, 690, 235),
        (
            "This is intentionally long body text that crosses the crop edge and should "
            "not trigger a large inward trim of the chart area."
        ),
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_table_note_and_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=820)
    page.draw_rect(
        fitz.Rect(60, 90, 560, 390), color=(0, 0, 0), fill=(0.95, 0.95, 0.95)
    )
    page.insert_text((74, 122), "Table 1. Synthetic projections", fontsize=16)
    page.insert_textbox(
        fitz.Rect(72, 408, 560, 470),
        "Note: Values are shown for illustration only and do not represent real forecasts.",
        fontsize=10,
    )
    page.insert_text((72, 486), "Source: synthetic dataset.", fontsize=10)
    page.insert_text((372, 508), "StatLink https://example.invalid", fontsize=10)
    page.insert_text((72, 560), "Recent Developments", fontsize=20)
    page.insert_textbox(
        fitz.Rect(72, 590, 560, 780),
        "This section must remain outside the strict table crop. " * 32,
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_mid_statlink_and_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=820)
    page.draw_rect(
        fitz.Rect(60, 120, 560, 300), color=(0, 0, 0), fill=(0.95, 0.95, 0.95)
    )
    page.insert_text((74, 152), "Figure 1. Mid-page statlink case", fontsize=14)
    page.insert_text((72, 352), "StatLink https://example.invalid", fontsize=10)
    page.insert_text((72, 430), "Recent Developments", fontsize=20)
    page.insert_textbox(
        fitz.Rect(72, 462, 560, 760),
        "This section must remain outside the strict crop. " * 38,
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_partial_note_overlap(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=820)
    page.draw_rect(
        fitz.Rect(60, 120, 560, 398),
        color=(0, 0, 0),
        fill=(0.95, 0.95, 0.95),
    )
    page.insert_text((74, 152), "Figure 1. Partial note overlap", fontsize=14)
    page.insert_textbox(
        fitz.Rect(72, 395, 560, 455),
        (
            "Notes: This note starts inside the chart bbox and continues below it. "
            "The full note should remain in the strict crop."
        ),
        fontsize=10,
    )
    page.insert_textbox(
        fitz.Rect(72, 500, 560, 760),
        "This section must remain outside the strict crop. " * 24,
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_top_chart_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(65, 116, 540, 176),
        (
            "Given the heterogeneity in regulation trends across states, there are again large "
            "variations between regions. This paragraph should remain outside the saved chart crop."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_text(
        (65, 208),
        "Figure 2.6. Rising regulatory compliance costs have suppressed productivity and business",
        fontsize=18,
    )
    page.insert_text(
        (65, 228),
        "dynamism in the United States over the past decade",
        fontsize=18,
    )
    page.insert_text(
        (65, 256),
        "Estimated contribution of changes in regulation to productivity and business dynamism",
        fontsize=12,
    )
    page.draw_rect(
        fitz.Rect(65, 300, 540, 700),
        color=(0, 0, 0),
        fill=(0.95, 0.95, 0.95),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_internal_heading_card(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=540)
    page.draw_rect(
        fitz.Rect(40, 180, 640, 430),
        color=(0.95, 0.95, 0.95),
        fill=(0.95, 0.95, 0.95),
        width=0.5,
    )
    page.insert_text((178, 212), "Experience over ownership", fontsize=18)
    page.insert_text((72, 268), "44%", fontsize=36)
    page.insert_text(
        (214, 266), "Shoppers want richer in-store experiences", fontsize=16
    )
    page.insert_text(
        (214, 292), "that blend service, entertainment, and value", fontsize=16
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_internal_sentence_card(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=540)
    page.draw_rect(
        fitz.Rect(40, 180, 640, 430),
        color=(0.70, 0.98, 0.52),
        fill=(0.70, 0.98, 0.52),
        width=0.5,
    )
    page.insert_textbox(
        fitz.Rect(186, 212, 564, 254),
        "Consumers are concerned about the lack of clarity in how AI collects and uses their personal data",
        fontsize=14,
    )
    page.insert_text((72, 266), "60%", fontsize=34)
    page.insert_text(
        (214, 294), "marketers should make data collection clearer", fontsize=16
    )
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_bottom_edge_chart_text(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=520, height=620)
    page.draw_rect(
        fitz.Rect(60, 90, 420, 420),
        color=(0.95, 0.80, 0.80),
        fill=(0.95, 0.80, 0.80),
        width=0.5,
    )
    page.insert_text((74, 132), "Impact of subscription auto-renewals", fontsize=18)
    page.insert_text((74, 164), "on consumer trust", fontsize=18)
    page.draw_circle(
        (240, 275), 110, color=(0.10, 0.35, 0.85), fill=(0.10, 0.35, 0.85), width=0.5
    )
    page.draw_circle(
        (240, 275), 64, color=(0.95, 0.80, 0.80), fill=(0.95, 0.80, 0.80), width=0.5
    )
    page.insert_text((184, 382), "Slight", fontsize=14)
    page.insert_text((184, 410), "23%", fontsize=24)
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_table_header_band_and_page_number(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595.276, height=793.701)
    page.insert_text((530, 40), "47 |", fontsize=11)
    page.draw_line((42, 66), (554, 66), color=(0, 0, 0), width=1)
    page.insert_text((220, 78), "Risk factors", fontsize=8)
    page.insert_text((480, 78), "Protective factor", fontsize=8)
    page.insert_text((64, 93), "Country", fontsize=8)
    page.insert_text((128, 93), "Smoking (%)", fontsize=8)
    page.insert_text((205, 93), "Heavy episodic", fontsize=8)
    page.insert_text((292, 93), "Overweight (%)", fontsize=8)
    page.insert_text((378, 93), "Physical inactivity (%)²", fontsize=8)
    page.insert_text((462, 93), "Vegetable consumption (%)", fontsize=8)
    page.insert_text((208, 98), "drinking (%)", fontsize=8)
    for x in [110, 190, 270, 360, 452]:
        page.draw_line((x, 66), (x, 300), color=(0.7, 0.7, 0.7), width=0.5)
    for y in range(108, 300, 22):
        page.draw_line((42, y), (554, y), color=(0.8, 0.8, 0.8), width=0.5)
    page.insert_text((48, 120), "Netherlands", fontsize=8.5)
    page.insert_text((134, 120), "16", fontsize=8.5)
    page.insert_text((174, 120), "11", fontsize=8.5)
    page.insert_text((204, 120), "35", fontsize=8.5)
    page.insert_text((250, 120), "16", fontsize=8.5)
    page.insert_text((303, 120), "51", fontsize=8.5)
    page.insert_text((348, 120), "46", fontsize=8.5)
    page.insert_text((394, 120), "10", fontsize=8.5)
    page.insert_text((440, 120), "13", fontsize=8.5)
    page.insert_text((493, 120), "51", fontsize=8.5)
    page.insert_text((539, 120), "62", fontsize=8.5)
    doc.save(path.as_posix())
    doc.close()

def _build_pdf_with_split_table_title_and_note(path: Path) -> None:
    doc = fitz.open()

    page1 = doc.new_page(width=595.276, height=793.701)
    page1.insert_textbox(
        fitz.Rect(42, 70, 555, 250),
        (
            "3. Men have higher overweight rates in all OECD countries, with gaps largest "
            "in Luxembourg and Germany and smallest in Türkiye and the Netherlands."
        ),
        fontsize=12,
    )
    page1.insert_text(
        (42, 305),
        "Table 2.3. Dashboard on protective and risk factors for health, 2023 (or nearest year)",
        fontsize=14,
    )
    page1.draw_line((42, 322), (555, 322), color=(0, 0, 0), width=1)
    page1.insert_text((220, 340), "Risk factors", fontsize=9)
    page1.insert_text((470, 340), "Protective factor", fontsize=9)
    page1.insert_text((62, 357), "Country", fontsize=8.5)
    page1.insert_text((128, 357), "Smoking (%)", fontsize=8.5)
    page1.insert_text((205, 357), "Heavy episodic", fontsize=8.5)
    page1.insert_text((292, 357), "Overweight (%)", fontsize=8.5)
    page1.insert_text((378, 357), "Physical inactivity (%)", fontsize=8.5)
    page1.insert_text((460, 357), "Vegetable consumption (%)", fontsize=8.5)
    page1.insert_text((208, 370), "drinking (%)", fontsize=8.5)
    for x in [110, 190, 270, 360, 452]:
        page1.draw_line((x, 322), (x, 700), color=(0.75, 0.75, 0.75), width=0.5)
    for y in range(390, 701, 24):
        page1.draw_line((42, y), (555, y), color=(0.8, 0.8, 0.8), width=0.5)
    page1.insert_text((48, 408), "OECD", fontsize=8.5)
    page1.insert_text((140, 408), "19", fontsize=8.5)
    page1.insert_text((176, 408), "11", fontsize=8.5)
    page1.insert_text((214, 408), "34", fontsize=8.5)
    page1.insert_text((250, 408), "20", fontsize=8.5)
    page1.insert_text((303, 408), "61", fontsize=8.5)
    page1.insert_text((348, 408), "48", fontsize=8.5)
    page1.insert_text((394, 408), "27", fontsize=8.5)
    page1.insert_text((440, 408), "32", fontsize=8.5)
    page1.insert_text((493, 408), "53", fontsize=8.5)
    page1.insert_text((539, 408), "64", fontsize=8.5)

    page2 = doc.new_page(width=595.276, height=793.701)
    page2.insert_text((530, 40), "47 |", fontsize=11)
    page2.draw_line((42, 66), (555, 66), color=(0, 0, 0), width=1)
    page2.insert_text((220, 78), "Risk factors", fontsize=9)
    page2.insert_text((470, 78), "Protective factor", fontsize=9)
    page2.insert_text((62, 95), "Country", fontsize=8.5)
    page2.insert_text((128, 95), "Smoking (%)", fontsize=8.5)
    page2.insert_text((205, 95), "Heavy episodic", fontsize=8.5)
    page2.insert_text((292, 95), "Overweight (%)", fontsize=8.5)
    page2.insert_text((378, 95), "Physical inactivity (%)", fontsize=8.5)
    page2.insert_text((460, 95), "Vegetable consumption (%)", fontsize=8.5)
    page2.insert_text((208, 108), "drinking (%)", fontsize=8.5)
    for x in [110, 190, 270, 360, 452]:
        page2.draw_line((x, 66), (x, 290), color=(0.75, 0.75, 0.75), width=0.5)
    for y in range(128, 291, 24):
        page2.draw_line((42, y), (555, y), color=(0.8, 0.8, 0.8), width=0.5)
    page2.insert_text((48, 146), "Netherlands", fontsize=8.5)
    page2.insert_text((140, 146), "16", fontsize=8.5)
    page2.insert_text((176, 146), "11", fontsize=8.5)
    page2.insert_text((214, 146), "35", fontsize=8.5)
    page2.insert_text((250, 146), "16", fontsize=8.5)
    page2.insert_text((303, 146), "51", fontsize=8.5)
    page2.insert_text((348, 146), "46", fontsize=8.5)
    page2.insert_text((394, 146), "10", fontsize=8.5)
    page2.insert_text((440, 146), "13", fontsize=8.5)
    page2.insert_text((493, 146), "51", fontsize=8.5)
    page2.insert_text((539, 146), "62", fontsize=8.5)
    page2.insert_textbox(
        fitz.Rect(42, 305, 555, 450),
        (
            "1. 2019 data. 2. 2020-2022 data. 3. 2024 data.\n"
            "Note: * Accession/partner country. See the weblink to metadata in the Reader's guide.\n"
            "Source: Synthetic OECD Health Statistics."
        ),
        fontsize=10,
        lineheight=1.1,
    )
    page2.insert_textbox(
        fitz.Rect(42, 470, 555, 620),
        "This paragraph must remain outside the saved table crop. " * 12,
        fontsize=12,
    )

    doc.save(path.as_posix())
    doc.close()



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
