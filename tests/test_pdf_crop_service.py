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


def test_strict_crop_filenames_do_not_collide_across_table_and_chart_calls(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    table_item = CropItem(
        id="table-1-0",
        type="table",
        score=90.0,
        page=0,
        bbox=(60.0, 90.0, 220.0, 220.0),
    )
    chart_item = CropItem(
        id="chart-1-0",
        type="chart",
        score=91.0,
        page=0,
        bbox=(220.0, 90.0, 360.0, 260.0),
    )

    table_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[table_item],
            subdir="slices",
            mode="table_strict",
        ),
        _ctx(),
    )
    chart_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[chart_item],
            subdir="slices",
            mode="chart_strict",
        ),
        _ctx(),
    )

    assert len(table_resp.paths) == 1
    assert len(chart_resp.paths) == 1
    assert table_resp.paths[0] != chart_resp.paths[0]

    slices_dir = out_dir / "report" / "slices"
    files = sorted(p.name for p in slices_dir.glob("*.png"))
    assert len(files) == 2
    assert "report-table-1-0.png" in files
    assert "report-chart-1-0.png" in files


def test_chart_strict_tightens_partial_bottom_text_spillover(tmp_path):
    pdf_path = tmp_path / "spillover.pdf"
    _build_pdf_with_bottom_body_text(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=95.0,
        page=0,
        bbox=(60.0, 90.0, 540.0, 500.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict",
            pad=0,
            mode="chart_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height > int(legacy_img.height * 0.65)


def test_tighten_chart_crop_rect_reclamps_padded_top_to_caption(tmp_path):
    pdf_path = tmp_path / "top_chart_spillover.pdf"
    _build_pdf_with_top_chart_spillover(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        padded_rect = fitz.Rect(53.2, 178.54, 544.8, 707.04)
        tightened = _tighten_chart_crop_rect(page, padded_rect)
    finally:
        doc.close()

    assert tightened.y0 > 186.0
    assert tightened.y0 < 187.0
    assert tightened.y1 == pytest.approx(padded_rect.y1)


def test_tighten_chart_crop_rect_leaves_plain_chart_without_context_unchanged(tmp_path):
    pdf_path = tmp_path / "plain_chart.pdf"
    _build_basic_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(60.0, 90.0, 360.0, 280.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.x0 == pytest.approx(rect.x0)
    assert tightened.y0 == pytest.approx(rect.y0)
    assert tightened.x1 == pytest.approx(rect.x1)
    assert tightened.y1 == pytest.approx(rect.y1)


def test_tighten_chart_crop_rect_does_not_trim_internal_panel_label_block(tmp_path):
    pdf_path = tmp_path / "internal-panel-side-labels.pdf"
    from tests.test_pdf_figures_service import (
        _build_internal_panel_with_side_labels_pdf,
    )

    _build_internal_panel_with_side_labels_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(70.1, 127.8, 584.6, 472.2)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 <= 130.0
    assert tightened.y1 >= 470.0


def test_tighten_chart_crop_rect_keeps_draw_backed_internal_heading_band(tmp_path):
    pdf_path = tmp_path / "internal-heading-card.pdf"
    _build_pdf_with_internal_heading_card(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(36.0, 188.0, 644.0, 430.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 <= 188.5
    assert tightened.y0 >= 176.0
    assert tightened.y1 == pytest.approx(rect.y1)


def test_tighten_chart_crop_rect_expands_to_fill_top_when_internal_sentence_is_not_heading(
    tmp_path,
):
    pdf_path = tmp_path / "internal-sentence-card.pdf"
    _build_pdf_with_internal_sentence_card(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(36.0, 186.0, 644.0, 430.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 < rect.y0
    assert tightened.y0 <= 180.5
    assert tightened.y0 >= 176.0
    assert tightened.y1 == pytest.approx(rect.y1)


def test_legacy_chart_border_trim_keeps_extra_bottom_padding_for_bottom_edge_text(
    tmp_path,
):
    pdf_path = tmp_path / "bottom-edge-chart-text.pdf"
    _build_pdf_with_bottom_edge_chart_text(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(60.0, 90.0, 420.0, 420.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        trimmed = _legacy_chart_border_trim(page, rect, img)
    finally:
        doc.close()

    bg = _dominant_border_color(trimmed)
    width, height = trimmed.size
    bottommost = -1
    for y in range(height - 1, -1, -1):
        found = False
        for x in range(width):
            px = trimmed.getpixel((x, y))
            if any(abs(px[i] - bg[i]) > 8 for i in range(3)):
                bottommost = y
                found = True
                break
        if found:
            break

    assert bottommost >= 0
    assert height - 1 - bottommost >= 16


def test_tighten_table_crop_rect_trims_top_page_number_but_keeps_header_band(tmp_path):
    pdf_path = tmp_path / "table_header_page_number.pdf"
    _build_pdf_with_table_header_band_and_page_number(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        padded_rect = fitz.Rect(0.0, 54.8, 595.0, 300.0)
        tightened = _tighten_table_crop_rect(page, padded_rect)
    finally:
        doc.close()

    assert tightened.y0 > 53.4
    assert tightened.y0 < 61.0
    assert tightened.y1 == pytest.approx(padded_rect.y1)


def test_table_crop_regions_stitch_split_table_title_and_note_for_adjacent_pages(
    tmp_path,
):
    pdf_path = tmp_path / "split_table_pair.pdf"
    _build_pdf_with_split_table_title_and_note(pdf_path)
    out_dir = tmp_path / "out"
    first = CropItem(
        id="table-47-0",
        type="table",
        score=90.0,
        page=0,
        bbox=(0.0, 291.0, 595.0, 724.0),
    )
    second = CropItem(
        id="table-48-0",
        type="table",
        score=91.0,
        page=1,
        bbox=(0.0, 54.8, 595.0, 431.0),
    )

    first_only = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="single-first",
            items=[first],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    second_only = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="single-second",
            items=[second],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    paired = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="paired",
            items=[first, second],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )

    first_single_path = out_dir / first_only.paths[0]
    second_single_path = out_dir / second_only.paths[0]
    paired_first_path = out_dir / paired.paths[0]
    paired_second_path = out_dir / paired.paths[1]
    with (
        Image.open(first_single_path) as first_single,
        Image.open(second_single_path) as second_single,
        Image.open(paired_first_path) as paired_first,
        Image.open(paired_second_path) as paired_second,
    ):
        assert paired_first.height > first_single.height + 80
        assert paired_second.height > second_single.height + 20
        assert paired_first.width >= first_single.width
        assert paired_second.width >= second_single.width


def test_table_strict_clamps_after_note_and_avoids_section_spillover(tmp_path):
    pdf_path = tmp_path / "table_spillover.pdf"
    _build_pdf_with_table_note_and_spillover(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="table-0-0",
        type="table",
        score=96.0,
        page=0,
        bbox=(60.0, 90.0, 560.0, 740.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_table",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_table",
            pad=0,
            mode="table_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height < 940
        assert strict_img.height > 760


def test_table_strict_detects_mid_statlink_for_bottom_clamp(tmp_path):
    pdf_path = tmp_path / "table_mid_statlink.pdf"
    _build_pdf_with_mid_statlink_and_spillover(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="table-0-1",
        type="table",
        score=92.0,
        page=0,
        bbox=(60.0, 120.0, 560.0, 760.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_mid_statlink",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_mid_statlink",
            pad=0,
            mode="table_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height < 620
        assert strict_img.height > 420


def test_chart_strict_keeps_note_that_crosses_bbox_bottom(tmp_path):
    pdf_path = tmp_path / "chart_partial_note_overlap.pdf"
    _build_pdf_with_partial_note_overlap(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-1",
        type="chart",
        score=92.0,
        page=0,
        bbox=(60.0, 120.0, 560.0, 405.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_partial_note",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_partial_note",
            pad=0,
            mode="chart_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height > legacy_img.height
        assert strict_img.height < 760


def test_render_preview_and_crop_refine_page_render_create_assets(tmp_path):
    pdf_path = tmp_path / "preview.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    preview_response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )
    page_render_response = render_page_for_crop_refine(
        CropRefinePageRenderRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page=0,
            dpi=110,
        ),
        _ctx(),
    )

    assert preview_response.schema_version == "1.1"
    assert preview_response.image_path == "report/assets/report-contents.png"
    assert (out_dir / preview_response.image_path).exists()

    assert page_render_response.page == 0
    assert page_render_response.image_width > 0
    assert page_render_response.image_height > 0
    assert page_render_response.scale_x > 0
    assert page_render_response.scale_y > 0
    assert (out_dir / page_render_response.image_path).exists()


def test_apply_crop_refine_bbox_clamps_to_page_bounds(tmp_path):
    pdf_path = tmp_path / "bbox.pdf"
    _build_basic_pdf(pdf_path)

    response = apply_crop_refine_bbox(
        CropRefineBBoxApplyRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            page=0,
            bbox=(-30.0, -25.0, 500.0, 700.0),
        ),
        _ctx(),
    )

    x0, y0, x1, y1 = response.bbox
    assert response.page == 0
    assert 0.0 <= x0 < x1 <= 420.0
    assert 0.0 <= y0 < y1 <= 560.0


def test_apply_crop_refine_bbox_rejects_page_out_of_range(tmp_path, assert_app_error):
    pdf_path = tmp_path / "bbox_oob.pdf"
    _build_basic_pdf(pdf_path)

    with pytest.raises(AppError) as exc_info:
        apply_crop_refine_bbox(
            CropRefineBBoxApplyRequest(
                schema_version="1.0",
                pdf_path=pdf_path.as_posix(),
                page=3,
                bbox=(10.0, 10.0, 40.0, 40.0),
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="crop_refine_page_out_of_range",
        retryable=False,
    )


def test_apply_crop_refine_bbox_does_not_over_trim_for_long_crossing_text(tmp_path):
    pdf_path = tmp_path / "edge-trim-guard.pdf"
    _build_pdf_with_long_line_crossing_crop_edge(pdf_path)
    response = apply_crop_refine_bbox(
        CropRefineBBoxApplyRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            page=0,
            bbox=(60.0, 90.0, 360.0, 420.0),
        ),
        _ctx(),
    )

    assert response.bbox[2] >= 348.0


def test_crop_and_preview_sanitize_report_and_subdir_segments(tmp_path):
    pdf_path = tmp_path / "preview_escape.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=90.0,
        page=0,
        bbox=(60.0, 90.0, 220.0, 220.0),
    )

    crop_response = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="../escape",
            items=[item],
            subdir="../slices",
            mode="legacy",
        ),
        _ctx(),
    )
    preview_response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="../escape",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )

    assert crop_response.paths == ["escape/slices/escape-chart-0-0.png"]
    assert preview_response.image_path == "escape/assets/escape-contents.png"
    assert (out_dir / crop_response.paths[0]).exists()
    assert (out_dir / preview_response.image_path).exists()


def test_render_preview_reuses_fingerprint_cache_on_partial_change_rerun(
    tmp_path, caplog
) -> None:
    pdf_v1 = tmp_path / "preview-v1.pdf"
    pdf_v2 = tmp_path / "preview-v2.pdf"
    out_dir = tmp_path / "out"
    _build_partial_change_pdf(
        pdf_v1,
        first_page_label="Stable first page",
        second_page_label="Original second page",
    )
    _build_partial_change_pdf(
        pdf_v2,
        first_page_label="Stable first page",
        second_page_label="Updated second page",
    )

    first = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_v1.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )
    artifact_path = out_dir / first.image_path
    first_mtime = artifact_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.preview")
    second = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_v2.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )

    assert second.image_path == first.image_path
    assert artifact_path.stat().st_mtime_ns == first_mtime
    events = _events(caplog, "market_lense.pdf_service.preview")
    assert any(event.get("event") == "preview_render_cache_hit" for event in events)


def test_render_page_for_crop_refine_invalidates_stale_artifact_version(
    tmp_path, caplog
) -> None:
    pdf_path = tmp_path / "refine.pdf"
    out_dir = tmp_path / "out"
    _build_basic_pdf(pdf_path)

    first = render_page_for_crop_refine(
        CropRefinePageRenderRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page=0,
            dpi=110,
        ),
        _ctx(),
    )
    artifact_path = out_dir / first.image_path
    sidecar_path = artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    payload["artifact_version"] = "0.0"
    sidecar_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    time.sleep(0.02)
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = render_page_for_crop_refine(
        CropRefinePageRenderRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page=0,
            dpi=110,
        ),
        _ctx(),
    )

    assert second.image_path == first.image_path
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_refine_page_render_cache_store"
        and isinstance(event.get("fields"), dict)
        and event["fields"].get("validity_reason") == "version_changed"
        for event in events
    )


def test_crop_regions_reuses_fingerprint_cache_on_partial_change_rerun(
    tmp_path, caplog
) -> None:
    pdf_v1 = tmp_path / "crop-v1.pdf"
    pdf_v2 = tmp_path / "crop-v2.pdf"
    out_dir = tmp_path / "out"
    _build_partial_change_pdf(
        pdf_v1,
        first_page_label="Stable chart page",
        second_page_label="Original trailing page",
    )
    _build_partial_change_pdf(
        pdf_v2,
        first_page_label="Stable chart page",
        second_page_label="Updated trailing page",
    )
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=91.0,
        page=0,
        bbox=(60.0, 90.0, 360.0, 280.0),
    )

    first = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_v1.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="slices",
            mode="legacy",
        ),
        _ctx(),
    )
    artifact_path = out_dir / first.paths[0]
    first_mtime = artifact_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_v2.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="slices",
            mode="legacy",
        ),
        _ctx(),
    )

    assert second.paths == first.paths
    assert artifact_path.stat().st_mtime_ns == first_mtime
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(event.get("event") == "crop_region_cache_hit" for event in events)
