# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_render_preview_reuses_fingerprint_cache_on_partial_change_rerun(
    tmp_path, caplog
) -> None:
    pdf_v1 = tmp_path / "preview-v1.pdf"
    pdf_v2 = tmp_path / "preview-v2.pdf"
    out_dir = tmp_path / "out"
    _build_partial_change_pdf(
        pdf_v1,
        first_page_label="Stable first page",
        second_page_label="Original second page",
    )
    _build_partial_change_pdf(
        pdf_v2,
        first_page_label="Stable first page",
        second_page_label="Updated second page",
    )

    first = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_v1.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )
    artifact_path = out_dir / first.image_path
    first_mtime = artifact_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.preview")
    second = render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=pdf_v2.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            page_number=0,
            variant="contents",
            dpi=96,
        ),
        _ctx(),
    )

    assert second.image_path == first.image_path
    assert artifact_path.stat().st_mtime_ns == first_mtime
    events = _events(caplog, "market_lense.pdf_service.preview")
    assert any(event.get("event") == "preview_render_cache_hit" for event in events)

def test_render_page_for_crop_refine_invalidates_stale_artifact_version(
    tmp_path, caplog
) -> None:
    pdf_path = tmp_path / "refine.pdf"
    out_dir = tmp_path / "out"
    _build_basic_pdf(pdf_path)

    first = render_page_for_crop_refine(
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
    artifact_path = out_dir / first.image_path
    sidecar_path = artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    payload["artifact_version"] = "0.0"
    sidecar_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    time.sleep(0.02)
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = render_page_for_crop_refine(
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

    assert second.image_path == first.image_path
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_refine_page_render_cache_store"
        and isinstance(event.get("fields"), dict)
        and event["fields"].get("validity_reason") == "version_changed"
        for event in events
    )

def test_crop_regions_reuses_fingerprint_cache_on_partial_change_rerun(
    tmp_path, caplog
) -> None:
    pdf_v1 = tmp_path / "crop-v1.pdf"
    pdf_v2 = tmp_path / "crop-v2.pdf"
    out_dir = tmp_path / "out"
    _build_partial_change_pdf(
        pdf_v1,
        first_page_label="Stable chart page",
        second_page_label="Original trailing page",
    )
    _build_partial_change_pdf(
        pdf_v2,
        first_page_label="Stable chart page",
        second_page_label="Updated trailing page",
    )
    item = CropItem(
        id="chart-0-0",
        type="chart",
        score=91.0,
        page=0,
        bbox=(60.0, 90.0, 360.0, 280.0),
    )

    first = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_v1.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="slices",
            mode="legacy",
        ),
        _ctx(),
    )
    artifact_path = out_dir / first.paths[0]
    first_mtime = artifact_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_v2.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
            items=[item],
            subdir="slices",
            mode="legacy",
        ),
        _ctx(),
    )

    assert second.paths == first.paths
    assert artifact_path.stat().st_mtime_ns == first_mtime
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(event.get("event") == "crop_region_cache_hit" for event in events)

__all__ = [
    "test_render_preview_reuses_fingerprint_cache_on_partial_change_rerun",
    "test_render_page_for_crop_refine_invalidates_stale_artifact_version",
    "test_crop_regions_reuses_fingerprint_cache_on_partial_change_rerun",
]
