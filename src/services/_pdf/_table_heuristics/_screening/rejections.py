from __future__ import annotations

import math
import re
from typing import List, Tuple

from ..policy import (
    EMAIL_ADDRESS_RX,
    TABLE_CONTACT_MAX_COLS,
    TABLE_CONTACT_MAX_NUMERIC_RATIO,
    TABLE_CONTACT_MIN_AREA_FRAC,
    TABLE_CONTACT_MIN_AVG_LINE_LEN,
    TABLE_CONTACT_MIN_LINES,
    TABLE_CONTENTS_GRID_MAX_AVG_LINE_LEN,
    TABLE_CONTENTS_GRID_MAX_AVG_WORDS,
    TABLE_CONTENTS_GRID_MAX_COLS,
    TABLE_CONTENTS_GRID_MAX_FIRST_COL_WORDS,
    TABLE_CONTENTS_GRID_MAX_NUMERIC_RATIO,
    TABLE_CONTENTS_GRID_MIN_AREA,
    TABLE_CONTENTS_GRID_MIN_COLS,
    TABLE_CONTENTS_GRID_MIN_NUMBERED_LINES,
    TABLE_CONTENTS_GRID_MIN_NUMERIC_RATIO,
    TABLE_CONTENTS_GRID_MIN_ROWS,
    TABLE_CONTENTS_GRID_MIN_UPPERCASE_SHORT_RATIO,
    TABLE_CONTENTS_MAX_AVG_WORDS_PER_CELL,
    TABLE_CONTENTS_MAX_FILLED_CELLS_PER_ROW,
    TABLE_CONTENTS_MAX_FIRST_COL_WORDS,
    TABLE_CONTENTS_MAX_NUMERIC_RATIO,
    TABLE_CONTENTS_MIN_COLS,
    TABLE_CONTENTS_MIN_NUMERIC_RATIO,
    TABLE_CONTENTS_MIN_ROWS,
    TABLE_FIGURE_FRAGMENT_COMPACT_MAX_AREA_FRAC,
    TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS,
    TABLE_FIGURE_FRAGMENT_MAX_AVG_WORDS_PER_CELL,
    TABLE_FIGURE_FRAGMENT_MAX_FILL_RATIO,
    TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO,
    TABLE_FIGURE_FRAGMENT_MIN_WIDE_COLS,
    TABLE_FRONT_MATTER_MAX_AVG_WORDS_PER_CELL,
    TABLE_FRONT_MATTER_MAX_COLS,
    TABLE_FRONT_MATTER_MAX_NUMERIC_RATIO,
    TABLE_FRONT_MATTER_MIN_AREA_FRAC,
    TABLE_FRONT_MATTER_TERMS,
    TABLE_INDEX_MAX_COLS,
    TABLE_INDEX_MIN_FIRST_COL_WORDS,
    TABLE_INDEX_MIN_ROWS,
    TABLE_INDEX_PAGE_RATIO,
    TABLE_MAX_ASPECT,
    TABLE_MIN_AREA_FRAC,
    TABLE_MIN_ASPECT,
    TABLE_MIN_COLS,
    TABLE_MIN_HEIGHT_FRAC,
    TABLE_MIN_NONEMPTY_CELLS,
    TABLE_MIN_ROWS,
    TABLE_MIN_TEXT_CHARS,
    TABLE_MIN_WIDTH_FRAC,
    TABLE_PROSE_BOX_LINECOUNT_EXTRA,
    TABLE_PROSE_BOX_MAX_FILLED_CELLS_PER_ROW,
    TABLE_PROSE_BOX_MAX_LINECOUNT_ROW_MULT,
    TABLE_PROSE_BOX_MAX_NUMERIC_RATIO,
    TABLE_PROSE_BOX_MIN_COLS,
    TABLE_PROSE_BOX_MIN_FIRST_COL_WORDS,
    TABLE_PROSE_BOX_MIN_ROWS,
    TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AREA,
    TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AVG_LINE_LEN,
    TABLE_REFERENCE_MAX_COLS,
    TABLE_REFERENCE_MAX_FILLED_CELLS_PER_ROW,
    TABLE_REFERENCE_MAX_NUMERIC_RATIO,
    TABLE_REFERENCE_MIN_AVG_LINE_LEN,
    TABLE_REFERENCE_MIN_AVG_WORDS_PER_CELL,
    TABLE_REFERENCE_MIN_FIRST_COL_WORDS,
    TABLE_REFERENCE_MIN_NUMBERED_HITS,
    TABLE_REFERENCE_MIN_ROWS,
    TABLE_REFERENCE_MIN_TERM_HITS,
    TABLE_REFERENCE_MIN_URL_HITS,
    TABLE_REFERENCE_MIN_YEAR_HITS,
    TABLE_REFERENCE_TERMS,
    TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS,
    TABLE_SECTION_LIST_MAX_AVG_LINE_LEN,
    TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL,
    TABLE_SECTION_LIST_MAX_COLS,
    TABLE_SECTION_LIST_MAX_NARROW_ASPECT,
    TABLE_SECTION_LIST_MAX_NUMERIC_RATIO,
    TABLE_SECTION_LIST_MIN_FRAGMENTED_DOT_HITS,
    TABLE_SECTION_LIST_MIN_ROWS,
    TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO,
    TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS,
    TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA,
    TABLE_STREAM_INFOBOX_MAX_AVG_WORDS,
    TABLE_STREAM_INFOBOX_MAX_COLS,
    TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO,
    TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV,
    TABLE_STREAM_INFOBOX_MIN_AREA,
    TABLE_STREAM_INFOBOX_MIN_LINES,
    TABLE_STREAM_INFOBOX_MIN_ROWS,
    TABLE_STREAM_LIST_MAX_AREA_FRAC,
    TABLE_STREAM_LIST_MAX_AVG_WORDS,
    TABLE_STREAM_LIST_MAX_COLS,
    TABLE_STREAM_LIST_MAX_NUMERIC_RATIO,
    TABLE_STREAM_LIST_MIN_ROWS,
    TABLE_STREAM_MAX_ROW_LEN_CV,
    TABLE_STREAM_MIN_COLS_FOR_LIKENESS,
    TABLE_STREAM_MIN_COL_CONSISTENCY,
    TABLE_STREAM_MIN_ROWS_FOR_LIKENESS,
    TABLE_STREAM_PANEL_MAX_AVG_WORDS,
    TABLE_STREAM_PANEL_MAX_COLS,
    TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO,
    TABLE_STREAM_PANEL_MIN_AREA_FRAC,
    TABLE_STREAM_PANEL_MIN_ROWS,
    TABLE_STREAM_SLIDE_CARD_LINE_PAD,
    TABLE_STREAM_SLIDE_CARD_MAX_AREA,
    TABLE_STREAM_SLIDE_CARD_MAX_AVG_WORDS,
    TABLE_STREAM_SLIDE_CARD_MAX_COLS,
    TABLE_STREAM_SLIDE_CARD_MAX_COL_CONSISTENCY,
    TABLE_STREAM_SLIDE_CARD_MAX_NUMERIC_RATIO,
    TABLE_STREAM_SLIDE_CARD_MIN_AREA,
    TABLE_STREAM_SLIDE_CARD_MIN_AVG_LINE_LEN,
    TABLE_STREAM_SLIDE_CARD_MIN_AVG_WORDS,
    TABLE_STREAM_SLIDE_CARD_MIN_LINES,
    TABLE_STREAM_SLIDE_CARD_MIN_ROWS,
    TABLE_STREAM_SLIDE_CARD_MIN_TEXT_BLOCK_AREA,
    TABLE_STREAM_SPARSE_MAX_COLS,
    TABLE_STREAM_SPARSE_MAX_LINES,
    TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO,
    TABLE_STREAM_SPARSE_MIN_AREA,
    TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY,
    TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO,
    TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO,
    TABLE_STREAM_TEXTBLOCK_MIN_AREA,
    TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTBLOCK_MIN_LINES,
    TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV,
    TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO,
    TABLE_STREAM_TEXTY_MIN_AREA,
    TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTY_MIN_COLS,
    TABLE_STREAM_TEXTY_MIN_LINES,
    TABLE_STREAM_TEXTY_MIN_ROWS,
    TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO,
    TABLE_TEXT_HEAVY_MIN_AVG_WORDS,
    TABLE_TEXT_HEAVY_MIN_ROWS,
    TABLE_VISUAL_QUOTE_MAX_ASPECT,
    TABLE_VISUAL_QUOTE_MAX_AVG_WORDS_PER_CELL,
    TABLE_VISUAL_QUOTE_MAX_COLS,
    TABLE_VISUAL_QUOTE_MAX_FILLED_CELLS_PER_ROW,
    TABLE_VISUAL_QUOTE_MAX_NUMERIC_RATIO,
    TABLE_VISUAL_QUOTE_MAX_ROWS,
    TABLE_VISUAL_QUOTE_MAX_TEXT_BLOCK_AREA,
    TABLE_VISUAL_QUOTE_MAX_TEXT_LEN,
    TABLE_VISUAL_QUOTE_MAX_WIDTH_FRAC,
    TABLE_VISUAL_QUOTE_MIN_HEIGHT_FRAC,
    TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO,
    TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN,
    TEXT_BLOCK_LOOSE_MIN_LINES,
    TEXT_BLOCK_MAX_NUMERIC_RATIO,
    TEXT_BLOCK_MIN_AREA_FRAC,
    TEXT_BLOCK_MIN_AVG_LINE_LEN,
    TEXT_BLOCK_MIN_LINES,
)

