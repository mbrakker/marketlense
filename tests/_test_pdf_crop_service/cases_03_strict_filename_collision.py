# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *


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
    files = sorted(path.name for path in slices_dir.glob("*.png"))
    assert len(files) == 2
    assert "report-table-1-0.png" in files
    assert "report-chart-1-0.png" in files


__all__ = ["test_strict_crop_filenames_do_not_collide_across_table_and_chart_calls"]
