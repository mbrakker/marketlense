# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_panel_label_block_looks_like_footer_banner_accepts_mixed_year_page_line() -> (
    None
):
    assert (
        _panel_label_block_looks_like_footer_banner(
            fitz.Rect(28.0, 503.0, 114.0, 519.0),
            "Kantar 2025 | 9",
            page_rect=fitz.Rect(0.0, 0.0, 960.0, 540.0),
        )
        is True
    )

def test_panel_should_clamp_to_internal_caption_for_stacked_panel_pair() -> None:
    lower = _ChartRect(
        rect=fitz.Rect(42.5, 384.5, 552.8, 785.1),
        kind="panel",
        caption="Private labels go premium",
        caption_rect=fitz.Rect(110.0, 517.5, 330.0, 538.0),
    )
    upper = _ChartRect(
        rect=fitz.Rect(42.5, 385.8, 552.8, 556.1),
        kind="panel",
        caption="44% of shoppers are buying private-label",
        caption_rect=fitz.Rect(88.0, 437.0, 300.0, 458.0),
    )

    assert _panel_should_clamp_to_internal_caption(lower, [lower, upper]) is True
    assert _panel_should_clamp_to_internal_caption(upper, [lower, upper]) is False

def test_panel_candidate_shadowed_by_heading_candidate_for_metric_stub_panel() -> None:
    panel = _ChartRect(
        rect=fitz.Rect(500.0, 236.0, 808.0, 510.0),
        kind="panel",
        caption="Probably 20%",
        caption_rect=fitz.Rect(568.0, 299.0, 672.0, 335.0),
    )
    heading = _ChartRect(
        rect=fitz.Rect(497.0, 95.0, 790.0, 515.0),
        kind="heading",
        caption="Consumer likelihood to use Buy Now, Pay Later loans in 2026",
        caption_rect=fitz.Rect(506.0, 111.0, 756.0, 156.0),
    )

    assert (
        _panel_candidate_shadowed_by_heading_candidate(panel, [panel, heading]) is True
    )
    assert (
        _panel_candidate_shadowed_by_heading_candidate(heading, [panel, heading])
        is False
    )

def test_panel_candidate_shadowed_by_larger_panel_for_compact_banner() -> None:
    compact_panel = _ChartRect(
        rect=fitz.Rect(40.0, 380.0, 555.0, 490.0),
        kind="panel",
        caption="of shoppers are buying private-label or low-",
        caption_rect=fitz.Rect(260.0, 407.0, 523.0, 423.0),
    )
    larger_panel = _ChartRect(
        rect=fitz.Rect(42.0, 518.0, 553.0, 785.0),
        kind="panel",
        caption="Private labels go premium",
        caption_rect=fitz.Rect(214.0, 527.0, 381.0, 544.0),
    )

    assert (
        _panel_candidate_shadowed_by_larger_panel(
            compact_panel,
            [compact_panel, larger_panel],
            "44%\nof shoppers are buying private-label or low-\ncost brands over name brands",
        )
        is True
    )

def test_panel_candidate_shadowed_by_larger_panel_keeps_equal_stacked_cards() -> None:
    upper_panel = _ChartRect(
        rect=fitz.Rect(36.0, 318.0, 559.0, 429.0),
        kind="panel",
        caption="of shoppers make purchases based on AI",
        caption_rect=fitz.Rect(421.0, 352.0, 827.0, 364.0),
    )
    lower_panel = _ChartRect(
        rect=fitz.Rect(36.0, 429.0, 559.0, 540.0),
        kind="panel",
        caption="are willing to order products via AI tools",
        caption_rect=fitz.Rect(421.0, 463.0, 851.0, 497.0),
    )

    assert (
        _panel_candidate_shadowed_by_larger_panel(
            upper_panel,
            [upper_panel, lower_panel],
            "46%\nof shoppers make purchases based on AI recommendations\nEarly findings: What matters to today's consumers, 2026",
        )
        is False
    )

def test_panel_stacked_bottom_clip_y_prefers_next_lower_panel() -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    upper = _ChartRect(
        rect=fitz.Rect(42.5, 385.8, 552.8, 556.1),
        kind="panel",
        caption="44% of shoppers are buying private-label",
        caption_rect=fitz.Rect(88.0, 407.0, 300.0, 428.0),
    )
    lower = _ChartRect(
        rect=fitz.Rect(42.5, 384.5, 552.8, 785.1),
        kind="panel",
        caption="Private labels go premium",
        caption_rect=fitz.Rect(110.0, 517.5, 330.0, 538.0),
    )

    try:
        assert _panel_stacked_bottom_clip_y(page, upper, [upper, lower]) == 517.5
        assert _panel_stacked_bottom_clip_y(page, lower, [upper, lower]) is None
    finally:
        doc.close()

