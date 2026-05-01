from __future__ import annotations

import io

import json

import logging

from pathlib import Path

from typing import Any, cast

from PIL import Image, ImageDraw

from src.contracts.candidates import Candidate, CandidateFeatures

from src.contracts.pdf_context import PdfContextBuildRequest

from src.contracts.report_assets import ExtractCandidatesRequest, FigureExtractRequest

from src.contracts.report_assets import CropRequest

from src.contracts.report_models import CropItem

from src.contracts.run_context import RunContext

from src.services._pdf.figures import (
    _ChartRect,
    _TableCandidate,
    _chart_axis_label_band_like,
    _clamp_panel_rect_to_dominant_fill_rect,
    _clamp_top_to_caption,
    _dedupe_table_candidates,
    _extend_chart_rect_with_adjacent_drawings,
    _extend_panel_rect_with_nearby_label_blocks,
    _extend_with_adjacent_text_blocks,
    _expand_table_bbox,
    _extend_panel_with_adjacent_text_blocks,
    _final_chart_candidate_looks_forecast_table,
    _final_chart_header_reanchor_line,
    _final_chart_candidate_looks_heading_slice,
    _has_figure_context_hint,
    _panel_chart_has_compact_stat_card_signal,
    _panel_chart_has_data_signal,
    _panel_candidate_shadowed_by_heading_candidate,
    _panel_candidate_shadowed_by_larger_panel,
    _panel_component_looks_like_guidance_card,
    _panel_label_block_looks_like_footer_banner,
    _panel_chart_rects,
    _panel_preferred_local_title_line,
    _panel_stacked_bottom_clip_y,
    _panel_should_clamp_to_internal_caption,
    _panel_title_looks_short_proper_name,
    _panel_title_slice_bounds,
    _plan_candidate_pages,
    _prune_charts_overlapping_ranked_tables,
    _validate_table_candidate,
)

from src.services._pdf.page_artifacts import create_page_artifact_cache

from src.services._pdf.visual_candidates import (
    _RasterProbeCache,
    _embedded_visual_looks_chart_like,
    _page_has_chart_caption_blocks,
    _text_has_visual_context_hint,
    _visual_probe_profile,
    _visual_candidate_looks_bare_heading_fragment,
    _visual_candidate_looks_cover_art,
    _visual_candidate_looks_inline_numbered_panel,
    _visual_candidate_looks_narrative_panel_card,
    _visual_candidate_looks_note_fragment,
    _visual_candidate_looks_reference_or_prose,
    _visual_candidate_looks_section_opener_banner,
    _visual_candidate_looks_table_like,
    _visual_text_dense_recovery_allowed,
)

from src.services.pdf_service import (
    build_pdf_context,
    collect_candidates,
    crop_regions,
    extract_best_figure,
)

from src.utils.errors import AppError

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

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

def _scan_image_bytes() -> bytes:
    image = Image.new("RGB", (620, 900), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 120, 540, 780), outline="black", fill=(235, 235, 235))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()

def _photo_panel_image_bytes() -> bytes:
    image = Image.new("RGB", (520, 360), color=(28, 188, 203))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 70, 330, 290), fill=(219, 180, 150))
    draw.ellipse((178, 120, 232, 174), fill=(255, 255, 255))
    draw.ellipse((248, 120, 302, 174), fill=(255, 255, 255))
    draw.rectangle((152, 244, 308, 352), fill=(96, 140, 188))
    draw.rectangle((0, 292, 520, 360), fill=(18, 148, 162))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()

def _light_photo_card_image_bytes() -> bytes:
    image = Image.new("RGB", (520, 360), color=(248, 244, 232))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 520, 360), fill=(246, 232, 196))
    draw.ellipse((132, 70, 344, 288), fill=(214, 182, 162))
    draw.ellipse((190, 122, 244, 174), fill=(255, 255, 255))
    draw.ellipse((258, 122, 312, 174), fill=(255, 255, 255))
    draw.rectangle((164, 244, 324, 352), fill=(118, 88, 62))
    draw.rectangle((0, 296, 520, 360), fill=(226, 208, 164))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()

def _table_image_bytes() -> bytes:
    image = Image.new("RGB", (900, 560), color=(19, 150, 159))
    draw = ImageDraw.Draw(image)
    left = 70
    top = 34
    right = 860
    bottom = 522
    col_edges = [left, 180, 320, 470, 615, 760, right]
    row_step = 18
    for idx, x in enumerate(col_edges):
        width = 3 if idx in (0, len(col_edges) - 1) else 1
        draw.line((x, top, x, bottom), fill=(220, 240, 242), width=width)
    for y in range(top, bottom + 1, row_step):
        width = 3 if y in (top, bottom) else 1
        draw.line((left, y, right, y), fill=(220, 240, 242), width=width)
    for row in range(1, 24):
        y = top + row * row_step + 4
        draw.text((left + 12, y), f"{row:02d}", fill="white")
        draw.text((190, y), f"Brand {row}", fill="white")
        draw.text((340, y), f"{row * 10}", fill="white")
        draw.text((500, y), f"{row * 7}", fill="white")
        draw.text((640, y), f"{row * 5}", fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def _portrait_chart_image_bytes() -> bytes:
    image = Image.new("RGB", (220, 430), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((18, 18), "% of markets seeing shopper growth", fill="black")
    for idx, year in enumerate(["2023", "2024"]):
        x = 40 + idx * 84
        draw.rectangle(
            (x, 124, x + 36, 304), fill=(238, 241, 246), outline=(210, 220, 232)
        )
        draw.rectangle((x, 204 - idx * 26, x + 36, 304), fill=(80, 167, 184))
        draw.text((x - 4, 320), year, fill="black")
    draw.text((102, 372), "Source: synthetic narrow chart panel.", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def _dark_chart_card_image_bytes() -> bytes:
    image = Image.new("RGB", (360, 420), color=(64, 92, 88))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 360, 62), fill=(28, 58, 54))
    draw.text((24, 18), "WHAT THIS MEANS", fill=(168, 214, 132))
    draw.text((24, 110), "81%", fill=(176, 224, 138))
    draw.text((24, 148), "buyers want clearer", fill=(246, 248, 248))
    draw.text((24, 180), "signals to trust AI", fill=(246, 248, 248))
    draw.text((24, 212), "next to paid content", fill=(246, 248, 248))
    draw.text((24, 370), "Source: synthetic chart card.", fill=(246, 248, 248))
    draw.rectangle((24, 252, 186, 268), fill=(170, 214, 132))
    draw.rectangle((24, 286, 236, 302), fill=(170, 214, 132))
    draw.rectangle((24, 320, 214, 336), fill=(170, 214, 132))
    for y in (242, 276, 310, 344):
        draw.line((24, y, 210, y), fill=(246, 248, 248), width=1)
    for x in (24, 72, 120, 168, 216, 264, 312):
        draw.line((x, 238, x, 348), fill=(210, 220, 220), width=1)
    draw.line((244, 338, 244, 250), fill=(246, 248, 248), width=2)
    draw.line((274, 338, 274, 284), fill=(246, 248, 248), width=2)
    draw.line((304, 338, 304, 270), fill=(246, 248, 248), width=2)
    draw.line((334, 338, 334, 230), fill=(246, 248, 248), width=2)
    draw.line((238, 230, 270, 202), fill=(170, 214, 132), width=4)
    draw.line((270, 202, 298, 222), fill=(170, 214, 132), width=4)
    draw.line((298, 222, 334, 188), fill=(170, 214, 132), width=4)
    draw.rectangle((232, 174, 340, 352), outline=(246, 248, 248), width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def _decorative_shape_card_image_bytes() -> bytes:
    image = Image.new("RGB", (360, 180), color=(244, 244, 244))
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 64, 74, 128), outline=(46, 224, 194), width=4)
    draw.pieslice((86, 64, 150, 128), start=270, end=90, fill=(255, 214, 48))
    draw.pieslice((158, 64, 222, 128), start=90, end=270, fill=(13, 91, 104))
    draw.ellipse((236, 42, 316, 122), outline=(49, 222, 74), width=6)
    draw.arc((236, 98, 316, 176), start=180, end=360, fill=(13, 91, 104), width=3)
    draw.arc((318, 34, 438, 194), start=180, end=350, fill=(55, 225, 193), width=18)
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

def _build_full_page_scan_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_image(fitz.Rect(0, 0, 620, 900), stream=_scan_image_bytes())
    doc.save(path.as_posix())
    doc.close()

def _build_chart_context_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 48), "54 |", fontsize=12)
    page.insert_text(
        (18, 82),
        "Figure 1.35. Net purchases of sovereign bonds by investor type in selected advanced economies",
        fontsize=18,
    )
    page.insert_text((18, 112), "Quarterly averages", fontsize=12)
    page.insert_image(fitz.Rect(40, 150, 580, 430), stream=_chart_image_bytes())
    page.insert_textbox(
        fitz.Rect(18, 455, 590, 520),
        (
            "Note: Net purchases of short and long-term government debt securities, "
            "consolidated to eliminate intra-government transactions."
        ),
        fontsize=10,
    )
    page.insert_textbox(
        fitz.Rect(18, 520, 590, 575),
        (
            "Source: Australian Bureau of Statistics; European Central Bank; Federal Reserve; "
            "Statistics Canada; OECD calculations."
        ),
        fontsize=10,
    )
    page.insert_text((420, 585), "StatLink https://stat.link/bfj2wr", fontsize=10)
    page.insert_textbox(
        fitz.Rect(18, 610, 590, 700),
        (
            "Emerging market economies should ensure that inflation durably returns to target "
            "and further reform their public finances."
        ),
        fontsize=14,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_panel_local_title_preference_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=420)
    page.insert_text((40, 40), "TOP MEDIA PRIORITIES IN 2026", fontsize=20)
    page.insert_text((40, 112), "Top Digital Formats", fontsize=12)
    page.draw_rect(fitz.Rect(40, 126, 320, 300), color=(0, 0, 0))
    page.insert_text((72, 188), "87%", fontsize=34)
    page.insert_text((72, 236), "Digital Video", fontsize=12)
    doc.save(path.as_posix())
    doc.close()

