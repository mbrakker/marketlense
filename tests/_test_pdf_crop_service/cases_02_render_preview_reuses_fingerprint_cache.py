# ruff: noqa: F401,F403,F405
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from ._shared import *  # noqa: F401,F403

from src.services._pdf.fingerprint_cache import (
    PdfArtifactFingerprintDescriptor,
    write_artifact_sidecar,
)


def test_fingerprint_sidecar_write_is_safe_for_concurrent_same_artifact(
    tmp_path,
) -> None:
    artifact_path = tmp_path / "slices" / "report-chart-1.png"
    artifact_path.parent.mkdir()
    artifact_path.write_bytes(b"image")
    descriptor = PdfArtifactFingerprintDescriptor(
        artifact_kind="crop_region",
        source_pdf_path="source.pdf",
        output_rel_path="slices/report-chart-1.png",
        page=1,
        artifact_identity="chart-1",
        content_fingerprint="content",
        settings_payload={"dpi": 144},
        artifact_version="1.0",
    )
    barrier = Barrier(2)

    def write_once() -> str:
        barrier.wait()
        return write_artifact_sidecar(descriptor, artifact_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda _: write_once(), range(2)))

    sidecar_path = artifact_path.with_name(f"{artifact_path.name}.fingerprint.json")
    assert paths == [sidecar_path.as_posix(), sidecar_path.as_posix()]
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["cache_key"] == (
        descriptor.cache_key
    )
    assert list(sidecar_path.parent.glob(f"{sidecar_path.name}.tmp-write-*")) == []

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


def test_publication_strict_cache_rejects_cached_crop_from_qa_diagnostics(
    tmp_path, caplog
) -> None:
    pdf_path = tmp_path / "strict-cache.pdf"
    out_dir = tmp_path / "out"
    _build_basic_pdf(pdf_path)
    item = CropItem(
        id="strict-figure",
        type="figure",
        score=91.0,
        page=0,
        bbox=(60, 90, 360, 280),
    )
    request = CropRequest(
        schema_version="1.0",
        pdf_path=pdf_path.as_posix(),
        out_dir=out_dir.as_posix(),
        report_name="report",
        items=[item],
        subdir="slices",
        mode="publication_strict",
    )

    first = crop_regions(request, _ctx())
    assert first.paths
    assert first.outcomes[0].accepted is True
    artifact_path = out_dir / first.paths[0]
    diagnostics_path = artifact_path.with_suffix(artifact_path.suffix + ".qa.json")
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["accepted"] = False
    diagnostics["qa"]["accepted"] = False
    diagnostics["qa"]["defect_labels"] = ["neighbor_contamination"]
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = crop_regions(request, _ctx())

    assert second.paths == []
    assert len(second.outcomes) == 1
    assert second.outcomes[0].accepted is False
    assert second.outcomes[0].path == ""
    assert second.outcomes[0].rejection_reason == "neighbor_contamination"
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(event.get("event") == "crop_region_cache_rejected" for event in events)


@pytest.mark.parametrize("diagnostics_payload", [None, "not-json"])
def test_publication_strict_cache_regenerates_missing_or_invalid_qa_diagnostics(
    tmp_path, caplog, diagnostics_payload
) -> None:
    pdf_path = tmp_path / "strict-cache-diagnostics.pdf"
    out_dir = tmp_path / "out"
    _build_basic_pdf(pdf_path)
    item = CropItem(
        id="strict-figure",
        type="figure",
        score=91.0,
        page=0,
        bbox=(60, 90, 360, 280),
    )
    request = CropRequest(
        schema_version="1.0",
        pdf_path=pdf_path.as_posix(),
        out_dir=out_dir.as_posix(),
        report_name="report",
        items=[item],
        subdir="slices",
        mode="publication_strict",
    )

    first = crop_regions(request, _ctx())
    artifact_path = out_dir / first.paths[0]
    diagnostics_path = artifact_path.with_suffix(artifact_path.suffix + ".qa.json")
    if diagnostics_payload is None:
        diagnostics_path.unlink()
    else:
        diagnostics_path.write_text(diagnostics_payload, encoding="utf-8")

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = crop_regions(request, _ctx())

    assert second.paths == first.paths
    assert second.outcomes[0].accepted is True
    restored = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert restored["accepted"] is True
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_region_cache_store"
        and event.get("fields", {}).get("validity_reason")
        == "qa_diagnostics_missing_or_invalid"
        for event in events
    )


def test_publication_strict_cache_invalidates_old_crop_artifact_version(
    tmp_path, caplog
) -> None:
    pdf_path = tmp_path / "strict-cache-version.pdf"
    out_dir = tmp_path / "out"
    _build_basic_pdf(pdf_path)
    item = CropItem(
        id="strict-figure",
        type="figure",
        score=91.0,
        page=0,
        bbox=(60, 90, 360, 280),
    )
    request = CropRequest(
        schema_version="1.0",
        pdf_path=pdf_path.as_posix(),
        out_dir=out_dir.as_posix(),
        report_name="report",
        items=[item],
        subdir="slices",
        mode="publication_strict",
    )

    first = crop_regions(request, _ctx())
    artifact_path = out_dir / first.paths[0]
    fingerprint_path = artifact_path.with_name(
        f"{artifact_path.name}.fingerprint.json"
    )
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    fingerprint["artifact_version"] = "1.0"
    fingerprint_path.write_text(json.dumps(fingerprint), encoding="utf-8")

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = crop_regions(request, _ctx())

    assert second.paths == first.paths
    assert second.outcomes[0].accepted is True
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_region_cache_store"
        and event.get("fields", {}).get("validity_reason") == "version_changed"
        for event in events
    )

__all__ = [
    "test_fingerprint_sidecar_write_is_safe_for_concurrent_same_artifact",
    "test_render_preview_reuses_fingerprint_cache_on_partial_change_rerun",
    "test_render_page_for_crop_refine_invalidates_stale_artifact_version",
    "test_crop_regions_reuses_fingerprint_cache_on_partial_change_rerun",
    "test_publication_strict_cache_rejects_cached_crop_from_qa_diagnostics",
    "test_publication_strict_cache_regenerates_missing_or_invalid_qa_diagnostics",
    "test_publication_strict_cache_invalidates_old_crop_artifact_version",
]