def test_panel_stacked_bottom_clip_y_skips_clip_when_bottom_axis_band_exists() -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((120, 540), "Retail Media", fontsize=10)
    page.insert_text((220, 540), "CTV", fontsize=10)
    page.insert_text((300, 540), "Social", fontsize=10)

    upper = _ChartRect(
        rect=fitz.Rect(42.5, 385.8, 552.8, 556.1),
        kind="panel",
        caption="Top Digital Environments",
        caption_rect=fitz.Rect(88.0, 407.0, 300.0, 428.0),
    )
    lower = _ChartRect(
        rect=fitz.Rect(42.5, 384.5, 552.8, 785.1),
        kind="panel",
        caption="Social Media",
        caption_rect=fitz.Rect(110.0, 532.0, 330.0, 552.0),
    )

    try:
        assert _panel_stacked_bottom_clip_y(page, upper, [upper, lower]) is None
    finally:
        doc.close()

def test_panel_chart_has_data_signal_accepts_dense_axis_only_panel() -> None:
    text = (
        "Better quality\n"
        "Innovative\n"
        "Capture my attention\n"
        "Too much advertising\n"
        "Intrusive\n"
        "Dull and boring\n"
        "Repetitive\n"
        "Excessive targeting\n"
        "Something I try to ignore\n"
        "Trustworthy\n"
        "Relevant and useful\n"
        "Fun and entertaining\n"
        "Total Average\n"
        "DOOH\n"
    )

    assert _panel_chart_has_data_signal(text) is True

def test_panel_preferred_local_title_line_prefers_near_component_title(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-local-title-preference.pdf"
    _build_panel_local_title_preference_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        title = _panel_preferred_local_title_line(
            page,
            fitz.Rect(40.0, 126.0, 320.0, 300.0),
        )
    finally:
        doc.close()

    assert title is not None
    assert title.text == "Top Digital Formats"

def test_panel_preferred_local_title_line_prefers_internal_card_title_over_metric_fragment(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-internal-title-preference.pdf"
    _build_panel_internal_title_preference_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        title = _panel_preferred_local_title_line(
            page,
            fitz.Rect(40.0, 150.0, 360.0, 320.0),
        )
    finally:
        doc.close()

    assert title is not None
    assert title.text == "Private labels go premium"

def test_panel_title_looks_short_proper_name_accepts_country_like_title() -> None:
    assert _panel_title_looks_short_proper_name("Belgium") is True
    assert _panel_title_looks_short_proper_name("New Zealand") is True
    assert _panel_title_looks_short_proper_name("HIGH") is False
    assert _panel_title_looks_short_proper_name("2025") is False

def test_panel_title_slice_bounds_separates_peer_titles(tmp_path) -> None:
    pdf_path = tmp_path / "panel-title-slices.pdf"
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 150), "Advertising equity", fontsize=22)
    page.insert_text((435, 150), "Advertising attitudes", fontsize=22)
    doc.save(pdf_path.as_posix())
    doc.close()

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        bounds = _panel_title_slice_bounds(page, fitz.Rect(435, 130, 595, 160))
    finally:
        doc.close()

    assert bounds is not None
    left, right = bounds
    assert left > 250.0
    assert right <= 960.0

