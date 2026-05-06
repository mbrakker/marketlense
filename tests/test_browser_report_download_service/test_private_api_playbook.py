from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .builders import (
    _FakeResponse,
    _runtime,
    _settings,
    browser_runtime,
    http_runtime,
    service,
)
from src.contracts.browser_download import BrowserReportDownloadRequest


def test_private_api_playbook_downloads_pdf_before_full_agent(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    playbook_dir = _write_private_api_playbook(tmp_path)
    page_url = "https://example.com/research/report-2026"
    api_url = "https://example.com/api/reports/report-2026"
    pdf_url = "https://example.com/asset/report-2026.pdf"

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == api_url:
            return _FakeResponse(
                content=json.dumps(
                    {"asset": {"pdfUrl": "/asset/report-2026.pdf"}}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                url=api_url,
            )
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 private api pdf",
                headers={"Content-Type": "application/pdf"},
                url=pdf_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Report landing page</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("full browser-use agent should not load")
        ),
    )
    caplog.set_level(logging.INFO)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=replace(
                _settings(tmp_path),
                route_playbook_dir=str(playbook_dir),
            ),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.route_family == "private_api_playbook_pdf_probe"
    assert response.outcome == "downloaded"
    assert response.route_steps[0].action == "http_private_api"
    assert response.route_steps[0].verification_status == "verified"
    assert Path(response.downloaded_file_path).read_bytes().startswith(b"%PDF-")
    assert "private_api_playbook" in response.terminal_evidence.evidence_labels
    events = [json.loads(record.message) for record in caplog.records]
    complete_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_private_api_playbook_complete"
    ]
    assert complete_events
    fields = complete_events[-1]["fields"]
    assert fields["playbook_id"] == "private-api-example"
    assert fields["validation_result"] == "verified"


def test_stale_private_api_playbook_falls_back_to_normal_browser_route(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    playbook_dir = _write_private_api_playbook(tmp_path)
    page_url = "https://example.com/research/report-2026"
    api_url = "https://example.com/api/reports/report-2026"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == api_url:
            return _FakeResponse(
                content=b'{"error":"gone"}',
                status_code=404,
                headers={"Content-Type": "application/json"},
                url=api_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Report landing page</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        load_agent_runtime,
    )
    caplog.set_level(logging.INFO)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=replace(
                _settings(tmp_path),
                route_playbook_dir=str(playbook_dir),
            ),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert full_agent_loaded["value"] is True
    assert response.outcome == "downloaded"
    events = [json.loads(record.message) for record in caplog.records]
    fallback_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_private_api_playbook_fallback"
    ]
    assert fallback_events
    assert fallback_events[-1]["fields"]["validation_result"] == "status_rejected"
    assert fallback_events[-1]["fields"]["fallback_reason"] == (
        "unexpected_private_api_status"
    )


def _write_private_api_playbook(tmp_path: Path) -> Path:
    playbook_dir = tmp_path / "playbooks"
    private_api_dir = playbook_dir / "private_api"
    private_api_dir.mkdir(parents=True)
    (private_api_dir / "private-api-example.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "playbook_id": "private-api-example",
                "version": "1.0.0",
                "status": "active",
                "updated_at": "2026-05-06T00:00:00+00:00",
                "stale_after_days": 120,
                "publisher_pattern": "Example",
                "host_patterns": ["example.com"],
                "url_path_markers": ["research", "report"],
                "route_family": "browser_pdf_click",
                "route_kind": "pdf_download",
                "summary": "Use the learned report metadata endpoint.",
                "steps": [
                    {
                        "schema_version": "1.0",
                        "action": "http_private_api",
                        "target": "/api/reports/{last_path_segment}",
                        "verification": "validated PDF artifact",
                    }
                ],
                "private_api_evidence": [
                    {
                        "schema_version": "1.0",
                        "evidence_id": "example-report-metadata",
                        "endpoint_pattern": "/api/reports/{last_path_segment}",
                        "method": "GET",
                        "request_shape_summary": (
                            "GET with report slug path parameter; no auth headers."
                        ),
                        "response_pdf_url_json_pointer": "/asset/pdfUrl",
                        "expected_status_codes": [200],
                        "required_response_markers": ["pdfUrl"],
                        "success_count": 2,
                        "fallback_route_family": "browser_pdf_click",
                    }
                ],
                "traps": ["Fallback when endpoint status or response shape drifts."],
                "evidence_notes": [
                    "Promoted after repeated validated network evidence."
                ],
                "source_evidence": ["browser_network_private_api"],
                "history": [
                    {
                        "schema_version": "1.0",
                        "changed_at": "2026-05-06T00:00:00+00:00",
                        "source": "test_seed",
                        "summary": "Seeded private API test playbook.",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return playbook_dir
