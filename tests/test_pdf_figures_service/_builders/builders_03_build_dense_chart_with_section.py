# ruff: noqa: F401,F403,F405
from __future__ import annotations

from .shared import *  # noqa: F401,F403

def _build_dense_chart_with_section_heading_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((42, 96), "Figure 1.1. Dense labeled chart", fontsize=20)
    page.draw_rect(
        fitz.Rect(36, 132, 584, 682),
        color=(0.7, 0.7, 0.7),
        fill=(0.93, 0.93, 0.93),
        width=1.0,
    )
    for idx in range(34):
        y = 168 + idx * 6
        page.insert_text((60, y), f"C{idx:02d}", fontsize=8)
        page.insert_text((118, y), f"{60 + idx}", fontsize=8)
        page.insert_text((186, y), f"{24 + idx % 9}%", fontsize=8)
        page.insert_text((256, y), f"L{idx % 7}", fontsize=8)
        page.insert_text((322, y), f"{100 + idx}", fontsize=8)
        page.insert_text((396, y), f"{idx % 5}.{idx % 9}", fontsize=8)
        page.insert_text((462, y), f"R{idx % 8}", fontsize=8)
    page.insert_text((48, 360), "Methodology, interpretation and use", fontsize=21)
    page.insert_textbox(
        fitz.Rect(48, 398, 566, 648),
        "This explanatory section must stay outside the figure crop. " * 20,
        fontsize=12,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_multi_figure_dense_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((42, 96), "Figure 5.26. Upper dense chart", fontsize=18)
    page.draw_rect(
        fitz.Rect(36, 132, 584, 520),
        color=(0.8, 0.8, 0.8),
        fill=(0.94, 0.94, 0.94),
        width=1.0,
    )
    page.draw_rect(
        fitz.Rect(36, 522, 584, 762),
        color=(0.8, 0.8, 0.8),
        fill=(0.94, 0.94, 0.94),
        width=1.0,
    )
    for idx in range(28):
        y = 174 + idx * 8
        page.insert_text((60, y), f"A{idx:02d}", fontsize=8)
        page.insert_text((126, y), f"{80 + idx}", fontsize=8)
        page.insert_text((208, y), f"{idx % 10}%", fontsize=8)
        page.insert_text((284, y), f"B{idx % 6}", fontsize=8)
        page.insert_text((350, y), f"{40 + idx}", fontsize=8)
        page.insert_text((430, y), f"{idx % 7}.{idx % 3}", fontsize=8)
    page.insert_text(
        (42, 470),
        "Figure 5.27. Lower dense chart",
        fontsize=18,
    )
    for idx in range(24):
        y = 528 + idx * 8
        page.insert_text((60, y), f"C{idx:02d}", fontsize=8)
        page.insert_text((126, y), f"{50 + idx}", fontsize=8)
        page.insert_text((208, y), f"{idx % 9}%", fontsize=8)
        page.insert_text((284, y), f"D{idx % 5}", fontsize=8)
        page.insert_text((350, y), f"{25 + idx}", fontsize=8)
        page.insert_text((430, y), f"{idx % 4}.{idx % 8}", fontsize=8)
    doc.save(path.as_posix())
    doc.close()

def _build_wide_captioned_draw_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(42, 110, 576, 360),
        "This explanatory paragraph should remain outside the figure crop. " * 12,
        fontsize=12,
        lineheight=1.2,
    )
    page.draw_rect(
        fitz.Rect(36, 430, 584, 640),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 442), "Figure 1", fontsize=12)
    page.insert_text(
        (48, 468),
        "How vision-language-action models work",
        fontsize=18,
    )
    page.draw_rect(
        fitz.Rect(54, 520, 274, 576),
        color=(0.55, 0.75, 0.85),
        width=1.0,
    )
    page.draw_rect(
        fitz.Rect(332, 520, 552, 576),
        color=(0.55, 0.75, 0.85),
        width=1.0,
    )
    page.draw_line((288, 548), (320, 548), color=(0.2, 0.2, 0.2), width=1.0)
    page.insert_text((92, 544), "Vision", fontsize=10)
    page.insert_text((400, 544), "Action", fontsize=10)
    page.insert_text((48, 620), "Source: Deloitte analysis.", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_captioned_draw_charts_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(42, 72, 576, 148),
        "Lead-in paragraph text that should stay outside both figure crops.",
        fontsize=12,
        lineheight=1.2,
    )

    page.draw_rect(
        fitz.Rect(36, 170, 584, 382),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 182), "Figure 1", fontsize=12)
    page.insert_text(
        (48, 208),
        "Projected agentic AI adoption",
        fontsize=17,
    )
    page.draw_line((240, 250), (240, 340), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((360, 250), (360, 340), color=(0.6, 0.6, 0.6), width=0.8)
    page.draw_line((210, 340), (390, 340), color=(0.25, 0.25, 0.25), width=1.0)
    page.draw_line((240, 340), (360, 280), color=(0.15, 0.15, 0.15), width=1.0)
    page.draw_line((240, 340), (360, 220), color=(0.15, 0.15, 0.15), width=1.0)
    page.insert_text((370, 220), "33%", fontsize=10)
    page.insert_text((370, 280), "15%", fontsize=10)
    page.insert_text((48, 354), "Source: Deloitte analysis.", fontsize=10)

    page.draw_rect(
        fitz.Rect(36, 440, 584, 652),
        color=(0.8, 0.8, 0.8),
        fill=(0.95, 0.95, 0.95),
        width=1.0,
    )
    page.insert_text((48, 452), "Figure 2", fontsize=12)
    page.insert_text(
        (48, 478),
        "AI model security risks and associated mitigation strategies",
        fontsize=17,
    )
    page.insert_text((48, 524), "Risks", fontsize=11)
    page.insert_text((320, 524), "Mitigation", fontsize=11)
    page.draw_line((48, 538), (552, 538), color=(0.2, 0.2, 0.2), width=1.0)
    page.draw_line((300, 504), (300, 618), color=(0.4, 0.4, 0.4), width=0.8)
    risk_labels = [
        "Collapse",
        "Stealing",
        "Inversion",
        "Agency abuse",
        "Bias drift",
        "Leakage",
        "Skew",
        "Outage",
        "Misuse",
        "Drift",
    ]
    mitigation_labels = [
        "Isolation",
        "Access mgmt",
        "Audit logs",
        "Safeguards",
        "Red team",
        "Hardening",
        "Alerts",
        "Monitoring",
        "Testing",
        "Reviews",
    ]
    for idx, label in enumerate(risk_labels):
        page.insert_text((48, 550 + idx * 7), label, fontsize=8)
    for idx, label in enumerate(mitigation_labels):
        page.insert_text((320, 550 + idx * 7), label, fontsize=8)
    page.insert_text((48, 624), "Source: Deloitte analysis.", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_table_context_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 32), "130 |", fontsize=12)
    page.insert_text(
        (18, 82),
        "Chile: Demand, output and prices",
        fontsize=20,
    )

    x0, y0, x1, y1 = 40, 130, 560, 360
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [320, 390, 450, 500]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [170, 210, 250, 290, 330]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))

    headers = ["2022", "2023", "2024", "2025", "2026"]
    for idx, header in enumerate(headers):
        page.insert_text((330 + idx * 45, 150), header, fontsize=11)
    row_labels = [
        "GDP at market prices*",
        "Private consumption",
        "Government consumption",
        "Gross fixed capital formation",
        "Exports of goods and services",
    ]
    values = [
        ["263 104.8", "0.6", "2.4", "2.4", "2.2"],
        ["166 968.0", "-4.8", "0.9", "2.7", "1.7"],
        ["38 686.1", "2.4", "3.2", "4.8", "3.4"],
        ["67 404.4", "0.3", "-1.8", "6.8", "5.1"],
        ["93 653.1", "0.4", "6.3", "3.5", "1.3"],
    ]
    for row_index, label in enumerate(row_labels):
        y = 190 + row_index * 40
        page.insert_text((50, y), label, fontsize=11)
        for col_index, value in enumerate(values[row_index]):
            page.insert_text((330 + col_index * 45, y), value, fontsize=11)

    page.insert_text(
        (40, 390),
        "* Based on seasonally adjusted quarterly data; may differ from official annual data.",
        fontsize=9,
    )
    page.insert_text(
        (40, 408),
        "1. Contributions to changes in GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 426),
        "Source: OECD Economic Outlook 118 database. StatLink https://stat.link/example",
        fontsize=9,
    )
    page.insert_textbox(
        fitz.Rect(40, 490, 580, 660),
        (
            "Global financial conditions have eased over the past year, supporting Chile's "
            "external environment. The terms of trade have improved, driven by rising "
            "copper prices, and the direct macroeconomic effects of higher tariffs are "
            "expected to be limited."
        ),
        fontsize=14,
        lineheight=1.3,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_table_legend_footer_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (40, 82), "Table 1.2. Dashboard on health status, 2023", fontsize=18
    )

    x0, y0, x1, y1 = 40, 130, 560, 420
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [160, 300, 430]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [180, 230, 280, 330, 380]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))

    headers = ["Life expectancy", "Avoidable mortality", "Self-rated health"]
    for idx, header in enumerate(headers):
        page.insert_text((58 + idx * 138, 160), header, fontsize=11)
    rows = [
        ("OECD", ["81.1", "222", "8.0"]),
        ("Australia", ["83.0", "146", "3.8"]),
        ("Belgium", ["82.5", "184", "8.3"]),
        ("Canada", ["81.7", "184", "3.2"]),
        ("Chile", ["81.6", "229", "6.1"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 210 + row_index * 50
        page.insert_text((52, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((190 + col_index * 130, y), value, fontsize=11)

    page.insert_textbox(
        fitz.Rect(40, 432, 570, 540),
        (
            "Better than the OECD average.\n"
            "Close to the OECD average.\n"
            "Worse than the OECD average.\n"
            "1. 2024 data for Chile and Mexico.\n"
            "2. 2020-2022 data for Belgium and Canada."
        ),
        fontsize=9,
        lineheight=1.1,
    )
    page.insert_textbox(
        fitz.Rect(40, 585, 570, 690),
        "This paragraph must remain outside the table crop. " * 16,
        fontsize=13,
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_legend_footer_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((18, 32), "19 |", fontsize=12)
    page.insert_text(
        (40, 82),
        "Table 1.2. Dashboard on health status, 2023 (unless indicated)",
        fontsize=18,
    )

    year_positions = [220, 340, 470]
    headers = ["Life expectancy", "Avoidable mortality", "Self-rated health"]
    for idx, header in enumerate(headers):
        page.insert_text((year_positions[idx], 124), header, fontsize=11)

    rows = [
        ("OECD", ["81.1", "222", "8.0"]),
        ("Australia", ["83.0", "146", "3.8"]),
        ("Belgium", ["82.5", "184", "8.3"]),
        ("Canada", ["81.7", "184", "3.2"]),
        ("Chile", ["81.6", "229", "6.1"]),
        ("Colombia", ["77.5", "419", "1.3"]),
        ("Costa Rica", ["81.0", "241", "N/A"]),
        ("Czechia", ["79.9", "229", "9.1"]),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 168 + row_index * 26
        page.insert_text((48, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_textbox(
        fitz.Rect(42, 366, 650, 456),
        (
            "Better than the OECD average.\n"
            "Close to the OECD average.\n"
            "Worse than the OECD average.\n"
            "1. 2024 data for Chile and Mexico.\n"
            "2. 2020-2022 data for Belgium and Canada."
        ),
        fontsize=9,
        lineheight=1.1,
    )
    page.insert_textbox(
        fitz.Rect(42, 520, 650, 680),
        "This paragraph must remain outside the stream table crop. " * 18,
        fontsize=13,
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_spillover_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 32), "222 |", fontsize=12)
    page.insert_text((40, 292), "1. Four quarters moving average.", fontsize=9)
    page.insert_text(
        (40, 310),
        "Source: OECD Economic Outlook 118 database; and Haut commissariat au Plan, DCN.",
        fontsize=9,
    )
    page.insert_text((400, 332), "StatLink https://stat.link/ryce5w", fontsize=9)
    page.insert_text(
        (40, 356),
        "Morocco: Demand, output and prices",
        fontsize=20,
    )
    year_positions = [330, 375, 420, 465, 510, 555]
    for idx, year in enumerate(["2022", "2023", "2024", "2025", "2026", "2027"]):
        page.insert_text((year_positions[idx], 386), year, fontsize=11)
    page.insert_text((310, 404), "Current prices", fontsize=10)
    page.insert_text((420, 404), "Percentage changes, volume", fontsize=10)
    page.insert_text((316, 420), "MAD billion", fontsize=10)
    page.insert_text((448, 420), "(2014 prices)", fontsize=10)
    page.insert_text((40, 424), "Morocco", fontsize=11)

    rows = [
        ("GDP at market prices", ["1 333.5", "3.7", "3.8", "4.5", "4.2", "4.0"]),
        ("Private consumption", ["827.9", "4.8", "3.4", "4.3", "3.6", "3.3"]),
        ("Government consumption", ["252.6", "6.1", "5.6", "5.4", "4.0", "3.8"]),
        (
            "Gross fixed capital formation",
            ["354.9", "3.0", "13.2", "12.0", "7.3", "7.4"],
        ),
        ("Final domestic demand", ["1 435.4", "4.7", "6.2", "6.5", "4.7", "4.4"]),
        ("Stockbuilding", ["51.3", "0.6", "-0.1", "1.2", "0.5", "0.0"]),
        (
            "Current account balance (% of GDP)",
            ["", "-1.0", "-1.2", "-2.0", "-2.0", "-2.2"],
        ),
    ]
    for row_index, (label, values) in enumerate(rows):
        y = 448 + row_index * 22
        page.insert_text((45 if row_index == 0 else 58, y), label, fontsize=11)
        for col_index, value in enumerate(values):
            if not value:
                continue
            page.insert_text((year_positions[col_index], y), value, fontsize=11)

    page.insert_text(
        (40, 622),
        "1. Contributions to changes in real GDP, actual amount in the first column.",
        fontsize=9,
    )
    page.insert_text(
        (40, 640), "Source: OECD Economic Outlook 118 database.", fontsize=9
    )
    page.insert_text((405, 660), "StatLink https://stat.link/6ptr2h", fontsize=9)
    page.insert_text(
        (40, 708),
        "The fiscal deficit is expected to narrow gradually, while monetary policy interest rates are on hold",
        fontsize=16,
    )
    page.insert_textbox(
        fitz.Rect(40, 742, 585, 860),
        (
            "After bringing the policy rate to 2.25% in March 2025, the central bank paused its easing cycle "
            "despite inflation declining substantially in 2025. The fiscal deficit is expected to narrow "
            "gradually despite robust spending growth."
        ),
        fontsize=13,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_with_heading_bounds_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_textbox(
        fitz.Rect(40, 40, 660, 120),
        (
            "Health inequalities between men and women are also linked to gendered health risks. "
            "Women are more likely to experience physical and mental health impacts of gender-based violence."
        ),
        fontsize=12,
        lineheight=1.2,
    )
    page.insert_text(
        (40, 154),
        "Table 2.3. Dashboard on protective and risk factors for health, 2023 (or nearest year)",
        fontsize=16,
    )
    x0, y0, x1, y1 = 60, 190, 640, 610
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [130, 215, 300, 385, 470, 555]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0), width=0.6)
    for y in range(230, 611, 28):
        page.draw_line((x0, y), (x1, y), color=(0.7, 0.7, 0.7), width=0.5)
    page.insert_text((82, 214), "Country", fontsize=11)
    page.insert_text((180, 214), "Smoking (%)", fontsize=11)
    page.insert_text((266, 214), "Alcohol (%)", fontsize=11)
    page.insert_text((360, 214), "Overweight (%)", fontsize=11)
    page.insert_text((472, 214), "Vegetable consumption (%)", fontsize=11)
    rows = [
        ("OECD", "19", "8.5", "61", "53"),
        ("Australia", "9", "7", "53", "80"),
        ("Austria", "24", "18", "60", "39"),
        ("Belgium", "14", "11", "53", "72"),
        ("Canada", "10", "7", "63", "71"),
        ("Chile", "16", "16", "70", "0"),
    ]
    for idx, row in enumerate(rows):
        y = 252 + idx * 28
        page.insert_text((72, y), row[0], fontsize=11)
        page.insert_text((175, y), row[1], fontsize=11)
        page.insert_text((270, y), row[2], fontsize=11)
        page.insert_text((372, y), row[3], fontsize=11)
        page.insert_text((520, y), row[4], fontsize=11)
    page.insert_text((40, 648), "References", fontsize=14)
    page.insert_textbox(
        fitz.Rect(40, 672, 660, 820),
        (
            "OECD (2024), Rethinking Health System Performance Assessment: A Renewed Framework, OECD Publishing, Paris, "
            "https://doi.org/10.1787/107182c8.\n"
            "OECD/The Health Foundation (2025), How Do Health System Features Influence Health System Performance?, OECD Publishing, Paris."
        ),
        fontsize=11,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_title_note_and_right_edge_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=700, height=900)
    page.insert_text((530, 40), "35 |", fontsize=12)
    page.insert_text(
        (40, 82),
        "Table 2.2. Measured in potential years of life lost, cancer in women and external causes are the leading killers",
        fontsize=16,
    )
    page.insert_text(
        (40, 110),
        "Ranking of top ten diseases by absolute difference (men-women) in potential years of life lost (PYLL)",
        fontsize=12,
    )
    x0, y0, x1, y1 = 60, 150, 650, 330
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [220, 360, 480, 600]:
        page.draw_line((x, y0), (x, y1), color=(0.6, 0.6, 0.6), width=0.6)
    for y in range(182, 331, 28):
        page.draw_line((x0, y), (x1, y), color=(0.75, 0.75, 0.75), width=0.5)
    headers = [
        (88, 170, "Causes¹"),
        (265, 170, "Men"),
        (395, 170, "Women"),
        (505, 170, "Share² among women"),
    ]
    for x, y, text in headers:
        page.insert_text((x, y), text, fontsize=11)
    rows = [
        ("External causes", "2 028", "711", "21% (2)"),
        ("Cardiovascular diseases", "1 268", "556", "16% (3)"),
        ("Neoplasms", "1 215", "1 061", "31% (1)"),
    ]
    for idx, row in enumerate(rows):
        y = 205 + idx * 28
        page.insert_text((72, y), row[0], fontsize=11)
        page.insert_text((282, y), row[1], fontsize=11)
        page.insert_text((408, y), row[2], fontsize=11)
        page.insert_text((560, y), row[3], fontsize=11)
    page.insert_textbox(
        fitz.Rect(42, 248, 655, 436),
        (
            "Note: PYLL is a measure of the impact of different mortality causes for those aged 0-74, "
            "putting a higher weight on premature deaths among younger individuals. OECD averages are "
            "weighted with the 2022 OECD historical population data, using country rates age-standardised "
            "to the 2015 OECD population."
        ),
        fontsize=11,
        lineheight=1.15,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stream_table_continuation_header_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595.276, height=793.701)
    page.insert_text((530, 40), "47 |", fontsize=11)
    page.draw_line((42, 66), (554, 66), color=(0, 0, 0), width=1)
    page.insert_text((220, 78), "Risk factors", fontsize=8)
    page.insert_text((480, 78), "Protective factor", fontsize=8)
    page.insert_text((64, 93), "Country", fontsize=8)
    page.insert_text((128, 93), "Smoking (%)", fontsize=8)
    page.insert_text((205, 93), "Heavy episodic", fontsize=8)
    page.insert_text((292, 93), "Overweight (%)", fontsize=8)
    page.insert_text((378, 93), "Physical inactivity (%)²", fontsize=8)
    page.insert_text((462, 93), "Vegetable consumption (%)", fontsize=8)
    page.insert_text((208, 98), "drinking (%)", fontsize=8)
    for x in [110, 190, 270, 360, 452]:
        page.draw_line((x, 66), (x, 300), color=(0.7, 0.7, 0.7), width=0.5)
    for y in range(108, 300, 22):
        page.draw_line((42, y), (554, y), color=(0.8, 0.8, 0.8), width=0.5)
    rows = [
        ("Netherlands", "16", "11", "35", "16", "51", "46", "10", "13", "51", "62"),
        ("New Zealand", "8", "6", "", "", "", "", "20", "22", "95", "96"),
        ("Norway", "8", "8", "43", "32", "59", "44", "34", "42", "59", "74"),
        ("Peru*", "2", "1", "", "", "", "", "32", "37", "", ""),
    ]
    for idx, row in enumerate(rows):
        y = 120 + idx * 22
        page.insert_text((48, y), row[0], fontsize=8.5)
        xs = [134, 174, 204, 250, 303, 348, 394, 440, 493, 539]
        for x, value in zip(xs, row[1:]):
            if value:
                page.insert_text((x, y), value, fontsize=8.5)
    doc.save(path.as_posix())
    doc.close()

def _build_lattice_right_edge_table_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (42, 474),
        "Table 2. Accession candidate and Key Partner country ISO codes",
        fontsize=16,
    )
    x0, y0, x1, y1 = 42, 490, 560, 570
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    for x in [180, 280, 420]:
        page.draw_line((x, y0), (x, y1), color=(0.7, 0.7, 0.7), width=0.6)
    for y in [515, 540]:
        page.draw_line((x0, y), (x1, y), color=(0.7, 0.7, 0.7), width=0.6)
    rows = [
        ("Argentina", "ARG", "Indonesia", "IDN"),
        ("Brazil", "BRA", "Peru", "PER"),
        ("Croatia", "HRV", "Thailand", "THA"),
    ]
    for idx, row in enumerate(rows):
        y = 507 + idx * 25
        page.insert_text((52, y), row[0], fontsize=11)
        page.insert_text((190, y), row[1], fontsize=11)
        page.insert_text((285, y), row[2], fontsize=11)
        page.insert_text((452, y), row[3], fontsize=11)
    doc.save(path.as_posix())
    doc.close()

__all__ = [
    "_build_dense_chart_with_section_heading_pdf",
    "_build_multi_figure_dense_chart_pdf",
    "_build_wide_captioned_draw_chart_pdf",
    "_build_stacked_captioned_draw_charts_pdf",
    "_build_table_context_pdf",
    "_build_table_legend_footer_pdf",
    "_build_stream_table_legend_footer_pdf",
    "_build_stream_table_spillover_pdf",
    "_build_stream_table_with_heading_bounds_pdf",
    "_build_stream_table_title_note_and_right_edge_pdf",
    "_build_stream_table_continuation_header_pdf",
    "_build_lattice_right_edge_table_pdf",
]