def test_collect_candidates_merges_multiline_metric_band_with_quote_card(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "metric-band-quote-card.pdf"
    out_dir = tmp_path / "out"
    _build_panel_metric_band_with_quote_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="metric-band-quote-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert charts[0].bbox[0] < 60.0
    assert charts[0].bbox[1] < 150.0
    assert charts[0].bbox[3] > 320.0

def test_collect_candidates_keeps_dense_numeric_panel_chart(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "dense-numeric-panel-chart.pdf"
    out_dir = tmp_path / "out"
    _build_dense_numeric_panel_chart_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="dense-numeric-panel-chart",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert (
        "adjacencies to unsuitable gen ai content" in (charts[0].caption or "").lower()
    )
    assert charts[0].bbox[2] >= 648.0
    assert charts[0].bbox[3] >= 300.0

def test_collect_candidates_merges_multiline_panel_title_with_numeric_side_card(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "multiline-panel-side-card.pdf"
    out_dir = tmp_path / "out"
    _build_multiline_title_panel_with_side_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="multiline-panel-side-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 1
    assert (
        "as digital content grows, the need for innovation"
        in (charts[0].caption or "").lower()
    )
    assert charts[0].bbox[1] < 36.0
    assert charts[0].bbox[2] > 660.0

def test_panel_chart_rects_skip_pages_with_explicit_figure_captions(tmp_path) -> None:
    pdf_path = tmp_path / "panel-chart-with-caption.pdf"
    _build_panel_chart_slide_with_figure_caption_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        assert _panel_chart_rects(page) == []
    finally:
        doc.close()

def test_collect_candidates_recovers_internal_panel_cards_without_external_titles(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "internal-panel-cards.pdf"
    out_dir = tmp_path / "out"
    _build_internal_panel_cards_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="internal-panel-cards",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    assert len(charts) == 2
    captions = [(chart.caption or "").lower() for chart in charts]
    assert any("lower-cost" in caption for caption in captions)
    assert any(
        "3 ways retailers can prepare for 2026" in caption for caption in captions
    )
    assert all(chart.bbox[2] > 520.0 for chart in charts)
    assert tables == []

def test_collect_candidates_extends_internal_panel_to_side_labels(tmp_path) -> None:
    pdf_path = tmp_path / "internal-panel-with-side-labels.pdf"
    out_dir = tmp_path / "out"
    _build_internal_panel_with_side_labels_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="internal-panel-with-side-labels",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]
    assert chart.bbox[2] > 560.0
    assert chart.bbox[1] <= 170.0
    assert chart.bbox[3] >= 440.0

def test_collect_candidates_extends_titled_panel_to_bottom_labels(tmp_path) -> None:
    pdf_path = tmp_path / "internal-panel-with-bottom-labels.pdf"
    out_dir = tmp_path / "out"
    _build_internal_panel_with_bottom_labels_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="internal-panel-with-bottom-labels",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]
    assert chart.bbox[1] <= 90.0
    assert chart.bbox[3] >= 512.0

def test_collect_candidates_keeps_internal_panel_title_band_padding(tmp_path) -> None:
    pdf_path = tmp_path / "panel-chart-with-wide-internal-title-band-e2e.pdf"
    out_dir = tmp_path / "out"
    _build_panel_chart_with_wide_internal_title_band_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="panel-chart-with-wide-internal-title-band-e2e",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 1
    assert charts[0].bbox[1] < 40.0

def test_collect_candidates_rejects_contents_panel_page(tmp_path) -> None:
    pdf_path = tmp_path / "contents-panel-page.pdf"
    out_dir = tmp_path / "out"
    _build_contents_panel_page_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="contents-panel-page",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []

def test_extend_with_adjacent_text_blocks_keeps_internal_title_band(tmp_path) -> None:
    pdf_path = tmp_path / "chart-with-internal-title-band.pdf"
    _build_chart_with_internal_title_band_pdf(pdf_path)
    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        base_rect = fitz.Rect(90.0, 140.0, 530.0, 300.0)
        expanded = _extend_with_adjacent_text_blocks(page, base_rect)
    finally:
        doc.close()
    assert expanded.y0 < 120.0

def test_extend_panel_with_adjacent_text_blocks_keeps_wide_internal_title_band(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-chart-with-wide-internal-title-band.pdf"
    _build_panel_chart_with_wide_internal_title_band_pdf(pdf_path)
    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        base_rect = fitz.Rect(94.0, 194.0, 624.0, 336.0)
        expanded = _extend_panel_with_adjacent_text_blocks(page, base_rect)
    finally:
        doc.close()

    assert expanded.y0 < 120.0

def test_extend_panel_with_adjacent_text_blocks_rejects_cross_panel_text(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "cross-panel-label.pdf"
    _build_cross_panel_label_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        base_rect = fitz.Rect(28.0, 136.9, 462.0, 467.6)
        expanded = _extend_panel_with_adjacent_text_blocks(page, base_rect)
    finally:
        doc.close()

    assert expanded.x1 < 500.0
    assert expanded.y1 > 450.0

def test_extend_panel_with_adjacent_text_blocks_attaches_overlapping_left_stat_block(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-overlapping-left-stat.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((232.0, 390.0), "compared to", fontsize=20, color=(0, 0, 0))
    page.insert_text((232.0, 418.0), "56%", fontsize=26, color=(0, 0, 0))
    page.insert_text((232.0, 446.0), "who said", fontsize=20, color=(0, 0, 0))
    page.insert_text(
        (232.0, 474.0),
        "the same last year.",
        fontsize=20,
        color=(0, 0, 0),
    )
    page.insert_text(
        (42.0, 390.0),
        "71% of consumers",
        fontsize=20,
        color=(0, 0, 0),
    )
    page.insert_text(
        (42.0, 418.0),
        "want Gen AI-integrated",
        fontsize=18,
        color=(0, 0, 0),
    )
    page.insert_text(
        (42.0, 446.0),
        "shopping interactions",
        fontsize=18,
        color=(0, 0, 0),
    )
    doc.save(pdf_path.as_posix())
    doc.close()

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        base_rect = fitz.Rect(190.0, 352.0, 556.0, 574.0)
        expanded = _extend_panel_with_adjacent_text_blocks(page, base_rect)
    finally:
        doc.close()

    assert expanded.x0 < 80.0

def test_extend_panel_with_adjacent_text_blocks_attaches_narrow_centered_top_title(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-narrow-centered-top-title.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    base_rect = fitz.Rect(54.0, 420.0, 558.0, 760.0)
    page.draw_rect(base_rect, color=(0.1, 0.2, 0.5), fill=(0.1, 0.2, 0.5))
    page.insert_text((268.0, 332.0), "Searchless", fontsize=18, color=(1, 1, 1))
    page.insert_text((285.0, 356.0), "retail:", fontsize=18, color=(1, 1, 1))
    page.insert_text(
        (262.0, 392.0),
        "Anticipating intent",
        fontsize=16,
        color=(1, 1, 1),
    )
    page.insert_text(
        (276.0, 416.0),
        "and delivering via GEO",
        fontsize=16,
        color=(1, 1, 1),
    )
    doc.save(pdf_path.as_posix())
    doc.close()

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _extend_panel_with_adjacent_text_blocks(page, base_rect)
    finally:
        doc.close()

    assert expanded.y0 < 340.0

def test_visual_text_dense_recovery_only_uses_panel_heuristic_for_panel_kind() -> None:
    text = "\n".join(
        [
            "AU 41 12%",
            "NZ 38 11%",
            "JP 36 10%",
            "KR 35 10%",
            "CN 34 9%",
            "IN 31 9%",
            "TH 28 8%",
            "MY 27 8%",
            "PH 25 7%",
            "ID 24 7%",
        ]
    )
    line_count = len(text.splitlines())
    char_count = len(text)
    text_ratio = 0.34

    assert (
        _visual_text_dense_recovery_allowed(
            "draw", text, line_count, char_count, text_ratio
        )
        is False
    )
    assert (
        _visual_text_dense_recovery_allowed(
            "panel", text, line_count, char_count, text_ratio
        )
        is True
    )
    assert _panel_chart_has_data_signal(text) is True

__all__ = [
    "test_panel_label_block_looks_like_footer_banner_accepts_mixed_year_page_line",
    "test_panel_should_clamp_to_internal_caption_for_stacked_panel_pair",
    "test_panel_candidate_shadowed_by_heading_candidate_for_metric_stub_panel",
    "test_panel_candidate_shadowed_by_larger_panel_for_compact_banner",
    "test_panel_candidate_shadowed_by_larger_panel_keeps_equal_stacked_cards",
    "test_panel_stacked_bottom_clip_y_prefers_next_lower_panel",
    "test_panel_stacked_bottom_clip_y_skips_clip_when_bottom_axis_band_exists",
    "test_panel_chart_has_data_signal_accepts_dense_axis_only_panel",
    "test_panel_preferred_local_title_line_prefers_near_component_title",
    "test_panel_preferred_local_title_line_prefers_internal_card_title_over_metric_fragment",
    "test_panel_title_looks_short_proper_name_accepts_country_like_title",
    "test_panel_title_slice_bounds_separates_peer_titles",
    "test_collect_candidates_merges_multiline_metric_band_with_quote_card",
    "test_collect_candidates_keeps_dense_numeric_panel_chart",
    "test_collect_candidates_merges_multiline_panel_title_with_numeric_side_card",
    "test_panel_chart_rects_skip_pages_with_explicit_figure_captions",
    "test_collect_candidates_recovers_internal_panel_cards_without_external_titles",
    "test_collect_candidates_extends_internal_panel_to_side_labels",
    "test_collect_candidates_extends_titled_panel_to_bottom_labels",
    "test_collect_candidates_keeps_internal_panel_title_band_padding",
    "test_collect_candidates_rejects_contents_panel_page",
    "test_extend_with_adjacent_text_blocks_keeps_internal_title_band",
    "test_extend_panel_with_adjacent_text_blocks_keeps_wide_internal_title_band",
    "test_extend_panel_with_adjacent_text_blocks_rejects_cross_panel_text",
    "test_extend_panel_with_adjacent_text_blocks_attaches_overlapping_left_stat_block",
    "test_extend_panel_with_adjacent_text_blocks_attaches_narrow_centered_top_title",
    "test_visual_text_dense_recovery_only_uses_panel_heuristic_for_panel_kind",
]
