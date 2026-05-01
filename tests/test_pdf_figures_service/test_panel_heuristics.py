from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_clamp_top_to_caption_reserves_crop_padding_from_prior_paragraph(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "chart-caption-spillover.pdf"
    _build_chart_caption_spillover_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        cap_rect = None
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if "Figure 2.6." in str(text):
                cap_rect = fitz.Rect(x0, y0, x1, y1)
                break
        assert cap_rect is not None
        rect = fitz.Rect(59.2, cap_rect.y0 - 10.0, 538.8, 691.0)
        clamped = _clamp_top_to_caption(rect, cap_rect, page, page.rect)
    finally:
        doc.close()

    assert clamped.y0 > 186.0
    assert clamped.y0 < 187.0


def test_collect_candidates_splits_stacked_captioned_draw_charts(tmp_path) -> None:
    pdf_path = tmp_path / "stacked-captioned-draw-charts.pdf"
    out_dir = tmp_path / "out"
    _build_stacked_captioned_draw_charts_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="stacked-captioned-draw-charts",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 2
    upper = next(
        candidate
        for candidate in charts
        if (candidate.caption or "").lower() == "figure 1"
    )
    lower = next(
        candidate
        for candidate in charts
        if (candidate.caption or "").lower() == "figure 2"
    )
    assert upper.id == "chart-0-0"
    assert lower.id == "chart-0-1"
    assert upper.bbox[1] <= 182.0
    assert upper.bbox[3] >= 354.0
    assert upper.bbox[3] < 400.0
    assert lower.bbox[1] <= 452.0
    assert lower.bbox[3] >= 624.0


def test_collect_candidates_rejects_top_stacked_captioned_draw_chart(tmp_path) -> None:
    pdf_path = tmp_path / "top-stacked-captioned-draw-charts.pdf"
    out_dir = tmp_path / "out"
    _build_top_stacked_captioned_draw_charts_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="top-stacked-captioned-draw-charts",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert (charts[0].caption or "").lower().startswith("figure 2")


def test_collect_candidates_detects_captionless_embedded_chart_image_card(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "embedded-chart-image-card.pdf"
    out_dir = tmp_path / "out"
    _build_embedded_chart_image_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="embedded-chart-image-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]
    assert chart.bbox[0] >= 315.0
    assert chart.bbox[1] >= 165.0
    assert chart.bbox[2] <= 880.0
    assert chart.bbox[3] > 430.0


def test_collect_candidates_detects_relaxed_geometry_embedded_chart_images(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "relaxed-embedded-chart-geometries.pdf"
    out_dir = tmp_path / "out"
    _build_relaxed_embedded_chart_geometries_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="relaxed-embedded-chart-geometries",
        ),
        _ctx(),
    )

    charts = sorted(
        [candidate for candidate in response.candidates if candidate.kind == "chart"],
        key=lambda candidate: (candidate.page, candidate.id),
    )
    assert len(charts) == 2
    wide = charts[0]
    narrow = charts[1]
    assert wide.page == 0
    assert wide.bbox[0] >= 315.0
    assert wide.bbox[2] <= 880.0
    assert narrow.page == 1
    assert narrow.bbox[0] >= 620.0
    assert narrow.bbox[2] <= 880.0
    assert narrow.bbox[3] >= 490.0


def test_collect_candidates_does_not_relax_captioned_embedded_chart_geometry(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "relaxed-embedded-chart-with-figure-caption.pdf"
    out_dir = tmp_path / "out"
    _build_relaxed_embedded_chart_with_figure_caption_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="relaxed-embedded-chart-with-figure-caption",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert not any(candidate.page == 1 for candidate in charts)


def test_collect_candidates_rejects_decorative_photo_panel_without_figure_context(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "decorative-photo-panel.pdf"
    out_dir = tmp_path / "out"
    _build_decorative_photo_panel_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="decorative-photo-panel",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_visual_candidate_looks_table_like_keeps_compact_panel_rank_card() -> None:
    text = (
        "Advertising equity\n"
        "43.3\n"
        "47.6\n"
        "2024\n"
        "2025\n"
        "#3\n"
        "#1\n"
        "Rank 1 of 25 of total\n"
        "media channel\n"
    )
    assert (
        _visual_candidate_looks_table_like(
            "Advertising equity",
            text,
            kind="panel",
            panel_data_signal=True,
        )
        is False
    )


def test_final_chart_candidate_looks_heading_slice_keeps_large_panel_chart() -> None:
    candidate = Candidate(
        schema_version="1.0",
        id="chart-0-0",
        kind="chart",
        page=0,
        bbox=(18.4, 102.65, 471.6, 472.32),
        preview_text="Trustworthy Ads",
        caption="Trustworthy Ads",
    )

    assert (
        _final_chart_candidate_looks_heading_slice(candidate, "Trustworthy Ads\n")
        is False
    )


def test_visual_candidate_looks_narrative_panel_card_rejects_long_worldpanel_style_card() -> (
    None
):
    text = (
        "The inflation headwind returns\n"
        "Brand growth is about to face its sternest test since 2022.\n"
        "With inflation showing renewed upward momentum across key markets, we predict 2025 will "
        "see fewer than 50% of brands achieving growth.\n"
        "This isn't speculation; it's what economic history teaches us about consumer behaviour "
        "under pressure.\n"
        "For brand managers, this means recalibrating expectations now.\n"
        "The 43% growth rate observed during the last inflation spike may prove to be a preview.\n"
        "Only the most adaptive brands will avoid being caught off guard.\n"
        "History suggests pressure makes shopper recruitment harder for weaker brands.\n"
        "The coming year will reward strategic discipline over passive expectation-setting.\n"
    )
    assert (
        _visual_candidate_looks_narrative_panel_card(
            "The inflation",
            text,
            kind="panel",
            text_ratio=0.46,
            area_frac=0.28,
        )
        is True
    )


def test_panel_chart_has_data_signal_rejects_non_numeric_label_grid() -> None:
    text = (
        "Trustworthy\n"
        "Relevant and useful\n"
        "Fun and entertaining\n"
        "Better quality\n"
        "Innovative\n"
        "Captures my attention\n"
    )
    assert _panel_chart_has_data_signal(text) is False


def test_visual_candidate_looks_inline_numbered_panel_rejects_short_numbered_sidebar() -> (
    None
):
    text = (
        "Euro area 2\n"
        "The euro has appreciated strongly\n"
        "High uncertainty calls for prudent monetary policy\n"
        "Note: The indicator is standardised over the period 2007-2024.\n"
        "Source: OECD Economic Outlook 118 database.\n"
        "StatLink https://stat.link/example\n"
    )
    assert (
        _visual_candidate_looks_inline_numbered_panel(
            "Euro area 2",
            text,
            note_included=True,
            area_frac=0.205,
            aspect=2.15,
        )
        is True
    )


def test_collect_candidates_detects_panel_charts_without_figure_captions(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-chart-slide.pdf"
    out_dir = tmp_path / "out"
    _build_panel_chart_slide_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="panel-chart-slide",
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
    assert tables == []
    captions = sorted((candidate.caption or "").lower() for candidate in charts)
    assert captions == ["better quality ads", "trustworthy ads"]
    left = next(
        candidate
        for candidate in charts
        if (candidate.caption or "").lower() == "trustworthy ads"
    )
    right = next(
        candidate
        for candidate in charts
        if (candidate.caption or "").lower() == "better quality ads"
    )
    assert left.bbox[2] < 500.0
    assert right.bbox[0] > 460.0


def test_collect_candidates_groups_shared_title_split_panels_into_one_chart(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "shared-title-split-panel.pdf"
    out_dir = tmp_path / "out"
    _build_shared_title_split_panel_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="shared-title-split-panel",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 1
    assert (
        "top anticipated media challenges by company type"
        in (charts[0].caption or "").lower()
    )
    assert charts[0].bbox[2] > 900.0


def test_extend_panel_rect_with_nearby_label_blocks_respects_horizontal_guard() -> None:
    rect = fitz.Rect(430.0, 160.0, 900.0, 420.0)
    page_rect = fitz.Rect(0.0, 0.0, 960.0, 540.0)
    blocks = [
        (112.0, 248.0, 292.0, 280.0, "Left panel label"),
        (846.0, 194.0, 934.0, 210.0, "Total Average"),
    ]

    expanded = _extend_panel_rect_with_nearby_label_blocks(
        rect,
        blocks=blocks,
        page_rect=page_rect,
        min_x=420.0,
        max_x=940.0,
    )

    assert expanded.x0 >= 420.0
    assert expanded.x1 <= 940.0
    assert expanded.x0 > 320.0
    assert expanded.x1 > rect.x1


def test_collect_candidates_groups_stacked_shared_title_panels_into_one_chart(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stacked-shared-title-panel.pdf"
    out_dir = tmp_path / "out"
    _build_stacked_shared_title_panel_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="stacked-shared-title-panel",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 1
    assert (
        "year-on-year growth in brand switching behaviour"
        in (charts[0].caption or "").lower()
    )
    assert charts[0].bbox[2] >= 748.0
    assert charts[0].bbox[3] >= 476.0


def test_collect_candidates_keeps_stacked_independent_panel_cards_separate(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stacked-independent-panel-cards.pdf"
    out_dir = tmp_path / "out"
    _build_stacked_independent_panel_cards_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="stacked-independent-panel-cards",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 2
    captions = sorted((candidate.caption or "").lower() for candidate in charts)
    assert captions == [
        "3 ways retailers can prepare for a searchless future:",
        "of shoppers make purchases based on ai",
    ]
    lower = next(
        candidate
        for candidate in charts
        if (candidate.caption or "")
        .lower()
        .startswith("3 ways retailers can prepare for a searchless future")
    )
    upper = next(
        candidate
        for candidate in charts
        if (candidate.caption or "")
        .lower()
        .startswith("of shoppers make purchases based on ai")
    )
    assert lower.bbox[1] >= 540.0
    assert upper.bbox[3] <= 560.0


def test_collect_candidates_detects_wide_panel_chart_with_resource_title(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "wide-panel-chart.pdf"
    out_dir = tmp_path / "out"
    _build_wide_panel_chart_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="wide-panel-chart",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert "changes in budget/resource allocation" in (charts[0].caption or "").lower()
    assert charts[0].bbox[0] > 0.0
    assert charts[0].bbox[2] < 960.0
    assert charts[0].bbox[3] < 520.0


def test_collect_candidates_detects_right_column_raster_chart_card_with_left_context(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "right-column-raster-chart-card.pdf"
    out_dir = tmp_path / "out"
    _build_right_column_raster_chart_card_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        image_rect = page.get_image_rects(page.get_images(full=True)[0][0])[0]
        assert _embedded_visual_looks_chart_like(page, image_rect) is False
    finally:
        doc.close()

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="right-column-raster-chart-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(charts) == 1
    assert charts[0].bbox[0] >= 440.0
    assert charts[0].bbox[2] >= 800.0
    assert charts[0].bbox[3] >= 398.0


def test_collect_candidates_rejects_right_column_raster_photo_card_with_left_context(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "right-column-raster-photo-card.pdf"
    out_dir = tmp_path / "out"
    _build_right_column_raster_photo_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="right-column-raster-photo-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_collect_candidates_rejects_light_raster_photo_card(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "light-raster-photo-card.pdf"
    out_dir = tmp_path / "out"
    _build_light_raster_photo_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="light-raster-photo-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_collect_candidates_rejects_small_uncaptioned_decorative_raster_card(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "small-decorative-raster-card.pdf"
    out_dir = tmp_path / "out"
    _build_small_decorative_raster_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="small-decorative-raster-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_collect_candidates_rejects_panel_action_card_without_data_signal(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "panel-action-card.pdf"
    out_dir = tmp_path / "out"
    _build_panel_action_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="panel-action-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_panel_chart_has_compact_stat_card_signal_accepts_metric_card() -> None:
    text = (
        "44%\n"
        "of shoppers are buying private-label or low-cost brands over name brands\n"
        "Early findings: What matters to today's consumers, 2026\n"
    )
    assert _panel_chart_has_compact_stat_card_signal(text) is True


def test_clamp_panel_rect_to_dominant_fill_rect_prefers_local_compact_card() -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.draw_rect(fitz.Rect(40, 100, 360, 160), color=None, fill=(0.1, 0.3, 0.6))
    page.draw_rect(fitz.Rect(40, 185, 360, 220), color=None, fill=(0.2, 0.7, 0.9))
    page.insert_text((52, 125), "44%", fontsize=22)
    page.insert_text(
        (150, 125),
        "of shoppers are buying private-label brands",
        fontsize=12,
    )
    page.insert_text(
        (150, 145),
        "Early findings: What matters today",
        fontsize=10,
    )
    page.insert_text((150, 208), "Private labels go premium", fontsize=13)

    polluted_text = (
        "44%\n"
        "of shoppers are buying private-label brands\n"
        "Early findings: What matters today\n"
        "Private labels go premium\n"
        "Longer narrative body text that should not remain part of the compact stat card.\n"
    )

    clamped = _clamp_panel_rect_to_dominant_fill_rect(
        page,
        fitz.Rect(40, 100, 360, 220),
        text=polluted_text,
    )

    assert clamped.y0 <= 102.5
    assert clamped.y1 <= 163.0
    assert clamped.y1 < 180.0


def test_clamp_panel_rect_to_dominant_fill_rect_leaves_multi_stat_card_unchanged() -> (
    None
):
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.draw_rect(fitz.Rect(40, 100, 360, 240), color=None, fill=(0.1, 0.3, 0.6))
    lines = [
        "46%",
        "of shoppers make purchases based on AI recommendations",
        "Early findings: What matters today",
        "52%",
        "of shoppers switch retailers for better data protection",
        "Early findings: What matters today",
        "33%",
        "of shoppers want explanations before completing purchases",
    ]
    y = 122
    for line in lines:
        page.insert_text((52, y), line, fontsize=12)
        y += 18

    text = "\n".join(lines)
    original = fitz.Rect(40, 100, 360, 240)

    clamped = _clamp_panel_rect_to_dominant_fill_rect(page, original, text=text)

    assert clamped == original


def test_panel_component_looks_like_guidance_card_accepts_step_and_key_cards() -> None:
    numbered_text = (
        "3 ways retailers can win with invisible AI experiences\n"
        "01\n"
        "Establish visible safeguards\n"
        "02\n"
        "Use contextual signals to guide discovery\n"
        "03\n"
        "Offer real-time controls customers can understand\n"
    )
    colon_text = (
        "4 keys to building trust for retailers\n"
        "Consistency: Ensure reliable experiences across every channel.\n"
        "Contextualization: Respond to each shopper's moment.\n"
        "Care: Reflect the values that matter to customers.\n"
    )

    assert _panel_component_looks_like_guidance_card(numbered_text) is True
    assert _panel_component_looks_like_guidance_card(colon_text) is True


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
