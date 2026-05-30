from __future__ import annotations

from .builders import *  # noqa: F401,F403
from src.services._pdf._table_heuristics.screening import _TableDedupeSpatialIndex


def test_collect_candidates_detects_ranked_table_slide_without_chart_duplicate(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "ranked-table-slide.pdf"
    out_dir = tmp_path / "out"
    _build_ranked_table_slide_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="ranked-table-slide",
        ),
        _ctx(),
    )

    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(tables) == 1
    assert charts == []
    table = tables[0]
    assert int(table.meta["rows"]) >= 5
    assert int(table.meta["cols"]) >= 2


def test_collect_candidates_detects_full_page_image_table_without_photo_false_positive(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "full-page-image-table.pdf"
    out_dir = tmp_path / "out"
    _build_full_page_image_table_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="full-page-image-table",
        ),
        _ctx(),
    )

    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    charts = [
        candidate for candidate in response.candidates if candidate.kind == "chart"
    ]

    assert len(tables) == 1
    table = tables[0]
    assert table.page == 0
    assert (table.meta or {}).get("method") == "image"
    assert charts == []


def test_prune_charts_overlapping_ranked_tables_removes_chart_duplicate() -> None:
    charts = [
        Candidate(
            schema_version="1.0",
            id="chart-0-0",
            kind="chart",
            page=0,
            bbox=(0.0, 188.0, 553.0, 492.0),
            preview_text="Also #1 in",
            caption="Also #1 in",
            thumb_path="",
            meta={"text_ratio": 0.304},
        ),
        Candidate(
            schema_version="1.0",
            id="chart-0-1",
            kind="chart",
            page=1,
            bbox=(0.0, 0.0, 300.0, 200.0),
            preview_text="Other chart",
            caption="Other chart",
            thumb_path="",
            meta={"text_ratio": 0.1},
        ),
    ]
    tables = [
        Candidate(
            schema_version="1.0",
            id="table-0-0",
            kind="table",
            page=0,
            bbox=(29.0, 152.0, 553.0, 465.0),
            preview_text="Ranked table",
            caption="",
            thumb_path="",
            meta={"method": "ranked"},
        )
    ]

    kept, pruned = _prune_charts_overlapping_ranked_tables(charts, tables)

    assert pruned == 1
    assert [candidate.id for candidate in kept] == ["chart-0-1"]


def test_prune_charts_overlapping_ranked_tables_prunes_table_shadow_for_any_table_method() -> (
    None
):
    charts = [
        Candidate(
            schema_version="1.0",
            id="chart-108-0",
            kind="chart",
            page=108,
            bbox=(43.0, 88.0, 548.0, 384.0),
            preview_text="Argentina",
            caption="Argentina",
            thumb_path="",
            meta={"text_lines": 97, "text_chars": 877, "text_ratio": 0.282},
        )
    ]
    tables = [
        Candidate(
            schema_version="1.0",
            id="table-108-0",
            kind="table",
            page=108,
            bbox=(49.0, 92.0, 545.0, 380.0),
            preview_text="Argentina table",
            caption="",
            thumb_path="",
            meta={"method": "stream"},
        )
    ]

    kept, pruned = _prune_charts_overlapping_ranked_tables(charts, tables)

    assert pruned == 1
    assert kept == []


def test_visual_candidate_looks_table_like_rejects_country_table_text() -> None:
    text = (
        "2022 2023 2024 2025 2026 2027\n"
        "Current prices EUR billion\n"
        "GDP at market prices 561.3 1.7 1.1 1.1 1.1 1.2\n"
        "Private consumption 289.7 1.1 2.0 1.9 1.1 0.9\n"
        "Government consumption 131.6 2.7 1.8 1.0 1.0 0.5\n"
        "Gross fixed capital formation 134.3 3.1 2.0 -1.1 1.1 1.4\n"
    )
    assert _visual_candidate_looks_table_like("Belgium", text) is True


