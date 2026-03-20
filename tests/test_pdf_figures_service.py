from __future__ import annotations

import io
import json
import logging
from pathlib import Path

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - depends on PyMuPDF packaging alias
    import pymupdf as fitz

from PIL import Image, ImageDraw

from src.contracts.report_assets import ExtractCandidatesRequest, FigureExtractRequest
from src.contracts.run_context import RunContext
from src.services._pdf.figures import (
    _TableCandidate,
    _clamp_top_to_caption,
    _dedupe_table_candidates,
    _expand_table_bbox,
    _has_figure_context_hint,
    _validate_table_candidate,
)
from src.services.pdf_service import collect_candidates, extract_best_figure


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _chart_image_bytes() -> bytes:
    image = Image.new("RGB", (480, 240), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 440, 200), outline="black", fill=(220, 230, 245))
    draw.text((60, 60), "Figure 1. Growth by quarter", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_candidates_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((72, 72), "Executive summary", fontsize=18)
    page.insert_image(fitz.Rect(70, 120, 550, 360), stream=_chart_image_bytes())
    page.insert_text((74, 382), "Figure 1. Synthetic chart", fontsize=14)
    page.insert_text((74, 402), "Source: synthetic data", fontsize=10)

    x0, y0, x1, y1 = 60, 480, 560, 780
    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0))
    for x in [180, 320, 450]:
        page.draw_line((x, y0), (x, y1), color=(0, 0, 0))
    for y in [540, 600, 660, 720]:
        page.draw_line((x0, y), (x1, y), color=(0, 0, 0))
    page.insert_text((72, 500), "Table 1. Synthetic projections", fontsize=14)
    for row, y in enumerate([560, 620, 680, 740], start=1):
        page.insert_text((80, y), f"R{row}", fontsize=11)
        page.insert_text((200, y), str(row * 10), fontsize=11)
        page.insert_text((340, y), str(row * 20), fontsize=11)
        page.insert_text((470, y), str(row * 30), fontsize=11)

    doc.save(path.as_posix())
    doc.close()


def _build_chart_context_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((18, 48), "54 |", fontsize=12)
    page.insert_text(
        (18, 82),
        "Figure 1.35. Net purchases of sovereign bonds by investor type in selected advanced economies",
        fontsize=18,
    )
    page.insert_text((18, 112), "Quarterly averages", fontsize=12)
    page.insert_image(fitz.Rect(40, 150, 580, 430), stream=_chart_image_bytes())
    page.insert_textbox(
        fitz.Rect(18, 455, 590, 520),
        (
            "Note: Net purchases of short and long-term government debt securities, "
            "consolidated to eliminate intra-government transactions."
        ),
        fontsize=10,
    )
    page.insert_textbox(
        fitz.Rect(18, 520, 590, 575),
        (
            "Source: Australian Bureau of Statistics; European Central Bank; Federal Reserve; "
            "Statistics Canada; OECD calculations."
        ),
        fontsize=10,
    )
    page.insert_text((420, 585), "StatLink https://stat.link/bfj2wr", fontsize=10)
    page.insert_textbox(
        fitz.Rect(18, 610, 590, 700),
        (
            "Emerging market economies should ensure that inflation durably returns to target "
            "and further reform their public finances."
        ),
        fontsize=14,
        lineheight=1.25,
    )

    doc.save(path.as_posix())
    doc.close()


