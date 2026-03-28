from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services.browser_report_download_service import (
    download_report_with_browser_use,
)


class _DownloadFixtureHandler(BaseHTTPRequestHandler):
    fixture_root: Path = Path(".")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            body = (
                "<html><body>"
                "<h1>Report download</h1>"
                '<a href="/report.pdf" download>Download report PDF</a>'
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/report.pdf":
            payload = (self.fixture_root / "report.pdf").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="integration-run",
        task_id="integration-task",
        span_id="integration-span",
    )


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.browser_report_download_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


@pytest.mark.integration
def test_browser_report_download_service_local_guarded(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    if os.getenv("RUN_BROWSER_DOWNLOAD_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_BROWSER_DOWNLOAD_INTEGRATION=1 to run the local browser-use integration."
        )
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is required.")
    try:
        __import__("browser_use")
    except Exception:
        pytest.skip("browser_use is not installed in this environment.")

    fixture_root = tmp_path / "site"
    fixture_root.mkdir(parents=True, exist_ok=True)
    (fixture_root / "report.pdf").write_bytes(b"%PDF-1.7 integration")
    _DownloadFixtureHandler.fixture_root = fixture_root

    server = HTTPServer(("127.0.0.1", 0), _DownloadFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    caplog.set_level(
        logging.INFO, logger="market_lense.browser_report_download_service"
    )
    try:
        settings = BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key=api_key,
            model=os.getenv("BROWSER_DOWNLOAD_MODEL", "openai/gpt-5-mini"),
            temperature=0.0,
            timeout_seconds=60.0,
            max_steps=10,
            output_dir=str(tmp_path / "downloads"),
            state_db=str(tmp_path / "state.sqlite"),
            reports_db=str(tmp_path / "reports.sqlite"),
            identity_config_path=str(tmp_path / "browser_download_identity.yaml"),
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="work_email",
                        label="Work email",
                        value="ops@example.com",
                        aliases=["email"],
                    )
                ],
            ),
            openrouter_http_referer=os.getenv("OPENROUTER_HTTP_REFERER"),
            headed=False,
            retry_retries=0,
            retry_base_delay_seconds=0.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
        )
        url = f"http://127.0.0.1:{server.server_port}/"
        response = download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url=url,
                settings=settings,
            ),
            _ctx(),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert_logs_have_required_fields(_events(caplog))