def test_visual_candidate_looks_table_like_rejects_forecast_header_block() -> None:
    text = (
        "2022 2023 2024 2025 2026 2027\n"
        "Current prices\n"
        "Percentage changes, volume\n"
        "GDP at market prices 5 4 3 2 1 0\n"
        "Memorandum items\n"
        "Consumer price index 6 5 4 3 2 1\n"
    )

    assert (
        _visual_candidate_looks_table_like(
            "Ukraine: Demand, output and prices",
            text,
            kind="panel",
            panel_data_signal=False,
        )
        is True
    )


def test_final_chart_candidate_looks_forecast_table_rejects_country_table_shadow() -> (
    None
):
    candidate = Candidate(
        schema_version="1.0",
        id="chart-271-0",
        kind="chart",
        page=271,
        bbox=(40.0, 40.0, 400.0, 260.0),
        preview_text="Ukraine",
        caption="Ukraine: Demand, output and prices",
    )
    text = (
        "2022 2023 2024 2025 2026 2027\n"
        "Current prices\n"
        "Percentage changes, volume\n"
        "GDP at market prices 5 4 3 2 1 0\n"
        "Memorandum items\n"
        "Consumer price index 6 5 4 3 2 1\n"
    )

    assert _final_chart_candidate_looks_forecast_table(candidate, text) is True


def test_final_chart_candidate_looks_forecast_table_rejects_split_year_header_shadow() -> (
    None
):
    candidate = Candidate(
        schema_version="1.0",
        id="chart-271-0",
        kind="chart",
        page=271,
        bbox=(40.0, 40.0, 400.0, 260.0),
        preview_text="Ukraine",
        caption="Ukraine: Demand, output and prices",
    )
    text = (
        "Ukraine: Demand, output and prices\n"
        "StatLink https://stat.link/example\n"
        "2022\n2023\n2024\n2025\n2026\n2027\n"
        "Ukraine\n"
        "Current prices\n"
        "UAH billion\n"
        "GDP at market prices\n"
        "Memorandum items\n"
        "Consumer price index\n"
        "Source: OECD Economic Outlook 118 database.\n"
        "Percentage changes, volume\n"
        "(2020 prices)\n"
    )

    assert _final_chart_candidate_looks_forecast_table(candidate, text) is True


def test_collect_candidates_table_bbox_keeps_title_and_notes_but_excludes_body_text(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "table-context.pdf"
    out_dir = tmp_path / "out"
    _build_table_context_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    assert tables
    table = max(tables, key=lambda candidate: candidate.bbox[2] - candidate.bbox[0])

    assert table.bbox[1] <= 90.0
    assert table.bbox[3] >= 420.0
    assert table.bbox[3] < 485.0


def test_expand_table_bbox_stream_trims_unrelated_top_notes_and_body_text(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-table-spillover.pdf"
    _build_stream_table_spillover_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (40.0, 40.0, 585.0, 820.0), "stream")
    finally:
        doc.close()

    assert expanded[1] > 320.0
    assert expanded[1] < 365.0
    assert expanded[3] >= 660.0
    assert expanded[3] < 708.0


def test_expand_table_bbox_stream_keeps_trailing_row_and_wrapped_footnotes(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-country-table-split.pdf"
    _build_stream_country_table_split_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (60.0, 40.0, 650.0, 780.0), "stream")
    finally:
        doc.close()

    assert expanded[1] > 50.0
    assert expanded[1] < 90.0
    assert expanded[3] >= 648.0
    assert expanded[3] < 690.0


def test_expand_table_bbox_stream_clamps_internal_title_and_references(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-table-heading-bounds.pdf"
    _build_stream_table_with_heading_bounds_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (40.0, 40.0, 660.0, 820.0), "stream")
    finally:
        doc.close()

    assert expanded[1] >= 130.0
    assert expanded[1] < 180.0
    assert expanded[3] >= 380.0
    assert expanded[3] < 648.0


def test_expand_table_bbox_stream_keeps_explicit_title_restores_right_edge_and_note(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-table-title-note-right-edge.pdf"
    _build_stream_table_title_note_and_right_edge_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (40.0, 140.0, 520.0, 392.0), "stream")
    finally:
        doc.close()

    assert expanded[1] <= 90.0
    assert expanded[2] >= 620.0
    assert expanded[3] >= 288.0


def test_expand_table_bbox_stream_keeps_mixed_legend_and_footnote_footer(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-table-legend-footer.pdf"
    _build_stream_table_legend_footer_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (40.0, 40.0, 650.0, 760.0), "stream")
    finally:
        doc.close()

    assert expanded[3] >= 420.0
    assert expanded[3] < 460.0


def test_expand_table_bbox_lattice_keeps_mixed_legend_and_footnote_footer(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "table-legend-footer.pdf"
    _build_table_legend_footer_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (40.0, 130.0, 560.0, 420.0), "lattice")
    finally:
        doc.close()

    assert expanded[3] >= 480.0
    assert expanded[3] < 540.0


def test_expand_table_bbox_lattice_restores_right_edge_from_overlapping_text(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "lattice-table-right-edge.pdf"
    _build_lattice_right_edge_table_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (42.0, 468.0, 436.0, 567.0), "lattice")
    finally:
        doc.close()

    assert expanded[2] >= 470.0


def test_expand_table_bbox_lattice_restores_left_edge_and_title_from_dense_tabular_block(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "lattice-table-left-edge-and-title.pdf"
    _build_lattice_right_edge_table_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (180.0, 490.0, 436.0, 567.0), "lattice")
    finally:
        doc.close()

    assert expanded[0] <= 50.0
    assert expanded[1] <= 476.0
    assert expanded[2] >= 470.0


def test_expand_table_bbox_stream_restores_top_slack_for_continuation_header_band(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "stream-table-continuation-header.pdf"
    _build_stream_table_continuation_header_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        expanded = _expand_table_bbox(page, (0.0, 66.0, 595.0, 300.0), "stream")
    finally:
        doc.close()

    assert expanded[1] <= 58.0
    assert expanded[1] > 52.0


def test_collect_candidates_rejects_boxed_prose_false_table(tmp_path) -> None:
    pdf_path = tmp_path / "boxed-prose.pdf"
    out_dir = tmp_path / "out"
    _build_boxed_prose_pdf(pdf_path)

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="boxed-prose",
        ),
        _ctx(),
    )

    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    assert tables == []