def _build_chart_partial_note_overlap_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (18, 82),
        "Figure 1.35. Partial note overlap case",
        fontsize=18,
    )
    page.insert_text((18, 112), "Quarterly averages", fontsize=12)
    page.insert_image(fitz.Rect(40, 150, 580, 398), stream=_chart_image_bytes())
    page.insert_textbox(
        fitz.Rect(18, 395, 590, 455),
        (
            "Notes: This note begins inside the padded chart bbox but should still be kept "
            "in full, without clipping its wrapped continuation line. This sentence is "
            "intentionally long so the note wraps across multiple lines and extends below "
            "the original chart bottom."
        ),
        fontsize=10,
    )
    page.insert_textbox(
        fitz.Rect(18, 500, 590, 620),
        "This paragraph must remain outside the chart crop. " * 12,
        fontsize=13,
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()


def _build_chart_caption_spillover_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(65, 116, 540, 176),
        (
            "Given the heterogeneity in regulation trends across states, there are again large "
            "variations between regions. This paragraph should remain outside the final chart crop."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_text(
        (65, 208),
        "Figure 2.6. Rising regulatory compliance costs have suppressed productivity and business",
        fontsize=18,
    )
    page.insert_text(
        (65, 228),
        "dynamism in the United States over the past decade",
        fontsize=18,
    )
    page.insert_text(
        (65, 256),
        "Estimated contribution of changes in regulation to productivity and business dynamism between 2012 and 2023",
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()


def _build_infographic_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text((24, 96), "Infographic 1. Key facts and figures", fontsize=20)
    page.draw_rect(
        fitz.Rect(24, 132, 590, 560),
        color=(0.7, 0.55, 0.1),
        fill=(0.99, 0.92, 0.72),
        width=1.0,
    )
    page.draw_line((306, 152), (306, 542), color=(0.55, 0.42, 0.08), width=1.0)
    page.insert_text(
        (42, 174),
        "Health spending on the rise again",
        fontsize=18,
    )
    page.insert_text((42, 202), "% annual real growth", fontsize=12)
    for idx, year in enumerate(["2018", "2019", "2020", "2021", "2022", "2023", "2024"]):
        x = 56 + idx * 48
        page.insert_text((x, 376), year, fontsize=9)
        page.insert_text((x, 344 - idx * 10), str(idx * 2), fontsize=9)
    page.insert_text(
        (346, 174),
        "Many countries turn to foreign-trained doctors",
        fontsize=18,
    )
    countries = ["Norway", "UK", "Australia", "Canada", "Germany", "France", "Colombia", "Mexico"]
    for idx, country in enumerate(countries):
        y = 236 + idx * 24
        page.insert_text((352, y), country, fontsize=11)
        page.draw_rect(
            fitz.Rect(430, y - 10, 430 + (110 - idx * 15), y + 8),
            color=(0.7, 0.3, 0.1),
            fill=(0.78, 0.28, 0.08),
            width=0.5,
        )
    doc.save(path.as_posix())
    doc.close()


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
    page.insert_text((40, 82), "Table 1.2. Dashboard on health status, 2023", fontsize=18)

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
        ("Gross fixed capital formation", ["354.9", "3.0", "13.2", "12.0", "7.3", "7.4"]),
        ("Final domestic demand", ["1 435.4", "4.7", "6.2", "6.5", "4.7", "4.4"]),
        ("Stockbuilding", ["51.3", "0.6", "-0.1", "1.2", "0.5", "0.0"]),
        ("Current account balance (% of GDP)", ["", "-1.0", "-1.2", "-2.0", "-2.0", "-2.2"]),
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
    page.insert_text((40, 640), "Source: OECD Economic Outlook 118 database.", fontsize=9)
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
        ("Gross fixed capital formation", ["134.3", "3.1", "2.0", "-1.1", "1.1", "1.4"]),
        ("Final domestic demand", ["555.6", "1.9", "2.0", "0.9", "1.1", "0.9"]),
        ("Stockbuilding¹", ["18.8", "-0.8", "-0.5", "0.4", "0.0", "0.0"]),
        ("Total domestic demand", ["574.4", "1.1", "1.4", "1.4", "1.1", "0.9"]),
        ("Exports of goods and services", ["530.0", "-7.2", "-1.7", "-0.4", "1.1", "2.2"]),
        ("Imports of goods and services", ["543.1", "-7.6", "-1.3", "0.0", "1.1", "1.8"]),
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
        ("Harmonised index of consumer prices", ["", "2.3", "4.3", "3.0", "1.6", "1.7"]),
        ("Harmonised index of core inflation²", ["", "6.0", "3.4", "2.2", "2.3", "1.8"]),
        ("Unemployment rate (% of labour force)", ["", "5.5", "5.7", "6.0", "6.0", "5.9"]),
        ("General government financial balance (% of GDP)", ["", "-4.0", "-4.4", "-5.5", "-5.4", "-5.2"]),
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
    page.insert_text((40, 628), "Source: OECD Economic Outlook 118 database.", fontsize=9)
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
        ("The productivity slowdown has been underpinned by a decline in economic dynamism", "68", 14, 40),
        ("The case for a regulatory reset", "69", 14, 40),
        ("Executing the regulatory reset", "79", 14, 40),
        ("References", "96", 14, 40),
        ("3. Developments in individual OECD and selected non-member economies", "105", 18, 20),
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


def _table_candidate(**overrides) -> _TableCandidate:
    candidate = _TableCandidate(
        bbox=(40.0, 120.0, 560.0, 620.0),
        method="stream",
        row_count=18,
        col_count=7,
        col_consistency=0.95,
        row_len_cv=0.35,
        non_empty_cells=90,
        total_cells=126,
        numeric_cells=70,
        numeric_ratio=0.32,
        avg_words_per_cell=1.8,
        avg_first_col_words=2.0,
        index_page_ratio=0.05,
        preview="GDP at market prices 263 104.8 0.6 2.4 2.4 2.2 2.2",
        text=(
            "Chile: Demand, output and prices\n"
            "GDP at market prices 263 104.8 0.6 2.4 2.4 2.2 2.2\n"
            "Private consumption 166 968.0 -4.8 0.9 2.7 1.7 1.5\n"
            "Government consumption 38 686.1 2.4 3.2 4.8 3.4 2.3\n"
            "Gross fixed capital formation 67 404.4 0.3 -1.8 6.8 5.1 3.0\n"
            "Final domestic demand 273 058.6 -2.5 0.6 4.1 2.8 2.0\n"
            "GDP deflator - 6.6 7.7 6.1 3.7 3.1\n"
            "Source: OECD Economic Outlook 118 database.\n"
            "https://stat.link/dpyrm2\n"
        ),
        text_len=520,
        line_count=9,
        avg_line_len=44.0,
        text_block_area_frac=0.18,
        text_block_line_count=9,
        text_block_avg_line_len=28.0,
        caption_hint=False,
        figure_context_hint=False,
        wide_figure_context_hint=False,
        area_frac=0.28,
        width_frac=0.84,
        height_frac=0.44,
        aspect=1.04,
    )
    return _TableCandidate(**{**candidate.__dict__, **overrides})


def test_collect_candidates_returns_chart_and_table_contracts(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "candidates.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.candidates
    kinds = {candidate.kind for candidate in response.candidates}
    assert "chart" in kinds
    assert "table" in kinds
    assert_no_defaulted_required_fields(response)
    for candidate in response.candidates:
        assert_no_defaulted_required_fields(candidate)

    events = _events(caplog, "market_lense.pdf_service.candidate_extraction")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"extract_candidates_start", "extract_candidates_complete"} <= event_names


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

    charts = [candidate for candidate in response.candidates if candidate.kind == "chart"]
    assert len(charts) == 1
    chart = charts[0]

    assert chart.bbox[1] > 55.0
    assert chart.bbox[1] < 95.0
    assert chart.bbox[3] > 530.0
    assert chart.bbox[3] < 602.0


def test_clamp_top_to_caption_reserves_crop_padding_from_prior_paragraph(tmp_path) -> None:
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


def test_collect_candidates_chart_bbox_keeps_full_partial_note_overlap(tmp_path) -> None:
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

    charts = [candidate for candidate in response.candidates if candidate.kind == "chart"]
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

    charts = [candidate for candidate in response.candidates if candidate.kind == "chart"]
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

    charts = [candidate for candidate in response.candidates if candidate.kind == "chart"]
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

    charts = [candidate for candidate in response.candidates if candidate.kind == "chart"]
    upper = next(
        candidate
        for candidate in charts
        if "figure 5.26" in ((candidate.caption or candidate.preview_text or "").lower())
    )
    lower = next(
        candidate
        for candidate in charts
        if "figure 5.27" in ((candidate.caption or candidate.preview_text or "").lower())
    )
    assert lower.id == "chart-0-0"
    assert upper.id == "chart-0-1"
    assert upper.bbox[3] < 460.0
    assert lower.bbox[1] > 430.0


def test_extract_best_figure_writes_asset_and_logs(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "figure.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.figure")

    response = extract_best_figure(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.image_path == "report/assets/report.png"
    assert response.caption == "Figure 1. Synthetic chart"
    assert response.page == 0
    assert (out_dir / response.image_path).exists()
    assert_no_defaulted_required_fields(response)

    events = _events(caplog, "market_lense.pdf_service.figure")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"figure_extract_start", "figure_extract_complete"} <= event_names


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

    tables = [candidate for candidate in response.candidates if candidate.kind == "table"]
    assert tables
    table = max(tables, key=lambda candidate: candidate.bbox[2] - candidate.bbox[0])

    assert table.bbox[1] <= 90.0
    assert table.bbox[3] >= 420.0
    assert table.bbox[3] < 485.0


def test_expand_table_bbox_stream_trims_unrelated_top_notes_and_body_text(tmp_path) -> None:
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


def test_expand_table_bbox_stream_keeps_trailing_row_and_wrapped_footnotes(tmp_path) -> None:
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


def test_expand_table_bbox_stream_clamps_internal_title_and_references(tmp_path) -> None:
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

    tables = [candidate for candidate in response.candidates if candidate.kind == "table"]
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

    tables = [candidate for candidate in response.candidates if candidate.kind == "table"]
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
        area_frac=0.45,
        width_frac=0.82,
        height_frac=0.62,
        aspect=0.86,
    )

    ok, reason = _validate_table_candidate(candidate)

    assert ok is False
    assert reason == "contents_like"


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
