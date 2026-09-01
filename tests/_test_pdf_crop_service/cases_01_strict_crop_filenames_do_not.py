# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

from src.services._pdf._crop.image_ops import _png_safe_pixmap


def test_png_safe_pixmap_converts_cmyk_before_png_encoding() -> None:
    cmyk = fitz.Pixmap(fitz.csCMYK, fitz.IRect(0, 0, 3, 2), False)
    cmyk.clear_with(0)

    normalized = _png_safe_pixmap(cmyk)

    assert normalized.colorspace == fitz.csRGB
    assert normalized.alpha == 0
    assert normalized.tobytes("png").startswith(b"\x89PNG\r\n\x1a\n")


def test_strict_crop_filenames_do_not_collide_across_table_and_chart_calls(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    table_item = CropItem(
        id="table-1-0",
        type="table",
        score=90.0,
        page=0,
        bbox=(60.0, 90.0, 220.0, 220.0),
    )
    chart_item = CropItem(
        id="chart-1-0",
        type="chart",
        score=91.0,
        page=0,
        bbox=(220.0, 90.0, 360.0, 260.0),
    )

    table_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[table_item],
            subdir="slices",
            mode="table_strict",
        ),
        _ctx(),
    )
    chart_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[chart_item],
            subdir="slices",
            mode="chart_strict",
        ),
        _ctx(),
    )

    assert len(table_resp.paths) == 1
    assert len(chart_resp.paths) == 1
    assert table_resp.paths[0] != chart_resp.paths[0]

    slices_dir = out_dir / "report" / "slices"
    files = sorted(p.name for p in slices_dir.glob("*.png"))
    assert len(files) == 2
    assert "report-table-1-0.png" in files
    assert "report-chart-1-0.png" in files


def test_crop_regions_compacts_filename_for_long_report_slug(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path.parent / "lc"
    report_name = (
        "institute-for-canadian-citizenship-retention-trends-in-highly-skilled-"
        "immigrants-and-in-demand-occupations-acig-pdf"
    )
    item = CropItem(
        id="chart-4-1",
        type="chart",
        score=90.0,
        page=0,
        bbox=(60.0, 90.0, 360.0, 280.0),
    )

    response = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name=report_name,
            items=[item],
            subdir="slices",
            mode="chart_strict",
        ),
        _ctx(),
    )

    assert len(response.paths) == 1
    artifact_path = out_dir / response.paths[0]
    assert artifact_path.is_file()
    assert artifact_path.name.startswith("chart-4-1-")
    assert len(artifact_path.name) <= 96