def test_collect_candidates_rejects_contents_like_false_table(tmp_path, caplog) -> None:
    pdf_path = tmp_path / "contents-like.pdf"
    out_dir = tmp_path / "out"
    _build_contents_like_pdf(pdf_path)

    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="contents-like",
        ),
        _ctx(),
    )

    tables = [
        candidate for candidate in response.candidates if candidate.kind == "table"
    ]
    assert tables == []
    events = _events(caplog, "market_lense.pdf_service.candidate_extraction")
    complete = next(
        event for event in events if event.get("event") == "extract_candidates_complete"
    )
    fields = complete.get("fields")
    assert isinstance(fields, dict)
    table_stats = fields.get("table_stats")
    assert isinstance(table_stats, dict)
    reasons = table_stats.get("reasons")
    assert isinstance(reasons, dict)
    assert (
        int(reasons.get("contents_like", 0))
        + int(reasons.get("section_list", 0))
        + int(reasons.get("stream_list", 0))
    ) >= 1


def test_validate_table_candidate_rejects_contents_like_layout() -> None:
    toc_lines = "\n".join(
        [
            "Acknowledgements 7",
            "Editorial Resilient growth but with increasing fragilities 9",
            "1. General assessment of the macroeconomic situation 11",
            "Introduction 11",
            "Recent Developments 13",
            "Projections 28",
            "Risks 33",
            "Policies 45",
            "References 61",
            "2. Time for a Regulatory Reset? 67",
            "Summary 67",
            "The productivity slowdown has been underpinned by a decline in economic dynamism 68",
            "The case for a regulatory reset 69",
            "Executing the regulatory reset 79",
            "References 96",
            "3. Developments in individual OECD and selected non-member economies 105",
        ]
    )
    candidate = _table_candidate(
        row_count=16,
        col_count=5,
        non_empty_cells=43,
        total_cells=80,
        numeric_cells=16,
        numeric_ratio=0.12,
        avg_words_per_cell=1.6,
        avg_first_col_words=1.4,
        preview="Acknowledgements 7",
        text=toc_lines,
        text_len=len(toc_lines),
        line_count=16,
        avg_line_len=31.0,
        text_block_area_frac=0.58,
        text_block_line_count=16,
        text_block_avg_line_len=31.0,
        area_frac=0.42,
        width_frac=0.82,
        height_frac=0.62,
        aspect=0.86,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "contents_like"


def test_validate_table_candidate_rejects_section_list_with_dot_leaders() -> None:
    toc_text = "\n".join(
        [
            "02 . . . Executive summary",
            "04 . . . Innovation compounds",
            "09 . . . AI goes physical: Navigating the convergence of AI and robotics",
            "21 . . . The agentic reality check: Preparing for a silicon-based workforce",
            "33 . . . The AI infrastructure reckoning: Optimizing compute strategy",
            "43 . . . The great rebuild: Architecting an AI-native tech organization",
            "53 . . . The AI dilemma: Securing and leveraging AI for cyber defense",
            "62 . . . Cutting through the noise: Tech signals worth tracking as AI advances",
            "Table of contents",
        ]
    )
    candidate = _table_candidate(
        row_count=13,
        col_count=3,
        non_empty_cells=23,
        total_cells=39,
        numeric_cells=5,
        numeric_ratio=0.09,
        avg_words_per_cell=2.57,
        avg_first_col_words=1.2,
        preview="02 . . . Executive summary",
        text=toc_text,
        text_len=len(toc_text),
        line_count=9,
        avg_line_len=38.0,
        text_block_area_frac=0.24,
        text_block_line_count=9,
        text_block_avg_line_len=38.0,
        area_frac=0.1145,
        width_frac=0.3,
        height_frac=0.62,
        aspect=0.27,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason in {"section_list", "front_matter"}


def test_validate_table_candidate_rejects_fragmented_dot_leader_section_list() -> None:
    toc_text = "\n".join(
        [
            "stn",
            "02 . .",
            ". Executive summary",
            "04 . .",
            ". Innovation compounds",
            "09 . .",
            ". AI goes physical",
            "21 . .",
            ". The agentic reality check",
            "33 . .",
            ". The AI infrastructure reckoning",
        ]
    )
    candidate = _table_candidate(
        row_count=13,
        col_count=3,
        non_empty_cells=23,
        total_cells=39,
        numeric_cells=5,
        numeric_ratio=0.09,
        avg_words_per_cell=2.57,
        avg_first_col_words=1.2,
        preview="stn | 02 . . | . Executive s",
        text=toc_text,
        text_len=len(toc_text),
        line_count=11,
        avg_line_len=18.0,
        text_block_area_frac=0.24,
        text_block_line_count=11,
        text_block_avg_line_len=18.0,
        area_frac=0.1145,
        width_frac=0.3,
        height_frac=0.62,
        aspect=0.27,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "section_list"


def test_validate_table_candidate_rejects_reference_block() -> None:
    reference_text = "\n".join(
        [
            "OECD (2024c), Competition and regulation in professions and occupations, OECD Roundtables on Competition Policy Papers, No. 307, OECD Publishing, Paris, https://doi.org/10.1787/218869f5-en.",
            "OECD (2024d), Competitive Neutrality Toolkit: Promoting a Level Playing Field, OECD Publishing, Paris, https://doi.org/10.1787/3247ba44-en.",
            "OECD (2024e), Education at a Glance 2024: OECD Indicators, OECD Publishing, Paris, https://doi.org/10.1787/c00cad36-en.",
            "OECD (2024f), Regulatory experimentation: Moving ahead on the agile regulatory governance agenda, OECD Public Governance Policy Papers, No. 47, OECD Publishing, Paris, https://doi.org/10.1787/f193910c-en.",
        ]
    )
    candidate = _table_candidate(
        row_count=46,
        col_count=5,
        non_empty_cells=179,
        total_cells=230,
        numeric_cells=5,
        numeric_ratio=0.106,
        avg_words_per_cell=2.74,
        avg_first_col_words=1.7,
        preview="OECD (2024c), Competition and regulation in professions and occupations",
        text=reference_text,
        text_len=len(reference_text),
        line_count=46,
        avg_line_len=75.0,
        text_block_area_frac=0.74,
        text_block_line_count=46,
        text_block_avg_line_len=71.0,
        area_frac=0.63,
        width_frac=0.74,
        height_frac=0.79,
        aspect=0.64,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "reference_block"


def test_validate_table_candidate_rejects_multicolumn_reference_block() -> None:
    reference_text = "\n".join(
        [
            "1. Gartner, Inc., “Gartner predicts over 40% of agentic AI projects will be canceled by end of 2027,” press release, June 25, 2025.",
            "2. Gartner, “Gartner survey reveals gen AI attacks are on the rise,” press release, Sept. 22, 2025.",
            "3. Deloitte US, “Artificial intelligence: An emerging oversight responsibility for audit committees?” accessed Nov. 11, 2025.",
            "4. Pat Niemann, “Cyber and AI oversight disclosures: What companies shared in 2025,” Harvard Law School Forum on Corporate Governance, Oct. 28, 2025.",
            "5. Roberto Frossard, interview with Deloitte, Sept. 17, 2025.",
        ]
    )
    candidate = _table_candidate(
        row_count=33,
        col_count=11,
        non_empty_cells=186,
        total_cells=363,
        numeric_cells=18,
        numeric_ratio=0.08,
        avg_words_per_cell=2.25,
        avg_first_col_words=1.1,
        preview="1. Gartner, Inc., Gartner predicts over 40% of agentic AI projects",
        text=reference_text,
        text_len=len(reference_text),
        line_count=33,
        avg_line_len=67.0,
        text_block_area_frac=0.69,
        text_block_line_count=33,
        text_block_avg_line_len=67.0,
        area_frac=0.6961,
        width_frac=1.0,
        height_frac=0.86,
        aspect=0.87,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "reference_block"


def test_validate_table_candidate_keeps_wide_table_with_numbered_footnotes() -> None:
    table_text = "\n".join(
        [
            "Euro area 1",
            "1. The job vacancy rate measures the proportion of total posts that are vacant.",
            "2. Three-month moving average.",
            "3. The dashed line indicates the ECB's inflation target of 2%.",
            "Source: Eurostat Job vacancy statistics database; OECD Economic Outlook 118 database.",
            "StatLink 2 https://stat.link/sohe47",
            "Euro area: Demand, output and prices",
            "2022 2023 2024 2025 2026 2027",
            "GDP at market prices 13 634.9 0.5 0.8 1.3 1.2 1.4",
            "Private consumption 7 188.7 0.5 1.2 1.2 1.1 1.2",
            "Government consumption 2 918.6 1.5 2.2 1.6 1.2 1.0",
            "General government gross debt (% of GDP) _ 94.4 93.6 94.3 95.5 96.5",
        ]
    )
    candidate = _table_candidate(
        row_count=40,
        col_count=14,
        non_empty_cells=323,
        total_cells=560,
        numeric_cells=80,
        numeric_ratio=0.14,
        avg_words_per_cell=1.44,
        avg_first_col_words=1.7,
        preview="Euro area 1",
        text=table_text,
        text_len=len(table_text),
        line_count=40,
        avg_line_len=54.4,
        text_block_area_frac=0.46,
        text_block_line_count=40,
        text_block_avg_line_len=54.4,
        area_frac=0.7059,
        width_frac=0.76,
        height_frac=0.93,
        aspect=0.65,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is True
    assert reason == ""


def test_validate_table_candidate_rejects_front_matter_page() -> None:
    front_matter_text = "\n".join(
        [
            "Acknowledgments",
            "Much gratitude goes to the many subject matter leaders across Deloitte who contributed to our research for this chapter: Jinlei Liu,",
            "Baris Sarer, Kate Fusillo Schmidt, Prakul Sharma, Akash Tayal, and Ashish Verma.",
        ]
    )
    candidate = _table_candidate(
        row_count=12,
        col_count=2,
        non_empty_cells=12,
        total_cells=24,
        numeric_cells=0,
        numeric_ratio=0.007,
        avg_words_per_cell=3.67,
        avg_first_col_words=3.67,
        preview="Acknowledgments",
        text=front_matter_text,
        text_len=len(front_matter_text),
        line_count=12,
        avg_line_len=52.0,
        text_block_area_frac=0.73,
        text_block_line_count=12,
        text_block_avg_line_len=52.0,
        area_frac=0.7255,
        width_frac=1.0,
        height_frac=0.83,
        aspect=0.83,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "front_matter"


def test_validate_table_candidate_rejects_visual_quote_page() -> None:
    quote_text = "\n".join(
        [
            "As technology innovation and adoption",
            "accelerate, five trends reveal how",
            "successful organizations are moving from",
            "experimentation to impact",
        ]
    )
    candidate = _table_candidate(
        row_count=8,
        col_count=2,
        non_empty_cells=8,
        total_cells=16,
        numeric_cells=0,
        numeric_ratio=0.026,
        avg_words_per_cell=2.75,
        avg_first_col_words=2.75,
        preview="As technology innovation and adoption",
        text=quote_text,
        text_len=len(quote_text),
        line_count=8,
        avg_line_len=31.0,
        text_block_area_frac=0.08,
        text_block_line_count=8,
        text_block_avg_line_len=31.0,
        area_frac=0.2896,
        width_frac=0.325,
        height_frac=0.93,
        aspect=0.28,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "visual_quote_page"


def test_validate_table_candidate_rejects_contact_block() -> None:
    contact_text = "\n".join(
        [
            "Find out more",
            "If you'd like additional information on Brand Footprint,",
            "please get in touch with your usual contacts or email:",
            "Benjamin Cawthray",
            "Worldpanel by Numerator",
            "Benjamin.Cawthray@wp.numerator.com",
        ]
    )
    candidate = _table_candidate(
        row_count=8,
        col_count=2,
        non_empty_cells=11,
        total_cells=16,
        numeric_cells=0,
        numeric_ratio=0.0,
        avg_words_per_cell=3.6,
        avg_first_col_words=2.8,
        preview="Find out more",
        text=contact_text,
        text_len=len(contact_text),
        line_count=8,
        avg_line_len=36.0,
        text_block_area_frac=0.27,
        text_block_line_count=8,
        text_block_avg_line_len=37.5,
        area_frac=0.226,
        width_frac=0.38,
        height_frac=0.60,
        aspect=0.88,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "contact_block"


def test_validate_table_candidate_rejects_short_prose_box() -> None:
    prose_text = "\n".join(
        [
            "Box 1.2. US tariff rates: in law and in effect",
            "In recent months the United States has continued to announce additional tariff increases on imports from most countries.",
            "This box discusses some of the issues involved in calculating the aggregate effective tariff rate for each country.",
            "The overall impact of tariffs is expected to vary widely by country.",
        ]
    )
    candidate = _table_candidate(
        method="lattice",
        row_count=4,
        col_count=3,
        non_empty_cells=4,
        total_cells=12,
        numeric_cells=0,
        numeric_ratio=0.006,
        avg_words_per_cell=14.0,
        avg_first_col_words=14.0,
        preview="Box 1.2. US tariff rates: in law and in effect",
        text=prose_text,
        text_len=len(prose_text),
        line_count=4,
        avg_line_len=88.0,
        text_block_area_frac=0.61,
        text_block_line_count=4,
        text_block_avg_line_len=88.0,
        caption_hint=True,
        area_frac=0.07,
        width_frac=0.77,
        height_frac=0.11,
        aspect=7.0,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "prose_box"


def test_validate_table_candidate_rejects_figure_caption_context() -> None:
    candidate = _table_candidate(
        method="lattice",
        row_count=4,
        col_count=4,
        non_empty_cells=12,
        total_cells=16,
        numeric_cells=0,
        numeric_ratio=0.05,
        avg_words_per_cell=3.2,
        text=(
            "Figure 1.1. Interpretation of quadrant charts\n"
            "Lower expenditure Higher life expectancy\n"
            "Higher expenditure Higher life expectancy\n"
            "Lower expenditure Lower life expectancy\n"
        ),
        text_len=180,
        line_count=4,
        avg_line_len=44.0,
        text_block_area_frac=0.16,
        text_block_line_count=4,
        text_block_avg_line_len=44.0,
        caption_hint=True,
        figure_context_hint=True,
        area_frac=0.08,
        width_frac=0.72,
        height_frac=0.18,
        aspect=1.8,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "figure_caption_context"


def test_validate_table_candidate_rejects_figure_chart_fragment() -> None:
    candidate = _table_candidate(
        method="lattice",
        row_count=2,
        col_count=6,
        non_empty_cells=12,
        total_cells=12,
        numeric_cells=12,
        numeric_ratio=0.76,
        avg_words_per_cell=2.0,
        avg_first_col_words=1.4,
        preview="Switzerland | 15 | Germany | 22",
        text="Switzerland 15 Germany 22 France 43",
        text_len=36,
        line_count=2,
        avg_line_len=18.0,
        text_block_area_frac=0.08,
        text_block_line_count=2,
        text_block_avg_line_len=18.0,
        caption_hint=False,
        figure_context_hint=False,
        wide_figure_context_hint=True,
        area_frac=0.016,
        width_frac=0.48,
        height_frac=0.05,
        aspect=3.1,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "figure_chart_fragment"


def test_validate_table_candidate_keeps_dense_infographic_value_panel() -> None:
    candidate = _table_candidate(
        method="lattice",
        row_count=6,
        col_count=4,
        non_empty_cells=18,
        total_cells=24,
        numeric_cells=12,
        numeric_ratio=0.6,
        avg_words_per_cell=1.0,
        avg_first_col_words=1.0,
        preview="OECD | 19.0 | 8.5 | 14.8",
        text="OECD 19.0 8.5 14.8\nHungary 22.2 10.3 24.9\nKorea 5.1 7.8 15.3",
        text_len=68,
        line_count=3,
        avg_line_len=22.0,
        text_block_area_frac=0.08,
        text_block_line_count=3,
        text_block_avg_line_len=22.0,
        caption_hint=False,
        figure_context_hint=False,
        wide_figure_context_hint=True,
        area_frac=0.036,
        width_frac=0.32,
        height_frac=0.14,
        aspect=2.6,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is True
    assert reason == ""


def test_validate_table_candidate_rejects_section_list() -> None:
    section_text = "\n".join(
        [
            "Population coverage for healthcare",
            "Unmet needs for healthcare",
            "Extent of healthcare coverage",
            "Financial hardship and out-of-pocket expenditure",
            "Waiting times",
            "Physical access to services",
            "Consultations with doctors",
            "Hospital beds and occupancy",
            "Hospital activity",
            "Hip and knee replacement",
            "Ambulatory surgery",
            "5 Access and coverage",
        ]
    )
    candidate = _table_candidate(
        method="stream",
        row_count=12,
        col_count=3,
        non_empty_cells=24,
        total_cells=36,
        numeric_cells=0,
        numeric_ratio=0.0,
        avg_words_per_cell=2.8,
        avg_first_col_words=2.8,
        preview="Population coverage for healthcare",
        text=section_text,
        text_len=len(section_text),
        line_count=12,
        avg_line_len=29.0,
        text_block_area_frac=0.42,
        text_block_line_count=12,
        text_block_avg_line_len=29.0,
        area_frac=0.15,
        width_frac=0.52,
        height_frac=0.18,
        aspect=1.1,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "section_list"


def test_validate_table_candidate_rejects_stream_slide_card() -> None:
    candidate = _table_candidate(
        method="stream",
        row_count=10,
        col_count=6,
        col_consistency=0.57,
        non_empty_cells=40,
        total_cells=60,
        numeric_cells=1,
        numeric_ratio=0.01,
        avg_words_per_cell=3.0,
        avg_first_col_words=3.0,
        preview="84% | 82% | 76% | For marketers",
        text=(
            "84% 82% 76%\n"
            "You might trust a premium channel, but quality still varies.\n"
            "Brands should prioritise better transparency and optimisation.\n"
            "For marketers\n"
            "Concern for media quality will continue to be prevalent."
        ),
        text_len=196,
        line_count=18,
        avg_line_len=43.0,
        text_block_area_frac=0.56,
        text_block_line_count=38,
        text_block_avg_line_len=43.0,
        area_frac=0.42,
        width_frac=0.86,
        height_frac=0.52,
        aspect=1.5,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "stream_slide_card"


def test_validate_table_candidate_rejects_contents_grid() -> None:
    candidate = _table_candidate(
        method="stream",
        row_count=7,
        col_count=4,
        col_consistency=0.71,
        non_empty_cells=28,
        total_cells=28,
        numeric_cells=4,
        numeric_ratio=0.13,
        avg_words_per_cell=1.38,
        avg_first_col_words=1.29,
        preview="01 | 02 | 03 | 04",
        text=(
            "01 02 03 04\n"
            "TOP MEDIA THE RISE OF SOCIAL DIGITAL\n"
            "CHALLENGES AND GENERATIVE AI MEDIA VIDEO\n"
            "OPPORTUNITIES\n"
            "05 06 07 08\n"
            "CONNECTED RETAIL MEDIA LOOKING AHEAD ABOUT IAS\n"
            "TV NETWORKS TO 2026"
        ),
        text_len=184,
        line_count=7,
        avg_line_len=24.7,
        text_block_area_frac=1.08,
        text_block_line_count=7,
        text_block_avg_line_len=24.7,
        area_frac=0.42,
        width_frac=0.82,
        height_frac=0.32,
        aspect=2.66,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "contents_grid"


def test_has_figure_context_hint_detects_figure_but_not_table_title(tmp_path) -> None:
    figure_pdf = tmp_path / "figure-context.pdf"
    table_pdf = tmp_path / "table-context.pdf"
    _build_chart_caption_spillover_pdf(figure_pdf)
    _build_table_context_pdf(table_pdf)

    figure_doc = fitz.open(figure_pdf.as_posix())
    table_doc = fitz.open(table_pdf.as_posix())
    try:
        assert (
            _has_figure_context_hint(
                figure_doc[0],
                (65.0, 208.0, 560.0, 520.0),
            )
            is True
        )
        assert (
            _has_figure_context_hint(
                figure_doc[0],
                (320.0, 208.0, 560.0, 520.0),
            )
            is True
        )
        assert (
            _has_figure_context_hint(
                table_doc[0],
                (40.0, 130.0, 560.0, 360.0),
            )
            is False
        )
    finally:
        figure_doc.close()
        table_doc.close()


def test_validate_table_candidate_keeps_numeric_country_table() -> None:
    candidate = _table_candidate()

    ok, reason = _validate_table_candidate(candidate)

    assert ok is True
    assert reason == ""


def test_dedupe_table_candidates_prefers_inner_lattice_over_stream_shadow() -> None:
    stream_candidate = _table_candidate(
        bbox=(0.0, 64.6, 595.3, 711.7),
        method="stream",
        row_count=54,
        col_count=11,
        non_empty_cells=440,
        total_cells=594,
        numeric_cells=90,
        numeric_ratio=0.225,
        avg_words_per_cell=1.3,
        text_len=2424,
        area_frac=0.7273,
        aspect=0.72,
    )
    lattice_candidate = _table_candidate(
        bbox=(42.4, 64.6, 554.9, 711.7),
        method="lattice",
        row_count=41,
        col_count=24,
        non_empty_cells=320,
        total_cells=984,
        numeric_cells=140,
        numeric_ratio=0.432,
        avg_words_per_cell=1.09,
        text_len=1287,
        area_frac=0.4918,
        aspect=0.84,
    )

    deduped = _dedupe_table_candidates([stream_candidate, lattice_candidate])

    assert deduped == [lattice_candidate]


def test_table_dedupe_spatial_index_limits_lookup_to_overlapping_rows() -> None:
    index = _TableDedupeSpatialIndex()
    far_above = _table_candidate(bbox=(40.0, 10.0, 560.0, 60.0))
    near = _table_candidate(bbox=(40.0, 210.0, 560.0, 280.0))
    far_below = _table_candidate(bbox=(40.0, 700.0, 560.0, 760.0))

    index.add(0, far_above)
    index.add(1, near)
    index.add(2, far_below)

    matches = index.lookup(_table_candidate(bbox=(50.0, 220.0, 550.0, 260.0)))

    assert matches == [1]
