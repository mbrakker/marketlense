# ruff: noqa: F401,F403,F405
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest
from PIL import Image

from ._shared import *  # noqa: F401,F403

from src.services._pdf.fingerprint_cache import CROP_REFINE_PAGE_ARTIFACT_VERSION
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    is_windows_reserved_component,
    safe_path_segment,
    windows_path_units,
)


_TEMP_WRITE_HEADROOM = 10
_TEMP_WRITE_PREFIX = ".tmp-write-"
_REAL_REPORT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "pdf_benchmark"
    / "golden"
    / "CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"
)


def _render_request(
    pdf_path: Path,
    out_dir: Path,
    report_name: str,
    *,
    page: int = 0,
    dpi: int = 72,
) -> CropRefinePageRenderRequest:
    return CropRefinePageRenderRequest(
        schema_version="1.0",
        pdf_path=pdf_path.as_posix(),
        out_dir=out_dir.as_posix(),
        report_name=report_name,
        page=page,
        dpi=dpi,
    )


def _artifact_paths(root: Path, response) -> tuple[Path, Path, Path]:
    image_path = (root / response.image_path).resolve()
    fingerprint_path = image_path.with_name(f"{image_path.name}.fingerprint.json")
    temporary_path = image_path.parent / (
        f"{_TEMP_WRITE_PREFIX}{'x' * _TEMP_WRITE_HEADROOM}"
    )
    return image_path, fingerprint_path, temporary_path


def _assert_windows_path_policy(*paths: Path) -> None:
    for path in paths:
        assert windows_path_units(path) <= WINDOWS_PATH_BUDGET
        for component in path.parts:
            if component == path.anchor:
                continue
            assert windows_path_units(component) <= WINDOWS_COMPONENT_BUDGET
            assert not is_windows_reserved_component(component)


def _assert_rendered_artifact(root: Path, response) -> tuple[Path, Path, Path]:
    image_path, fingerprint_path, temporary_path = _artifact_paths(root, response)
    assert image_path.is_file()
    assert fingerprint_path.is_file()
    with Image.open(image_path) as image:
        image.load()
        assert image.width == response.image_width
        assert image.height == response.image_height
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    assert fingerprint["output_rel_path"] == response.image_path
    assert fingerprint["artifact_version"] == CROP_REFINE_PAGE_ARTIFACT_VERSION
    assert (
        fingerprint["output_sha256"]
        == hashlib.sha256(image_path.read_bytes()).hexdigest()
    )
    _assert_windows_path_policy(image_path, fingerprint_path, temporary_path)
    return image_path, fingerprint_path, temporary_path


def _make_deep_root(base: Path, target_units: int) -> Path:
    root = base / "deep-root"
    index = 0
    while windows_path_units(root) < target_units:
        root /= f"segment-{index:02d}-{'x' * 20}"
        index += 1
    root.mkdir(parents=True, exist_ok=True)
    return root


def _compact_component(path: str) -> str:
    return Path(path).parts[0]


def test_crop_refine_normal_path_preserves_relative_reference_and_sidecar(
    tmp_path,
):
    pdf_path = tmp_path / "normal.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    response = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, "report", dpi=96), _ctx()
    )

    assert response.image_path == "report/crop_refine_pages/page-0.png"
    _assert_rendered_artifact(out_dir, response)


@pytest.mark.parametrize(
    "report_name",
    [
        "ascii-report-" + ("long-name-" * 40),
        "unicode-report-" + ("😀" * 120),
    ],
)
def test_crop_refine_long_names_are_deterministically_compacted(tmp_path, report_name):
    pdf_path = tmp_path / "long-name.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"

    first = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name), _ctx()
    )
    second = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name), _ctx()
    )

    assert first.image_path == second.image_path
    report_component = _compact_component(first.image_path)
    assert re.search(r"-[0-9a-f]{12}$", report_component)
    assert report_component != safe_path_segment(report_name, fallback="report")
    _assert_rendered_artifact(out_dir, first)


def test_crop_refine_compacted_names_do_not_collide_after_sanitization(tmp_path):
    pdf_path = tmp_path / "collision.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    prefix = "same-readable-prefix-" + ("x" * 90)
    first_name = prefix + ("😀" * 80)
    second_name = prefix + ("🚀" * 80)
    assert safe_path_segment(first_name, fallback="report") == safe_path_segment(
        second_name, fallback="report"
    )

    first = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, first_name), _ctx()
    )
    second = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, second_name), _ctx()
    )

    assert first.image_path != second.image_path
    first_image, _, _ = _assert_rendered_artifact(out_dir, first)
    second_image, _, _ = _assert_rendered_artifact(out_dir, second)
    assert first_image != second_image


def test_crop_refine_compaction_succeeds_in_a_deep_valid_root(tmp_path):
    pdf_path = tmp_path / "deep.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = _make_deep_root(tmp_path, 160)
    report_name = "deep-readable-report-" + ("segment-" * 35)

    response = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name), _ctx()
    )

    image_path, fingerprint_path, temporary_path = _assert_rendered_artifact(
        out_dir, response
    )
    assert image_path.is_file()
    assert fingerprint_path.is_file()
    assert not temporary_path.exists()


