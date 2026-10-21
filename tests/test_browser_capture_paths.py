from __future__ import annotations

from pathlib import Path

import pytest

from src.services._browser_report_download._artifact import onsite as onsite_runtime
from src.services._browser_report_download._artifact.evidence import (
    _write_terminal_html_snapshot as _write_artifact_terminal_html_snapshot,
)
from src.services._browser_report_download._artifact.onsite import (
    _capture_salvaged_onsite_html,
    _generated_onsite_capture_format,
    _resolve_onsite_capture_path,
    _safe_onsite_capture_path,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.capture import (
    _browser_rendered_pdf_capture_path,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.page_state import (
    _write_terminal_html_snapshot,
)
from src.services._browser_report_download.artifact_paths import (
    resolve_browser_artifact_path,
    windows_path_units,
)
from src.services._browser_report_download.request import (
    create_download_workspace,
    resolve_download_dir_path,
)
from src.utils.errors import AppError


def test_browser_capture_paths_sanitize_url_stems_and_keep_root(tmp_path: Path) -> None:
    download_dir = tmp_path / "browser-output"
    long_stem = "длинный-отчёт-" * 30
    final_url = f"https://example.com/research/{long_stem}?edition=1"

    rendered_pdf = _browser_rendered_pdf_capture_path(
        download_dir=download_dir,
        final_page_url=final_url,
    )
    onsite_html = _safe_onsite_capture_path(
        download_dir=download_dir,
        claimed_path="",
        final_url=final_url,
        suffix=".html",
    )

    assert rendered_pdf.parent == download_dir.resolve()
    assert onsite_html.parent == download_dir.resolve()
    assert rendered_pdf.suffix == ".pdf"
    assert onsite_html.suffix == ".html"
    assert windows_path_units(rendered_pdf) <= 240
    assert windows_path_units(onsite_html) <= 240


def test_fixed_terminal_capture_name_remains_unchanged(tmp_path: Path) -> None:
    path = _write_terminal_html_snapshot(
        download_dir=tmp_path,
        final_page_html="<html><body>report</body></html>",
    )

    assert Path(path).name == "terminal_snapshot.html"


def test_terminal_html_snapshot_collision_preserves_verified_capture(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "terminal_snapshot.html"
    existing_bytes = b"<html><body>verified-existing</body></html>"
    snapshot_path.write_bytes(existing_bytes)

    path = _write_terminal_html_snapshot(
        download_dir=tmp_path,
        final_page_html="<html><body>replacement</body></html>",
    )

    assert Path(path) != snapshot_path
    assert snapshot_path.read_bytes() == existing_bytes
    assert Path(path).read_text(encoding="utf-8") == (
        "<html><body>replacement</body></html>"
    )


def test_artifact_terminal_html_snapshot_collision_preserves_verified_capture(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "terminal_snapshot.html"
    existing_bytes = b"<html><body>verified-existing</body></html>"
    snapshot_path.write_bytes(existing_bytes)

    path = _write_artifact_terminal_html_snapshot(
        download_dir=tmp_path,
        html="<html><body>replacement</body></html>",
    )

    assert Path(path) != snapshot_path
    assert snapshot_path.read_bytes() == existing_bytes
    assert Path(path).read_text(encoding="utf-8") == (
        "<html><body>replacement</body></html>"
    )


def test_salvage_capture_does_not_delete_existing_download_artifact(
    tmp_path: Path,
) -> None:
    normalized_url = "https://example.com/research/report"
    download_dir = resolve_download_dir_path(
        root_dir=str(tmp_path / "downloads"),
        normalized_url=normalized_url,
    )
    download_dir.mkdir(parents=True)
    attempt_dir = create_download_workspace(download_dir)
    existing_pdf = attempt_dir / "existing.pdf"
    existing_pdf.write_bytes(b"%PDF-1.7\nexisting")

    capture = _capture_salvaged_onsite_html(
        download_dir=attempt_dir,
        normalized_url=normalized_url,
        final_url=normalized_url,
        html="<html><body>report</body></html>",
    )

    assert capture.exists()
    assert capture.parent == attempt_dir.resolve()
    assert existing_pdf.read_bytes() == b"%PDF-1.7\nexisting"


def test_pdf_named_html_recovery_preserves_occupied_html_and_original_bytes(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    downloaded_path = attempt_dir / "report.pdf"
    existing_html = attempt_dir / "report.html"
    source_bytes = b"<html><body>source A</body></html>"
    existing_bytes = b"<html><body>existing B</body></html>"
    downloaded_path.write_bytes(source_bytes)
    existing_html.write_bytes(existing_bytes)

    capture_path = _resolve_onsite_capture_path(downloaded_path)

    assert capture_path.suffix == ".html"
    assert capture_path.read_bytes() == source_bytes
    assert downloaded_path.read_bytes() == source_bytes
    assert existing_html.read_bytes() == existing_bytes
    assert capture_path.parent == attempt_dir.resolve()
    assert windows_path_units(capture_path) <= 240


def test_already_html_recovery_preserves_path_and_bytes(tmp_path: Path) -> None:
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    downloaded_path = attempt_dir / "report.html"
    source_bytes = b"<html><body>already HTML</body></html>"
    downloaded_path.write_bytes(source_bytes)

    capture_path = _resolve_onsite_capture_path(downloaded_path)

    assert capture_path == downloaded_path.resolve()
    assert capture_path.read_bytes() == source_bytes


def test_recovered_capture_format_normalizes_extension_case() -> None:
    assert (
        _generated_onsite_capture_format(
            onsite_capture_format="browser_rendered_pdf",
            suffix=".HTML",
        )
        == "html"
    )


def test_salvage_capture_long_unicode_url_stays_within_windows_budget(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "attempt"
    normalized_url = (
        "https://example.com/research/" + ("длинный-отчёт-" * 30) + "?edition=1"
    )
    html = "<html><body><h1>Unicode research report</h1></body></html>"

    capture_path = _capture_salvaged_onsite_html(
        download_dir=download_dir,
        normalized_url=normalized_url,
        final_url=normalized_url,
        html=html,
    )

    assert capture_path.parent == download_dir.resolve()
    assert capture_path.suffix == ".html"
    assert windows_path_units(capture_path) <= 240
    assert capture_path.read_text(encoding="utf-8") == html


def test_salvage_capture_reuses_identical_bytes_without_duplicate(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "browser-output"
    normalized_url = "https://example.com/research/report"
    html = "<html><body><h1>Research report</h1></body></html>"

    first = _capture_salvaged_onsite_html(
        download_dir=download_dir,
        normalized_url=normalized_url,
        final_url=normalized_url,
        html=html,
    )
    second = _capture_salvaged_onsite_html(
        download_dir=download_dir,
        normalized_url=normalized_url,
        final_url=normalized_url,
        html=html,
    )

    assert second == first
    assert second.read_text(encoding="utf-8") == html
    assert sorted(path.name for path in download_dir.glob("*.html")) == [first.name]


def test_salvage_capture_does_not_overwrite_occupied_identity_variant(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "browser-output"
    normalized_url = "https://example.com/research/report"
    normal_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name="report",
        extension=".html",
        identity=normalized_url,
        temporary_suffixes=(".part",),
    )
    identity_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name="report",
        extension=".html",
        identity=normalized_url,
        force_identity_hash=True,
        temporary_suffixes=(".part",),
    )
    normal_path.parent.mkdir(parents=True)
    normal_path.write_bytes(b"existing normal capture")
    identity_path.write_bytes(b"existing identity capture")

    capture_path = _capture_salvaged_onsite_html(
        download_dir=download_dir,
        normalized_url=normalized_url,
        final_url=normalized_url,
        html="<html><body><h1>Research report A</h1></body></html>",
    )

    assert capture_path.suffix == ".html"
    assert capture_path not in {normal_path, identity_path}
    assert capture_path.read_text(encoding="utf-8").endswith(
        "<h1>Research report A</h1></body></html>"
    )
    assert normal_path.read_bytes() == b"existing normal capture"
    assert identity_path.read_bytes() == b"existing identity capture"


def test_salvage_capture_materialization_failure_is_typed_and_cleans_stage(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        onsite_runtime,
        "materialize_external_browser_artifact",
        lambda **kwargs: None,
    )

    with pytest.raises(AppError) as error:
        _capture_salvaged_onsite_html(
            download_dir=tmp_path / "browser-output",
            normalized_url="https://example.com/research/report",
            final_url="https://example.com/research/report",
            html="<html><body><h1>Research report</h1></body></html>",
        )

    assert error.value.code == "browser_download_artifact_materialization_failed"
    assert not list((tmp_path / "browser-output").glob("*.part"))


def test_pdf_named_html_recovery_materialization_failure_is_typed(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        onsite_runtime,
        "materialize_external_browser_artifact",
        lambda **kwargs: None,
    )
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    downloaded_path = attempt_dir / "report.pdf"
    source_bytes = b"<html><body>source A</body></html>"
    downloaded_path.write_bytes(source_bytes)

    with pytest.raises(AppError) as error:
        _resolve_onsite_capture_path(downloaded_path)

    assert error.value.code == "browser_download_artifact_materialization_failed"
    assert downloaded_path.read_bytes() == source_bytes
    assert not list(attempt_dir.glob("*.part"))
