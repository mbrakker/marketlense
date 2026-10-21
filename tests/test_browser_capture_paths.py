from __future__ import annotations

from pathlib import Path

from src.services._browser_report_download._artifact.onsite import (
    _capture_salvaged_onsite_html,
    _safe_onsite_capture_path,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.capture import (
    _browser_rendered_pdf_capture_path,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.page_state import (
    _write_terminal_html_snapshot,
)
from src.services._browser_report_download.artifact_paths import windows_path_units
from src.services._browser_report_download.request import (
    create_download_workspace,
    resolve_download_dir_path,
)


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