def _build_panel_internal_title_preference_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=420)
    page.insert_text(
        (260, 120),
        "of shoppers are buying private-label or low-cost brands",
        fontsize=14,
    )
    page.draw_rect(
        fitz.Rect(40, 150, 360, 320),
        color=(0.08, 0.12, 0.28),
        fill=(0.08, 0.12, 0.28),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(40, 150, 360, 188),
        color=(0.25, 0.66, 0.90),
        fill=(0.25, 0.66, 0.90),
        width=0.5,
    )
    page.insert_text(
        (132, 176),
        "Private labels go premium",
        fontsize=16,
        color=(1, 1, 1),
    )
    page.insert_textbox(
        fitz.Rect(74, 212, 326, 286),
        "Quality and trust remain the strongest decision drivers.",
        fontsize=13,
        color=(1, 1, 1),
        align=1,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_axis_label_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.draw_rect(fitz.Rect(90, 90, 320, 250), color=(0, 0, 0))
    page.insert_text((110, 120), "Chart 1", fontsize=14)
    page.insert_textbox(
        fitz.Rect(104, 230, 520, 262),
        "1990\n1995\n2000\n2005\n2010\n2015\n2020\n2025\n2030\n2035",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_axis_stroke_extension_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.insert_text((54, 52), "Chart 1: Fiscal outlook", fontsize=16)
    page.insert_text((92, 88), "Outlays in USD trillion", fontsize=11)
    baseline_y = 332
    page.draw_line(
        (86, baseline_y), (520, baseline_y), color=(0.3, 0.3, 0.3), width=0.7
    )
    for idx, height in enumerate([18, 24, 20, 16, 44, 39, 20, 26, 18]):
        x0 = 96 + idx * 34
        page.draw_rect(
            fitz.Rect(x0, baseline_y - height, x0 + 24, baseline_y),
            color=(0.11, 0.14, 0.40),
            fill=(0.11, 0.14, 0.40),
            width=0.5,
        )
    for idx, height in enumerate([26, 28, 30, 32]):
        x0 = 402 + idx * 28
        page.draw_rect(
            fitz.Rect(x0, baseline_y - height, x0 + 18, baseline_y),
            color=(0.82, 0.79, 0.64),
            fill=(0.82, 0.79, 0.64),
            width=0.5,
        )
    for x in [414, 458, 502]:
        page.draw_line(
            (x, baseline_y - 1), (x, baseline_y + 4), color=(0.3, 0.3, 0.3), width=0.5
        )
    page.insert_text((414, 352), "2025", fontsize=10)
    page.insert_text((458, 352), "2030", fontsize=10)
    page.insert_text((502, 352), "2035", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_cards_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (36, 64),
        "Retail trends",
        fontsize=28,
        color=(1, 1, 1),
    )

    top_rect = fitz.Rect(42, 150, 560, 340)
    page.draw_rect(top_rect, color=(0.15, 0.42, 0.76), fill=(0.15, 0.42, 0.76))
    page.draw_line((214, 150), (214, 340), color=(0.45, 0.65, 0.92), width=1.2)
    page.insert_text((66, 246), "44%", fontsize=56, color=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(240, 182, 534, 316),
        (
            "of shoppers are buying lower-cost alternatives over name brands\n"
            "Early findings: What matters to today's consumers, 2026"
        ),
        fontsize=17,
        color=(1, 1, 1),
        lineheight=1.25,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    bottom_rect = fitz.Rect(42, 390, 560, 710)
    page.draw_rect(bottom_rect, color=(0.15, 0.42, 0.76), fill=(0.10, 0.16, 0.32))
    page.draw_rect(
        fitz.Rect(42, 390, 560, 438),
        color=(0.25, 0.66, 0.90),
        fill=(0.25, 0.66, 0.90),
    )
    page.insert_text(
        (168, 422),
        "3 ways retailers can prepare for 2026",
        fontsize=18,
        color=(1, 1, 1),
    )
    page.draw_line((214, 438), (214, 710), color=(0.25, 0.35, 0.58), width=1.0)
    page.draw_line((388, 438), (388, 710), color=(0.25, 0.35, 0.58), width=1.0)
    page.insert_textbox(
        fitz.Rect(60, 470, 196, 676),
        (
            "Shift from search to suggestion:\n"
            "Leverage AI to drive proactive discovery and surface relevant products."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(234, 470, 370, 676),
        (
            "Optimize for algorithmic visibility:\n"
            "Structure content so recommendations engines can understand it."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(408, 470, 544, 676),
        (
            "Engineer moments of serendipity:\n"
            "Design timely nudges and discovery paths that feel contextual."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_panel_metric_band_with_quote_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.insert_text((42, 68), "Invisible AI", fontsize=26, color=(1, 1, 1))
    page.insert_text((42, 148), "71% of consumers", fontsize=24, color=(1, 1, 1))
    page.insert_text(
        (42, 178),
        "want Gen AI-integrated shopping interactions",
        fontsize=14,
        color=(1, 1, 1),
    )
    page.insert_text((250, 158), "compared to", fontsize=14, color=(1, 1, 1))
    page.insert_text((250, 194), "56% who said", fontsize=24, color=(1, 1, 1))
    page.insert_text((250, 224), "the same last year.", fontsize=14, color=(1, 1, 1))
    page.insert_text(
        (470, 194), "Source: Example dataset", fontsize=11, color=(0.2, 0.9, 0.9)
    )
    page.draw_rect(
        fitz.Rect(42, 244, 560, 338),
        color=(0.35, 0.4, 0.62),
        fill=(0.10, 0.16, 0.32),
        width=0.8,
    )
    page.insert_textbox(
        fitz.Rect(72, 270, 520, 318),
        (
            "Transparency builds confidence, even when the tech stays in the background.\n"
            "Mark Ruston, Global Retail Lead"
        ),
        fontsize=15,
        color=(1, 1, 1),
        align=0,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_label_grid_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    panel_rect = fitz.Rect(60, 72, 660, 420)
    page.draw_rect(panel_rect, color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
    page.insert_textbox(
        fitz.Rect(86, 98, 286, 166),
        (
            "To arrive at Ad Equity, we asked consumers their perceptions "
            "of the ads on each media platform."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    labels = [
        ("Trustworthy", 140, 178),
        ("Relevant and useful", 360, 178),
        ("Fun and entertaining", 580, 178),
        ("Better quality", 140, 314),
        ("Innovative", 360, 314),
        ("Captures my attention", 580, 314),
    ]
    for text, cx, cy in labels:
        page.draw_line(
            (cx - 92, cy - 40), (cx - 92, cy + 40), color=(0.1, 0.1, 0.1), width=1.2
        )
        box = fitz.Rect(cx - 76, cy - 22, cx + 16, cy + 30)
        page.draw_rect(box, color=(0.82, 0.42, 0.92), fill=(0.82, 0.42, 0.92))
        page.insert_textbox(
            fitz.Rect(cx - 76, cy + 46, cx + 92, cy + 126),
            text,
            fontsize=14,
            align=fitz.TEXT_ALIGN_CENTER,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_with_side_labels_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=640, height=520)
    page.draw_rect(
        fitz.Rect(140, 184, 500, 430),
        color=(0.10, 0.16, 0.32),
        fill=(0.10, 0.16, 0.32),
    )
    page.draw_circle((214, 338), 34, color=(0.98, 0.50, 0.42), width=3)
    page.draw_circle((320, 268), 34, color=(0.24, 0.76, 0.98), width=3)
    page.draw_circle((426, 338), 34, color=(0.20, 0.88, 0.86), width=3)
    page.draw_circle((320, 362), 106, color=(0.24, 0.38, 0.74), width=3)
    page.insert_text((198, 348), "01", fontsize=22, color=(1, 1, 1))
    page.insert_text((304, 278), "02", fontsize=22, color=(1, 1, 1))
    page.insert_text((410, 348), "03", fontsize=22, color=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(236, 302, 404, 388),
        "What’s inside:\n3 ways retailers can prepare",
        fontsize=18,
        color=(1, 1, 1),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    page.insert_textbox(
        fitz.Rect(74, 186, 174, 278),
        "Moments over\nmerchandise:\nUnlocking growth",
        fontsize=15,
        color=(0.12, 0.12, 0.12),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    page.insert_text((486, 196), "Trust as a", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text((496, 218), "profit", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text((488, 240), "driver:", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text(
        (474, 268), "Driving margins", fontsize=15, color=(0.12, 0.12, 0.12)
    )
    page.insert_textbox(
        fitz.Rect(266, 132, 374, 214),
        "Searchless\nretail:\n03",
        fontsize=15,
        color=(0.12, 0.12, 0.12),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_with_bottom_labels_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=640, height=560)
    page.insert_text(
        (92, 86),
        "Consumer response to unexpected fees",
        fontsize=22,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_circle((322, 302), 128, color=(0.94, 0.28, 0.28), width=36)
    page.draw_circle(
        (322, 302), 76, color=(0.96, 0.84, 0.82), fill=(0.96, 0.84, 0.82), width=2
    )
    page.insert_text((146, 180), "Stayed and", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text(
        (146, 204), "maintained trust", fontsize=16, color=(0.14, 0.14, 0.14)
    )
    page.insert_text((150, 238), "29%", fontsize=28, color=(0.14, 0.14, 0.14))
    page.insert_text((430, 180), "Stayed but", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((430, 204), "lost trust", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((432, 238), "40%", fontsize=28, color=(0.14, 0.14, 0.14))
    page.insert_text((270, 422), "Switched", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((275, 446), "provider", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((278, 480), "31%", fontsize=28, color=(0.14, 0.14, 0.14))
    doc.save(path.as_posix())
    doc.close()

def _build_contents_panel_page_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.draw_rect(page.rect, color=(0.20, 0.45, 0.34), fill=(0.20, 0.45, 0.34))
    page.insert_text((28, 42), "TABLE OF CONTENTS", fontsize=22, color=(1, 1, 1))
    cards = [
        ("01", "TOP MEDIA\nCHALLENGES"),
        ("02", "GENERATIVE\nAI"),
        ("03", "SOCIAL\nMEDIA"),
        ("04", "DIGITAL\nVIDEO"),
    ]
    for idx, (num, label) in enumerate(cards):
        x0 = 70 + idx * 150
        y0 = 110
        card = fitz.Rect(x0, y0, x0 + 105, y0 + 120)
        page.draw_rect(card, color=(0.20, 0.45, 0.34), fill=(0.20, 0.45, 0.34))
        page.insert_text((x0 + 10, y0 + 38), num, fontsize=46, color=(0.45, 0.98, 0.20))
        page.insert_textbox(
            fitz.Rect(x0 + 4, y0 + 62, x0 + 110, y0 + 122),
            label,
            fontsize=14,
            color=(1, 1, 1),
            align=fitz.TEXT_ALIGN_LEFT,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_chart_with_internal_title_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.insert_text(
        (72, 110),
        "Top Media Types with Potential for Innovation",
        fontsize=14,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_line((70, 132), (620, 132), color=(0.12, 0.12, 0.12), width=1.2)
    bars = [
        (90, 300, 150, 160, "50%"),
        (185, 300, 245, 205, "35%"),
        (280, 300, 340, 215, "32%"),
        (375, 300, 435, 225, "30%"),
        (470, 300, 530, 225, "30%"),
    ]
    for x0, y1, x1, y0, label in bars:
        rect = fitz.Rect(x0, y0, x1, y1)
        page.draw_rect(rect, color=(0.68, 0.96, 0.46), fill=(0.68, 0.96, 0.46))
        page.insert_text((x0 + 12, y0 + 28), label, fontsize=18, color=(0.1, 0.1, 0.1))
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_with_wide_internal_title_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.draw_rect(
        fitz.Rect(24, 24, 436, 88),
        color=(0.96, 0.96, 0.96),
        fill=(0.99, 0.99, 0.99),
        width=1.0,
    )
    page.insert_text(
        (28, 52),
        "Media Types with the Most Potential for Innovation",
        fontsize=18,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_line((28, 78), (430, 78), color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_rect(
        fitz.Rect(88, 188, 628, 340),
        color=(0.90, 0.90, 0.90),
        fill=(0.98, 0.98, 0.98),
        width=1.0,
    )
    bars = [
        (96, 336, 156, 196, "50%"),
        (190, 336, 250, 236, "35%"),
        (284, 336, 344, 246, "32%"),
        (378, 336, 438, 256, "30%"),
        (472, 336, 532, 256, "30%"),
    ]
    for x0, y1, x1, y0, label in bars:
        rect = fitz.Rect(x0, y0, x1, y1)
        page.draw_rect(rect, color=(0.68, 0.96, 0.46), fill=(0.68, 0.96, 0.46))
        page.insert_text(
            (x0 + 12, y0 + 28),
            label,
            fontsize=18,
            color=(0.1, 0.1, 0.1),
        )
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_independent_panel_cards_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    upper_rect = fitz.Rect(42, 300, 552, 520)
    lower_rect = fitz.Rect(42, 560, 552, 820)

    page.draw_rect(
        upper_rect,
        color=(0.92, 0.92, 0.92),
        fill=(0.92, 0.92, 0.92),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(70, 320, 226, 418),
        color=(0.70, 0.98, 0.55),
        fill=(0.70, 0.98, 0.55),
        width=0.5,
    )
    page.insert_text((88, 374), "46%", fontsize=34)
    page.insert_text((264, 344), "of shoppers make purchases based on AI", fontsize=16)
    page.insert_text((264, 364), "recommendations", fontsize=16)
    page.insert_text((264, 392), "Early findings: What matters to today's", fontsize=12)
    page.insert_text((264, 408), "consumers, 2026", fontsize=12)

    page.draw_rect(
        lower_rect,
        color=(0.95, 0.97, 0.91),
        fill=(0.95, 0.97, 0.91),
        width=0.5,
    )
    page.insert_text(
        (136, 584), "3 ways retailers can prepare for a searchless future:", fontsize=16
    )
    columns = [
        (
            74,
            "01",
            [
                "Shift from search",
                "to suggestion:",
                "Use contextual",
                "signals to surface",
                "relevant products.",
            ],
        ),
        (
            252,
            "02",
            [
                "Optimize for",
                "algorithmic",
                "visibility:",
                "Strengthen product",
                "and content tagging.",
            ],
        ),
        (
            426,
            "03",
            [
                "Engineer moments",
                "of serendipity:",
                "Use timed prompts",
                "and content to spark",
                "discovery.",
            ],
        ),
    ]
    for x, number, lines in columns:
        page.insert_text((x, 636), number, fontsize=18)
        y = 658
        for line in lines:
            page.insert_text((x + 8, y), line, fontsize=12)
            y += 18

    doc.save(path.as_posix())
    doc.close()

def _build_chart_partial_note_overlap_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (18, 82),
        "Figure 1.35. Partial note overlap case",
        fontsize=18,
    )
    page.insert_text((18, 112), "Quarterly averages", fontsize=12)
    page.insert_image(fitz.Rect(40, 150, 580, 398), stream=_chart_image_bytes())
    page.insert_textbox(
        fitz.Rect(18, 395, 590, 455),
        (
            "Notes: This note begins inside the padded chart bbox but should still be kept "
            "in full, without clipping its wrapped continuation line. This sentence is "
            "intentionally long so the note wraps across multiple lines and extends below "
            "the original chart bottom."
        ),
        fontsize=10,
    )
    page.insert_textbox(
        fitz.Rect(18, 500, 590, 620),
        "This paragraph must remain outside the chart crop. " * 12,
        fontsize=13,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_chart_caption_spillover_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(65, 116, 540, 176),
        (
            "Given the heterogeneity in regulation trends across states, there are again large "
            "variations between regions. This paragraph should remain outside the final chart crop."
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
        "Estimated contribution of changes in regulation to productivity and business dynamism between 2012 and 2023",
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_infographic_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 96), "Infographic 1. Key facts and figures", fontsize=20)
    page.draw_rect(
        fitz.Rect(24, 132, 590, 560),
        color=(0.7, 0.55, 0.1),
        fill=(0.99, 0.92, 0.72),
        width=1.0,
    )
    page.draw_line((306, 152), (306, 542), color=(0.55, 0.42, 0.08), width=1.0)
    page.insert_text(
        (42, 174),
        "Health spending on the rise again",
        fontsize=18,
    )
    page.insert_text((42, 202), "% annual real growth", fontsize=12)
    for idx, year in enumerate(
        ["2018", "2019", "2020", "2021", "2022", "2023", "2024"]
    ):
        x = 56 + idx * 48
        page.insert_text((x, 376), year, fontsize=9)
        page.insert_text((x, 344 - idx * 10), str(idx * 2), fontsize=9)
    page.insert_text(
        (346, 174),
        "Many countries turn to foreign-trained doctors",
        fontsize=18,
    )
    countries = [
        "Norway",
        "UK",
        "Australia",
        "Canada",
        "Germany",
        "France",
        "Colombia",
        "Mexico",
    ]
    for idx, country in enumerate(countries):
        y = 236 + idx * 24
        page.insert_text((352, y), country, fontsize=11)
        page.draw_rect(
            fitz.Rect(430, y - 10, 430 + (110 - idx * 15), y + 8),
            color=(0.7, 0.3, 0.1),
            fill=(0.78, 0.28, 0.08),
            width=0.5,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_side_by_side_photo_examples_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Digital Out of Home is driving high-impact campaigns across APAC through creative use of ad format",
        fontsize=18,
    )
    page.insert_image(
        fitz.Rect(110, 160, 433, 353),
        stream=_photo_panel_image_bytes(),
    )
    page.insert_image(
        fitz.Rect(527, 160, 849, 353),
        stream=_photo_panel_image_bytes(),
    )
    page.insert_textbox(
        fitz.Rect(176, 366, 812, 406),
        (
            "Maybelline Superstay Teddy Tint\n"
            "Central Square, Philippines (2024)\n"
            "L'Oreal Thailand\n"
            "Emsphere, Bangkok (2024)"
        ),
        fontsize=12,
        align=1,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_embedded_chart_image_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((34, 72), "How strong brands keep momentum", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 128, 266, 286),
        (
            "Momentum remains one of the clearest signals of brand health. "
            "The chart card on this page is embedded as a slide image rather "
            "than a vector figure caption."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(320, 172, 874, 430),
        stream=_chart_image_bytes(),
    )
    page.insert_text(
        (320, 450),
        "Source: synthetic embedded chart card data.",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_relaxed_embedded_chart_geometries_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((34, 72), "Why the odds shifted in 2024", fontsize=24)
    page.insert_textbox(
        fitz.Rect(302, 88, 544, 315),
        (
            "Wide embedded chart cards should still be detected even when the "
            "aspect is broader than the default image gate."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(302, 332, 813, 510),
        stream=_chart_image_bytes(),
    )

    page = doc.new_page(width=842, height=595)
    page.insert_text((34, 72), "Brand spotlight", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 118, 262, 432),
        (
            "Narrow right-side data panels should be kept when they contain a "
            "real chart and source area rather than a decorative photo."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(631, 133, 813, 515),
        stream=_portrait_chart_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_decorative_photo_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((34, 72), "A tale of two halves", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 120, 430, 260),
        (
            "The headlines from the ranking reveal a fascinating divide. "
            "This page pairs a narrative callout with a decorative hero photo "
            "that should not be extracted as a chart."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(468, 90, 902, 486),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_relaxed_embedded_chart_with_figure_caption_pdf(path: Path) -> None:
    doc = fitz.open()

    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (302, 116),
        "Figure 1.2. Captioned wide embedded image should not use relaxed geometry",
        fontsize=16,
    )
    page.insert_image(
        fitz.Rect(302, 332, 813, 510),
        stream=_chart_image_bytes(),
    )

    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (630, 112),
        "Figure 1.3. Captioned narrow embedded image should not use relaxed geometry",
        fontsize=16,
    )
    page.insert_image(
        fitz.Rect(631, 133, 813, 515),
        stream=_portrait_chart_image_bytes(),
    )

    doc.save(path.as_posix())
    doc.close()

def _build_full_page_image_table_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_image(
        fitz.Rect(8, 20, 952, 520),
        stream=_table_image_bytes(),
    )
    page = doc.new_page(width=960, height=540)
    page.insert_image(
        fitz.Rect(8, 20, 952, 520),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_ranked_table_slide_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (30, 64),
        "Ad Equity ranking APAC 2025 - All Media Brands (Global brands)",
        fontsize=22,
    )
    page.insert_text((30, 118), "Preference", fontsize=20)
    page.insert_text((220, 118), "APAC consumers", fontsize=20)
    page.insert_text((760, 118), "Also #1 in", fontsize=20)
    page.draw_line((30, 156), (930, 156), color=(0.2, 0.2, 0.2), width=2.0)
    row_tops = [182, 260, 338, 416, 494]
    colors = [
        (0.09, 0.84, 0.76),
        (0.14, 0.67, 0.92),
        (0.42, 0.48, 0.79),
        (0.64, 0.2, 0.86),
        (0.84, 0.03, 0.82),
    ]
    brand_names = ["NETFLIX", "amazon", "Pinterest", "Google", "prime"]
    categories = ["OTT", "E-commerce", "Social", "Search", "OTT"]
    regions = [
        "Japan, Korea",
        "-",
        "Australia, Indonesia, Singapore, Thailand",
        "India, Philippines",
        "-",
    ]
    for idx, (top, color) in enumerate(zip(row_tops, colors), start=1):
        bottom = top + 48
        page.draw_rect(
            fitz.Rect(42, top, 160, bottom),
            color=color,
            fill=color,
            width=0.5,
        )
        page.insert_text((92, top + 32), str(idx), fontsize=24, color=(1, 1, 1))
        page.draw_line((30, bottom + 18), (930, bottom + 18), color=(0.82, 0.82, 0.82))
        page.insert_text((270, top + 28), brand_names[idx - 1], fontsize=26)
        page.draw_rect(
            fitz.Rect(470, top + 4, 680, bottom - 4),
            color=(0.98, 0.9, 0.4),
            fill=(0.98, 0.9, 0.4),
            width=0.5,
        )
        page.insert_text((540, top + 28), categories[idx - 1], fontsize=18)
        page.insert_textbox(
            fitz.Rect(760, top + 4, 920, bottom + 8),
            regions[idx - 1],
            fontsize=14,
            align=1,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_slide_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Panel charts without figure captions should still be detected",
        fontsize=24,
    )
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 170, 932, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    for idx, height in enumerate([95, 72, 64, 58, 52, 45], start=0):
        x0 = 70 + idx * 55
        page.draw_rect(
            fitz.Rect(x0, 420 - height, x0 + 28, 420),
            color=(0.78, 0.0, 0.86) if idx == 0 else (0.82, 0.82, 0.82),
            fill=(0.78, 0.0, 0.86) if idx == 0 else (0.82, 0.82, 0.82),
            width=0.5,
        )
    page.draw_line((62, 420), (430, 420), color=(0.75, 0.75, 0.75))
    page.draw_line((62, 252), (430, 252), color=(0.9, 0.9, 0.9))
    page.draw_circle((715, 318), 96, color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_circle((715, 318), 72, color=(1, 1, 1), width=18)
    page.draw_circle((715, 318), 72, color=(0.82, 0.0, 0.86), width=18)
    page.draw_line((715, 318), (802, 286), color=(0.82, 0.0, 0.86), width=3.0)
    page.draw_line((715, 318), (632, 298), color=(0.14, 0.83, 0.76), width=3.0)
    page.draw_line((715, 318), (690, 405), color=(0.14, 0.83, 0.76), width=3.0)
    page.insert_textbox(
        fitz.Rect(54, 210, 548, 246),
        "37% 35%",
        fontsize=26,
        align=0,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_shared_title_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (42, 74),
        "Brand switching reaches critical mass",
        fontsize=26,
    )
    page.insert_text(
        (42, 116),
        "Year-on-year growth in brand switching behaviour",
        fontsize=20,
    )
    bands = [
        fitz.Rect(492, 172, 748, 252),
        fitz.Rect(492, 284, 736, 364),
        fitz.Rect(492, 396, 712, 476),
    ]
    labels = [("2025", "78%"), ("2024", "50%"), ("2023", "40%")]
    fills = [
        (0.82, 0.10, 0.62),
        (0.84, 0.84, 0.84),
        (0.84, 0.84, 0.84),
    ]
    for band, (year, value), fill in zip(bands, labels, fills):
        page.draw_rect(band, color=fill, fill=fill, width=0.5)
        page.insert_text((band.x0 + 12, band.y0 + 52), year, fontsize=28)
        page.insert_text((band.x1 - 74, band.y0 + 52), value, fontsize=28)
    doc.save(path.as_posix())
    doc.close()

def _build_shared_title_split_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Top anticipated media challenges", fontsize=24)
    page.insert_text((28, 84), "by company type", fontsize=24)
    page.draw_rect(
        fitz.Rect(28, 128, 462, 468),
        color=(0.96, 0.96, 0.96),
        fill=(0.96, 0.96, 0.96),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 128, 932, 468),
        color=(0.96, 0.96, 0.96),
        fill=(0.96, 0.96, 0.96),
        width=0.5,
    )
    page.insert_text((56, 166), "78%", fontsize=28)
    page.insert_text((152, 160), "Ad content adjacency", fontsize=20)
    page.insert_text((152, 190), "AI-generated content (37%)", fontsize=14)
    page.insert_text((152, 214), "Deepfakes (27%)", fontsize=14)
    page.insert_text((152, 238), "Influencer content (20%)", fontsize=14)
    page.insert_text((540, 166), "40%", fontsize=28)
    page.insert_text((636, 160), "Publishers & platforms", fontsize=20)
    page.insert_text((636, 190), "Brand suitability", fontsize=14)
    page.insert_text((636, 214), "Premium inventory", fontsize=14)
    page.insert_text((636, 238), "Trusted context", fontsize=14)
    doc.save(path.as_posix())
    doc.close()

def _build_right_column_raster_chart_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((40, 82), "What this means for brands", fontsize=24)
    page.insert_textbox(
        fitz.Rect(40, 126, 404, 410),
        (
            "In 2026, trust is more fragmented than ever. Consumers want "
            "measurement partners that can identify harmful generative-AI "
            "content, prove safe adjacencies, and make brand suitability "
            "controls easier to audit across campaigns."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(444, 16, 843, 404),
        stream=_dark_chart_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_right_column_raster_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((40, 82), "Why people are holding back", fontsize=24)
    page.insert_textbox(
        fitz.Rect(40, 126, 404, 420),
        (
            "Consumers continue to feel pressure on household budgets. "
            "Even as inflation eases, many say they will not return to "
            "freer spending until prices fall, incomes grow, and savings "
            "buffers improve."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_small_decorative_raster_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "What momentum means", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 122, 430, 260),
        (
            "This paragraph should remain body copy. The decorative motif "
            "below is not a standalone chart even though it uses geometric "
            "shapes and a high-contrast card design."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(500, 395, 846, 555),
        stream=_decorative_shape_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_light_raster_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "How everyday moments shape preferences", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 126, 404, 420),
        (
            "This page uses narrative body copy beside a lifestyle image. "
            "The image should not be extracted as a chart candidate even "
            "though it sits inside a clean card layout."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_light_photo_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_prose_mentioning_figure_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "Where shoppers begin", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 126, 404, 420),
        (
            "When it comes to starting a shopping journey, only a small "
            "share of consumers say they would begin with a chatbot. "
            "That figure rises slightly among younger audiences, but the "
            "adjacent lifestyle photo is still not a chart."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_light_photo_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_oversized_raster_wrapper_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    # Oversized embedded image rect that bleeds off-page.
    page.insert_image(
        fitz.Rect(260, 50, 1157, 554),
        stream=_chart_image_bytes(),
    )
    # Real chart card fully inside the page; this is the crop we want to keep.
    page.insert_image(
        fitz.Rect(302, 121, 654, 510),
        stream=_chart_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_wide_panel_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Marketers continue to shift budget toward higher-performing channels",
        fontsize=24,
    )
    page.insert_text(
        (28, 138),
        "Changes in budget/resource allocation (% net positive)",
        fontsize=18,
    )
    page.draw_rect(
        fitz.Rect(20, 170, 932, 476),
        color=(1, 1, 1),
        fill=(1, 1, 1),
        width=0.5,
    )
    page.draw_line((42, 270), (920, 270), color=(0.2, 0.2, 0.2), width=1.0)
    values = [
        68,
        58,
        54,
        51,
        48,
        44,
        41,
        40,
        37,
        35,
        29,
        28,
        20,
        19,
        14,
        8,
        4,
        -16,
        -30,
        -38,
    ]
    for idx, value in enumerate(values):
        x = 52 + idx * 42
        if value >= 0:
            page.draw_rect(
                fitz.Rect(x, 270 - value * 1.3, x + 12, 270),
                color=(0.78, 0.0, 0.86),
                fill=(0.78, 0.0, 0.86),
                width=0.5,
            )
        else:
            page.draw_rect(
                fitz.Rect(x, 270, x + 12, 270 - value * 1.3),
                color=(0.78, 0.0, 0.86),
                fill=(0.78, 0.0, 0.86),
                width=0.5,
            )
    doc.save(path.as_posix())
    doc.close()

def _build_multiline_title_panel_with_side_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text(
        (28, 42), "As digital content grows, the need for innovation", fontsize=20
    )
    page.insert_text(
        (28, 66), "in ensuring media quality within digital video", fontsize=20
    )
    page.insert_text((28, 90), "platforms is especially important", fontsize=20)
    page.draw_rect(
        fitz.Rect(28, 128, 418, 332),
        color=(1, 1, 1),
        fill=(1, 1, 1),
        width=0.5,
    )
    page.draw_line((28, 168), (418, 168), color=(0.2, 0.2, 0.2), width=1.0)
    page.insert_text(
        (28, 158), "Media Quality Considerations on Social Media", fontsize=16
    )
    page.insert_textbox(
        fitz.Rect(28, 192, 208, 300),
        "Viewability is an important metric when assessing social media campaigns",
        fontsize=12,
        align=2,
    )
    page.draw_rect(
        fitz.Rect(240, 184, 404, 236),
        color=(0.67, 0.98, 0.51),
        fill=(0.67, 0.98, 0.51),
        width=0.5,
    )
    page.insert_text((338, 221), "85%", fontsize=24)
    page.draw_rect(
        fitz.Rect(240, 252, 404, 304),
        color=(0.67, 0.98, 0.51),
        fill=(0.67, 0.98, 0.51),
        width=0.5,
    )
    page.insert_text((338, 289), "85%", fontsize=24)
    page.draw_rect(
        fitz.Rect(458, 140, 690, 356),
        color=(0.19, 0.37, 0.31),
        fill=(0.19, 0.37, 0.31),
        width=0.5,
    )
    page.insert_text((486, 176), "WHAT THIS MEANS", fontsize=18, color=(0.72, 1.0, 0.4))
    page.insert_text((486, 202), "FOR MARKETERS", fontsize=18, color=(0.72, 1.0, 0.4))
    page.insert_textbox(
        fitz.Rect(478, 224, 678, 334),
        (
            "Media quality on digital video remains important as spending climbs to "
            "$306.4 billion globally. Improved detection should help cut 14.9% of "
            "avoidable risk by 2026."
        ),
        fontsize=12,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(28, 364, 690, 398),
        "Source: Synthetic IAS-style slide footer used to keep the page layout realistic.",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_slide_with_figure_caption_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Figure 1.1. Captioned panel chart", fontsize=20)
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 170, 932, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(80, 360, 110, 420),
        color=(0.78, 0.0, 0.86),
        fill=(0.78, 0.0, 0.86),
        width=0.5,
    )
    page.draw_circle((715, 318), 96, color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_circle((715, 318), 72, color=(0.82, 0.0, 0.86), width=18)
    doc.save(path.as_posix())
    doc.close()

def _build_panel_action_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Take action", fontsize=24)
    page.insert_text((42, 138), "Context control avoidance", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.15, 0.28, 0.24),
        fill=(0.15, 0.28, 0.24),
        width=0.5,
    )
    page.insert_textbox(
        fitz.Rect(56, 214, 428, 430),
        (
            "Avoid content you deem risky or unsuitable with a contextual "
            "solution that leverages semantic intelligence and custom controls. "
            "Use the workflow to align teams, reduce manual review, and improve "
            "consistency across channels."
        ),
        fontsize=14,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_dense_numeric_panel_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text(
        (28, 56),
        "Adjacencies to unsuitable Gen AI content",
        fontsize=20,
    )
    panel_rect = fitz.Rect(28, 88, 676, 328)
    page.draw_rect(
        panel_rect,
        color=(0.95, 0.95, 0.95),
        fill=(0.95, 0.95, 0.95),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(478, 112, 652, 304),
        color=(0.12, 0.34, 0.25),
        fill=(0.12, 0.34, 0.25),
        width=0.5,
    )
    categories = [
        ("Content that contains inaccurate information", "22%", "9%", "68%"),
        ("Content that provides an ad-spammy user experience", "26%", "11%", "63%"),
        (
            "Content that regurgitates or plagiarizes existing content",
            "25%",
            "14%",
            "61%",
        ),
        (
            "Content that comes from unknown domains with no editorial team",
            "24%",
            "17%",
            "59%",
        ),
    ]
    for idx, (label, safe, unsure, avoid) in enumerate(categories):
        y = 124 + idx * 46
        page.insert_textbox(
            fitz.Rect(44, y, 236, y + 36),
            label,
            fontsize=8,
            align=2,
        )
        bar_y0 = y + 6
        page.draw_rect(
            fitz.Rect(256, bar_y0, 354, bar_y0 + 24),
            color=(0.67, 0.98, 0.51),
            fill=(0.67, 0.98, 0.51),
            width=0.5,
        )
        page.draw_rect(
            fitz.Rect(354, bar_y0, 394, bar_y0 + 24),
            color=(0.52, 0.69, 0.59),
            fill=(0.52, 0.69, 0.59),
            width=0.5,
        )
        page.draw_rect(
            fitz.Rect(394, bar_y0, 470, bar_y0 + 24),
            color=(0.86, 0.86, 0.86),
            fill=(0.86, 0.86, 0.86),
            width=0.5,
        )
        page.insert_text((300, y + 22), safe, fontsize=11)
        page.insert_text((366, y + 22), unsure, fontsize=11)
        page.insert_text((425, y + 22), avoid, fontsize=11)
    page.insert_textbox(
        fitz.Rect(500, 144, 638, 286),
        (
            "Not all AI-generated content is created equal. Prioritising "
            "classification and robust avoidance strategies helps ensure "
            "brands maintain trust."
        ),
        fontsize=11,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_cross_panel_label_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    left = fitz.Rect(28, 170, 462, 468)
    right = fitz.Rect(498, 170, 932, 468)
    page.draw_rect(left, color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93), width=0.5)
    page.draw_rect(right, color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93), width=0.5)
    page.insert_textbox(fitz.Rect(52, 214, 550, 248), "37% 35%", fontsize=26)
    page.insert_textbox(
        fitz.Rect(66, 430, 440, 460), "Netflix Pinterest Amazon", fontsize=12
    )
    page.insert_textbox(
        fitz.Rect(536, 430, 906, 460), "Netflix Spotify Prime Video", fontsize=12
    )
    doc.save(path.as_posix())
    doc.close()

def _build_dense_chart_with_section_heading_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((42, 96), "Figure 1.1. Dense labeled chart", fontsize=20)
    page.draw_rect(
        fitz.Rect(36, 132, 584, 682),
        color=(0.7, 0.7, 0.7),
        fill=(0.93, 0.93, 0.93),
        width=1.0,
    )
    for idx in range(34):
        y = 168 + idx * 6
        page.insert_text((60, y), f"C{idx:02d}", fontsize=8)
        page.insert_text((118, y), f"{60 + idx}", fontsize=8)
        page.insert_text((186, y), f"{24 + idx % 9}%", fontsize=8)
        page.insert_text((256, y), f"L{idx % 7}", fontsize=8)
        page.insert_text((322, y), f"{100 + idx}", fontsize=8)
        page.insert_text((396, y), f"{idx % 5}.{idx % 9}", fontsize=8)
        page.insert_text((462, y), f"R{idx % 8}", fontsize=8)
    page.insert_text((48, 360), "Methodology, interpretation and use", fontsize=21)
    page.insert_textbox(
        fitz.Rect(48, 398, 566, 648),
        "This explanatory section must stay outside the figure crop. " * 20,
        fontsize=12,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_multi_figure_dense_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((42, 96), "Figure 5.26. Upper dense chart", fontsize=18)
    page.draw_rect(
        fitz.Rect(36, 132, 584, 520),
        color=(0.8, 0.8, 0.8),
        fill=(0.94, 0.94, 0.94),
        width=1.0,
    )
    page.draw_rect(
        fitz.Rect(36, 522, 584, 762),
        color=(0.8, 0.8, 0.8),
        fill=(0.94, 0.94, 0.94),
        width=1.0,
    )
    for idx in range(28):
        y = 174 + idx * 8
        page.insert_text((60, y), f"A{idx:02d}", fontsize=8)
        page.insert_text((126, y), f"{80 + idx}", fontsize=8)
        page.insert_text((208, y), f"{idx % 10}%", fontsize=8)
        page.insert_text((284, y), f"B{idx % 6}", fontsize=8)
        page.insert_text((350, y), f"{40 + idx}", fontsize=8)
        page.insert_text((430, y), f"{idx % 7}.{idx % 3}", fontsize=8)
    page.insert_text(
        (42, 470),
        "Figure 5.27. Lower dense chart",
        fontsize=18,
    )
    for idx in range(24):
        y = 528 + idx * 8
        page.insert_text((60, y), f"C{idx:02d}", fontsize=8)
        page.insert_text((126, y), f"{50 + idx}", fontsize=8)
        page.insert_text((208, y), f"{idx % 9}%", fontsize=8)
        page.insert_text((284, y), f"D{idx % 5}", fontsize=8)
        page.insert_text((350, y), f"{25 + idx}", fontsize=8)
        page.insert_text((430, y), f"{idx % 4}.{idx % 8}", fontsize=8)
    doc.save(path.as_posix())
    doc.close()

def _build_wide_captioned_draw_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(42, 110, 576, 360),
        "This explanatory paragraph should remain outside the figure crop. " * 12,
        fontsize=12,
        lineheight=1.2,
    )
    page.draw_rect(
        fitz.Rect(36, 430, 584, 640),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 442), "Figure 1", fontsize=12)
    page.insert_text(
        (48, 468),
        "How vision-language-action models work",
        fontsize=18,
    )
    page.draw_rect(
        fitz.Rect(54, 520, 274, 576),
        color=(0.55, 0.75, 0.85),
        width=1.0,
    )
    page.draw_rect(
        fitz.Rect(332, 520, 552, 576),
        color=(0.55, 0.75, 0.85),
        width=1.0,
    )
    page.draw_line((288, 548), (320, 548), color=(0.2, 0.2, 0.2), width=1.0)
    page.insert_text((92, 544), "Vision", fontsize=10)
    page.insert_text((400, 544), "Action", fontsize=10)
    page.insert_text((48, 620), "Source: Deloitte analysis.", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_captioned_draw_charts_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(42, 72, 576, 148),
        "Lead-in paragraph text that should stay outside both figure crops.",
        fontsize=12,
        lineheight=1.2,
    )

    page.draw_rect(
        fitz.Rect(36, 170, 584, 382),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 182), "Figure 1", fontsize=12)
    page.insert_text(
        (48, 208),
        "Projected agentic AI adoption",
        fontsize=17,
    )
    page.draw_line((240, 250), (240, 340), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((360, 250), (360, 340), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((210, 340), (390, 340), color=(0.25, 0.25, 0.25), width=1.0)
    page.draw_line((240, 340), (360, 280), color=(0.15, 0.15, 0.15), width=1.0)
    page.draw_line((240, 340), (360, 220), color=(0.15, 0.15, 0.15), width=1.0)
    page.insert_text((370, 220), "33%", fontsize=10)
    page.insert_text((370, 280), "15%", fontsize=10)
    page.insert_text((48, 354), "Source: Deloitte analysis.", fontsize=10)

    page.draw_rect(
        fitz.Rect(36, 440, 584, 652),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 452), "Figure 2", fontsize=12)
    page.insert_text(
        (48, 478),
        "AI model security risks and associated mitigation strategies",
        fontsize=17,
    )
    page.insert_text((48, 524), "Risks", fontsize=11)
    page.insert_text((320, 524), "Mitigation", fontsize=11)
    page.draw_line((48, 538), (552, 538), color=(0.2, 0.2, 0.2), width=1.0)
    page.draw_line((300, 504), (300, 618), color=(0.4, 0.4, 0.4), width=0.8)
    risk_labels = [
        "Collapse",
        "Stealing",
        "Inversion",
        "Agency abuse",
        "Bias drift",
        "Leakage",
        "Skew",
        "Outage",
        "Misuse",
        "Drift",
    ]
    mitigation_labels = [
        "Isolation",
        "Access mgmt",
        "Audit logs",
        "Safeguards",
        "Red team",
        "Hardening",
        "Alerts",
        "Monitoring",
        "Testing",
        "Reviews",
    ]
    for idx, label in enumerate(risk_labels):
        page.insert_text((48, 550 + idx * 7), label, fontsize=8)
    for idx, label in enumerate(mitigation_labels):
        page.insert_text((320, 550 + idx * 7), label, fontsize=8)
    page.insert_text((48, 624), "Source: Deloitte analysis.", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_table_context_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 32), "130 |", fontsize=12)
    page.insert_text(
        (18, 82),
        "Chile: Demand, output and prices",
        fontsize=20,
    )

    x0, y0, x1, y1 = 40, 130, 560, 360
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [320, 390, 450, 500]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [170, 210, 250, 290, 330]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))

    headers = ["2022", "2023", "2024", "2025", "2026"]
    for idx, header in enumerate(headers):
        page.insert_text((330 + idx * 45, 150), header, fontsize=11)
    row_labels = [
        "GDP at market prices*",
        "Private consumption",
        "Government consumption",
        "Gross fixed capital formation",
        "Exports of goods and services",
    ]
    values = [
        ["263 104.8", "0.6", "2.4", "2.4", "2.2"],
        ["166 968.0", "-4.8", "0.9", "2.7", "1.7"],
        ["38 686.1", "2.4", "3.2", "4.8", "3.4"],
        ["67 404.4", "0.3", "-1.8", "6.8", "5.1"],
        ["93 653.1", "0.4", "6.3", "3.5", "1.3"],
    ]
    for row_index, label in enumerate(row_labels):
        y = 190 + row_index * 40
        page.insert_text((50, y), label, fontsize=11)
        for col_index, value in enumerate(values[row_index]):
            page.insert_text((330 + col_index * 45, y), value, fontsize=11)

    page.insert_text(
        (40, 390),
        "* Based on seasonally adjusted quarterly data; may differ from official annual data.",
        fontsize=9,
    )
    page.insert_text(
        (40, 408),
        "1. Contributions to changes in GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 426),
        "Source: OECD Economic Outlook 118 database. StatLink https://stat.link/example",
        fontsize=9,
    )
    page.insert_textbox(
        fitz.Rect(40, 490, 580, 660),
        (
            "Global financial conditions have eased over the past year, supporting Chile's "
            "external environment. The terms of trade have improved, driven by rising "
            "copper prices, and the direct macroeconomic effects of higher tariffs are "
            "expected to be limited."
        ),
        fontsize=14,
        lineheight=1.3,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_table_legend_footer_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (40, 82), "Table 1.2. Dashboard on health status, 2023", fontsize=18
    )

    x0, y0, x1, y1 = 40, 130, 560, 420
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [160, 300, 430]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [180, 230, 280, 330, 380]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))

    headers = ["Life expectancy", "Avoidable mortality", "Self-rated health"]
    for idx, header in enumerate(headers):
        page.insert_text((58 + idx * 138, 160), header, fontsize=11)
    rows = [
        ("OECD", ["81.1", "222", "8.0"]),
        ("Australia", ["83.0", "146", "3.8"]),
        ("Belgium", ["82.5", "184", "8.3"]),
        ("Canada", ["81.7", "184", "3.2"]),
        ("Chile", ["81.6", "229", "6.1"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 210 + row_index * 50
        page.insert_text((52, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((190 + col_index * 130, y), value, fontsize=11)

    page.insert_textbox(
        fitz.Rect(40, 432, 570, 540),
        (
            "Better than the OECD average.\n"
            "Close to the OECD average.\n"
            "Worse than the OECD average.\n"
            "1. 2024 data for Chile and Mexico.\n"
            "2. 2020-2022 data for Belgium and Canada."
        ),
        fontsize=9,
        lineheight=1.1,
    )
    page.insert_textbox(
        fitz.Rect(40, 585, 570, 690),
        "This paragraph must remain outside the table crop. " * 16,
        fontsize=13,
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_legend_footer_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((18, 32), "19 |", fontsize=12)
    page.insert_text(
        (40, 82),
        "Table 1.2. Dashboard on health status, 2023 (unless indicated)",
        fontsize=18,
    )

    year_positions = [220, 340, 470]
    headers = ["Life expectancy", "Avoidable mortality", "Self-rated health"]
    for idx, header in enumerate(headers):
        page.insert_text((year_positions[idx], 124), header, fontsize=11)

    rows = [
        ("OECD", ["81.1", "222", "8.0"]),
        ("Australia", ["83.0", "146", "3.8"]),
        ("Belgium", ["82.5", "184", "8.3"]),
        ("Canada", ["81.7", "184", "3.2"]),
        ("Chile", ["81.6", "229", "6.1"]),
        ("Colombia", ["77.5", "419", "1.3"]),
        ("Costa Rica", ["81.0", "241", "N/A"]),
        ("Czechia", ["79.9", "229", "9.1"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 168 + row_index * 26
        page.insert_text((48, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_textbox(
        fitz.Rect(42, 366, 650, 456),
        (
            "Better than the OECD average.\n"
            "Close to the OECD average.\n"
            "Worse than the OECD average.\n"
            "1. 2024 data for Chile and Mexico.\n"
            "2. 2020-2022 data for Belgium and Canada."
        ),
        fontsize=9,
        lineheight=1.1,
    )
    page.insert_textbox(
        fitz.Rect(42, 520, 650, 680),
        "This paragraph must remain outside the stream table crop. " * 18,
        fontsize=13,
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_spillover_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 32), "222 |", fontsize=12)
    page.insert_text((40, 292), "1. Four quarters moving average.", fontsize=9)
    page.insert_text(
        (40, 310),
        "Source: OECD Economic Outlook 118 database; and Haut commissariat au Plan, DCN.",
        fontsize=9,
    )
    page.insert_text((400, 332), "StatLink https://stat.link/ryce5w", fontsize=9)
    page.insert_text(
        (40, 356),
        "Morocco: Demand, output and prices",
        fontsize=20,
    )
    year_positions = [330, 375, 420, 465, 510, 555]
    for idx, year in enumerate(["2022", "2023", "2024", "2025", "2026", "2027"]):
        page.insert_text((year_positions[idx], 386), year, fontsize=11)
    page.insert_text((310, 404), "Current prices", fontsize=10)
    page.insert_text((420, 404), "Percentage changes, volume", fontsize=10)
    page.insert_text((316, 420), "MAD billion", fontsize=10)
    page.insert_text((448, 420), "(2014 prices)", fontsize=10)
    page.insert_text((40, 424), "Morocco", fontsize=11)

    rows = [
        ("GDP at market prices", ["1 333.5", "3.7", "3.8", "4.5", "4.2", "4.0"]),
        ("Private consumption", ["827.9", "4.8", "3.4", "4.3", "3.6", "3.3"]),
        ("Government consumption", ["252.6", "6.1", "5.6", "5.4", "4.0", "3.8"]),
        (
            "Gross fixed capital formation",
            ["354.9", "3.0", "13.2", "12.0", "7.3", "7.4"],
        ),
        ("Final domestic demand", ["1 435.4", "4.7", "6.2", "6.5", "4.7", "4.4"]),
        ("Stockbuilding", ["51.3", "0.6", "-0.1", "1.2", "0.5", "0.0"]),
        (
            "Current account balance (% of GDP)",
            ["", "-1.0", "-1.2", "-2.0", "-2.0", "-2.2"],
        ),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 448 + row_index * 22
        page.insert_text((45 if row_index == 0 else 58, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            if not value:
                continue
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text(
        (40, 622),
        "1. Contributions to changes in real GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 640), "Source: OECD Economic Outlook 118 database.", fontsize=9
    )
    page.insert_text((405, 660), "StatLink https://stat.link/6ptr2h", fontsize=9)
    page.insert_text(
        (40, 708),
        "The fiscal deficit is expected to narrow gradually, while monetary policy interest rates are on hold",
        fontsize=16,
    )
    page.insert_textbox(
        fitz.Rect(40, 742, 585, 860),
        (
            "After bringing the policy rate to 2.25% in March 2025, the central bank paused its easing cycle "
            "despite inflation declining substantially in 2025. The fiscal deficit is expected to narrow "
            "gradually despite robust spending growth."
        ),
        fontsize=13,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_with_heading_bounds_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_textbox(
        fitz.Rect(40, 40, 660, 120),
        (
            "Health inequalities between men and women are also linked to gendered health risks. "
            "Women are more likely to experience physical and mental health impacts of gender-based violence."
        ),
        fontsize=12,
        lineheight=1.2,
    )
    page.insert_text(
        (40, 154),
        "Table 2.3. Dashboard on protective and risk factors for health, 2023 (or nearest year)",
        fontsize=16,
    )
    x0, y0, x1, y1 = 60, 190, 640, 610
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [130, 215, 300, 385, 470, 555]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0), width=0.6)
    for y in range(230, 611, 28):
        page.draw_line((x0, y), (x1, y), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text((82, 214), "Country", fontsize=11)
    page.insert_text((180, 214), "Smoking (%)", fontsize=11)
    page.insert_text((266, 214), "Alcohol (%)", fontsize=11)
    page.insert_text((360, 214), "Overweight (%)", fontsize=11)
    page.insert_text((472, 214), "Vegetable consumption (%)", fontsize=11)
    rows = [
        ("OECD", "19", "8.5", "61", "53"),
        ("Australia", "9", "7", "53", "80"),
        ("Austria", "24", "18", "60", "39"),
        ("Belgium", "14", "11", "53", "72"),
        ("Canada", "10", "7", "63", "71"),
        ("Chile", "16", "16", "70", "0"),
    ]
    for idx, row in enumerate(rows):
        y = 252 + idx * 28
        page.insert_text((72, y), row[0], fontsize=11)
        page.insert_text((175, y), row[1], fontsize=11)
        page.insert_text((270, y), row[2], fontsize=11)
        page.insert_text((372, y), row[3], fontsize=11)
        page.insert_text((520, y), row[4], fontsize=11)
    page.insert_text((40, 648), "References", fontsize=14)
    page.insert_textbox(
        fitz.Rect(40, 672, 660, 820),
        (
            "OECD (2024), Rethinking Health System Performance Assessment: A Renewed Framework, OECD Publishing, Paris, "
            "https://doi.org/10.1787/107182c8.\n"
            "OECD/The Health Foundation (2025), How Do Health System Features Influence Health System Performance?, OECD Publishing, Paris."
        ),
        fontsize=11,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_title_note_and_right_edge_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((530, 40), "35 |", fontsize=12)
    page.insert_text(
        (40, 82),
        "Table 2.2. Measured in potential years of life lost, cancer in women and external causes are the leading killers",
        fontsize=16,
    )
    page.insert_text(
        (40, 110),
        "Ranking of top ten diseases by absolute difference (men-women) in potential years of life lost (PYLL)",
        fontsize=12,
    )
    x0, y0, x1, y1 = 60, 150, 650, 330
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [220, 360, 480, 600]:
        page.draw_line((x, y0), (x, y1), color=(0.6, 0.6, 0.6), width=0.6)
    for y in range(182, 331, 28):
        page.draw_line((x0, y), (x1, y), color=(0.75, 0.75, 0.75), width=0.5)
    headers = [
        (88, 170, "Causes¹"),
        (265, 170, "Men"),
        (395, 170, "Women"),
        (505, 170, "Share² among women"),
    ]
    for x, y, text in headers:
        page.insert_text((x, y), text, fontsize=11)
    rows = [
        ("External causes", "2 028", "711", "21% (2)"),
        ("Cardiovascular diseases", "1 268", "556", "16% (3)"),
        ("Neoplasms", "1 215", "1 061", "31% (1)"),
    ]
    for idx, row in enumerate(rows):
        y = 205 + idx * 28
        page.insert_text((72, y), row[0], fontsize=11)
        page.insert_text((282, y), row[1], fontsize=11)
        page.insert_text((408, y), row[2], fontsize=11)
        page.insert_text((560, y), row[3], fontsize=11)
    page.insert_textbox(
        fitz.Rect(42, 248, 655, 436),
        (
            "Note: PYLL is a measure of the impact of different mortality causes for those aged 0-74, "
            "putting a higher weight on premature deaths among younger individuals. OECD averages are "
            "weighted with the 2022 OECD historical population data, using country rates age-standardised "
            "to the 2015 OECD population."
        ),
        fontsize=11,
        lineheight=1.15,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_continuation_header_pdf(path: Path) -> None:
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
    rows = [
        ("Netherlands", "16", "11", "35", "16", "51", "46", "10", "13", "51", "62"),
        ("New Zealand", "8", "6", "", "", "", "", "20", "22", "95", "96"),
        ("Norway", "8", "8", "43", "32", "59", "44", "34", "42", "59", "74"),
        ("Peru*", "2", "1", "", "", "", "", "32", "37", "", ""),
    ]
    for idx, row in enumerate(rows):
        y = 120 + idx * 22
        page.insert_text((48, y), row[0], fontsize=8.5)
        xs = [134, 174, 204, 250, 303, 348, 394, 440, 493, 539]
        for x, value in zip(xs, row[1:]):
            if value:
                page.insert_text((x, y), value, fontsize=8.5)
    doc.save(path.as_posix())
    doc.close()

def _build_lattice_right_edge_table_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (42, 474),
        "Table 2. Accession candidate and Key Partner country ISO codes",
        fontsize=16,
    )
    x0, y0, x1, y1 = 42, 490, 560, 570
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [180, 280, 420]:
        page.draw_line((x, y0), (x, y1), color=(0.7, 0.7, 0.7), width=0.6)
    for y in [515, 540]:
        page.draw_line((x0, y), (x1, y), color=(0.7, 0.7, 0.7), width=0.6)
    rows = [
        ("Argentina", "ARG", "Indonesia", "IDN"),
        ("Brazil", "BRA", "Peru", "PER"),
        ("Croatia", "HRV", "Thailand", "THA"),
    ]
    for idx, row in enumerate(rows):
        y = 507 + idx * 25
        page.insert_text((52, y), row[0], fontsize=11)
        page.insert_text((190, y), row[1], fontsize=11)
        page.insert_text((285, y), row[2], fontsize=11)
        page.insert_text((452, y), row[3], fontsize=11)
    doc.save(path.as_posix())
    doc.close()

def _build_stream_country_table_split_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((18, 32), "116 |", fontsize=12)
    page.insert_text((40, 82), "Belgium: Demand, output and prices", fontsize=20)

    year_positions = [380, 430, 475, 520, 565, 610]
    for idx, year in enumerate(["2022", "2023", "2024", "2025", "2026", "2027"]):
        page.insert_text((year_positions[idx], 122), year, fontsize=11)
    page.insert_text((360, 140), "Current prices", fontsize=10)
    page.insert_text((500, 140), "Percentage changes, volume", fontsize=10)
    page.insert_text((366, 156), "EUR billion", fontsize=10)
    page.insert_text((534, 156), "(2020 prices)", fontsize=10)
    page.insert_text((40, 166), "Belgium", fontsize=11)

    rows = [
        ("GDP at market prices", ["561.3", "1.7", "1.1", "1.1", "1.1", "1.2"]),
        ("Private consumption", ["289.7", "1.1", "2.0", "1.9", "1.1", "0.9"]),
        ("Government consumption", ["131.6", "2.7", "1.8", "1.0", "1.0", "0.5"]),
        (
            "Gross fixed capital formation",
            ["134.3", "3.1", "2.0", "-1.1", "1.1", "1.4"],
        ),
        ("Final domestic demand", ["555.6", "1.9", "2.0", "0.9", "1.1", "0.9"]),
        ("Stockbuilding¹", ["18.8", "-0.8", "-0.5", "0.4", "0.0", "0.0"]),
        ("Total domestic demand", ["574.4", "1.1", "1.4", "1.4", "1.1", "0.9"]),
        (
            "Exports of goods and services",
            ["530.0", "-7.2", "-1.7", "-0.4", "1.1", "2.2"],
        ),
        (
            "Imports of goods and services",
            ["543.1", "-7.6", "-1.3", "0.0", "1.1", "1.8"],
        ),
        ("Net exports¹", ["-13.1", "0.6", "-0.3", "-0.3", "-0.1", "0.3"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 194 + row_index * 22
        page.insert_text((44 if row_index == 0 else 58, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text((40, 400), "Memorandum items", fontsize=11)
    memo_rows = [
        ("GDP deflator", ["", "5.5", "1.9", "2.4", "1.5", "1.8"]),
        (
            "Harmonised index of consumer prices",
            ["", "2.3", "4.3", "3.0", "1.6", "1.7"],
        ),
        (
            "Harmonised index of core inflation²",
            ["", "6.0", "3.4", "2.2", "2.3", "1.8"],
        ),
        (
            "Unemployment rate (% of labour force)",
            ["", "5.5", "5.7", "6.0", "6.0", "5.9"],
        ),
        (
            "General government financial balance (% of GDP)",
            ["", "-4.0", "-4.4", "-5.5", "-5.4", "-5.2"],
        ),
    ]
    for row_index, (label, values) in enumerate(memo_rows):
        y = 420 + row_index * 18
        page.insert_text((44, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            if value:
                page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text((44, 520), "Current account balance (% of GDP)", fontsize=11)
    for col_index, value in enumerate(["", "0.2", "-0.4", "-1.4", "-1.2", "-0.8"]):
        if value:
            page.insert_text((year_positions[col_index], 520), value, fontsize=11)

    page.insert_text(
        (40, 556),
        "1. Contributions to changes in real GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 574),
        "2. Core inflation excluding volatile items and temporary tax changes.",
        fontsize=9,
    )
    page.insert_text(
        (40, 592),
        "3. The current account balance reflects goods, services and income flows. This note continues on the next line for testing.",
        fontsize=9,
    )
    page.insert_text(
        (40, 610),
        "Continuation of note 3 to ensure wrapped footnotes remain attached to the crop.",
        fontsize=9,
    )
    page.insert_text(
        (40, 628), "Source: OECD Economic Outlook 118 database.", fontsize=9
    )
    page.insert_text((445, 648), "StatLink https://stat.link/example", fontsize=9)
    page.insert_textbox(
        fitz.Rect(40, 700, 650, 820),
        (
            "The fiscal stance is expected to remain prudent, with domestic demand gradually recovering and inflation "
            "converging toward target over the projection horizon."
        ),
        fontsize=13,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_boxed_prose_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 38), "20 |", fontsize=12)
    page.draw_rect(fitz.Rect(20, 90, 600, 820), color=(0.5, 0.0, 0.8), width=1.0)
    page.insert_text(
        (30, 120),
        "Box 1.4. Growing linkages between stablecoins and traditional finance",
        fontsize=18,
    )
    page.insert_textbox(
        fitz.Rect(30, 165, 590, 790),
        (
            "The market valuation of crypto-assets rose sharply over the past year and remains highly volatile.\n\n"
            "Fast growth, high concentration and non-negligible risks also permeate segments of crypto-assets that are intended to be safer.\n\n"
            "The total value of payments using stablecoins surpassed that of major traditional digital payment providers in 2024.\n\n"
            "The growth of crypto-asset exchange-traded products is likely to ease access to crypto-assets further."
        ),
        fontsize=15,
        lineheight=1.35,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_top_stacked_captioned_draw_charts_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 34), "34 |", fontsize=12)

    page.insert_text((36, 58), "Figure 1. Upper stacked draw chart", fontsize=16)
    page.draw_line((60, 120), (280, 120), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((60, 160), (280, 160), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_rect(
        fitz.Rect(62, 190, 268, 300),
        color=(0.2, 0.2, 0.2),
        fill=(0.8, 0.88, 0.98),
        width=1.0,
    )
    page.insert_text(
        (36, 332),
        "Source: synthetic upper chart source.",
        fontsize=10,
    )

    page.insert_text((36, 414), "Figure 2. Lower stacked draw chart", fontsize=16)
    page.draw_rect(
        fitz.Rect(62, 460, 520, 700),
        color=(0.8, 0.8, 0.8),
        fill=(0.96, 0.96, 0.96),
        width=1.0,
    )
    page.draw_line((84, 640), (494, 640), color=(0.25, 0.25, 0.25), width=1.0)
    page.draw_line((150, 640), (150, 520), color=(0.2, 0.2, 0.2), width=1.0)
    page.draw_line((150, 640), (260, 560), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line((260, 560), (360, 520), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line((360, 520), (464, 548), color=(0.1, 0.1, 0.1), width=1.0)
    page.insert_text((36, 726), "Source: synthetic lower chart source.", fontsize=10)

    doc.save(path.as_posix())
    doc.close()

def _build_contents_like_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    entries = [
        ("Acknowledgements", "7", 18, 20),
        ("Editorial  Resilient growth but with increasing fragilities", "9", 18, 20),
        ("1. General assessment of the macroeconomic situation", "11", 18, 20),
        ("Introduction", "11", 14, 40),
        ("Recent Developments", "13", 14, 40),
        ("Projections", "28", 14, 40),
        ("Risks", "33", 14, 40),
        ("Policies", "45", 14, 40),
        ("References", "61", 14, 40),
        ("2. Time for a Regulatory Reset?", "67", 18, 20),
        ("Summary", "67", 14, 40),
        (
            "The productivity slowdown has been underpinned by a decline in economic dynamism",
            "68",
            14,
            40,
        ),
        ("The case for a regulatory reset", "69", 14, 40),
        ("Executing the regulatory reset", "79", 14, 40),
        ("References", "96", 14, 40),
        (
            "3. Developments in individual OECD and selected non-member economies",
            "105",
            18,
            20,
        ),
        ("Argentina", "106", 14, 40),
        ("Australia", "109", 14, 40),
        ("Austria", "112", 14, 40),
        ("Belgium", "115", 14, 40),
    ]
    y = 46
    for text, page_no, font_size, x in entries:
        page.insert_text((x, y), text, fontsize=font_size)
        page.insert_textbox(
            fitz.Rect(500, y - 18, 595, y + 4),
            page_no,
            fontsize=font_size,
            align=fitz.TEXT_ALIGN_RIGHT,
        )
        y += 28 if font_size >= 18 else 24
    doc.save(path.as_posix())
    doc.close()

def _table_candidate(**overrides) -> _TableCandidate:
    candidate = _TableCandidate(
        bbox=(40.0, 120.0, 560.0, 620.0),
        method="stream",
        row_count=18,
        col_count=7,
        col_consistency=0.95,
        row_len_cv=0.35,
        non_empty_cells=90,
        total_cells=126,
        numeric_cells=70,
        numeric_ratio=0.32,
        avg_words_per_cell=1.8,
        avg_first_col_words=2.0,
        index_page_ratio=0.05,
        preview="GDP at market prices 263 104.8 0.6 2.4 2.4 2.2 2.2",
        text=(
            "Chile: Demand, output and prices\n"
            "GDP at market prices 263 104.8 0.6 2.4 2.4 2.2 2.2\n"
            "Private consumption 166 968.0 -4.8 0.9 2.7 1.7 1.5\n"
            "Government consumption 38 686.1 2.4 3.2 4.8 3.4 2.3\n"
            "Gross fixed capital formation 67 404.4 0.3 -1.8 6.8 5.1 3.0\n"
            "Final domestic demand 273 058.6 -2.5 0.6 4.1 2.8 2.0\n"
            "GDP deflator - 6.6 7.7 6.1 3.7 3.1\n"
            "Source: OECD Economic Outlook 118 database.\n"
            "https://stat.link/dpyrm2\n"
        ),
        text_len=520,
        line_count=9,
        avg_line_len=44.0,
        text_block_area_frac=0.18,
        text_block_line_count=9,
        text_block_avg_line_len=28.0,
        caption_hint=False,
        figure_context_hint=False,
        wide_figure_context_hint=False,
        area_frac=0.28,
        width_frac=0.84,
        height_frac=0.44,
        aspect=1.04,
    )
    return _TableCandidate(**{**candidate.__dict__, **overrides})

class _ExplodingTriageDoc:
    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int):
        raise RuntimeError(f"triage failed on page {index}")

__all__ = [name for name in globals() if name not in {'__name__', '__annotations__', '__doc__', '__spec__', '__file__', '__package__', '__loader__', '__cached__', '__builtins__'}]

