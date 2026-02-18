from pathlib import Path

import pymupdf as fitz
from PIL import Image

from src.contracts.report_assets import CropRequest
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services.pdf_service import crop_regions


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
