from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services._browser_report_download._artifact.pdf import (
    _adopt_external_downloaded_file,
    _resolve_downloaded_file,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.artifacts import (
    _copy_external_artifact,
    _materialize_external_artifacts,
    _prefetch_structured_pdf_artifact,
    _pdf_prefetch_destination_path,
)
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.artifact_materialization import (
    materialize_external_browser_artifact,
)
from src.services._browser_report_download.artifact_paths import windows_path_units
from src.services._browser_report_download.artifact_paths import (
    resolve_browser_artifact_path,
)


def _create_overbudget_source(
    *,
    download_dir: Path,
    directory_prefix: str,
) -> Path:
    source_dir = download_dir / (directory_prefix * 3)
    source_dir.mkdir(parents=True)
    for repeat_count in range(2, 8):
        candidate = source_dir / (("published-market-report-" * repeat_count) + ".pdf")
        if 240 < windows_path_units(candidate) <= 258:
            return candidate
    pytest.skip("test root cannot represent a safe over-budget local path")


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
    assert adopted == copied
    assert adopted.read_bytes().startswith(b"%PDF-")
    assert windows_path_units(adopted) <= 240


def test_external_pdf_materialization_is_idempotent_across_same_basename_sources(
    tmp_path: Path,
) -> None:
    first_source_dir = tmp_path / "first"
    second_source_dir = tmp_path / "second"
    first_source_dir.mkdir()
    second_source_dir.mkdir()
    first_source = first_source_dir / "report.pdf"
    second_source = second_source_dir / "report.pdf"
    first_bytes = b"%PDF-1.7\nfirst"
    second_bytes = b"%PDF-1.7\nsecond"
    first_source.write_bytes(first_bytes)
    second_source.write_bytes(second_bytes)
    download_dir = tmp_path / "browser-output"

    first_copy = _copy_external_artifact(
        source_path=first_source,
        download_dir=download_dir,
    )
    second_copy = _copy_external_artifact(
        source_path=second_source,
        download_dir=download_dir,
    )
    first_replay = _adopt_external_downloaded_file(
        source_path=first_source,
        download_dir=download_dir,
    )
    second_replay = _adopt_external_downloaded_file(
        source_path=second_source,
        download_dir=download_dir,
    )

    assert first_copy is not None
    assert second_copy is not None
    assert first_copy != second_copy
    assert first_replay == first_copy
    assert second_replay == second_copy
    assert first_copy.read_bytes() == first_bytes
    assert second_copy.read_bytes() == second_bytes
    assert sorted(path.name for path in download_dir.glob("*.pdf")) == sorted(
        [first_copy.name, second_copy.name]
    )


def test_external_pdf_materialization_preserves_previous_bytes_when_source_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "external" / "report.pdf"
    source.parent.mkdir()
    download_dir = tmp_path / "browser-output"
    source.write_bytes(b"%PDF-1.7\noriginal")

    original_copy = _copy_external_artifact(
        source_path=source,
        download_dir=download_dir,
    )
    source.write_bytes(b"%PDF-1.7\nupdated")
    updated_copy = _copy_external_artifact(
        source_path=source,
        download_dir=download_dir,
    )

    assert original_copy is not None
    assert updated_copy is not None
    assert updated_copy != original_copy
    assert original_copy.read_bytes() == b"%PDF-1.7\noriginal"
    assert updated_copy.read_bytes() == b"%PDF-1.7\nupdated"


def test_materialization_preferred_filename_keeps_html_extension_and_no_clobber(
    tmp_path: Path,
) -> None:
    source = tmp_path / "external" / "report.pdf"
    source.parent.mkdir()
    source.write_bytes(b"<html><body>source A</body></html>")
    download_dir = tmp_path / "browser-output"
    preferred = download_dir / "report.html"
    preferred.parent.mkdir()
    preferred.write_bytes(b"<html><body>existing B</body></html>")

    first = materialize_external_browser_artifact(
        source_path=source,
        download_dir=download_dir,
        preferred_filename="report.html",
        source_identity="https://example.com/research/report",
    )

    source.write_bytes(b"<html><body>source C</body></html>")
    second = materialize_external_browser_artifact(
        source_path=source,
        download_dir=download_dir,
        preferred_filename="report.html",
        source_identity="https://example.com/research/report",
    )

    assert first is not None
    assert second is not None
    assert first.suffix == second.suffix == ".html"
    assert first not in {preferred, second}
    assert second not in {preferred, first}
    assert first.read_bytes() == b"<html><body>source A</body></html>"
    assert second.read_bytes() == b"<html><body>source C</body></html>"
    assert preferred.read_bytes() == b"<html><body>existing B</body></html>"


def test_overbudget_local_browser_artifact_is_compacted_before_return(
    tmp_path: Path,
    run_context,
) -> None:
    download_dir = tmp_path / "browser-output"
    source = _create_overbudget_source(
        download_dir=download_dir,
        directory_prefix="nested-artifact-directory-",
    )
    source.write_bytes(b"%PDF-1.7\nlocal")
    assert windows_path_units(source) > 240

    payload = json.dumps({"downloaded_file_path": str(source)})
    materialized = _materialize_external_artifacts(
        raw_model_response=payload,
        attachment_paths=[],
        downloaded_files=[],
        download_dir=download_dir,
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert len(materialized) == 1
    materialized_path = Path(materialized[0])
    assert materialized_path != source
    assert materialized_path.read_bytes() == b"%PDF-1.7\nlocal"
    assert windows_path_units(materialized_path) <= 240


def test_overbudget_local_download_candidate_is_compacted_before_return(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "browser-output"
    source = _create_overbudget_source(
        download_dir=download_dir,
        directory_prefix="nested-download-directory-",
    )
    source.write_bytes(b"%PDF-1.7\nlocal")
    assert windows_path_units(source) > 240

    selected = _resolve_downloaded_file(
        explicit_path=str(source),
        attachment_paths=[],
        browser_downloaded_files=[],
        download_dir=download_dir,
    )

    assert selected is not None
    assert selected != source
    assert selected.read_bytes() == b"%PDF-1.7\nlocal"
    assert windows_path_units(selected) <= 240


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


def test_structured_prefetch_isolates_same_basename_urls_and_reuses_identity_artifact(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    urls = {
        "https://publisher.example/2025/report.pdf": b"%PDF-1.7\nA",
        "https://publisher.example/2026/report.pdf": b"%PDF-1.7\nB",
    }
    calls: list[str] = []

    def fake_download(**kwargs) -> None:
        url = kwargs["pdf_url"]
        calls.append(url)
        Path(kwargs["destination_path"]).write_bytes(urls[url])

    external_boundary_mocks_only.setattr(
        http_runtime,
        "download_pdf_from_url",
        fake_download,
    )
    request = SimpleNamespace(settings=SimpleNamespace(timeout_seconds=5.0))

    def prefetch(url: str) -> Path:
        payload = json.dumps(
            {
                "route_kind": "pdf_download",
                "downloaded_file_name": "report.pdf",
                "downloaded_mime_type": "application/pdf",
                "resolved_target_url": url,
                "final_page_url": url,
            }
        )
        return Path(
            _prefetch_structured_pdf_artifact(
                request=request,
                ctx=run_context,
                normalized_url="https://publisher.example/report",
                download_dir=tmp_path,
                raw_model_response=payload,
                history_final_page_url=url,
            )
        )

    first = prefetch("https://publisher.example/2025/report.pdf")
    second = prefetch("https://publisher.example/2026/report.pdf")
    repeated = prefetch("https://publisher.example/2026/report.pdf")

    assert first != second
    assert repeated == second
    assert first.read_bytes() == urls["https://publisher.example/2025/report.pdf"]
    assert second.read_bytes() == urls["https://publisher.example/2026/report.pdf"]
    assert calls == [
        "https://publisher.example/2025/report.pdf",
        "https://publisher.example/2026/report.pdf",
    ]


def test_long_prefetch_names_keep_url_identity_without_second_hash(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    basename = ("same-long-report-name-" * 30) + ".pdf"
    urls = {
        f"https://publisher.example/2025/{basename}": b"%PDF-1.7\nA",
        f"https://publisher.example/2026/{basename}": b"%PDF-1.7\nB",
    }

    def fake_download(**kwargs) -> None:
        Path(kwargs["destination_path"]).write_bytes(urls[kwargs["pdf_url"]])

    external_boundary_mocks_only.setattr(
        http_runtime,
        "download_pdf_from_url",
        fake_download,
    )
    request = SimpleNamespace(settings=SimpleNamespace(timeout_seconds=5.0))

    def prefetch(url: str) -> Path:
        payload = json.dumps(
            {
                "route_kind": "pdf_download",
                "downloaded_file_name": basename,
                "downloaded_mime_type": "application/pdf",
                "resolved_target_url": url,
            }
        )
        return Path(
            _prefetch_structured_pdf_artifact(
                request=request,
                ctx=run_context,
                normalized_url="https://publisher.example/report",
                download_dir=tmp_path,
                raw_model_response=payload,
                history_final_page_url=url,
            )
        )

    first = prefetch(f"https://publisher.example/2025/{basename}")
    second = prefetch(f"https://publisher.example/2026/{basename}")

    assert first != second
    assert first.suffix == second.suffix == ".pdf"
    assert first.read_bytes() == b"%PDF-1.7\nA"
    assert second.read_bytes() == b"%PDF-1.7\nB"
    assert first == prefetch(f"https://publisher.example/2025/{basename}")