def test_crop_refine_impossible_root_fails_before_pdf_or_output_side_effects(
    tmp_path,
):
    out_dir = _make_deep_root(tmp_path, 218)
    before = sorted(path.name for path in out_dir.iterdir())
    request = _render_request(
        tmp_path / "does-not-exist.pdf",
        out_dir,
        "report",
    )

    with pytest.raises(AppError) as exc_info:
        render_page_for_crop_refine(request, _ctx())

    error = exc_info.value
    assert error.code == "crop_refine_page_path_invalid"
    assert error.retryable is False
    assert "shorten output_dir" in error.message
    assert error.context["windows_path_budget"] == WINDOWS_PATH_BUDGET
    assert error.context["windows_component_budget"] == WINDOWS_COMPONENT_BUDGET
    assert sorted(path.name for path in out_dir.iterdir()) == before


def test_crop_refine_cache_replay_reuses_image_without_rewriting(tmp_path, caplog):
    pdf_path = tmp_path / "cache.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    request = _render_request(pdf_path, out_dir, "cache-report", dpi=96)

    first = render_page_for_crop_refine(request, _ctx())
    image_path, _, _ = _assert_rendered_artifact(out_dir, first)
    first_mtime = image_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    second = render_page_for_crop_refine(request, _ctx())

    assert second.image_path == first.image_path
    assert image_path.stat().st_mtime_ns == first_mtime
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_refine_page_render_cache_hit" for event in events
    )


def test_crop_refine_invalid_fingerprint_regenerates_then_replays(tmp_path, caplog):
    pdf_path = tmp_path / "invalid-fingerprint.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = tmp_path / "out"
    request = _render_request(pdf_path, out_dir, "invalid-fingerprint")

    first = render_page_for_crop_refine(request, _ctx())
    image_path, fingerprint_path, _ = _assert_rendered_artifact(out_dir, first)
    payload = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    payload["cache_key"] = "mismatched-cache-key"
    fingerprint_path.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.02)
    original_mtime = image_path.stat().st_mtime_ns

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")
    regenerated = render_page_for_crop_refine(request, _ctx())
    regenerated_mtime = image_path.stat().st_mtime_ns
    replayed = render_page_for_crop_refine(request, _ctx())

    assert regenerated.image_path == first.image_path
    assert replayed.image_path == first.image_path
    assert regenerated_mtime > original_mtime
    _assert_rendered_artifact(out_dir, regenerated)
    events = _events(caplog, "market_lense.pdf_service.crop")
    assert any(
        event.get("event") == "crop_refine_page_render_cache_store"
        and event.get("fields", {}).get("validity_reason") == "cache_key_changed"
        for event in events
    )
    assert any(
        event.get("event") == "crop_refine_page_render_cache_hit" for event in events
    )


def test_crop_refine_page_identity_dimensions_and_transforms_survive_compaction(
    tmp_path,
):
    pdf_path = tmp_path / "geometry.pdf"
    doc = fitz.open()
    first_page = doc.new_page(width=320, height=240)
    first_page.insert_text((30, 40), "first page", fontsize=14)
    second_page = doc.new_page(width=480, height=300)
    second_page.insert_text((30, 40), "second page", fontsize=14)
    second_page.set_rotation(90)
    doc.save(pdf_path.as_posix())
    doc.close()
    out_dir = tmp_path / "out"
    report_name = "geometry-report-" + ("long-" * 45)

    first = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name, page=0, dpi=72), _ctx()
    )
    second = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name, page=1, dpi=72), _ctx()
    )

    assert first.page == 0
    assert second.page == 1
    assert first.image_path != second.image_path
    assert first.rotation == 0
    assert second.rotation == 90
    for response in (first, second):
        assert response.image_width == pytest.approx(
            response.page_width * response.scale_x
        )
        assert response.image_height == pytest.approx(
            response.page_height * response.scale_y
        )
        assert response.scale_x > 0
        assert response.scale_y > 0
        assert response.image_to_pdf_transform[0] == pytest.approx(
            response.display_to_pdf_transform[0] / response.scale_x
        )
        _assert_rendered_artifact(out_dir, response)
    assert (
        hashlib.sha256((out_dir / first.image_path).read_bytes()).hexdigest()
        != hashlib.sha256((out_dir / second.image_path).read_bytes()).hexdigest()
    )


def test_crop_refine_downstream_output_dir_join_resolves_compacted_image(tmp_path):
    pdf_path = tmp_path / "downstream.pdf"
    _build_basic_pdf(pdf_path)
    out_dir = _make_deep_root(tmp_path, 150)
    report_name = "downstream-report-" + ("long-name-" * 35)
    settings = SimpleNamespace(output_dir=out_dir)

    response = render_page_for_crop_refine(
        _render_request(pdf_path, out_dir, report_name), _ctx()
    )
    actual_path, _, _ = _assert_rendered_artifact(out_dir, response)
    llm_image_path = (Path(settings.output_dir) / response.image_path).resolve()

    assert llm_image_path == actual_path
    assert llm_image_path.is_file()


def test_crop_refine_real_report_renders_two_pages_and_replays(tmp_path):
    assert _REAL_REPORT.is_file()
    out_dir = _make_deep_root(tmp_path, 155)
    report_name = "CAPGEMINI retail trends report " + ("long-" * 30)

    responses = []
    for page in (0, 1):
        request = _render_request(
            _REAL_REPORT,
            out_dir,
            report_name,
            page=page,
            dpi=72,
        )
        response = render_page_for_crop_refine(request, _ctx())
        replay = render_page_for_crop_refine(request, _ctx())
        assert replay.image_path == response.image_path
        assert replay.page == page
        assert replay.rotation in {0, 90, 180, 270}
        _assert_rendered_artifact(out_dir, response)
        responses.append(response)

    assert [response.page for response in responses] == [0, 1]
    assert responses[0].image_path != responses[1].image_path


__all__ = [name for name in globals() if name.startswith("test_")]
