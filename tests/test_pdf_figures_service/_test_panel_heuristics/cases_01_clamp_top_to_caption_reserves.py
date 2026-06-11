# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

__all__ = [
    "test_clamp_top_to_caption_reserves_crop_padding_from_prior_paragraph",
    "test_collect_candidates_splits_stacked_captioned_draw_charts",
    "test_collect_candidates_rejects_top_stacked_captioned_draw_chart",
    "test_collect_candidates_detects_captionless_embedded_chart_image_card",
    "test_collect_candidates_detects_relaxed_geometry_embedded_chart_images",
    "test_collect_candidates_does_not_relax_captioned_embedded_chart_geometry",
    "test_collect_candidates_rejects_decorative_photo_panel_without_figure_context",
    "test_visual_candidate_looks_table_like_keeps_compact_panel_rank_card",
    "test_final_chart_candidate_looks_heading_slice_keeps_large_panel_chart",
    "test_visual_candidate_looks_narrative_panel_card_rejects_long_worldpanel_style_card",
    "test_panel_chart_has_data_signal_rejects_non_numeric_label_grid",
    "test_visual_candidate_looks_inline_numbered_panel_rejects_short_numbered_sidebar",
    "test_collect_candidates_detects_panel_charts_without_figure_captions",
    "test_collect_candidates_groups_shared_title_split_panels_into_one_chart",
    "test_extend_panel_rect_with_nearby_label_blocks_respects_horizontal_guard",
    "test_collect_candidates_groups_stacked_shared_title_panels_into_one_chart",
    "test_collect_candidates_keeps_stacked_independent_panel_cards_separate",
    "test_collect_candidates_detects_wide_panel_chart_with_resource_title",
    "test_collect_candidates_detects_right_column_raster_chart_card_with_left_context",
    "test_collect_candidates_rejects_right_column_raster_photo_card_with_left_context",
    "test_collect_candidates_rejects_light_raster_photo_card",
    "test_collect_candidates_rejects_small_uncaptioned_decorative_raster_card",
    "test_collect_candidates_rejects_panel_action_card_without_data_signal",
    "test_panel_chart_has_compact_stat_card_signal_accepts_metric_card",
    "test_clamp_panel_rect_to_dominant_fill_rect_prefers_local_compact_card",
    "test_clamp_panel_rect_to_dominant_fill_rect_leaves_multi_stat_card_unchanged",
    "test_panel_component_looks_like_guidance_card_accepts_step_and_key_cards",
]
