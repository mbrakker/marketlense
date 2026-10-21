# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

from src.services._browser_report_download._artifact.onsite import (
    _resolve_onsite_capture_path,
)
from src.services._browser_report_download.artifact_paths import windows_path_units

from ._shared import *  # noqa: F401,F403


def test_download_report_with_browser_use_recovers_html_pdf_without_clobbering_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent
    source_html = (
        "<html><body><article><h1>Research report</h1><p>"
        + ("Research analysis and report findings. " * 80)
        + "</p></article></body></html>"
    ).encode("utf-8")
    existing_html = b"<html><body>different existing capture</body></html>"

    class MisclassifiedHtmlAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            download_dir = Path(self.browser.downloads_path)
            downloaded_path = download_dir / "report.pdf"
            occupied_capture_path = download_dir / "report.html"
            downloaded_path.write_bytes(source_html)
            occupied_capture_path.write_bytes(existing_html)
            self.browser.downloaded_files = [str(downloaded_path)]
            self.browser.url = "https://example.com/research/report"
            self.browser.title = "Research report"
            self.browser.html = source_html.decode("utf-8")
            payload = json.loads(history.final_result())
            payload.update(
                {
                    "route_kind": "pdf_download",
                    "route_family": "browser_onsite_report",
                    "final_page_url": self.browser.url,
                    "downloaded_file_path": str(downloaded_path),
                    "downloaded_file_name": downloaded_path.name,
                    "downloaded_mime_type": "application/pdf",
                }
            )

            class MisclassifiedHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return MisclassifiedHistory()

    runtime.Agent = MisclassifiedHtmlAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    capture_path = Path(response.onsite_capture_path)
    downloaded_path = capture_path.parent / "report.pdf"
    occupied_capture_path = capture_path.parent / "report.html"
    assert capture_path.suffix == ".html"
    assert capture_path.read_bytes() == source_html
    assert downloaded_path.read_bytes() == source_html
    assert occupied_capture_path.read_bytes() == existing_html
    assert capture_path.parent == downloaded_path.parent
    assert windows_path_units(capture_path) <= 240

    replayed_path = _resolve_onsite_capture_path(downloaded_path)
    assert replayed_path == capture_path
    assert len(list(capture_path.parent.glob("report*.html"))) == 2


__all__ = [
    "test_download_report_with_browser_use_recovers_html_pdf_without_clobbering_capture",
]
