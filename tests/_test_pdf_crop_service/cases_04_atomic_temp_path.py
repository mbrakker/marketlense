# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *


def test_crop_refine_compacts_report_slug_before_fingerprint_sidecar_write(tmp_path):
    pdf_path = tmp_path / "refine-long-report.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / ("nested-output-root-" + ("x" * 50))
    report_name = (
        "2026-20b2c-20ecommerce-20ai-20trends-ebook-en-2-pdf-"
        "with-a-long-source-report-name"
    )

    response = render_page_for_crop_refine(
        CropRefinePageRenderRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name=report_name,
            page=0,
            dpi=110,
        ),
        _ctx(),
    )

    artifact_path = out_dir / response.image_path
    fingerprint_path = artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")
    assert artifact_path.is_file()
    assert fingerprint_path.is_file()
    assert len(str(fingerprint_path)) <= 240
    assert response.image_path.split("/")[0] != report_name
