"""Textual and false-positive screening for PDF visual candidates.

This module owns deterministic caption interpretation and rejection policies;
it performs no candidate sequencing or PDF output operations.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional

import pymupdf as fitz

from ..visual_heuristics import (
    CHART_CAPTION_HINTS,
    CHART_DENSE_RECOVERY_MIN_CHARS,
    CHART_DENSE_RECOVERY_MIN_LINES,
    _caption_blocks,
    _chart_is_label_dense_not_prose,
    _chart_text_heavy,
    _line_starts_with_caption_hint,
    _panel_chart_has_compact_stat_card_signal,
    _panel_chart_has_data_signal,
    _panel_chart_has_structured_card_signal,
    _panel_chart_is_label_dense_not_prose,
    _panel_component_looks_like_guidance_card,
)
from .raster import _RasterProbeCache, _embedded_visual_looks_photo_like

__all__ = [
    "_VISUAL_CONTEXT_LINE_RX",
    "_FIGURE_HINT_RX",
    "_BOX_HINT_RX",
    "_URL_REF_RX",
    "_SOURCE_OR_STATLINK_RX",
    "_EXPLANATORY_FIGURE_REF_RX",
    "_YEAR_RX",
    "_NUMBER_RX",
    "_TERMINAL_INTEGER_RX",
    "_BARE_TITLE_HEADING_RX",
    "_MID_SENTENCE_START_WORDS",
    "_iter_visual_context_lines",
    "_page_has_chart_caption_blocks",
    "_text_has_visual_context_hint",
    "_visual_nonempty_lines",
    "_caption_has_figure_hint",
    "_caption_looks_explanatory_figure_reference",
    "_caption_looks_bare_title_heading",
    "_caption_looks_mid_sentence_fragment",
    "_visual_candidate_looks_table_like",
    "_visual_candidate_looks_note_fragment",
    "_visual_candidate_looks_bare_heading_fragment",
    "_visual_candidate_looks_reference_or_prose",
    "_visual_candidate_looks_cover_art",
    "_visual_candidate_looks_section_opener_banner",
    "_visual_candidate_looks_photo_narrative_card",
    "_visual_candidate_looks_narrative_panel_card",
    "_visual_candidate_looks_inline_numbered_panel",
    "_next_figure_caption_below",
    "_visual_text_dense_recovery_allowed",
]

_VISUAL_CONTEXT_LINE_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|source|infographic)\b",
    re.IGNORECASE,
)
_FIGURE_HINT_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|infographic)\b",
    re.IGNORECASE,
)
_BOX_HINT_RX = re.compile(r"^\s*box\b", re.IGNORECASE)
_URL_REF_RX = re.compile(r"https?://|doi\.org|www\.", re.IGNORECASE)
_SOURCE_OR_STATLINK_RX = re.compile(r"(?im)(?:^|\n)\s*(?:source:|statlink\b)")
_EXPLANATORY_FIGURE_REF_RX = re.compile(
    r"^\s*(?:figure|fig\.|chart|exhibit|infographic)\s+\d+(?:\.\d+)?(?:\s*[,:\-]\s*|\s+)"
    r"(?:[\w’'/-]+\s+){0,8}"
    r"(?:is|was|are|were|shows?|showing|illustrates?|describes?|presents?|"
    r"reflects?|compares?|compared|highlights?|based\s+on)\b",
    re.IGNORECASE,
)
_YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_NUMBER_RX = re.compile(r"\b\d+(?:\.\d+)?\b")
_TERMINAL_INTEGER_RX = re.compile(r"\b\d{1,4}\s*$")
_BARE_TITLE_HEADING_RX = re.compile(
    r"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,2}$"
)
_MID_SENTENCE_START_WORDS = {
    "after",
    "although",
    "amid",
    "because",
    "but",
    "continue",
    "despite",
    "following",
    "growth",
    "however",
    "mainly",
    "monthly",
    "quarterly",
    "strong",
    "the",
    "top-up",
    "while",
}


def _iter_visual_context_lines(text: str, *, max_lines: int = 4, max_chars: int = 200):
    seen_lines = 0
    seen_chars = 0
    for raw_line in str(text or "").splitlines():
        normalized = raw_line.strip()
        if not normalized:
            continue
        yield normalized
        seen_lines += 1
        seen_chars += len(normalized)
        if seen_lines >= max_lines or seen_chars >= max_chars:
            break


def _page_has_chart_caption_blocks(
    blocks: List[tuple[float, float, float, float, str]],
) -> bool:
    for _x0, _y0, _x1, _y1, text in blocks:
        for normalized in _iter_visual_context_lines(text):
            normalized = normalized.lower()
            if _line_starts_with_caption_hint(normalized, CHART_CAPTION_HINTS):
                return True
    return False


def _text_has_visual_context_hint(text: str) -> bool:
    for normalized in _iter_visual_context_lines(text):
        if _VISUAL_CONTEXT_LINE_RX.match(normalized):
            return True
    return False


def _visual_nonempty_lines(text: str) -> List[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _caption_has_figure_hint(text: str) -> bool:
    return bool(_FIGURE_HINT_RX.match(str(text or "").strip()))


def _caption_looks_explanatory_figure_reference(text: str) -> bool:
    return bool(_EXPLANATORY_FIGURE_REF_RX.match(str(text or "").strip()))


def _caption_looks_bare_title_heading(text: str) -> bool:
    caption = str(text or "").strip()
    if not caption or _caption_has_figure_hint(caption):
        return False
    if any(ch.isdigit() for ch in caption):
        return False
    return bool(_BARE_TITLE_HEADING_RX.fullmatch(caption))


def _caption_looks_mid_sentence_fragment(text: str) -> bool:
    caption = str(text or "").strip()
    if not caption or _caption_has_figure_hint(caption):
        return False
    if caption.lower().startswith(("source:", "statlink")):
        return False
    if caption[0].islower() or caption[0] in "(+%":
        return True
    words = [word for word in re.split(r"\s+", caption) if word]
    if len(words) < 5:
        return False
    first = words[0].strip("“\"'([{").lower()
    return first in _MID_SENTENCE_START_WORDS


def _visual_candidate_looks_table_like(
    caption: str,
    text: str,
    *,
    kind: str = "",
    panel_data_signal: bool = False,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) < 6:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 3)
    terminal_numeric_hits = sum(
        1
        for line in lines
        if _TERMINAL_INTEGER_RX.search(line) and len(_NUMBER_RX.findall(line)) >= 1
    )
    single_token_numeric_hits = sum(
        1
        for line in lines
        if len(line.split()) == 1 and bool(_NUMBER_RX.fullmatch(line))
    )
    alpha_line_ratio = sum(
        1 for line in lines if any(ch.isalpha() for ch in line)
    ) / max(1, len(lines))
    mixed_alpha_numeric_hits = sum(
        1
        for line in lines
        if any(ch.isalpha() for ch in line) and bool(_NUMBER_RX.search(line))
    )
    dense_year_header = any(
        len(_YEAR_RX.findall(line)) >= 3 for line in lines[: min(4, len(lines))]
    )
    lower_text = text.lower()
    lower_lines = [line.lower() for line in lines]
    if (
        numeric_row_hits >= 4
        and avg_line_len <= 44.0
        and (short_line_ratio >= 0.15 or dense_year_header or len(lines) <= 8)
    ):
        return True
    if (
        dense_year_header
        and any("current prices" in line for line in lower_lines)
        and (
            any("percentage changes" in line for line in lower_lines)
            or any("volume" in line for line in lower_lines)
        )
        and (
            numeric_row_hits >= 1
            or "memorandum items" in lower_text
            or len(lines) >= 10
        )
    ):
        return True
    if (
        kind == "panel"
        and panel_data_signal
        and numeric_row_hits < 3
        and dense_year_header is False
        and alpha_line_ratio < 0.45
        and single_token_numeric_hits >= max(6, len(lines) // 3)
    ):
        return False
    if (
        kind == "panel"
        and panel_data_signal
        and len(lines) <= 12
        and numeric_row_hits == 0
        and terminal_numeric_hits >= 4
        and single_token_numeric_hits >= 4
        and alpha_line_ratio >= 0.2
        and mixed_alpha_numeric_hits >= 1
    ):
        return False
    if (
        terminal_numeric_hits >= max(6, math.ceil(len(lines) * 0.25))
        and short_line_ratio >= 0.55
        and avg_line_len <= 24.0
    ):
        return True
    if dense_year_header and numeric_row_hits >= 2 and avg_line_len <= 30.0:
        return True
    return (
        len(lines) >= 18
        and short_line_ratio >= 0.7
        and avg_line_len <= 18.0
        and numeric_row_hits >= 3
    )


def _visual_candidate_looks_note_fragment(
    caption: str,
    text: str,
    *,
    kind: str,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    lower_caption = caption_text.lower()
    if not caption_text:
        return False
    if not _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if (
        _panel_chart_has_data_signal(text)
        or _panel_chart_has_structured_card_signal(text)
        or _panel_component_looks_like_guidance_card(text)
        or _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
    ):
        return False
    lines = _visual_nonempty_lines(text)
    if not lines:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    numbered_hits = len(re.findall(r"(?m)^\s*\d+\.\s+", text))
    if lower_caption.startswith(("source:", "statlink")):
        return True
    if (
        _caption_looks_mid_sentence_fragment(caption_text)
        and len(lines) <= 10
        and avg_line_len <= 56.0
        and numeric_hits <= 10
    ):
        return True
    return (
        numbered_hits >= 1
        and len(lines) <= 8
        and avg_line_len <= 52.0
        and numeric_hits <= 12
    )


def _visual_candidate_looks_bare_heading_fragment(
    caption: str,
    text: str,
    *,
    kind: str,
    area_frac: float,
    aspect: float,
) -> bool:
    if kind != "panel":
        return False
    if not _caption_looks_bare_title_heading(caption):
        return False
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if (
        _panel_chart_has_data_signal(text)
        or _panel_chart_has_structured_card_signal(text)
        or _panel_component_looks_like_guidance_card(text)
        or _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
    ):
        return False
    lines = _visual_nonempty_lines(text)
    total_chars = sum(len(line) for line in lines)
    return total_chars <= 24 and area_frac <= 0.18 and aspect >= 1.4


def _visual_candidate_looks_reference_or_prose(
    caption: str,
    text: str,
    *,
    text_ratio: float,
) -> bool:
    explanatory_figure_reference = _caption_looks_explanatory_figure_reference(caption)
    if _caption_has_figure_hint(caption) and not explanatory_figure_reference:
        return False
    lines = _visual_nonempty_lines(text)
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    year_hits = len(_YEAR_RX.findall(text))
    url_hits = len(_URL_REF_RX.findall(text))
    numbered_hits = len(re.findall(r"(?m)^\s*\d+\.\s+", text))
    colon_hits = sum(1 for line in lines if ":" in line and len(line) <= 100)
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    sentence_hits = len(re.findall(r"[.!?;](?:\s|$)", text))
    if (
        explanatory_figure_reference
        and len(lines) >= 4
        and avg_line_len >= 55.0
        and text_ratio >= 0.18
    ):
        return True
    if len(lines) < 6:
        return False
    if (
        len(lines) >= 10
        and avg_line_len >= 26.0
        and text_ratio >= 0.16
        and numeric_hits <= max(8, len(lines) // 2)
        and not _panel_chart_has_data_signal(text)
        and not _panel_component_looks_like_guidance_card(text)
    ):
        return True
    if (
        url_hits == 0
        and len(lines) <= 18
        and avg_line_len <= 60.0
        and colon_hits >= 3
        and short_line_ratio >= 0.15
    ):
        return False
    if (
        url_hits >= 1
        and year_hits >= 2
        and (numbered_hits >= 2 or avg_line_len >= 42.0)
    ):
        return True
    if (
        _BOX_HINT_RX.match(str(caption or "").strip())
        and len(lines) >= 6
        and avg_line_len >= 32.0
        and text_ratio >= 0.2
    ):
        return True
    if (
        numbered_hits >= 2
        and len(lines) >= 18
        and avg_line_len >= 34.0
        and text_ratio >= 0.28
    ):
        return True
    if (
        len(lines) >= 16
        and avg_line_len >= 60.0
        and text_ratio >= 0.22
        and sentence_hits >= 4
        and not _SOURCE_OR_STATLINK_RX.search(text)
    ):
        return True
    if (
        len(lines) >= 18
        and avg_line_len >= 48.0
        and text_ratio >= 0.22
        and sentence_hits >= 3
        and numbered_hits >= 1
    ):
        return True
    return (
        len(lines) >= 12
        and avg_line_len >= 40.0
        and text_ratio >= 0.25
        and numeric_hits <= max(6, len(lines) // 3)
    )


def _visual_candidate_looks_cover_art(
    rect_candidate: fitz.Rect,
    page_rect: fitz.Rect,
    caption: str,
    *,
    area_frac: float,
    text_chars: int,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    width_frac = rect_candidate.width / max(1.0, page_rect.width)
    height_frac = rect_candidate.height / max(1.0, page_rect.height)
    top_frac = (rect_candidate.y0 - page_rect.y0) / max(1.0, page_rect.height)
    if area_frac < 0.12:
        return False
    if (
        area_frac >= 0.25
        and width_frac >= 0.6
        and height_frac >= 0.42
        and text_chars <= 90
        and len(caption_text) <= 24
        and len(caption_text.split()) <= 3
    ):
        return True
    if top_frac > 0.1:
        return False
    if height_frac > 0.35:
        return False
    return text_chars <= 80 and len(caption_text) <= 20


def _visual_candidate_looks_section_opener_banner(
    rect_candidate: fitz.Rect,
    page_rect: fitz.Rect,
    caption: str,
    text: str,
    *,
    kind: str,
    area_frac: float,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    if rect_candidate.y0 > page_rect.y0 + page_rect.height * 0.08:
        return False
    if rect_candidate.height > page_rect.height * 0.42:
        return False
    if area_frac < 0.12 or area_frac > 0.34:
        return False
    if rect_candidate.width / max(1.0, page_rect.width) < 0.65:
        return False
    caption_text = str(caption or "").strip()
    words = caption_text.split()
    if not caption_text or len(words) > 12:
        return False
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    lines = _visual_nonempty_lines(text)
    if not lines:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    short_line_ratio = sum(1 for line in lines if len(line) <= 20) / max(1, len(lines))
    fragmented_banner_text = (
        len(lines) >= 10
        and avg_line_len <= 14.0
        and short_line_ratio >= 0.7
        and numeric_hits <= 4
    )
    if (
        (_panel_chart_has_data_signal(text) and not fragmented_banner_text)
        or _panel_component_looks_like_guidance_card(text)
        or _panel_chart_has_structured_card_signal(text)
    ):
        return False
    return numeric_hits <= 2 and (
        (len(lines) <= 4 and total_chars <= 160 and avg_line_len <= 40.0)
        or (len(lines) <= 24 and total_chars <= 280 and avg_line_len <= 22.0)
    )


def _visual_candidate_looks_photo_narrative_card(
    page: fitz.Page,
    rect_candidate: fitz.Rect,
    caption: str,
    *,
    caption_rect: Optional[fitz.Rect],
    kind: str,
    area_frac: float,
    aspect: float,
    text_chars: int,
    panel_data_signal: bool,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    if panel_data_signal:
        return False
    if area_frac < 0.22 or area_frac > 0.5:
        return False
    if aspect < 0.72 or aspect > 1.25:
        return False
    if text_chars > 40:
        return False
    if caption_rect is None:
        return False
    inter = caption_rect & rect_candidate
    if inter.is_empty or inter.get_area() < caption_rect.get_area() * 0.9:
        return False
    words = [word for word in str(caption or "").split() if word]
    if len(words) < 5 or len(words) > 16:
        return False
    if ":" in str(caption or ""):
        return False
    return _embedded_visual_looks_photo_like(
        page,
        rect_candidate,
        probe_cache=probe_cache,
    )


def _visual_candidate_looks_narrative_panel_card(
    caption: str,
    text: str,
    *,
    kind: str,
    text_ratio: float,
    area_frac: float,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    if area_frac < 0.12:
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) < 8:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 2)
    sentence_hits = len(re.findall(r"[.!?;](?:\s|$)", text))
    colon_hits = sum(1 for line in lines if ":" in line and len(line) <= 100)
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    long_line_hits = sum(1 for line in lines if len(line) >= 30)
    has_data_signal = _panel_chart_has_data_signal(text)
    if _panel_component_looks_like_guidance_card(text):
        return False
    structured_card_signal = _panel_chart_has_structured_card_signal(text)
    if structured_card_signal and sentence_hits < 3:
        return False
    if _panel_chart_has_compact_stat_card_signal(text):
        return False
    fragmented_prose = text_ratio >= 0.3 and sentence_hits >= 3 and long_line_hits >= 8
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if colon_hits >= 3 and short_line_ratio >= 0.2:
        return False
    if has_data_signal and (
        numeric_row_hits >= 3 or (short_line_ratio >= 0.35 and not fragmented_prose)
    ):
        return False
    return (
        text_ratio >= 0.22
        and sentence_hits >= 2
        and numeric_hits <= max(12, len(lines))
        and (avg_line_len >= 28.0 or fragmented_prose)
    )


def _visual_candidate_looks_inline_numbered_panel(
    caption: str,
    text: str,
    *,
    note_included: bool,
    area_frac: float,
    aspect: float,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    if not re.search(r"\b\d\b\s*$", caption_text):
        return False
    if _YEAR_RX.search(caption_text):
        return False
    if not note_included:
        return False
    if area_frac > 0.24 or aspect < 1.8 or aspect > 2.8:
        return False
    if not _SOURCE_OR_STATLINK_RX.search(text):
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) > 10:
        return False
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 3)
    return numeric_row_hits <= 2


def _next_figure_caption_below(
    page: fitz.Page,
    cap_rect: fitz.Rect,
    *,
    blocks: Optional[List[tuple[float, float, float, float, str]]] = None,
) -> Optional[fitz.Rect]:
    for other_rect, other_text in _caption_blocks(
        page, CHART_CAPTION_HINTS, blocks=blocks
    ):
        if other_rect.y0 <= cap_rect.y0 + 8.0:
            continue
        if not _caption_has_figure_hint(other_text):
            continue
        return other_rect
    return None


def _visual_text_dense_recovery_allowed(
    kind: str,
    text: str,
    text_lines: int,
    text_chars: int,
    text_ratio: float,
) -> bool:
    lines = _visual_nonempty_lines(text)
    avg_line_len = text_chars / max(1, text_lines)
    numeric_hits = len(_NUMBER_RX.findall(text))
    return (
        _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
        or (
            text_lines >= CHART_DENSE_RECOVERY_MIN_LINES
            and text_chars >= CHART_DENSE_RECOVERY_MIN_CHARS
            and not _chart_text_heavy(text_lines, text_chars, text_ratio)
        )
        or (
            kind == "draw"
            and bool(_SOURCE_OR_STATLINK_RX.search(text))
            and text_lines >= 12
            and numeric_hits >= 10
            and avg_line_len <= 42.0
            and text_ratio <= 0.68
            and not _caption_looks_explanatory_figure_reference(
                lines[0] if lines else ""
            )
        )
    )