from ..models import _TableCandidate

def _validate_table_candidate(cand: _TableCandidate) -> Tuple[bool, str]:
    if cand.method == "image":
        if cand.area_frac < 0.75:
            return False, "image_table_too_small"
        if cand.row_count < 20 or cand.col_count < 5:
            return False, "image_table_too_few_grid_groups"
        if cand.aspect < 1.2 or cand.aspect > 3.5:
            return False, "image_table_extreme_aspect"
        return True, ""
    if cand.row_count < TABLE_MIN_ROWS or cand.col_count < TABLE_MIN_COLS:
        return False, "too_few_rows_cols"
    if cand.non_empty_cells < TABLE_MIN_NONEMPTY_CELLS:
        return False, "too_few_cells"
    if cand.text_len < TABLE_MIN_TEXT_CHARS:
        return False, "no_text"
    if (
        cand.area_frac < TABLE_MIN_AREA_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_small"
    if (
        cand.aspect < TABLE_MIN_ASPECT or cand.aspect > TABLE_MAX_ASPECT
    ) and cand.text_len < TABLE_MIN_TEXT_CHARS * 3:
        return False, "extreme_aspect"
    if (
        cand.width_frac < TABLE_MIN_WIDTH_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_narrow"
    if (
        cand.height_frac < TABLE_MIN_HEIGHT_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_short"
    if _contents_like(cand):
        return False, "contents_like"
    if _section_list_like(cand):
        return False, "section_list"
    if _contents_grid_like(cand):
        return False, "contents_grid"
    if _reference_block_like(cand):
        return False, "reference_block"
    if _front_matter_like(cand):
        return False, "front_matter"
    if _contact_block_like(cand):
        return False, "contact_block"
    if _prose_box_like(cand):
        return False, "prose_box"
    if _visual_quote_page_like(cand):
        return False, "visual_quote_page"
    if cand.figure_context_hint:
        return False, "figure_caption_context"
    if _chart_fragment_like(cand):
        return False, "figure_chart_fragment"
    if cand.method == "stream":
        if (
            cand.row_count >= TABLE_TEXT_HEAVY_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.numeric_ratio <= TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO
            and cand.avg_words_per_cell >= TABLE_TEXT_HEAVY_MIN_AVG_WORDS
        ):
            return False, "text_heavy_stream"
        if (
            cand.row_count >= TABLE_INDEX_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.index_page_ratio >= TABLE_INDEX_PAGE_RATIO
            and cand.avg_first_col_words >= TABLE_INDEX_MIN_FIRST_COL_WORDS
        ):
            return False, "index_like"
        if _stream_slide_card_like(cand):
            return False, "stream_slide_card"
        if _stream_text_layout_like(cand):
            return False, "stream_text_layout"
        if _stream_text_block_like(cand):
            return False, "stream_text_block"
        if _stream_infobox_like(cand):
            return False, "stream_infobox"
        if _stream_list_like(cand):
            return False, "stream_list"
        if _stream_panel_like(cand):
            return False, "stream_panel"
        if _stream_sparse_text_like(cand):
            return False, "stream_sparse_text"
        if _stream_multilist_infographic_like(cand):
            return False, "stream_multilist_infographic"
        if _stream_low_consistency(cand):
            return False, "stream_low_consistency"
        if _text_block_like_loose(cand):
            return False, "text_block_like_loose"
        if _text_block_like(cand):
            return False, "text_block_like"
    return True, ""


def _stream_text_layout_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if (
        cand.row_count < TABLE_STREAM_TEXTY_MIN_ROWS
        or cand.col_count < TABLE_STREAM_TEXTY_MIN_COLS
    ):
        return False
    if cand.area_frac < TABLE_STREAM_TEXTY_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTY_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN:
        return False
    return True


def _stream_text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_TEXTBLOCK_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTBLOCK_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.col_consistency > TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY:
        return False
    if cand.row_len_cv < TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV:
        return False
    fill_ratio = cand.non_empty_cells / max(1, cand.total_cells)
    if fill_ratio > TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO:
        return False
    return True


def _stream_infobox_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_INFOBOX_MIN_AREA:
        return False
    if cand.row_count < TABLE_STREAM_INFOBOX_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_INFOBOX_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_INFOBOX_MAX_AVG_WORDS:
        return False
    if cand.line_count < TABLE_STREAM_INFOBOX_MIN_LINES:
        return False
    if cand.row_len_cv > TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV:
        return False
    return True


def _stream_list_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.row_count < TABLE_STREAM_LIST_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_LIST_MAX_COLS:
        return False
    if cand.area_frac > TABLE_STREAM_LIST_MAX_AREA_FRAC:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_LIST_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_LIST_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_panel_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_PANEL_MIN_AREA_FRAC:
        return False
    if cand.row_count < TABLE_STREAM_PANEL_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_PANEL_MAX_COLS:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_PANEL_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_slide_card_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_SLIDE_CARD_MIN_AREA:
        return False
    if cand.area_frac > TABLE_STREAM_SLIDE_CARD_MAX_AREA:
        return False
    if cand.row_count < TABLE_STREAM_SLIDE_CARD_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_SLIDE_CARD_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_SLIDE_CARD_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell < TABLE_STREAM_SLIDE_CARD_MIN_AVG_WORDS:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_SLIDE_CARD_MAX_AVG_WORDS:
        return False
    if cand.text_block_area_frac < TABLE_STREAM_SLIDE_CARD_MIN_TEXT_BLOCK_AREA:
        return False
    if cand.avg_line_len < TABLE_STREAM_SLIDE_CARD_MIN_AVG_LINE_LEN:
        return False
    if cand.col_consistency > TABLE_STREAM_SLIDE_CARD_MAX_COL_CONSISTENCY:
        return False
    return cand.line_count >= max(
        TABLE_STREAM_SLIDE_CARD_MIN_LINES,
        cand.row_count + TABLE_STREAM_SLIDE_CARD_LINE_PAD,
    )


def _stream_sparse_text_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_SPARSE_MIN_AREA:
        return False
    if cand.line_count > TABLE_STREAM_SPARSE_MAX_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO:
        return False
    if cand.col_count > TABLE_STREAM_SPARSE_MAX_COLS:
        return False
    return True


def _stream_multilist_infographic_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.area_frac < 0.4:
        return False
    if cand.row_count < 12 or cand.col_count < 5:
        return False
    if cand.avg_words_per_cell > 2.5:
        return False
    if cand.numeric_ratio > 0.12:
        return False
    if cand.line_count < 18 or cand.avg_line_len > 16.0:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < 12:
        return False
    numbered_list_hits = len(re.findall(r"\b[1-5]\.\s+\w", cand.text))
    if numbered_list_hits < 6:
        return False
    heading_hits = 0
    for line in lines:
        words = line.split()
        if 1 <= len(words) <= 3 and line[:1].isalpha() and line[:1].isupper():
            heading_hits += 1
    return heading_hits >= 3


def _stream_low_consistency(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if (
        cand.row_count < TABLE_STREAM_MIN_ROWS_FOR_LIKENESS
        or cand.col_count < TABLE_STREAM_MIN_COLS_FOR_LIKENESS
    ):
        return False
    if cand.col_consistency >= TABLE_STREAM_MIN_COL_CONSISTENCY:
        return False
    if cand.row_len_cv <= TABLE_STREAM_MAX_ROW_LEN_CV:
        return False
    return True


def _text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_MAX_NUMERIC_RATIO:
        return False
    return True


def _text_block_like_loose(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_LOOSE_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO:
        return False
    return True


def _filled_cells_per_row(cand: _TableCandidate) -> float:
    return cand.non_empty_cells / max(1, cand.row_count)


def _nonempty_text_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _terminal_page_number_hits(lines: List[str]) -> int:
    hits = 0
    for line in lines:
        if re.search(r"\b\d{1,3}\s*$", line):
            hits += 1
    return hits


def _contents_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_CONTENTS_MIN_ROWS:
        return False
    if cand.col_count < TABLE_CONTENTS_MIN_COLS:
        return False
    if _filled_cells_per_row(cand) > TABLE_CONTENTS_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio < TABLE_CONTENTS_MIN_NUMERIC_RATIO:
        return False
    if cand.numeric_ratio > TABLE_CONTENTS_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_CONTENTS_MAX_AVG_WORDS_PER_CELL:
        return False
    if cand.avg_first_col_words > TABLE_CONTENTS_MAX_FIRST_COL_WORDS:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_CONTENTS_MIN_ROWS:
        return False
    terminal_page_hits = 0
    for line in lines:
        if not re.search(r"\b\d{1,3}\s*$", line):
            continue
        numeric_tokens = re.findall(r"\b\d+(?:\.\d+)?\b", line)
        if len(numeric_tokens) != 1:
            continue
        if "." in numeric_tokens[0]:
            continue
        title = re.sub(r"\b\d{1,3}\s*$", "", line).strip(" .\t")
        if not title:
            continue
        terminal_page_hits += 1
    required_hits = max(6, math.ceil(len(lines) * 0.45))
    return terminal_page_hits >= required_hits


def _section_list_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_SECTION_LIST_MIN_ROWS:
        return False
    if cand.col_count > TABLE_SECTION_LIST_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_SECTION_LIST_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_SECTION_LIST_MIN_ROWS:
        return False
    avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
    if avg_line_len > TABLE_SECTION_LIST_MAX_AVG_LINE_LEN:
        return False
    short_line_ratio = sum(1 for line in lines if len(line) <= 60) / max(1, len(lines))
    if short_line_ratio < TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO:
        return False
    terminal_hits = _terminal_page_number_hits(lines)
    if terminal_hits >= TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS:
        return True
    dot_leader_hits = len(re.findall(r"(?:^|\n)\s*\d{1,2}\s*\.\s*\.\s*\.", cand.text))
    if dot_leader_hits >= 3:
        return True
    fragmented_dot_hits = len(re.findall(r"\.\s*\.", cand.text))
    if (
        fragmented_dot_hits >= TABLE_SECTION_LIST_MIN_FRAGMENTED_DOT_HITS
        and cand.area_frac <= TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS
        and cand.aspect <= TABLE_SECTION_LIST_MAX_NARROW_ASPECT
    ):
        return True
    if cand.text_block_area_frac < TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA:
        return False
    return (
        cand.numeric_ratio <= TABLE_CONTENTS_MIN_NUMERIC_RATIO / 2.0
        and cand.area_frac <= TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS
    )


def _contents_grid_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_CONTENTS_GRID_MIN_ROWS:
        return False
    if cand.col_count < TABLE_CONTENTS_GRID_MIN_COLS:
        return False
    if cand.col_count > TABLE_CONTENTS_GRID_MAX_COLS:
        return False
    if cand.area_frac < TABLE_CONTENTS_GRID_MIN_AREA:
        return False
    if cand.numeric_ratio < TABLE_CONTENTS_GRID_MIN_NUMERIC_RATIO:
        return False
    if cand.numeric_ratio > TABLE_CONTENTS_GRID_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_CONTENTS_GRID_MAX_AVG_WORDS:
        return False
    if cand.avg_first_col_words > TABLE_CONTENTS_GRID_MAX_FIRST_COL_WORDS:
        return False
    if cand.avg_line_len > TABLE_CONTENTS_GRID_MAX_AVG_LINE_LEN:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_CONTENTS_GRID_MIN_ROWS:
        return False
    numbered_line_hits = sum(
        1 for line in lines if len(re.findall(r"\b\d{1,2}\b", line)) >= 2
    )
    if numbered_line_hits < TABLE_CONTENTS_GRID_MIN_NUMBERED_LINES:
        return False
    uppercase_short_ratio = sum(
        1
        for line in lines
        if len(line) <= 42
        and any(char.isalpha() for char in line)
        and line == line.upper()
    ) / max(1, len(lines))
    return uppercase_short_ratio >= TABLE_CONTENTS_GRID_MIN_UPPERCASE_SHORT_RATIO


def _reference_block_like(cand: _TableCandidate) -> bool:
    lowered = cand.text.lower()
    url_hits = len(re.findall(r"https?://|doi\.org|www\.", lowered))
    year_hits = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", lowered))
    term_hits = sum(lowered.count(term) for term in TABLE_REFERENCE_TERMS)
    numbered_hits = len(re.findall(r"(?:^|\n)\s*\d+\.\s+", cand.text))
    if cand.method != "stream":
        return False
    if (
        numbered_hits >= TABLE_REFERENCE_MIN_NUMBERED_HITS
        and year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and (url_hits >= 1 or term_hits >= 1)
        and cand.numeric_ratio <= TABLE_REFERENCE_MAX_NUMERIC_RATIO
        and cand.avg_words_per_cell >= TABLE_REFERENCE_MIN_AVG_WORDS_PER_CELL
    ):
        return True
    if (
        url_hits >= TABLE_REFERENCE_MIN_URL_HITS
        and year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and cand.col_count <= TABLE_REFERENCE_MAX_COLS
    ):
        return True
    if cand.row_count < TABLE_REFERENCE_MIN_ROWS:
        return False
    if cand.col_count > TABLE_REFERENCE_MAX_COLS:
        return False
    if _filled_cells_per_row(cand) > TABLE_REFERENCE_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio > TABLE_REFERENCE_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_first_col_words < TABLE_REFERENCE_MIN_FIRST_COL_WORDS:
        return False
    if cand.avg_line_len < TABLE_REFERENCE_MIN_AVG_LINE_LEN:
        return False
    if url_hits >= TABLE_REFERENCE_MIN_URL_HITS:
        return year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
    return (
        year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and term_hits >= TABLE_REFERENCE_MIN_TERM_HITS
    )


def _front_matter_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    lowered = cand.text.lower()
    if not any(term in lowered for term in TABLE_FRONT_MATTER_TERMS):
        return False
    if cand.col_count > TABLE_FRONT_MATTER_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_FRONT_MATTER_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_FRONT_MATTER_MAX_AVG_WORDS_PER_CELL:
        return False
    return cand.area_frac >= TABLE_FRONT_MATTER_MIN_AREA_FRAC


def _contact_block_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.col_count > TABLE_CONTACT_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_CONTACT_MAX_NUMERIC_RATIO:
        return False
    if cand.area_frac < TABLE_CONTACT_MIN_AREA_FRAC:
        return False
    if cand.line_count < TABLE_CONTACT_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_CONTACT_MIN_AVG_LINE_LEN:
        return False
    return EMAIL_ADDRESS_RX.search(cand.text) is not None


def _prose_box_like(cand: _TableCandidate) -> bool:
    if cand.row_count < TABLE_PROSE_BOX_MIN_ROWS:
        return False
    if cand.col_count < TABLE_PROSE_BOX_MIN_COLS:
        return False
    filled_cells_per_row = _filled_cells_per_row(cand)
    if filled_cells_per_row > TABLE_PROSE_BOX_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio > TABLE_PROSE_BOX_MAX_NUMERIC_RATIO:
        return False
    if cand.text_block_area_frac < TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AREA:
        return False
    if cand.text_block_avg_line_len < TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AVG_LINE_LEN:
        return False
    if cand.avg_first_col_words < TABLE_PROSE_BOX_MIN_FIRST_COL_WORDS:
        return False
    max_line_count = max(
        cand.row_count + TABLE_PROSE_BOX_LINECOUNT_EXTRA,
        int(cand.row_count * TABLE_PROSE_BOX_MAX_LINECOUNT_ROW_MULT),
    )
    if cand.line_count > max_line_count:
        return False
    return True


def _visual_quote_page_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count > TABLE_VISUAL_QUOTE_MAX_ROWS:
        return False
    if cand.col_count > TABLE_VISUAL_QUOTE_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_VISUAL_QUOTE_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_VISUAL_QUOTE_MAX_AVG_WORDS_PER_CELL:
        return False
    if cand.text_len > TABLE_VISUAL_QUOTE_MAX_TEXT_LEN:
        return False
    if cand.aspect > TABLE_VISUAL_QUOTE_MAX_ASPECT:
        return False
    if cand.width_frac > TABLE_VISUAL_QUOTE_MAX_WIDTH_FRAC:
        return False
    if cand.height_frac < TABLE_VISUAL_QUOTE_MIN_HEIGHT_FRAC:
        return False
    if _filled_cells_per_row(cand) > TABLE_VISUAL_QUOTE_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.text_block_area_frac > TABLE_VISUAL_QUOTE_MAX_TEXT_BLOCK_AREA:
        return False
    return True


def _chart_fragment_like(cand: _TableCandidate) -> bool:
    if cand.method != "lattice":
        return False
    if not cand.wide_figure_context_hint:
        return False
    if cand.caption_hint:
        return False
    if cand.avg_words_per_cell > TABLE_FIGURE_FRAGMENT_MAX_AVG_WORDS_PER_CELL:
        return False
    fill_ratio = cand.non_empty_cells / max(1, cand.total_cells)
    compact_numeric_fragment = (
        cand.row_count <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS
        and cand.area_frac <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_AREA_FRAC
        and cand.numeric_ratio >= TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO
    )
    wide_sparse_fragment = (
        cand.col_count >= TABLE_FIGURE_FRAGMENT_MIN_WIDE_COLS
        and cand.row_count <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS + 5
        and cand.numeric_ratio >= TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO
        and fill_ratio <= TABLE_FIGURE_FRAGMENT_MAX_FILL_RATIO
    )
    return compact_numeric_fragment or wide_sparse_fragment
