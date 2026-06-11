# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "builders.py")

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
