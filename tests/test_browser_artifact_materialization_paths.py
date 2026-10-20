from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.services._browser_report_download._artifact.pdf import (
    _adopt_external_downloaded_file,
)
from src.services._browser_report_download._browser_runtime._terminal_assets.artifacts import (
    _copy_external_artifact,
    _prefetch_structured_pdf_artifact,
    _pdf_prefetch_destination_path,
)
from src.services._browser_report_download import http as http_runtime
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
