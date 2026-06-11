"""Compatibility surface for PDF table candidate screening."""

from __future__ import annotations

# ruff: noqa: F401

__all__ = [
    "_TableDedupeSpatialIndex",
    "_dedupe_table_candidates",
    "_table_quality",
    "_validate_table_candidate",
]

from ._screening.deduplication import (
    _TableDedupeSpatialIndex,
    _dedupe_table_candidates,
    _prefer_inner_lattice_table,
    _preferred_duplicate_table,
    _table_area,
    _table_containment_ratio,
    _table_iou,
    _table_quality,
    _table_sort_key,
)
from ._screening.metrics import (
    _avg_first_col_words,
    _avg_words_per_cell,
    _cell_is_page_number,
    _cell_words,
    _col_consistency,
    _has_caption_hint,
    _has_figure_context_hint,
    _index_page_ratio,
    _numeric_char_ratio,
    _row_len_cv,
    _row_nonempty_counts,
    _row_text_lengths,
)
from ._screening.rejections import (
    _chart_fragment_like,
    _contact_block_like,
    _contents_grid_like,
    _contents_like,
    _filled_cells_per_row,
    _front_matter_like,
    _nonempty_text_lines,
    _prose_box_like,
    _reference_block_like,
    _section_list_like,
    _stream_infobox_like,
    _stream_list_like,
    _stream_low_consistency,
    _stream_multilist_infographic_like,
    _stream_panel_like,
    _stream_slide_card_like,
    _stream_sparse_text_like,
    _stream_text_block_like,
    _stream_text_layout_like,
    _terminal_page_number_hits,
    _text_block_like,
    _text_block_like_loose,
    _validate_table_candidate,
    _visual_quote_page_like,
)
