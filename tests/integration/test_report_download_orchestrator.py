from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSettings,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators.report_download_orchestrator import run_report_download


class _OrchestratorDownloadFixtureHandler(BaseHTTPRequestHandler):
    fixture_root: Path = Path(".")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            body = (
                "<html><body>"
                "<h1>Market research report</h1>"
                '<button type="button" onclick="window.location.href=\'/deliver\'">'
                "Download report"
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
        run_id="orchestrator-integration-run",
        task_id="orchestrator-integration-task",
        span_id="orchestrator-integration-span",
    )


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.report_download_orchestrator":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


@pytest.mark.integration
def test_report_download_orchestrator_local_browser_route_guarded(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    if os.getenv("RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION") != "1":
        pytest.skip(
            "Set RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION=1 to run the "
            "live local orchestration integration."
        )
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openai_api_key and not openrouter_api_key:
        pytest.skip("OPENAI_API_KEY or OPENROUTER_API_KEY is required.")

    fixture_root = tmp_path / "site"
    fixture_root.mkdir(parents=True, exist_ok=True)
    (fixture_root / "report.pdf").write_bytes(b"%PDF-1.7 orchestrator integration")
    identity_path = tmp_path / "browser_download_identity.yaml"
    identity_path.write_text(
        "\n".join(
            [
                "schema_version: '1.0'",
                "fields:",
                "- schema_version: '1.0'",
                "  key: work_email",
                "  label: Work email",
                "  value: ops@example.com",
                "  aliases:",
                "  - email",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _OrchestratorDownloadFixtureHandler.fixture_root = fixture_root

    server = ThreadingHTTPServer(("127.0.0.1", 0), _OrchestratorDownloadFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")
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
            identity_config_path=str(identity_path),
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
            drive_upload_enabled=False,
            drive_upload_required=False,
        )
        url = f"http://127.0.0.1:{server.server_port}/"
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=_ctx(),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(response.downloaded_file_path).exists()
    assert response.drive_uploads == []

    with sqlite3.connect(settings.reports_db) as connection:
        route_history_count = connection.execute(
            "SELECT COUNT(*) FROM publisher_download_route_history"
        ).fetchone()[0]
        source_count = connection.execute(
            "SELECT COUNT(*) FROM report_sources"
        ).fetchone()[0]
    assert route_history_count >= 1
    assert source_count >= 1

    events = _events(caplog)
    assert any(event["event"] == "report_download_start" for event in events)
    assert any(event["event"] == "report_download_complete" for event in events)
    assert_logs_have_required_fields(events)
