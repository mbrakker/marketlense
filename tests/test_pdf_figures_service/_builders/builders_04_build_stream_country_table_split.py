# ruff: noqa: F401,F403,F405
from __future__ import annotations

from .shared import *  # noqa: F401,F403

def _build_stream_country_table_split_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((18, 32), "116 |", fontsize=12)
    page.insert_text((40, 82), "Belgium: Demand, output and prices", fontsize=20)

    year_positions = [380, 430, 475, 520, 565, 610]
    for idx, year in enumerate(["2022", "2023", "2024", "2025", "2026", "2027"]):
        page.insert_text((year_positions[idx], 122), year, fontsize=11)
    page.insert_text((360, 140), "Current prices", fontsize=10)
    page.insert_text((500, 140), "Percentage changes, volume", fontsize=10)
    page.insert_text((366, 156), "EUR billion", fontsize=10)
    page.insert_text((534, 156), "(2020 prices)", fontsize=10)
    page.insert_text((40, 166), "Belgium", fontsize=11)

    rows = [
        ("GDP at market prices", ["561.3", "1.7", "1.1", "1.1", "1.1", "1.2"]),
        ("Private consumption", ["289.7", "1.1", "2.0", "1.9", "1.1", "0.9"]),
        ("Government consumption", ["131.6", "2.7", "1.8", "1.0", "1.0", "0.5"]),
        (
            "Gross fixed capital formation",
            ["134.3", "3.1", "2.0", "-1.1", "1.1", "1.4"],
        ),
        ("Final domestic demand", ["555.6", "1.9", "2.0", "0.9", "1.1", "0.9"]),
        ("Stockbuilding¹", ["18.8", "-0.8", "-0.5", "0.4", "0.0", "0.0"]),
        ("Total domestic demand", ["574.4", "1.1", "1.4", "1.4", "1.1", "0.9"]),
        (
            "Exports of goods and services",
            ["530.0", "-7.2", "-1.7", "-0.4", "1.1", "2.2"],
        ),
        (
            "Imports of goods and services",
            ["543.1", "-7.6", "-1.3", "0.0", "1.1", "1.8"],
        ),
        ("Net exports¹", ["-13.1", "0.6", "-0.3", "-0.3", "-0.1", "0.3"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 194 + row_index * 22
        page.insert_text((44 if row_index == 0 else 58, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text((40, 400), "Memorandum items", fontsize=11)
    memo_rows = [
        ("GDP deflator", ["", "5.5", "1.9", "2.4", "1.5", "1.8"]),
        (
            "Harmonised index of consumer prices",
            ["", "2.3", "4.3", "3.0", "1.6", "1.7"],
        ),
        (
            "Harmonised index of core inflation²",
            ["", "6.0", "3.4", "2.2", "2.3", "1.8"],
        ),
        (
            "Unemployment rate (% of labour force)",
            ["", "5.5", "5.7", "6.0", "6.0", "5.9"],
        ),
        (
            "General government financial balance (% of GDP)",
            ["", "-4.0", "-4.4", "-5.5", "-5.4", "-5.2"],
        ),
    ]
    for row_index, (label, values) in enumerate(memo_rows):
        y = 420 + row_index * 18
        page.insert_text((44, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            if value:
                page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text((44, 520), "Current account balance (% of GDP)", fontsize=11)
    for col_index, value in enumerate(["", "0.2", "-0.4", "-1.4", "-1.2", "-0.8"]):
        if value:
            page.insert_text((year_positions[col_index], 520), value, fontsize=11)

    page.insert_text(
        (40, 556),
        "1. Contributions to changes in real GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 574),
        "2. Core inflation excluding volatile items and temporary tax changes.",
        fontsize=9,
    )
    page.insert_text(
        (40, 592),
        "3. The current account balance reflects goods, services and income flows. This note continues on the next line for testing.",
        fontsize=9,
    )
    page.insert_text(
        (40, 610),
        "Continuation of note 3 to ensure wrapped footnotes remain attached to the crop.",
        fontsize=9,
    )
    page.insert_text(
        (40, 628), "Source: OECD Economic Outlook 118 database.", fontsize=9
    )
    page.insert_text((445, 648), "StatLink https://stat.link/example", fontsize=9)
    page.insert_textbox(
        fitz.Rect(40, 700, 650, 820),
        (
            "The fiscal stance is expected to remain prudent, with domestic demand gradually recovering and inflation "
            "converging toward target over the projection horizon."
        ),
        fontsize=13,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_boxed_prose_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 38), "20 |", fontsize=12)
    page.draw_rect(fitz.Rect(20, 90, 600, 820), color=(0.5, 0.0, 0.8), width=1.0)
    page.insert_text(
        (30, 120),
        "Box 1.4. Growing linkages between stablecoins and traditional finance",
        fontsize=18,
    )
    page.insert_textbox(
        fitz.Rect(30, 165, 590, 790),
        (
            "The market valuation of crypto-assets rose sharply over the past year and remains highly volatile.\n\n"
            "Fast growth, high concentration and non-negligible risks also permeate segments of crypto-assets that are intended to be safer.\n\n"
            "The total value of payments using stablecoins surpassed that of major traditional digital payment providers in 2024.\n\n"
            "The growth of crypto-asset exchange-traded products is likely to ease access to crypto-assets further."
        ),
        fontsize=15,
        lineheight=1.35,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_top_stacked_captioned_draw_charts_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 34), "34 |", fontsize=12)

    page.insert_text((36, 58), "Figure 1. Upper stacked draw chart", fontsize=16)
    page.draw_line((60, 120), (280, 120), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((60, 160), (280, 160), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_rect(
        fitz.Rect(62, 190, 268, 300),
        color=(0.2, 0.2, 0.2),
        fill=(0.8, 0.88, 0.98),
        width=1.0,
    )
    page.insert_text(
        (36, 332),
        "Source: synthetic upper chart source.",
        fontsize=10,
    )

    page.insert_text((36, 414), "Figure 2. Lower stacked draw chart", fontsize=16)
    page.draw_rect(
        fitz.Rect(62, 460, 520, 700),
        color=(0.8, 0.8, 0.8),
        fill=(0.96, 0.96, 0.96),
        width=1.0,
    )
    page.draw_line((84, 640), (494, 640), color=(0.25, 0.25, 0.25), width=1.0)
    page.draw_line((150, 640), (150, 520), color=(0.2, 0.2, 0.2), width=1.0)
    page.draw_line((150, 640), (260, 560), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line((260, 560), (360, 520), color=(0.1, 0.1, 0.1), width=1.0)
    page.draw_line((360, 520), (464, 548), color=(0.1, 0.1, 0.1), width=1.0)
    page.insert_text((36, 726), "Source: synthetic lower chart source.", fontsize=10)

    doc.save(path.as_posix())
    doc.close()

def _build_contents_like_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    entries = [
        ("Acknowledgements", "7", 18, 20),
        ("Editorial  Resilient growth but with increasing fragilities", "9", 18, 20),
        ("1. General assessment of the macroeconomic situation", "11", 18, 20),
        ("Introduction", "11", 14, 40),
        ("Recent Developments", "13", 14, 40),
        ("Projections", "28", 14, 40),
        ("Risks", "33", 14, 40),
        ("Policies", "45", 14, 40),
        ("References", "61", 14, 40),
        ("2. Time for a Regulatory Reset?", "67", 18, 20),
        ("Summary", "67", 14, 40),
        (
            "The productivity slowdown has been underpinned by a decline in economic dynamism",
            "68",
            14,
            40,
        ),
        ("The case for a regulatory reset", "69", 14, 40),
        ("Executing the regulatory reset", "79", 14, 40),
        ("References", "96", 14, 40),
        (
            "3. Developments in individual OECD and selected non-member economies",
            "105",
            18,
            20,
        ),
        ("Argentina", "106", 14, 40),
        ("Australia", "109", 14, 40),
        ("Austria", "112", 14, 40),
        ("Belgium", "115", 14, 40),
    ]
    y = 46
    for text, page_no, font_size, x in entries:
        page.insert_text((x, y), text, fontsize=font_size)
        page.insert_textbox(
            fitz.Rect(500, y - 18, 595, y + 4),
            page_no,
            fontsize=font_size,
            align=fitz.TEXT_ALIGN_RIGHT,
        )
        y += 28 if font_size >= 18 else 24
    doc.save(path.as_posix())
    doc.close()

__all__ = [
    "_build_stream_country_table_split_pdf",
    "_build_boxed_prose_pdf",
    "_build_top_stacked_captioned_draw_charts_pdf",
    "_build_contents_like_pdf",
]
