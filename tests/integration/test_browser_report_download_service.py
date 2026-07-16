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
from src.contracts.logging import MAX_LOG_EVENT_BYTES
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
                '<button type="button" onclick="window.location.href=\'/deliver\'">'
                "Download report PDF"
                "</button>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/deliver":
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
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openai_api_key and not openrouter_api_key:
        pytest.skip("OPENAI_API_KEY or OPENROUTER_API_KEY is required.")
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
            openrouter_api_key=openrouter_api_key,
            model=os.getenv("BROWSER_DOWNLOAD_MODEL", "gpt-5-mini"),
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
            openai_api_key=openai_api_key,
            openrouter_model=os.getenv(
                "BROWSER_DOWNLOAD_OPENROUTER_MODEL", "openai/gpt-5-mini"
            ),
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
                route_family_hint="browser_pdf_click",
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
    events = _events(caplog)
    assert any(event["event"] == "browser_report_download_start" for event in events)
    completion = next(
        event
        for event in events
        if event["event"] == "browser_report_download_complete"
    )
    completion_serialized = json.dumps(completion, ensure_ascii=True)
    assert len(completion_serialized.encode("utf-8")) <= MAX_LOG_EVENT_BYTES
    assert "ops@example.com" not in completion_serialized
    assert "terminal_text_excerpt" not in completion["fields"]
    assert "encountered_form_fields" not in completion["fields"]
    assert {
        "outcome",
        "route_kind",
        "route_family",
        "route_status",
        "normalized_url_sha256",
        "final_host",
        "artifact_identity",
        "artifact_sha256",
        "artifact_size_bytes",
        "route_step_count",
        "confirmation_score",
        "blocker_code",
        "html_snapshot_audit_ref",
        "screenshot_audit_ref",
    }.issubset(completion["fields"])
    assert completion["fields"]["artifact_sha256"]
    assert "log_collection_reduced" not in completion["fields"]
    assert_logs_have_required_fields(events)
