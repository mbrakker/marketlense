from __future__ import annotations

from pathlib import Path

from src.services._browser_report_download._artifact.pdf import (
    _adopt_external_downloaded_file,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.artifacts import (
    _copy_external_artifact,
    _pdf_prefetch_destination_path,
)
from src.services._browser_report_download.artifact_paths import windows_path_units
from src.services._browser_report_download.artifact_paths import (
    resolve_browser_artifact_path,
)


def test_external_pdf_materialization_is_bounded_and_readable(tmp_path: Path) -> None:
    source_dir = tmp_path / "external"
    source_dir.mkdir()
    source = source_dir / (("publisher-report-" * 7) + ".pdf")
    source.write_bytes(b"%PDF-1.7\n")
    download_dir = tmp_path / ("browser-output-segment-" * 2)

    copied = _copy_external_artifact(
        source_path=source,
        download_dir=download_dir,
    )

    assert copied is not None
    assert copied.read_bytes().startswith(b"%PDF-")
    assert windows_path_units(copied) <= 240
    assert copied.parent == download_dir.resolve()

    adopted = _adopt_external_downloaded_file(
        source_path=source,
        download_dir=download_dir,
    )
    assert adopted is not None
    assert adopted != copied
    assert adopted.read_bytes().startswith(b"%PDF-")
    assert windows_path_units(adopted) <= 240


def test_structured_pdf_prefetch_path_preserves_short_name(tmp_path: Path) -> None:
    path = _pdf_prefetch_destination_path(
        download_dir=tmp_path,
        target_url="https://example.com/reports/annual-report.pdf?download=1",
        downloaded_file_name="fallback.pdf",
    )

    assert path.name == "annual-report.pdf"
    assert path.parent == tmp_path.resolve()


def test_same_short_pdf_basename_gets_identity_variant_when_occupied(
    tmp_path: Path,
) -> None:
    first = resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="report.pdf",
        identity="https://example.com/a/report.pdf",
    )
    first.write_bytes(b"%PDF-1.7\nfirst")
    second = resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="report.pdf",
        identity="https://example.com/b/report.pdf",
        force_identity_hash=True,
    )

    assert first.name == "report.pdf"
    assert second.name != first.name
    assert second.suffix == ".pdf"
    assert first.read_bytes() == b"%PDF-1.7\nfirst"
