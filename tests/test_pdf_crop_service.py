from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefinePageRenderRequest,
    CropRequest,
    PreviewRequest,
)
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services._pdf.crop import _tighten_chart_crop_rect
from src.services.pdf_service import (
    apply_crop_refine_bbox,
    crop_regions,
    render_page_for_crop_refine,
    render_preview,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def _build_basic_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=420, height=560)
    page.insert_text((40, 40), "Crop test page", fontsize=14)
    page.draw_rect(fitz.Rect(60, 90, 360, 280), color=(0, 0, 0), fill=(0.94, 0.94, 0.94))
    doc.save(path.as_posix())
    doc.close()


def _build_pdf_with_bottom_body_text(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.draw_rect(fitz.Rect(60, 90, 540, 420), color=(0, 0, 0), fill=(0.95, 0.95, 0.95))
    page.insert_text((74, 125), "Figure 1. Synthetic chart", fontsize=16)
    page.insert_text((74, 405), "Source: synthetic data", fontsize=10)
    page.insert_textbox(
        fitz.Rect(60, 445, 540, 730),
        "This paragraph should stay outside the final chart crop. " * 40,
        fontsize=11,
    )
    doc.save(path.as_posix())
    doc.close()


def _build_pdf_with_table_note_and_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=820)
    page.draw_rect(fitz.Rect(60, 90, 560, 390), color=(0, 0, 0), fill=(0.95, 0.95, 0.95))
    page.insert_text((74, 122), "Table 1. Synthetic projections", fontsize=16)
    page.insert_textbox(
        fitz.Rect(72, 408, 560, 470),
        "Note: Values are shown for illustration only and do not represent real forecasts.",
        fontsize=10,
    )
    page.insert_text((72, 486), "Source: synthetic dataset.", fontsize=10)
    page.insert_text((372, 508), "StatLink https://example.invalid", fontsize=10)
    page.insert_text((72, 560), "Recent Developments", fontsize=20)
    page.insert_textbox(
        fitz.Rect(72, 590, 560, 780),
        "This section must remain outside the strict table crop. " * 32,
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()


def _build_pdf_with_mid_statlink_and_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=820)
    page.draw_rect(fitz.Rect(60, 120, 560, 300), color=(0, 0, 0), fill=(0.95, 0.95, 0.95))
    page.insert_text((74, 152), "Figure 1. Mid-page statlink case", fontsize=14)
    page.insert_text((72, 352), "StatLink https://example.invalid", fontsize=10)
    page.insert_text((72, 430), "Recent Developments", fontsize=20)
    page.insert_textbox(
        fitz.Rect(72, 462, 560, 760),
        "This section must remain outside the strict crop. " * 38,
        fontsize=12,
    )
    doc.save(path.as_posix())
    doc.close()


def _build_pdf_with_top_chart_spillover(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=620, height=900)
    page.insert_textbox(
        fitz.Rect(65, 116, 540, 176),
        (
            "Given the heterogeneity in regulation trends across states, there are again large "
            "variations between regions. This paragraph should remain outside the saved chart crop."
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
        "Estimated contribution of changes in regulation to productivity and business dynamism",
        fontsize=12,
    )
    page.draw_rect(
        fitz.Rect(65, 300, 540, 700),
        color=(0, 0, 0),
        fill=(0.95, 0.95, 0.95),
    )
    doc.save(path.as_posix())
    doc.close()


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