def test_chart_strict_tightens_partial_bottom_text_spillover(tmp_path):
    pdf_path = tmp_path / "spillover.pdf"
    _build_pdf_with_bottom_body_text(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=95.0,
        page=0,
        bbox=(60.0, 90.0, 540.0, 500.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict",
            pad=0,
            mode="chart_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height > int(legacy_img.height * 0.65)


def test_tighten_chart_crop_rect_reclamps_padded_top_to_caption(tmp_path):
    pdf_path = tmp_path / "top_chart_spillover.pdf"
    _build_pdf_with_top_chart_spillover(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        padded_rect = fitz.Rect(53.2, 178.54, 544.8, 707.04)
        tightened = _tighten_chart_crop_rect(page, padded_rect)
    finally:
        doc.close()

    assert tightened.y0 > 186.0
    assert tightened.y0 < 187.0
    assert tightened.y1 == pytest.approx(padded_rect.y1)


def test_tighten_chart_crop_rect_leaves_plain_chart_without_context_unchanged(tmp_path):
    pdf_path = tmp_path / "plain_chart.pdf"
    _build_basic_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(60.0, 90.0, 360.0, 280.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.x0 == pytest.approx(rect.x0)
    assert tightened.y0 == pytest.approx(rect.y0)
    assert tightened.x1 == pytest.approx(rect.x1)
    assert tightened.y1 == pytest.approx(rect.y1)


def test_tighten_chart_crop_rect_does_not_trim_internal_panel_label_block(tmp_path):
    pdf_path = tmp_path / "internal-panel-side-labels.pdf"
    from tests.test_pdf_figures_service import (
        _build_internal_panel_with_side_labels_pdf,
    )

    _build_internal_panel_with_side_labels_pdf(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(70.1, 127.8, 584.6, 472.2)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 <= 130.0
    assert tightened.y1 >= 470.0


def test_tighten_chart_crop_rect_keeps_draw_backed_internal_heading_band(tmp_path):
    pdf_path = tmp_path / "internal-heading-card.pdf"
    _build_pdf_with_internal_heading_card(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(36.0, 188.0, 644.0, 430.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 <= 188.5
    assert tightened.y0 >= 176.0
    assert tightened.y1 == pytest.approx(rect.y1)


def test_tighten_chart_crop_rect_expands_to_fill_top_when_internal_sentence_is_not_heading(
    tmp_path,
):
    pdf_path = tmp_path / "internal-sentence-card.pdf"
    _build_pdf_with_internal_sentence_card(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(36.0, 186.0, 644.0, 430.0)
        tightened = _tighten_chart_crop_rect(page, rect)
    finally:
        doc.close()

    assert tightened.y0 < rect.y0
    assert tightened.y0 <= 180.5
    assert tightened.y0 >= 176.0
    assert tightened.y1 == pytest.approx(rect.y1)


def test_legacy_chart_border_trim_keeps_extra_bottom_padding_for_bottom_edge_text(
    tmp_path,
):
    pdf_path = tmp_path / "bottom-edge-chart-text.pdf"
    _build_pdf_with_bottom_edge_chart_text(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        rect = fitz.Rect(60.0, 90.0, 420.0, 420.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        trimmed = _legacy_chart_border_trim(page, rect, img)
    finally:
        doc.close()

    bg = _dominant_border_color(trimmed)
    width, height = trimmed.size
    bottommost = -1
    for y in range(height - 1, -1, -1):
        found = False
        for x in range(width):
            px = trimmed.getpixel((x, y))
            if any(abs(px[i] - bg[i]) > 8 for i in range(3)):
                bottommost = y
                found = True
                break
        if found:
            break

    assert bottommost >= 0
    assert height - 1 - bottommost >= 16


def test_tighten_table_crop_rect_trims_top_page_number_but_keeps_header_band(tmp_path):
    pdf_path = tmp_path / "table_header_page_number.pdf"
    _build_pdf_with_table_header_band_and_page_number(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        padded_rect = fitz.Rect(0.0, 54.8, 595.0, 300.0)
        tightened = _tighten_table_crop_rect(page, padded_rect)
    finally:
        doc.close()

    assert tightened.y0 > 53.4
    assert tightened.y0 < 61.0
    assert tightened.y1 == pytest.approx(padded_rect.y1)


def test_tighten_table_crop_rect_snaps_to_high_confidence_outer_rules(tmp_path):
    pdf_path = tmp_path / "table_outer_rules.pdf"
    _build_pdf_with_table_outer_rules(pdf_path)

    doc = fitz.open(pdf_path.as_posix())
    try:
        page = doc[0]
        clipped_rect = fitz.Rect(92.0, 130.0, 526.0, 336.0)
        tightened = _tighten_table_crop_rect(page, clipped_rect)
    finally:
        doc.close()

    assert tightened.x0 <= 70.5
    assert tightened.y0 <= 115.5
    assert tightened.x1 >= 549.5
    assert tightened.y1 >= 354.5


def test_table_crop_regions_stitch_split_table_title_and_note_for_adjacent_pages(
    tmp_path,
):
    pdf_path = tmp_path / "split_table_pair.pdf"
    _build_pdf_with_split_table_title_and_note(pdf_path)
    out_dir = tmp_path / "out"
    first = CropItem(
        id="table-47-0",
        type="table",
        score=90.0,
        page=0,
        bbox=(0.0, 291.0, 595.0, 724.0),
    )
    second = CropItem(
        id="table-48-0",
        type="table",
        score=91.0,
        page=1,
        bbox=(0.0, 54.8, 595.0, 431.0),
    )

    first_only = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="single-first",
            items=[first],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    second_only = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="single-second",
            items=[second],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    paired = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="paired",
            items=[first, second],
            subdir="tables",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )

    first_single_path = out_dir / first_only.paths[0]
    second_single_path = out_dir / second_only.paths[0]
    paired_first_path = out_dir / paired.paths[0]
    paired_second_path = out_dir / paired.paths[1]
    with (
        Image.open(first_single_path) as first_single,
        Image.open(second_single_path) as second_single,
        Image.open(paired_first_path) as paired_first,
        Image.open(paired_second_path) as paired_second,
    ):
        assert paired_first.height > first_single.height + 80
        assert paired_second.height > second_single.height + 20
        assert paired_first.width >= first_single.width
        assert paired_second.width >= second_single.width


def test_table_strict_clamps_after_note_and_avoids_section_spillover(tmp_path):
    pdf_path = tmp_path / "table_spillover.pdf"
    _build_pdf_with_table_note_and_spillover(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="table-0-0",
        type="table",
        score=96.0,
        page=0,
        bbox=(60.0, 90.0, 560.0, 740.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_table",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_table",
            pad=0,
            mode="table_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height < 940
        assert strict_img.height > 760


def test_table_strict_detects_mid_statlink_for_bottom_clamp(tmp_path):
    pdf_path = tmp_path / "table_mid_statlink.pdf"
    _build_pdf_with_mid_statlink_and_spillover(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="table-0-1",
        type="table",
        score=92.0,
        page=0,
        bbox=(60.0, 120.0, 560.0, 760.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_mid_statlink",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_mid_statlink",
            pad=0,
            mode="table_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height < legacy_img.height
        assert strict_img.height < 620
        assert strict_img.height > 420


def test_chart_strict_keeps_note_that_crosses_bbox_bottom(tmp_path):
    pdf_path = tmp_path / "chart_partial_note_overlap.pdf"
    _build_pdf_with_partial_note_overlap(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-1",
        type="chart",
        score=92.0,
        page=0,
        bbox=(60.0, 120.0, 560.0, 405.0),
    )

    legacy_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="legacy_partial_note",
            pad=0,
            mode="legacy",
        ),
        _ctx(),
    )
    strict_resp = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="strict_partial_note",
            pad=0,
            mode="chart_strict",
        ),
        _ctx(),
    )

    legacy_path = out_dir / legacy_resp.paths[0]
    strict_path = out_dir / strict_resp.paths[0]
    with Image.open(legacy_path) as legacy_img, Image.open(strict_path) as strict_img:
        assert strict_img.height > legacy_img.height
        assert strict_img.height < 760


def test_publication_strict_writes_final_crop_diagnostics(tmp_path):
    pdf_path = tmp_path / "publication-strict.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="visual-0-0",
        type="figure",
        score=90.0,
        page=0,
        bbox=(45.0, 75.0, 375.0, 305.0),
    )

    response = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="slices",
            pad=0,
            mode="publication_strict",
        ),
        _ctx(),
    )

    artifact_path = out_dir / response.paths[0]
    diagnostics_path = artifact_path.with_suffix(artifact_path.suffix + ".qa.json")
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))

    assert artifact_path.is_file()
    assert diagnostics["mode"] == "publication_strict"
    assert diagnostics["accepted"] is True
    assert diagnostics["qa"]["total_score"] >= 0.75
    assert diagnostics["qa"]["defect_labels"] == []


def test_verify_crop_image_rejects_neighbor_contamination() -> None:
    img = Image.new("RGB", (220, 120), (255, 255, 255))
    for x in range(30, 170):
        for y in range(25, 95):
            img.putpixel((x, y), (40, 90, 200))
    for x in range(2):
        for y in range(20, 100):
            img.putpixel((x, y), (20, 20, 20))

    result = verify_crop_image(img, crop_type="figure")

    assert result["accepted"] is False
    assert "neighbor_contamination" in result["defect_labels"]


def test_verify_crop_image_rejects_chart_with_axis_clipped_at_edges() -> None:
    img = Image.new("RGB", (320, 180), (255, 255, 255))
    for x in range(0, 285):
        img.putpixel((x, 179), (0, 0, 0))
        img.putpixel((x, 178), (0, 0, 0))
    for y in range(20, 180):
        img.putpixel((0, y), (0, 0, 0))
        img.putpixel((1, y), (0, 0, 0))
    for x in range(42, 280):
        y = 145 - ((x - 42) // 4)
        img.putpixel((x, y), (20, 80, 190))
        img.putpixel((x, min(179, y + 1)), (20, 80, 190))

    result = verify_crop_image(img, crop_type="chart")

    assert result["accepted"] is False
    assert "chart_axis_or_label_clipped" in result["defect_labels"]
    assert result["detectors"]["chart_completeness"]["accepted"] is False


def test_verify_crop_image_rejects_card_container_clipped_at_boundary() -> None:
    img = Image.new("RGB", (260, 160), (255, 255, 255))
    for x in range(0, 242):
        for y in range(12, 148):
            img.putpixel((x, y), (228, 236, 252))
    for x in range(16, 226):
        img.putpixel((x, 28), (55, 90, 160))
    for y in range(42, 128):
        img.putpixel((54, y), (55, 90, 160))
        img.putpixel((55, y), (55, 90, 160))

    result = verify_crop_image(img, crop_type="figure")

    assert result["accepted"] is False
    assert "visual_card_boundary_clipped" in result["defect_labels"]
    assert result["detectors"]["visual_card_boundary"]["accepted"] is False


def test_content_aware_trim_handles_gradient_margin_without_clipping_card() -> None:
    img = Image.new("RGB", (180, 120), (255, 255, 255))
    for x in range(180):
        shade = 240 - int(x / 180 * 20)
        for y in range(120):
            img.putpixel((x, y), (shade, shade, 248))
    for x in range(35, 145):
        for y in range(28, 92):
            img.putpixel((x, y), (80, 120, 210))

    trimmed, amounts = _content_aware_trim(img, crop_type="figure")

    assert trimmed.width < img.width
    assert trimmed.height < img.height
    assert amounts[0] < 28
    assert amounts[2] < 35


def test_render_preview_and_crop_refine_page_render_create_assets(tmp_path):
    pdf_path = tmp_path / "preview.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    preview_response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )
    page_render_response = render_page_for_crop_refine(
        CropRefinePageRenderRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page=0,
            dpi=110,
        ),
        _ctx(),
    )

    assert preview_response.schema_version == "1.1"
    assert preview_response.image_path == "report/assets/report-contents.png"
    assert (out_dir / preview_response.image_path).exists()

    assert page_render_response.page == 0
    assert page_render_response.image_width > 0
    assert page_render_response.image_height > 0
    assert page_render_response.scale_x > 0
    assert page_render_response.scale_y > 0
    assert (out_dir / page_render_response.image_path).exists()


def test_render_preview_compacts_filename_for_long_report_slug(tmp_path):
    pdf_path = tmp_path / "preview.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "nested-output-root" / "long-preview-destination"
    report_name = (
        "institute-for-canadian-citizenship-retention-trends-in-highly-skilled-"
        "immigrants-and-in-demand-occupations-acig-pdf"
    )

    response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name=report_name,
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )

    assert response.image_path is not None
    artifact_path = out_dir / response.image_path
    assert artifact_path.is_file()
    assert artifact_path.with_name(f"{artifact_path.name}.fingerprint.json").is_file()
    assert artifact_path.name.startswith("preview-contents-")
    assert len(artifact_path.name) <= 96


def test_apply_crop_refine_bbox_clamps_to_page_bounds(tmp_path):
    pdf_path = tmp_path / "bbox.pdf"
    _build_basic_pdf(pdf_path)

    response = apply_crop_refine_bbox(
        CropRefineBBoxApplyRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            page=0,
            bbox=(-30.0, -25.0, 500.0, 700.0),
        ),
        _ctx(),
    )

    x0, y0, x1, y1 = response.bbox
    assert response.page == 0
    assert 0.0 <= x0 < x1 <= 420.0
    assert 0.0 <= y0 < y1 <= 560.0


def test_apply_crop_refine_bbox_rejects_page_out_of_range(tmp_path, assert_app_error):
    pdf_path = tmp_path / "bbox_oob.pdf"
    _build_basic_pdf(pdf_path)

    with pytest.raises(AppError) as exc_info:
        apply_crop_refine_bbox(
            CropRefineBBoxApplyRequest(
                schema_version="1.0",
                pdf_path=pdf_path.as_posix(),
                page=3,
                bbox=(10.0, 10.0, 40.0, 40.0),
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="crop_refine_page_out_of_range",
        retryable=False,
    )


def test_apply_crop_refine_bbox_does_not_over_trim_for_long_crossing_text(tmp_path):
    pdf_path = tmp_path / "edge-trim-guard.pdf"
    _build_pdf_with_long_line_crossing_crop_edge(pdf_path)
    response = apply_crop_refine_bbox(
        CropRefineBBoxApplyRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            page=0,
            bbox=(60.0, 90.0, 360.0, 420.0),
        ),
        _ctx(),
    )

    assert response.bbox[2] >= 348.0


def test_crop_and_preview_sanitize_report_and_subdir_segments(tmp_path):
    pdf_path = tmp_path / "preview_escape.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=90.0,
        page=0,
        bbox=(60.0, 90.0, 220.0, 220.0),
    )

    crop_response = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="../escape",
            items=[item],
            subdir="../slices",
            mode="legacy",
        ),
        _ctx(),
    )
    preview_response = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="../escape",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )

    assert crop_response.paths == ["escape/slices/escape-chart-0-0.png"]
    assert preview_response.image_path == "escape/assets/escape-contents.png"
    assert (out_dir / crop_response.paths[0]).exists()
    assert (out_dir / preview_response.image_path).exists()


