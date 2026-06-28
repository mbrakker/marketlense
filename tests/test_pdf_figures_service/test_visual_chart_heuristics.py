from __future__ import annotations

from .builders import *  # noqa: F401,F403
from src.services._pdf.visual_candidates import (
    _embedded_visual_is_oversized_wrapper,
    _has_side_by_side_visual_sibling,
)
from src.services._pdf._visual_candidates._extraction.context import (
    _append_visual_page_candidate,
    _emit_visual_page_candidates,
)
from src.services._pdf.visual_heuristics import (
    _VisualCandidateRelationships,
    _VisualOverlapIndex,
)


class _TrackedRectItem:
    def __init__(self, *, rect: fitz.Rect, kind: str, xref: int | None = None):
        self._rect = rect
        self.kind = kind
        self.xref = xref
        self.rect_access_count = 0

    @property
    def rect(self) -> fitz.Rect:
        self.rect_access_count += 1
        return self._rect

    def reset_rect_access_count(self) -> None:
        self.rect_access_count = 0


def test_visual_relationship_index_bounds_sibling_and_wrapper_scans() -> None:
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)
    side_target = _TrackedRectItem(
        rect=fitz.Rect(100.0, 120.0, 210.0, 260.0),
        kind="xref",
    )
    side_sibling = _TrackedRectItem(
        rect=fitz.Rect(220.0, 130.0, 330.0, 270.0),
        kind="block",
    )
    wrapper = _TrackedRectItem(
        rect=fitz.Rect(-30.0, 390.0, 620.0, 610.0),
        kind="xref",
    )
    wrapped_child = _TrackedRectItem(
        rect=fitz.Rect(120.0, 430.0, 460.0, 560.0),
        kind="block",
    )
    far_items = [
        _TrackedRectItem(
            rect=fitz.Rect(40.0, 690.0 + index, 130.0, 730.0 + index),
            kind="xref",
        )
        for index in range(30)
    ]
    candidates = [side_target, side_sibling, wrapper, wrapped_child, *far_items]
    relationships = _VisualCandidateRelationships.build(
        candidates,
        page_rect=page_rect,
    )
    for item in candidates:
        item.reset_rect_access_count()

    assert (
        _has_side_by_side_visual_sibling(
            side_target,
            candidates,
            page_rect,
            relationships=relationships,
        )
        is True
    )
    assert (
        _embedded_visual_is_oversized_wrapper(
            wrapper,
            candidates,
            page_rect,
            relationships=relationships,
        )
        is True
    )
    assert sum(item.rect_access_count for item in far_items) == 0


def test_visual_overlap_index_limits_lookup_to_intersecting_page_bands() -> None:
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)
    overlap_index = _VisualOverlapIndex(page_rect=page_rect, bin_height=64.0)
    far_rects = [
        fitz.Rect(40.0, 500.0 + index * 4.0, 160.0, 522.0 + index * 4.0)
        for index in range(36)
    ]
    near_rect = fitz.Rect(100.0, 120.0, 220.0, 240.0)
    for index, rect in enumerate([*far_rects, near_rect]):
        overlap_index.add(index, rect)

    assert overlap_index.lookup(fitz.Rect(110.0, 130.0, 230.0, 250.0)) == [
        len(far_rects)
    ]


def test_append_visual_page_candidate_preserves_replacement_with_overlap_index() -> (
    None
):
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)
    overlap_index = _VisualOverlapIndex(page_rect=page_rect)
    page_candidates = []
    kept = []
    first = Candidate(
        schema_version="1.0",
        id="chart-0-pending-0",
        kind="chart",
        page=0,
        bbox=(100.0, 100.0, 220.0, 220.0),
        preview_text="first",
        caption="first",
    )
    replacement = Candidate(
        schema_version="1.0",
        id="chart-0-pending-1",
        kind="chart",
        page=0,
        bbox=(104.0, 104.0, 224.0, 224.0),
        preview_text="replacement",
        caption="replacement",
    )

    local_sequence = _append_visual_page_candidate(
        page_candidates=page_candidates,
        kept=kept,
        overlap_index=overlap_index,
        candidate=first,
        final_rect=fitz.Rect(first.bbox),
        score=0.4,
        local_sequence=0,
        legacy_order_candidate=True,
        stats={"raw": 0, "kept": 0, "rejected": 0, "reasons": {}},
    )
    local_sequence = _append_visual_page_candidate(
        page_candidates=page_candidates,
        kept=kept,
        overlap_index=overlap_index,
        candidate=replacement,
        final_rect=fitz.Rect(replacement.bbox),
        score=0.8,
        local_sequence=local_sequence,
        legacy_order_candidate=True,
        stats={"raw": 0, "kept": 1, "rejected": 0, "reasons": {}},
    )
    emitted = []
    _emit_visual_page_candidates(
        emitted, page_number=0, page_candidates=page_candidates
    )

    assert local_sequence == 1
    assert len(kept) == 1
    assert overlap_index.lookup(fitz.Rect(replacement.bbox)) == [0]
    assert [(candidate.id, candidate.caption) for candidate in emitted] == [
        ("chart-0-0", "replacement")
    ]


