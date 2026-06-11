# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

__all__ = [
    "test_validate_table_candidate_keeps_wide_table_with_numbered_footnotes",
    "test_validate_table_candidate_rejects_front_matter_page",
    "test_validate_table_candidate_rejects_visual_quote_page",
    "test_validate_table_candidate_rejects_contact_block",
    "test_validate_table_candidate_rejects_short_prose_box",
    "test_validate_table_candidate_rejects_figure_caption_context",
    "test_validate_table_candidate_rejects_figure_chart_fragment",
    "test_validate_table_candidate_keeps_dense_infographic_value_panel",
    "test_validate_table_candidate_rejects_section_list",
    "test_validate_table_candidate_rejects_stream_slide_card",
    "test_validate_table_candidate_rejects_contents_grid",
    "test_has_figure_context_hint_detects_figure_but_not_table_title",
    "test_validate_table_candidate_keeps_numeric_country_table",
    "test_dedupe_table_candidates_prefers_inner_lattice_over_stream_shadow",
    "test_table_dedupe_spatial_index_limits_lookup_to_overlapping_rows",
]
