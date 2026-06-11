# ruff: noqa: F401,F403,F405
from __future__ import annotations

from .shared import *  # noqa: F401,F403

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

def _build_full_page_scan_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_image(fitz.Rect(0, 0, 620, 900), stream=_scan_image_bytes())
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

def _build_panel_local_title_preference_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=420)
    page.insert_text((40, 40), "TOP MEDIA PRIORITIES IN 2026", fontsize=20)
    page.insert_text((40, 112), "Top Digital Formats", fontsize=12)
    page.draw_rect(fitz.Rect(40, 126, 320, 300), color=(0, 0, 0))
    page.insert_text((72, 188), "87%", fontsize=34)
    page.insert_text((72, 236), "Digital Video", fontsize=12)
    doc.save(path.as_posix())
    doc.close()

def _build_panel_internal_title_preference_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=420)
    page.insert_text(
        (260, 120),
        "of shoppers are buying private-label or low-cost brands",
        fontsize=14,
    )
    page.draw_rect(
        fitz.Rect(40, 150, 360, 320),
        color=(0.08, 0.12, 0.28),
        fill=(0.08, 0.12, 0.28),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(40, 150, 360, 188),
        color=(0.25, 0.66, 0.90),
        fill=(0.25, 0.66, 0.90),
        width=0.5,
    )
    page.insert_text(
        (132, 176),
        "Private labels go premium",
        fontsize=16,
        color=(1, 1, 1),
    )
    page.insert_textbox(
        fitz.Rect(74, 212, 326, 286),
        "Quality and trust remain the strongest decision drivers.",
        fontsize=13,
        color=(1, 1, 1),
        align=1,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_axis_label_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.draw_rect(fitz.Rect(90, 90, 320, 250), color=(0, 0, 0))
    page.insert_text((110, 120), "Chart 1", fontsize=14)
    page.insert_textbox(
        fitz.Rect(104, 230, 520, 262),
        "1990\n1995\n2000\n2005\n2010\n2015\n2020\n2025\n2030\n2035",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_axis_stroke_extension_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.insert_text((54, 52), "Chart 1: Fiscal outlook", fontsize=16)
    page.insert_text((92, 88), "Outlays in USD trillion", fontsize=11)
    baseline_y = 332
    page.draw_line(
        (86, baseline_y), (520, baseline_y), color=(0.3, 0.3, 0.3), width=0.7
    )
    for idx, height in enumerate([18, 24, 20, 16, 44, 39, 20, 26, 18]):
        x0 = 96 + idx * 34
        page.draw_rect(
            fitz.Rect(x0, baseline_y - height, x0 + 24, baseline_y),
            color=(0.11, 0.14, 0.40),
            fill=(0.11, 0.14, 0.40),
            width=0.5,
        )
    for idx, height in enumerate([26, 28, 30, 32]):
        x0 = 402 + idx * 28
        page.draw_rect(
            fitz.Rect(x0, baseline_y - height, x0 + 18, baseline_y),
            color=(0.82, 0.79, 0.64),
            fill=(0.82, 0.79, 0.64),
            width=0.5,
        )
    for x in [414, 458, 502]:
        page.draw_line(
            (x, baseline_y - 1), (x, baseline_y + 4), color=(0.3, 0.3, 0.3), width=0.5
        )
    page.insert_text((414, 352), "2025", fontsize=10)
    page.insert_text((458, 352), "2030", fontsize=10)
    page.insert_text((502, 352), "2035", fontsize=10)
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_cards_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_text(
        (36, 64),
        "Retail trends",
        fontsize=28,
        color=(1, 1, 1),
    )

    top_rect = fitz.Rect(42, 150, 560, 340)
    page.draw_rect(top_rect, color=(0.15, 0.42, 0.76), fill=(0.15, 0.42, 0.76))
    page.draw_line((214, 150), (214, 340), color=(0.45, 0.65, 0.92), width=1.2)
    page.insert_text((66, 246), "44%", fontsize=56, color=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(240, 182, 534, 316),
        (
            "of shoppers are buying lower-cost alternatives over name brands\n"
            "Early findings: What matters to today's consumers, 2026"
        ),
        fontsize=17,
        color=(1, 1, 1),
        lineheight=1.25,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    bottom_rect = fitz.Rect(42, 390, 560, 710)
    page.draw_rect(bottom_rect, color=(0.15, 0.42, 0.76), fill=(0.10, 0.16, 0.32))
    page.draw_rect(
        fitz.Rect(42, 390, 560, 438),
        color=(0.25, 0.66, 0.90),
        fill=(0.25, 0.66, 0.90),
    )
    page.insert_text(
        (168, 422),
        "3 ways retailers can prepare for 2026",
        fontsize=18,
        color=(1, 1, 1),
    )
    page.draw_line((214, 438), (214, 710), color=(0.25, 0.35, 0.58), width=1.0)
    page.draw_line((388, 438), (388, 710), color=(0.25, 0.35, 0.58), width=1.0)
    page.insert_textbox(
        fitz.Rect(60, 470, 196, 676),
        (
            "Shift from search to suggestion:\n"
            "Leverage AI to drive proactive discovery and surface relevant products."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(234, 470, 370, 676),
        (
            "Optimize for algorithmic visibility:\n"
            "Structure content so recommendations engines can understand it."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(408, 470, 544, 676),
        (
            "Engineer moments of serendipity:\n"
            "Design timely nudges and discovery paths that feel contextual."
        ),
        fontsize=15,
        color=(1, 1, 1),
        lineheight=1.2,
    )

    doc.save(path.as_posix())
    doc.close()

def _build_panel_metric_band_with_quote_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=420)
    page.insert_text((42, 68), "Invisible AI", fontsize=26, color=(1, 1, 1))
    page.insert_text((42, 148), "71% of consumers", fontsize=24, color=(1, 1, 1))
    page.insert_text(
        (42, 178),
        "want Gen AI-integrated shopping interactions",
        fontsize=14,
        color=(1, 1, 1),
    )
    page.insert_text((250, 158), "compared to", fontsize=14, color=(1, 1, 1))
    page.insert_text((250, 194), "56% who said", fontsize=24, color=(1, 1, 1))
    page.insert_text((250, 224), "the same last year.", fontsize=14, color=(1, 1, 1))
    page.insert_text(
        (470, 194), "Source: Example dataset", fontsize=11, color=(0.2, 0.9, 0.9)
    )
    page.draw_rect(
        fitz.Rect(42, 244, 560, 338),
        color=(0.35, 0.4, 0.62),
        fill=(0.10, 0.16, 0.32),
        width=0.8,
    )
    page.insert_textbox(
        fitz.Rect(72, 270, 520, 318),
        (
            "Transparency builds confidence, even when the tech stays in the background.\n"
            "Mark Ruston, Global Retail Lead"
        ),
        fontsize=15,
        color=(1, 1, 1),
        align=0,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_label_grid_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    panel_rect = fitz.Rect(60, 72, 660, 420)
    page.draw_rect(panel_rect, color=(0.95, 0.95, 0.95), fill=(0.95, 0.95, 0.95))
    page.insert_textbox(
        fitz.Rect(86, 98, 286, 166),
        (
            "To arrive at Ad Equity, we asked consumers their perceptions "
            "of the ads on each media platform."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    labels = [
        ("Trustworthy", 140, 178),
        ("Relevant and useful", 360, 178),
        ("Fun and entertaining", 580, 178),
        ("Better quality", 140, 314),
        ("Innovative", 360, 314),
        ("Captures my attention", 580, 314),
    ]
    for text, cx, cy in labels:
        page.draw_line(
            (cx - 92, cy - 40), (cx - 92, cy + 40), color=(0.1, 0.1, 0.1), width=1.2
        )
        box = fitz.Rect(cx - 76, cy - 22, cx + 16, cy + 30)
        page.draw_rect(box, color=(0.82, 0.42, 0.92), fill=(0.82, 0.42, 0.92))
        page.insert_textbox(
            fitz.Rect(cx - 76, cy + 46, cx + 92, cy + 126),
            text,
            fontsize=14,
            align=fitz.TEXT_ALIGN_CENTER,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_with_side_labels_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=640, height=520)
    page.draw_rect(
        fitz.Rect(140, 184, 500, 430),
        color=(0.10, 0.16, 0.32),
        fill=(0.10, 0.16, 0.32),
    )
    page.draw_circle((214, 338), 34, color=(0.98, 0.50, 0.42), width=3)
    page.draw_circle((320, 268), 34, color=(0.24, 0.76, 0.98), width=3)
    page.draw_circle((426, 338), 34, color=(0.20, 0.88, 0.86), width=3)
    page.draw_circle((320, 362), 106, color=(0.24, 0.38, 0.74), width=3)
    page.insert_text((198, 348), "01", fontsize=22, color=(1, 1, 1))
    page.insert_text((304, 278), "02", fontsize=22, color=(1, 1, 1))
    page.insert_text((410, 348), "03", fontsize=22, color=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(236, 302, 404, 388),
        "What’s inside:\n3 ways retailers can prepare",
        fontsize=18,
        color=(1, 1, 1),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    page.insert_textbox(
        fitz.Rect(74, 186, 174, 278),
        "Moments over\nmerchandise:\nUnlocking growth",
        fontsize=15,
        color=(0.12, 0.12, 0.12),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    page.insert_text((486, 196), "Trust as a", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text((496, 218), "profit", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text((488, 240), "driver:", fontsize=15, color=(0.12, 0.12, 0.12))
    page.insert_text(
        (474, 268), "Driving margins", fontsize=15, color=(0.12, 0.12, 0.12)
    )
    page.insert_textbox(
        fitz.Rect(266, 132, 374, 214),
        "Searchless\nretail:\n03",
        fontsize=15,
        color=(0.12, 0.12, 0.12),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_internal_panel_with_bottom_labels_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=640, height=560)
    page.insert_text(
        (92, 86),
        "Consumer response to unexpected fees",
        fontsize=22,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_circle((322, 302), 128, color=(0.94, 0.28, 0.28), width=36)
    page.draw_circle(
        (322, 302), 76, color=(0.96, 0.84, 0.82), fill=(0.96, 0.84, 0.82), width=2
    )
    page.insert_text((146, 180), "Stayed and", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text(
        (146, 204), "maintained trust", fontsize=16, color=(0.14, 0.14, 0.14)
    )
    page.insert_text((150, 238), "29%", fontsize=28, color=(0.14, 0.14, 0.14))
    page.insert_text((430, 180), "Stayed but", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((430, 204), "lost trust", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((432, 238), "40%", fontsize=28, color=(0.14, 0.14, 0.14))
    page.insert_text((270, 422), "Switched", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((275, 446), "provider", fontsize=16, color=(0.14, 0.14, 0.14))
    page.insert_text((278, 480), "31%", fontsize=28, color=(0.14, 0.14, 0.14))
    doc.save(path.as_posix())
    doc.close()

def _build_contents_panel_page_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.draw_rect(page.rect, color=(0.20, 0.45, 0.34), fill=(0.20, 0.45, 0.34))
    page.insert_text((28, 42), "TABLE OF CONTENTS", fontsize=22, color=(1, 1, 1))
    cards = [
        ("01", "TOP MEDIA\nCHALLENGES"),
        ("02", "GENERATIVE\nAI"),
        ("03", "SOCIAL\nMEDIA"),
        ("04", "DIGITAL\nVIDEO"),
    ]
    for idx, (num, label) in enumerate(cards):
        x0 = 70 + idx * 150
        y0 = 110
        card = fitz.Rect(x0, y0, x0 + 105, y0 + 120)
        page.draw_rect(card, color=(0.20, 0.45, 0.34), fill=(0.20, 0.45, 0.34))
        page.insert_text((x0 + 10, y0 + 38), num, fontsize=46, color=(0.45, 0.98, 0.20))
        page.insert_textbox(
            fitz.Rect(x0 + 4, y0 + 62, x0 + 110, y0 + 122),
            label,
            fontsize=14,
            color=(1, 1, 1),
            align=fitz.TEXT_ALIGN_LEFT,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_chart_with_internal_title_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.insert_text(
        (72, 110),
        "Top Media Types with Potential for Innovation",
        fontsize=14,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_line((70, 132), (620, 132), color=(0.12, 0.12, 0.12), width=1.2)
    bars = [
        (90, 300, 150, 160, "50%"),
        (185, 300, 245, 205, "35%"),
        (280, 300, 340, 215, "32%"),
        (375, 300, 435, 225, "30%"),
        (470, 300, 530, 225, "30%"),
    ]
    for x0, y1, x1, y0, label in bars:
        rect = fitz.Rect(x0, y0, x1, y1)
        page.draw_rect(rect, color=(0.68, 0.96, 0.46), fill=(0.68, 0.96, 0.46))
        page.insert_text((x0 + 12, y0 + 28), label, fontsize=18, color=(0.1, 0.1, 0.1))
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_with_wide_internal_title_band_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=520)
    page.draw_rect(
        fitz.Rect(24, 24, 436, 88),
        color=(0.96, 0.96, 0.96),
        fill=(0.99, 0.99, 0.99),
        width=1.0,
    )
    page.insert_text(
        (28, 52),
        "Media Types with the Most Potential for Innovation",
        fontsize=18,
        color=(0.12, 0.12, 0.12),
    )
    page.draw_line((28, 78), (430, 78), color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_rect(
        fitz.Rect(88, 188, 628, 340),
        color=(0.90, 0.90, 0.90),
        fill=(0.98, 0.98, 0.98),
        width=1.0,
    )
    bars = [
        (96, 336, 156, 196, "50%"),
        (190, 336, 250, 236, "35%"),
        (284, 336, 344, 246, "32%"),
        (378, 336, 438, 256, "30%"),
        (472, 336, 532, 256, "30%"),
    ]
    for x0, y1, x1, y0, label in bars:
        rect = fitz.Rect(x0, y0, x1, y1)
        page.draw_rect(rect, color=(0.68, 0.96, 0.46), fill=(0.68, 0.96, 0.46))
        page.insert_text(
            (x0 + 12, y0 + 28),
            label,
            fontsize=18,
            color=(0.1, 0.1, 0.1),
        )
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_independent_panel_cards_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    upper_rect = fitz.Rect(42, 300, 552, 520)
    lower_rect = fitz.Rect(42, 560, 552, 820)

    page.draw_rect(
        upper_rect,
        color=(0.92, 0.92, 0.92),
        fill=(0.92, 0.92, 0.92),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(70, 320, 226, 418),
        color=(0.70, 0.98, 0.55),
        fill=(0.70, 0.98, 0.55),
        width=0.5,
    )
    page.insert_text((88, 374), "46%", fontsize=34)
    page.insert_text((264, 344), "of shoppers make purchases based on AI", fontsize=16)
    page.insert_text((264, 364), "recommendations", fontsize=16)
    page.insert_text((264, 392), "Early findings: What matters to today's", fontsize=12)
    page.insert_text((264, 408), "consumers, 2026", fontsize=12)

    page.draw_rect(
        lower_rect,
        color=(0.95, 0.97, 0.91),
        fill=(0.95, 0.97, 0.91),
        width=0.5,
    )
    page.insert_text(
        (136, 584), "3 ways retailers can prepare for a searchless future:", fontsize=16
    )
    columns = [
        (
            74,
            "01",
            [
                "Shift from search",
                "to suggestion:",
                "Use contextual",
                "signals to surface",
                "relevant products.",
            ],
        ),
        (
            252,
            "02",
            [
                "Optimize for",
                "algorithmic",
                "visibility:",
                "Strengthen product",
                "and content tagging.",
            ],
        ),
        (
            426,
            "03",
            [
                "Engineer moments",
                "of serendipity:",
                "Use timed prompts",
                "and content to spark",
                "discovery.",
            ],
        ),
    ]
    for x, number, lines in columns:
        page.insert_text((x, 636), number, fontsize=18)
        y = 658
        for line in lines:
            page.insert_text((x + 8, y), line, fontsize=12)
            y += 18

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
    for idx, year in enumerate(
        ["2018", "2019", "2020", "2021", "2022", "2023", "2024"]
    ):
        x = 56 + idx * 48
        page.insert_text((x, 376), year, fontsize=9)
        page.insert_text((x, 344 - idx * 10), str(idx * 2), fontsize=9)
    page.insert_text(
        (346, 174),
        "Many countries turn to foreign-trained doctors",
        fontsize=18,
    )
    countries = [
        "Norway",
        "UK",
        "Australia",
        "Canada",
        "Germany",
        "France",
        "Colombia",
        "Mexico",
    ]
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

def _build_side_by_side_photo_examples_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Digital Out of Home is driving high-impact campaigns across APAC through creative use of ad format",
        fontsize=18,
    )
    page.insert_image(
        fitz.Rect(110, 160, 433, 353),
        stream=_photo_panel_image_bytes(),
    )
    page.insert_image(
        fitz.Rect(527, 160, 849, 353),
        stream=_photo_panel_image_bytes(),
    )
    page.insert_textbox(
        fitz.Rect(176, 366, 812, 406),
        (
            "Maybelline Superstay Teddy Tint\n"
            "Central Square, Philippines (2024)\n"
            "L'Oreal Thailand\n"
            "Emsphere, Bangkok (2024)"
        ),
        fontsize=12,
        align=1,
    )
    doc.save(path.as_posix())
    doc.close()

__all__ = [
    "_build_candidates_pdf",
    "_build_full_page_scan_pdf",
    "_build_chart_context_pdf",
    "_build_panel_local_title_preference_pdf",
    "_build_panel_internal_title_preference_pdf",
    "_build_axis_label_band_pdf",
    "_build_axis_stroke_extension_pdf",
    "_build_internal_panel_cards_pdf",
    "_build_panel_metric_band_with_quote_card_pdf",
    "_build_internal_label_grid_panel_pdf",
    "_build_internal_panel_with_side_labels_pdf",
    "_build_internal_panel_with_bottom_labels_pdf",
    "_build_contents_panel_page_pdf",
    "_build_chart_with_internal_title_band_pdf",
    "_build_panel_chart_with_wide_internal_title_band_pdf",
    "_build_stacked_independent_panel_cards_pdf",
    "_build_chart_partial_note_overlap_pdf",
    "_build_chart_caption_spillover_pdf",
    "_build_infographic_chart_pdf",
    "_build_side_by_side_photo_examples_pdf",
]