def test_dominant_border_color_normalizes_grayscale_and_alpha_pixels():
    assert _dominant_border_color(Image.new("L", (4, 4), 17)) == (17, 17, 17)
    assert _dominant_border_color(Image.new("LA", (4, 4), (19, 128))) == (19, 19, 19)
    assert _dominant_border_color(Image.new("RGBA", (4, 4), (10, 20, 30, 128))) == (
        10,
        20,
        30,
    )


__all__ = [
    "test_strict_crop_filenames_do_not_collide_across_table_and_chart_calls",
    "test_crop_regions_compacts_filename_for_long_report_slug",
    "test_chart_strict_tightens_partial_bottom_text_spillover",
    "test_tighten_chart_crop_rect_reclamps_padded_top_to_caption",
    "test_tighten_chart_crop_rect_leaves_plain_chart_without_context_unchanged",
    "test_tighten_chart_crop_rect_does_not_trim_internal_panel_label_block",
    "test_tighten_chart_crop_rect_keeps_draw_backed_internal_heading_band",
    "test_tighten_chart_crop_rect_expands_to_fill_top_when_internal_sentence_is_not_heading",
    "test_legacy_chart_border_trim_keeps_extra_bottom_padding_for_bottom_edge_text",
    "test_tighten_table_crop_rect_trims_top_page_number_but_keeps_header_band",
    "test_tighten_table_crop_rect_snaps_to_high_confidence_outer_rules",
    "test_table_crop_regions_stitch_split_table_title_and_note_for_adjacent_pages",
    "test_table_strict_clamps_after_note_and_avoids_section_spillover",
    "test_table_strict_detects_mid_statlink_for_bottom_clamp",
    "test_chart_strict_keeps_note_that_crosses_bbox_bottom",
    "test_publication_strict_writes_final_crop_diagnostics",
    "test_verify_crop_image_rejects_neighbor_contamination",
    "test_verify_crop_image_rejects_chart_with_axis_clipped_at_edges",
    "test_verify_crop_image_rejects_card_container_clipped_at_boundary",
    "test_content_aware_trim_handles_gradient_margin_without_clipping_card",
    "test_render_preview_and_crop_refine_page_render_create_assets",
    "test_render_preview_compacts_filename_for_long_report_slug",
    "test_apply_crop_refine_bbox_clamps_to_page_bounds",
    "test_apply_crop_refine_bbox_rejects_page_out_of_range",
    "test_apply_crop_refine_bbox_does_not_over_trim_for_long_crossing_text",
    "test_crop_and_preview_sanitize_report_and_subdir_segments",
    "test_dominant_border_color_normalizes_grayscale_and_alpha_pixels",
]