def test_collect_candidates_chart_bbox_excludes_corner_page_number_and_body_text(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "chart-context.pdf"
    out_dir = tmp_path / "out"
    _build_chart_context_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="chart-context",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]

    assert chart.bbox[1] > 55.0
    assert chart.bbox[1] < 95.0
    assert chart.bbox[3] > 530.0
    assert chart.bbox[3] < 602.0


def test_collect_candidates_chart_bbox_keeps_full_partial_note_overlap(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "chart-partial-note-overlap.pdf"
    out_dir = tmp_path / "out"
    _build_chart_partial_note_overlap_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="chart-partial-note-overlap",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]

    assert chart.bbox[3] > 430.0
    assert chart.bbox[3] < 500.0


def test_collect_candidates_chart_flow_recognizes_infographic_caption(tmp_path) -> None:
    pdf_path = tmp_path / "infographic-chart.pdf"
    out_dir = tmp_path / "out"
    _build_infographic_chart_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="infographic-chart",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert "infographic 1" in (charts[0].caption or "").lower()


def test_collect_candidates_chart_flow_keeps_dense_label_chart_above_section_heading(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "dense-chart-with-heading.pdf"
    out_dir = tmp_path / "out"
    _build_dense_chart_with_section_heading_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="dense-chart-with-heading",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    target = next(
        candidate
        for candidate in charts
        if "figure 1.1" in ((candidate.caption or candidate.preview_text or "").lower())
    )
    assert target.bbox[3] < 360.0
    assert target.bbox[3] > 250.0


def test_collect_candidates_chart_flow_keeps_upper_dense_chart_before_next_figure(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "multi-figure-dense-chart.pdf"
    out_dir = tmp_path / "out"
    _build_multi_figure_dense_chart_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="multi-figure-dense-chart",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    upper = next(
        candidate
        for candidate in charts
        if "figure 5.26"
        in ((candidate.caption or candidate.preview_text or "").lower())
    )
    lower = next(
        candidate
        for candidate in charts
        if "figure 5.27"
        in ((candidate.caption or candidate.preview_text or "").lower())
    )
    assert lower.id == "chart-0-0"
    assert upper.id == "chart-0-1"
    assert upper.bbox[3] < 460.0
    assert lower.bbox[1] > 430.0


def test_collect_candidates_detects_wide_captioned_draw_chart_with_source(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "wide-captioned-draw-chart.pdf"
    out_dir = tmp_path / "out"
    _build_wide_captioned_draw_chart_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="wide-captioned-draw-chart",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    chart = charts[0]
    assert (chart.caption or "").lower() == "figure 1"
    assert chart.bbox[1] <= 442.0
    assert chart.bbox[3] >= 620.0


def test_collect_candidates_chart_flow_rejects_side_by_side_photo_examples_without_visual_hint(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "side-by-side-photo-examples.pdf"
    out_dir = tmp_path / "out"
    _build_side_by_side_photo_examples_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="side-by-side-photo-examples",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert not any(candidate.page == 1 for candidate in charts)


def test_visual_candidate_looks_reference_or_prose_rejects_box_text() -> None:
    text = (
        "The growth of stablecoins may also pose risks to banks. Companies with crypto-related "
        "business models also hold bank deposits.\n"
        "Many countries have begun to develop tailored regulations relating to stablecoins.\n"
        "These include liquidity shortages and fire sales of collateral.\n"
        "Investors' redemption runs and funding costs may also rise.\n"
        "Another paragraph explains the risks in prose rather than chart labels.\n"
        "This page is a narrative box and not a chart.\n"
        "Source: OECD Publishing, Paris, https://doi.org/10.1787/example-en.\n"
    )
    assert (
        _visual_candidate_looks_reference_or_prose(
            "Box 2.3. Pro-competitive product market regulations support economic growth",
            text,
            text_ratio=0.42,
        )
        is True
    )


def test_visual_candidate_looks_reference_or_prose_rejects_long_prose_with_numbered_notes() -> (
    None
):
    text = (
        "The growth of stablecoins may also pose risks to banks. Companies with crypto-related "
        "business models, including stablecoin issuers, also hold bank deposits.\n"
        "The growing adoption and use of stablecoins also raise economic policy challenges.\n"
        "Exchange rate volatility in emerging-market economies could rise if capital controls "
        "are less effective at times of stress.\n"
        "More broadly, the use of foreign currency denominated stablecoins could weaken the "
        "control of monetary conditions by domestic central banks.\n"
        "Many countries have begun to develop tailored regulations relating to stablecoins, and "
        "crypto-assets more generally, with prominent recent examples in the United States and "
        "the European Union.\n"
        "Regulatory approaches differ across countries and significant gaps and inconsistencies "
        "remain.\n"
        "One key issue is the limited oversight of cross-border transactions, which could hamper "
        "responses to systemic risks and encourage regulatory arbitrage.\n"
        "The rapid growth of the stablecoin market highlights the need for enhanced international "
        "cooperation to ensure effective regulation, supervision, and oversight.\n"
        "A further issue is the interaction with bank-based financial intermediation.\n"
        "Runs on perceived high-risk stablecoins may transmit stress to broader markets.\n"
        "Liquidity strains could be amplified by collateral sales and funding pressures.\n"
        "Cross-border regulatory arbitrage remains a material policy concern.\n"
        "Supervisory gaps are still present in several jurisdictions.\n"
        "Large issuers have become more interconnected with critical funding markets.\n"
        "These feedback loops can complicate monetary-policy transmission.\n"
        "The role of reserve assets and redemption dynamics remains central.\n"
        "Operational resilience and cyber-risk considerations also matter.\n"
        "These topics require broad international coordination and oversight.\n"
        "1. Transaction volumes of fiat-collateralised stablecoins accounted for 31% of total "
        "stablecoin transaction volumes in 2024.\n"
        "2. Traditional investment funds rely on established authorised participants.\n"
        "3. The GENIUS Act was enacted in July 2025.\n"
    )
    assert (
        _visual_candidate_looks_reference_or_prose(
            "The growth of stablecoins may also pose risks to banks.",
            text,
            text_ratio=0.62,
        )
        is True
    )


def test_visual_candidate_looks_reference_or_prose_keeps_structured_instruction_card() -> (
    None
):
    text = (
        "3 ways retailers can win with invisible AI experiences\n"
        "Shift from personalization to contextualization: Shift from personalization to contextualization.\n"
        "Establish visible guardrails: Prioritize and promote clear, non-negotiable standards.\n"
        "Keep humans in the loop: Ensure there are smooth escalation paths and backup systems.\n"
        "01\n"
        "02\n"
        "03\n"
        "behavioral, contextual, and transactional signals to surface relevant products.\n"
        "standards around data privacy, security, and ethical use.\n"
        "human support in place to maintain a seamless experience.\n"
    )
    assert (
        _visual_candidate_looks_reference_or_prose(
            "3 ways retailers can win with invisible AI experiences",
            text,
            text_ratio=0.5,
        )
        is False
    )


def test_visual_candidate_looks_reference_or_prose_rejects_explanatory_figure_reference() -> (
    None
):
    text = (
        "Figure 10.4 is based on the European Union Statistics on Income and Living Conditions data.\n"
        "Self-reported health reflects people’s overall perception of their own health.\n"
        "Perceived health status by income quintile is derived from the respondent’s self-perceived health.\n"
        "This indicator looks at the difference in the proportion of adults aged 65 and over reporting poor health.\n"
        "Limitations in daily activities assess an individual’s independence across both ADL and IADL.\n"
        "Comparability is somewhat limited because different samples were used.\n"
    )
    assert (
        _visual_candidate_looks_reference_or_prose(
            "Figure 10.4 is based on the European Union Statistics on Income and Living Conditions data.",
            text,
            text_ratio=0.31,
        )
        is True
    )


def test_visual_candidate_looks_reference_or_prose_rejects_explanatory_figure_reference_with_comma() -> (
    None
):
    text = (
        "Figure 10.19, Japan’s data are added on an exceptional basis for comparability.\n"
        "This indicator is shown only for descriptive context and should not be treated as a chart.\n"
        "Comparability remains limited because different sources were used across the period.\n"
        "The figure therefore functions as explanatory reference text rather than a visual caption.\n"
    )
    assert (
        _visual_candidate_looks_reference_or_prose(
            "Figure 10.19, Japan’s data are added on an exceptional basis for comparability.",
            text,
            text_ratio=0.33,
        )
        is True
    )


def test_visual_candidate_looks_note_fragment_rejects_statlink_strip() -> None:
    text = "Source: OECD Economic Outlook 118 database.\nStatLink 2 https://stat.link/abcd12"

    assert (
        _visual_candidate_looks_note_fragment(
            "StatLink 2 https://stat.link/abcd12",
            text,
            kind="panel",
        )
        is True
    )


def test_visual_candidate_looks_note_fragment_rejects_mid_sentence_note_slice() -> None:
    text = (
        "1. Year-on-year growth rates.\n"
        "Source: OECD Economic Outlook 118 database.\n"
        "StatLink 2 https://stat.link/9xcsw1"
    )

    assert (
        _visual_candidate_looks_note_fragment(
            "(+0.5%). The downturn was driven by sharp declines in exports and business investment, as tariffs on",
            text,
            kind="panel",
        )
        is True
    )


def test_visual_candidate_looks_note_fragment_keeps_bare_heading_chart_with_source() -> (
    None
):
    text = (
        "Austria\n"
        "The pick up in inflation is driven by energy costs\n"
        "The fiscal situation has deteriorated\n"
        "Source: Eurostat; and OECD STEP 118 database.\n"
        "StatLink 2 https://stat.link/diupkh"
    )

    assert (
        _visual_candidate_looks_note_fragment(
            "Austria",
            text,
            kind="panel",
        )
        is False
    )


def test_visual_candidate_looks_bare_heading_fragment_rejects_empty_country_slice() -> (
    None
):
    assert (
        _visual_candidate_looks_bare_heading_fragment(
            "Argentina",
            "Argentina\n",
            kind="panel",
            area_frac=0.12,
            aspect=2.4,
        )
        is True
    )


def test_final_chart_candidate_looks_heading_slice_rejects_bare_country_banner() -> (
    None
):
    candidate = Candidate(
        schema_version="1.0",
        id="chart-258-0",
        kind="chart",
        page=258,
        bbox=(40.0, 40.0, 200.0, 100.0),
        preview_text="Sweden",
        caption="Sweden",
    )

    assert _final_chart_candidate_looks_heading_slice(candidate, "Sweden\n") is True


def test_final_chart_header_reanchor_line_prefers_short_country_label_above_note_crop(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "final-chart-header-reanchor.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((65, 460), "Belgium", fontsize=16)
    page.insert_text(
        (65, 640),
        "1. Year-on-year growth rates. Source: OECD Economic Outlook 118 database.",
        fontsize=10,
    )
    page.insert_text((385, 705), "StatLink 2 https://stat.link/example", fontsize=10)
    doc.save(pdf_path.as_posix())
    doc.close()

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        candidate = Candidate(
            schema_version="1.0",
            id="chart-116-0",
            kind="chart",
            page=0,
            bbox=(80.0, 500.0, 532.0, 720.0),
            preview_text="investment continued in the first half of the year",
            caption="investment continued in the first half of the year",
        )
        text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
        header = _final_chart_header_reanchor_line(candidate, page, text)
    finally:
        doc.close()

    assert header is not None
    assert header.text == "Belgium"


def test_visual_candidate_looks_cover_art_rejects_top_banner() -> None:
    rect = fitz.Rect(0.0, 0.0, 595.0, 162.0)
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    assert (
        _visual_candidate_looks_cover_art(
            rect,
            page_rect,
            "v",
            area_frac=0.405,
            text_chars=34,
        )
        is True
    )


def test_visual_candidate_looks_cover_art_rejects_large_lower_start_hero_art() -> None:
    rect = fitz.Rect(36.6, 177.1, 478.7, 636.5)
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    assert (
        _visual_candidate_looks_cover_art(
            rect,
            page_rect,
            "Retail",
            area_frac=0.404,
            text_chars=12,
        )
        is True
    )


def test_visual_candidate_looks_section_opener_banner_rejects_top_card() -> None:
    rect = fitz.Rect(0.0, 0.0, 595.0, 180.0)
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    text = (
        "Introduction\n"
        "This chapter reviews the current outlook.\n"
        "It highlights the main pressures and themes.\n"
    )
    assert (
        _visual_candidate_looks_section_opener_banner(
            rect,
            page_rect,
            "Introduction",
            text,
            kind="panel",
            area_frac=0.21,
        )
        is True
    )


def test_visual_candidate_looks_section_opener_banner_rejects_fragmented_banner() -> (
    None
):
    rect = fitz.Rect(0.0, 0.0, 595.0, 248.0)
    page_rect = fitz.Rect(0.0, 0.0, 595.0, 842.0)
    text = (
        "Introduction\n"
        "signal quality\n"
        "brand safety\n"
        "trust metrics\n"
        "clean supply\n"
        "video reach\n"
        "social lift\n"
        "context fit\n"
        "attention time\n"
        "fraud controls\n"
        "cross media\n"
        "quality score\n"
        "ROI\n"
        "37%\n"
    )
    assert _panel_chart_has_data_signal(text) is True
    assert (
        _visual_candidate_looks_section_opener_banner(
            rect,
            page_rect,
            "Introduction",
            text,
            kind="panel",
            area_frac=0.27,
        )
        is True
    )


def test_collect_candidates_does_not_treat_prose_mention_of_figure_as_caption_hint(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "prose-mentioning-figure-photo-card.pdf"
    out_dir = tmp_path / "out"
    _build_prose_mentioning_figure_photo_card_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="prose-mentioning-figure-photo-card",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []


def test_collect_candidates_prefers_inside_chart_over_oversized_xref_wrapper(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "oversized-raster-wrapper.pdf"
    out_dir = tmp_path / "out"
    _build_oversized_raster_wrapper_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="oversized-raster-wrapper",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert len(charts) == 1
    assert charts[0].bbox[0] >= 290.0
    assert charts[0].bbox[2] <= 665.0


def test_page_has_chart_caption_blocks_detects_hint_on_later_line() -> None:
    blocks = [(0.0, 0.0, 100.0, 50.0, "Intro line\nFigure 1. Test chart")]
    assert _page_has_chart_caption_blocks(blocks) is True


def test_text_has_visual_context_hint_detects_hint_on_later_line() -> None:
    text = "Intro line\nSource: Example dataset"
    assert _text_has_visual_context_hint(text) is True


def test_chart_axis_label_band_like_accepts_dense_short_label_block() -> None:
    text = (
        "Japan\nSingapore\nGreece\nItaly\nFrance\nUnited States\nBelgium\nSpain\n"
        "Canada\nPortugal\nBrazil\nIndia\nArgentina\n"
    )
    assert (
        _chart_axis_label_band_like(
            text,
            lines=len(text.splitlines()),
            chars=len(text),
            avg_line_len=len(text) / len(text.splitlines()),
        )
        is True
    )


def test_extend_chart_rect_with_adjacent_drawings_recovers_axis_tail(tmp_path) -> None:
    pdf_path = tmp_path / "axis-stroke-extension.pdf"
    _build_axis_stroke_extension_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _extend_chart_rect_with_adjacent_drawings(
            page,
            fitz.Rect(96.0, 110.0, 420.0, 332.0),
        )
    finally:
        doc.close()

    assert expanded.x1 > 500.0


def test_collect_candidates_rejects_internal_label_grid_without_metric_signal(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "internal-label-grid-panel.pdf"
    out_dir = tmp_path / "out"
    _build_internal_label_grid_panel_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="internal-label-grid-panel",
        ),
        _ctx(),
    )

    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]
    assert charts == []
