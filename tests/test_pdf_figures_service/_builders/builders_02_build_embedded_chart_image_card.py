# ruff: noqa: F401,F403,F405
from __future__ import annotations

from .shared import *  # noqa: F401,F403

def _build_embedded_chart_image_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((34, 72), "How strong brands keep momentum", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 128, 266, 286),
        (
            "Momentum remains one of the clearest signals of brand health. "
            "The chart card on this page is embedded as a slide image rather "
            "than a vector figure caption."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(320, 172, 874, 430),
        stream=_chart_image_bytes(),
    )
    page.insert_text(
        (320, 450),
        "Source: synthetic embedded chart card data.",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_relaxed_embedded_chart_geometries_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((34, 72), "Why the odds shifted in 2024", fontsize=24)
    page.insert_textbox(
        fitz.Rect(302, 88, 544, 315),
        (
            "Wide embedded chart cards should still be detected even when the "
            "aspect is broader than the default image gate."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(302, 332, 813, 510),
        stream=_chart_image_bytes(),
    )

    page = doc.new_page(width=842, height=595)
    page.insert_text((34, 72), "Brand spotlight", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 118, 262, 432),
        (
            "Narrow right-side data panels should be kept when they contain a "
            "real chart and source area rather than a decorative photo."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(631, 133, 813, 515),
        stream=_portrait_chart_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_decorative_photo_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((34, 72), "A tale of two halves", fontsize=24)
    page.insert_textbox(
        fitz.Rect(34, 120, 430, 260),
        (
            "The headlines from the ranking reveal a fascinating divide. "
            "This page pairs a narrative callout with a decorative hero photo "
            "that should not be extracted as a chart."
        ),
        fontsize=14,
    )
    page.insert_image(
        fitz.Rect(468, 90, 902, 486),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_relaxed_embedded_chart_with_figure_caption_pdf(path: Path) -> None:
    doc = fitz.open()

    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (302, 116),
        "Figure 1.2. Captioned wide embedded image should not use relaxed geometry",
        fontsize=16,
    )
    page.insert_image(
        fitz.Rect(302, 332, 813, 510),
        stream=_chart_image_bytes(),
    )

    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (630, 112),
        "Figure 1.3. Captioned narrow embedded image should not use relaxed geometry",
        fontsize=16,
    )
    page.insert_image(
        fitz.Rect(631, 133, 813, 515),
        stream=_portrait_chart_image_bytes(),
    )

    doc.save(path.as_posix())
    doc.close()

def _build_full_page_image_table_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_image(
        fitz.Rect(8, 20, 952, 520),
        stream=_table_image_bytes(),
    )
    page = doc.new_page(width=960, height=540)
    page.insert_image(
        fitz.Rect(8, 20, 952, 520),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_ranked_table_slide_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (30, 64),
        "Ad Equity ranking APAC 2025 - All Media Brands (Global brands)",
        fontsize=22,
    )
    page.insert_text((30, 118), "Preference", fontsize=20)
    page.insert_text((220, 118), "APAC consumers", fontsize=20)
    page.insert_text((760, 118), "Also #1 in", fontsize=20)
    page.draw_line((30, 156), (930, 156), color=(0.2, 0.2, 0.2), width=2.0)
    row_tops = [182, 260, 338, 416, 494]
    colors = [
        (0.09, 0.84, 0.76),
        (0.14, 0.67, 0.92),
        (0.42, 0.48, 0.79),
        (0.64, 0.2, 0.86),
        (0.84, 0.03, 0.82),
    ]
    brand_names = ["NETFLIX", "amazon", "Pinterest", "Google", "prime"]
    categories = ["OTT", "E-commerce", "Social", "Search", "OTT"]
    regions = [
        "Japan, Korea",
        "-",
        "Australia, Indonesia, Singapore, Thailand",
        "India, Philippines",
        "-",
    ]
    for idx, (top, color) in enumerate(zip(row_tops, colors), start=1):
        bottom = top + 48
        page.draw_rect(
            fitz.Rect(42, top, 160, bottom),
            color=color,
            fill=color,
            width=0.5,
        )
        page.insert_text((92, top + 32), str(idx), fontsize=24, color=(1, 1, 1))
        page.draw_line((30, bottom + 18), (930, bottom + 18), color=(0.82, 0.82, 0.82))
        page.insert_text((270, top + 28), brand_names[idx - 1], fontsize=26)
        page.draw_rect(
            fitz.Rect(470, top + 4, 680, bottom - 4),
            color=(0.98, 0.9, 0.4),
            fill=(0.98, 0.9, 0.4),
            width=0.5,
        )
        page.insert_text((540, top + 28), categories[idx - 1], fontsize=18)
        page.insert_textbox(
            fitz.Rect(760, top + 4, 920, bottom + 8),
            regions[idx - 1],
            fontsize=14,
            align=1,
        )
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_slide_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Panel charts without figure captions should still be detected",
        fontsize=24,
    )
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 170, 932, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    for idx, height in enumerate([95, 72, 64, 58, 52, 45], start=0):
        x0 = 70 + idx * 55
        page.draw_rect(
            fitz.Rect(x0, 420 - height, x0 + 28, 420),
            color=(0.78, 0.0, 0.86) if idx == 0 else (0.82, 0.82, 0.82),
            fill=(0.78, 0.0, 0.86) if idx == 0 else (0.82, 0.82, 0.82),
            width=0.5,
        )
    page.draw_line((62, 420), (430, 420), color=(0.75, 0.75, 0.75))
    page.draw_line((62, 252), (430, 252), color=(0.9, 0.9, 0.9))
    page.draw_circle((715, 318), 96, color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_circle((715, 318), 72, color=(1, 1, 1), width=18)
    page.draw_circle((715, 318), 72, color=(0.82, 0.0, 0.86), width=18)
    page.draw_line((715, 318), (802, 286), color=(0.82, 0.0, 0.86), width=3.0)
    page.draw_line((715, 318), (632, 298), color=(0.14, 0.83, 0.76), width=3.0)
    page.draw_line((715, 318), (690, 405), color=(0.14, 0.83, 0.76), width=3.0)
    page.insert_textbox(
        fitz.Rect(54, 210, 548, 246),
        "37% 35%",
        fontsize=26,
        align=0,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_stacked_shared_title_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text(
        (42, 74),
        "Brand switching reaches critical mass",
        fontsize=26,
    )
    page.insert_text(
        (42, 116),
        "Year-on-year growth in brand switching behaviour",
        fontsize=20,
    )
    bands = [
        fitz.Rect(492, 172, 748, 252),
        fitz.Rect(492, 284, 736, 364),
        fitz.Rect(492, 396, 712, 476),
    ]
    labels = [("2025", "78%"), ("2024", "50%"), ("2023", "40%")]
    fills = [
        (0.82, 0.10, 0.62),
        (0.84, 0.84, 0.84),
        (0.84, 0.84, 0.84),
    ]
    for band, (year, value), fill in zip(bands, labels, fills):
        page.draw_rect(band, color=fill, fill=fill, width=0.5)
        page.insert_text((band.x0 + 12, band.y0 + 52), year, fontsize=28)
        page.insert_text((band.x1 - 74, band.y0 + 52), value, fontsize=28)
    doc.save(path.as_posix())
    doc.close()

def _build_shared_title_split_panel_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Top anticipated media challenges", fontsize=24)
    page.insert_text((28, 84), "by company type", fontsize=24)
    page.draw_rect(
        fitz.Rect(28, 128, 462, 468),
        color=(0.96, 0.96, 0.96),
        fill=(0.96, 0.96, 0.96),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 128, 932, 468),
        color=(0.96, 0.96, 0.96),
        fill=(0.96, 0.96, 0.96),
        width=0.5,
    )
    page.insert_text((56, 166), "78%", fontsize=28)
    page.insert_text((152, 160), "Ad content adjacency", fontsize=20)
    page.insert_text((152, 190), "AI-generated content (37%)", fontsize=14)
    page.insert_text((152, 214), "Deepfakes (27%)", fontsize=14)
    page.insert_text((152, 238), "Influencer content (20%)", fontsize=14)
    page.insert_text((540, 166), "40%", fontsize=28)
    page.insert_text((636, 160), "Publishers & platforms", fontsize=20)
    page.insert_text((636, 190), "Brand suitability", fontsize=14)
    page.insert_text((636, 214), "Premium inventory", fontsize=14)
    page.insert_text((636, 238), "Trusted context", fontsize=14)
    doc.save(path.as_posix())
    doc.close()

def _build_right_column_raster_chart_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((40, 82), "What this means for brands", fontsize=24)
    page.insert_textbox(
        fitz.Rect(40, 126, 404, 410),
        (
            "In 2026, trust is more fragmented than ever. Consumers want "
            "measurement partners that can identify harmful generative-AI "
            "content, prove safe adjacencies, and make brand suitability "
            "controls easier to audit across campaigns."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(444, 16, 843, 404),
        stream=_dark_chart_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_right_column_raster_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((40, 82), "Why people are holding back", fontsize=24)
    page.insert_textbox(
        fitz.Rect(40, 126, 404, 420),
        (
            "Consumers continue to feel pressure on household budgets. "
            "Even as inflation eases, many say they will not return to "
            "freer spending until prices fall, incomes grow, and savings "
            "buffers improve."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_photo_panel_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_small_decorative_raster_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "What momentum means", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 122, 430, 260),
        (
            "This paragraph should remain body copy. The decorative motif "
            "below is not a standalone chart even though it uses geometric "
            "shapes and a high-contrast card design."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(500, 395, 846, 555),
        stream=_decorative_shape_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_light_raster_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "How everyday moments shape preferences", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 126, 404, 420),
        (
            "This page uses narrative body copy beside a lifestyle image. "
            "The image should not be extracted as a chart candidate even "
            "though it sits inside a clean card layout."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_light_photo_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_prose_mentioning_figure_photo_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((42, 82), "Where shoppers begin", fontsize=24)
    page.insert_textbox(
        fitz.Rect(42, 126, 404, 420),
        (
            "When it comes to starting a shopping journey, only a small "
            "share of consumers say they would begin with a chatbot. "
            "That figure rises slightly among younger audiences, but the "
            "adjacent lifestyle photo is still not a chart."
        ),
        fontsize=14,
        lineheight=1.2,
    )
    page.insert_image(
        fitz.Rect(458, 0, 843, 401),
        stream=_light_photo_card_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_oversized_raster_wrapper_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    # Oversized embedded image rect that bleeds off-page.
    page.insert_image(
        fitz.Rect(260, 50, 1157, 554),
        stream=_chart_image_bytes(),
    )
    # Real chart card fully inside the page; this is the crop we want to keep.
    page.insert_image(
        fitz.Rect(302, 121, 654, 510),
        stream=_chart_image_bytes(),
    )
    doc.save(path.as_posix())
    doc.close()

def _build_wide_panel_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text(
        (28, 56),
        "Marketers continue to shift budget toward higher-performing channels",
        fontsize=24,
    )
    page.insert_text(
        (28, 138),
        "Changes in budget/resource allocation (% net positive)",
        fontsize=18,
    )
    page.draw_rect(
        fitz.Rect(20, 170, 932, 476),
        color=(1, 1, 1),
        fill=(1, 1, 1),
        width=0.5,
    )
    page.draw_line((42, 270), (920, 270), color=(0.2, 0.2, 0.2), width=1.0)
    values = [
        68,
        58,
        54,
        51,
        48,
        44,
        41,
        40,
        37,
        35,
        29,
        28,
        20,
        19,
        14,
        8,
        4,
        -16,
        -30,
        -38,
    ]
    for idx, value in enumerate(values):
        x = 52 + idx * 42
        if value >= 0:
            page.draw_rect(
                fitz.Rect(x, 270 - value * 1.3, x + 12, 270),
                color=(0.78, 0.0, 0.86),
                fill=(0.78, 0.0, 0.86),
                width=0.5,
            )
        else:
            page.draw_rect(
                fitz.Rect(x, 270, x + 12, 270 - value * 1.3),
                color=(0.78, 0.0, 0.86),
                fill=(0.78, 0.0, 0.86),
                width=0.5,
            )
    doc.save(path.as_posix())
    doc.close()

def _build_multiline_title_panel_with_side_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text(
        (28, 42), "As digital content grows, the need for innovation", fontsize=20
    )
    page.insert_text(
        (28, 66), "in ensuring media quality within digital video", fontsize=20
    )
    page.insert_text((28, 90), "platforms is especially important", fontsize=20)
    page.draw_rect(
        fitz.Rect(28, 128, 418, 332),
        color=(1, 1, 1),
        fill=(1, 1, 1),
        width=0.5,
    )
    page.draw_line((28, 168), (418, 168), color=(0.2, 0.2, 0.2), width=1.0)
    page.insert_text(
        (28, 158), "Media Quality Considerations on Social Media", fontsize=16
    )
    page.insert_textbox(
        fitz.Rect(28, 192, 208, 300),
        "Viewability is an important metric when assessing social media campaigns",
        fontsize=12,
        align=2,
    )
    page.draw_rect(
        fitz.Rect(240, 184, 404, 236),
        color=(0.67, 0.98, 0.51),
        fill=(0.67, 0.98, 0.51),
        width=0.5,
    )
    page.insert_text((338, 221), "85%", fontsize=24)
    page.draw_rect(
        fitz.Rect(240, 252, 404, 304),
        color=(0.67, 0.98, 0.51),
        fill=(0.67, 0.98, 0.51),
        width=0.5,
    )
    page.insert_text((338, 289), "85%", fontsize=24)
    page.draw_rect(
        fitz.Rect(458, 140, 690, 356),
        color=(0.19, 0.37, 0.31),
        fill=(0.19, 0.37, 0.31),
        width=0.5,
    )
    page.insert_text((486, 176), "WHAT THIS MEANS", fontsize=18, color=(0.72, 1.0, 0.4))
    page.insert_text((486, 202), "FOR MARKETERS", fontsize=18, color=(0.72, 1.0, 0.4))
    page.insert_textbox(
        fitz.Rect(478, 224, 678, 334),
        (
            "Media quality on digital video remains important as spending climbs to "
            "$306.4 billion globally. Improved detection should help cut 14.9% of "
            "avoidable risk by 2026."
        ),
        fontsize=12,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    page.insert_textbox(
        fitz.Rect(28, 364, 690, 398),
        "Source: Synthetic IAS-style slide footer used to keep the page layout realistic.",
        fontsize=10,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_panel_chart_slide_with_figure_caption_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Figure 1.1. Captioned panel chart", fontsize=20)
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(498, 170, 932, 468),
        color=(0.93, 0.93, 0.93),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(80, 360, 110, 420),
        color=(0.78, 0.0, 0.86),
        fill=(0.78, 0.0, 0.86),
        width=0.5,
    )
    page.draw_circle((715, 318), 96, color=(0.12, 0.12, 0.12), width=1.2)
    page.draw_circle((715, 318), 72, color=(0.82, 0.0, 0.86), width=18)
    doc.save(path.as_posix())
    doc.close()

def _build_panel_action_card_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((28, 56), "Take action", fontsize=24)
    page.insert_text((42, 138), "Context control avoidance", fontsize=18)
    page.draw_rect(
        fitz.Rect(28, 170, 462, 468),
        color=(0.15, 0.28, 0.24),
        fill=(0.15, 0.28, 0.24),
        width=0.5,
    )
    page.insert_textbox(
        fitz.Rect(56, 214, 428, 430),
        (
            "Avoid content you deem risky or unsuitable with a contextual "
            "solution that leverages semantic intelligence and custom controls. "
            "Use the workflow to align teams, reduce manual review, and improve "
            "consistency across channels."
        ),
        fontsize=14,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_dense_numeric_panel_chart_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text(
        (28, 56),
        "Adjacencies to unsuitable Gen AI content",
        fontsize=20,
    )
    panel_rect = fitz.Rect(28, 88, 676, 328)
    page.draw_rect(
        panel_rect,
        color=(0.95, 0.95, 0.95),
        fill=(0.95, 0.95, 0.95),
        width=0.5,
    )
    page.draw_rect(
        fitz.Rect(478, 112, 652, 304),
        color=(0.12, 0.34, 0.25),
        fill=(0.12, 0.34, 0.25),
        width=0.5,
    )
    categories = [
        ("Content that contains inaccurate information", "22%", "9%", "68%"),
        ("Content that provides an ad-spammy user experience", "26%", "11%", "63%"),
        (
            "Content that regurgitates or plagiarizes existing content",
            "25%",
            "14%",
            "61%",
        ),
        (
            "Content that comes from unknown domains with no editorial team",
            "24%",
            "17%",
            "59%",
        ),
    ]
    for idx, (label, safe, unsure, avoid) in enumerate(categories):
        y = 124 + idx * 46
        page.insert_textbox(
            fitz.Rect(44, y, 236, y + 36),
            label,
            fontsize=8,
            align=2,
        )
        bar_y0 = y + 6
        page.draw_rect(
            fitz.Rect(256, bar_y0, 354, bar_y0 + 24),
            color=(0.67, 0.98, 0.51),
            fill=(0.67, 0.98, 0.51),
            width=0.5,
        )
        page.draw_rect(
            fitz.Rect(354, bar_y0, 394, bar_y0 + 24),
            color=(0.52, 0.69, 0.59),
            fill=(0.52, 0.69, 0.59),
            width=0.5,
        )
        page.draw_rect(
            fitz.Rect(394, bar_y0, 470, bar_y0 + 24),
            color=(0.86, 0.86, 0.86),
            fill=(0.86, 0.86, 0.86),
            width=0.5,
        )
        page.insert_text((300, y + 22), safe, fontsize=11)
        page.insert_text((366, y + 22), unsure, fontsize=11)
        page.insert_text((425, y + 22), avoid, fontsize=11)
    page.insert_textbox(
        fitz.Rect(500, 144, 638, 286),
        (
            "Not all AI-generated content is created equal. Prioritising "
            "classification and robust avoidance strategies helps ensure "
            "brands maintain trust."
        ),
        fontsize=11,
        color=(1, 1, 1),
        lineheight=1.2,
    )
    doc.save(path.as_posix())
    doc.close()

def _build_cross_panel_label_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((42, 138), "Trustworthy Ads", fontsize=18)
    page.insert_text((510, 138), "Better Quality Ads", fontsize=18)
    left = fitz.Rect(28, 170, 462, 468)
    right = fitz.Rect(498, 170, 932, 468)
    page.draw_rect(left, color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93), width=0.5)
    page.draw_rect(right, color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93), width=0.5)
    page.insert_textbox(fitz.Rect(52, 214, 550, 248), "37% 35%", fontsize=26)
    page.insert_textbox(
        fitz.Rect(66, 430, 440, 460), "Netflix Pinterest Amazon", fontsize=12
    )
    page.insert_textbox(
        fitz.Rect(536, 430, 906, 460), "Netflix Spotify Prime Video", fontsize=12
    )
    doc.save(path.as_posix())
    doc.close()

__all__ = [
    "_build_embedded_chart_image_card_pdf",
    "_build_relaxed_embedded_chart_geometries_pdf",
    "_build_decorative_photo_panel_pdf",
    "_build_relaxed_embedded_chart_with_figure_caption_pdf",
    "_build_full_page_image_table_pdf",
    "_build_ranked_table_slide_pdf",
    "_build_panel_chart_slide_pdf",
    "_build_stacked_shared_title_panel_pdf",
    "_build_shared_title_split_panel_pdf",
    "_build_right_column_raster_chart_card_pdf",
    "_build_right_column_raster_photo_card_pdf",
    "_build_small_decorative_raster_card_pdf",
    "_build_light_raster_photo_card_pdf",
    "_build_prose_mentioning_figure_photo_card_pdf",
    "_build_oversized_raster_wrapper_pdf",
    "_build_wide_panel_chart_pdf",
    "_build_multiline_title_panel_with_side_card_pdf",
    "_build_panel_chart_slide_with_figure_caption_pdf",
    "_build_panel_action_card_pdf",
    "_build_dense_numeric_panel_chart_pdf",
    "_build_cross_panel_label_pdf",
]
