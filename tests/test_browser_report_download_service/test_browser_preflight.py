from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .builders import (
    _FakeResponse,
    _runtime,
    _settings,
    browser_runtime,
    http_runtime,
    service,
)
from src.contracts.browser_download import (
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download import preflight as preflight_runtime


class _PreflightPage:
    def __init__(self, *, pdf_url: str | None, page_url: str) -> None:
        self.url = page_url
        self._pdf_url = pdf_url

    def title(self) -> str:
        return "Rendered publisher report"

    def content(self) -> str:
        if not self._pdf_url:
            return "<html><body><h1>Rendered publisher report</h1></body></html>"
        return (
            "<html><body><h1>Rendered publisher report</h1>"
            f'<a id="download" href="{self._pdf_url}">Download PDF</a>'
            "</body></html>"
        )

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        return None

    def evaluate(self, script: str) -> object:
        if "getEntriesByType" in script:
            return [self._pdf_url] if self._pdf_url else []
        return {
            "pdf_candidates": [self._pdf_url] if self._pdf_url else [],
            "form_text": [],
            "location_href": self.url,
            "title": "Rendered publisher report",
            "html_size": len(self.content()),
        }


class _PreflightBrowser:
    def __init__(
        self,
        *,
        downloads_path: str,
        headless: bool,
        auto_download_pdfs: bool,
        keep_alive: bool,
        pdf_url: str | None,
    ) -> None:
        self.downloads_path = downloads_path
        self.headless = headless
        self.auto_download_pdfs = auto_download_pdfs
        self.keep_alive = keep_alive
        self.pdf_url = pdf_url
        self.url = ""
        self.title = ""
        self.stopped = False

    def start(self) -> None:
        return None

    def navigate_to(self, url: str) -> None:
        self.url = url
        self.title = "Rendered publisher report"

    def get_current_page(self) -> _PreflightPage:
        return _PreflightPage(pdf_url=self.pdf_url, page_url=self.url)

    def kill(self) -> None:
        self.stopped = True


def _preflight_runtime(*, pdf_url: str | None):
    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs):
            super().__init__(pdf_url=pdf_url, **kwargs)

    return SimpleNamespace(Browser=Browser)


def test_browser_preflight_contract_round_trip() -> None:
    probe = BrowserPreflightProbeResult(
        schema_version="1.0",
        status="confirmed_direct_pdf",
        started_url="https://example.com/report",
        final_url="https://example.com/report",
        final_title="Example report",
        html_size=250,
        event_drain_seconds=0.35,
        duration_seconds=1.25,
        candidate_pdf_urls=["https://example.com/report.pdf"],
        selected_pdf_url="https://example.com/report.pdf",
        observed_event_urls=["https://example.com/report.pdf"],
        network_event_count=1,
        evidence_labels=["page_info", "js_rendered_dom", "network_event"],
        escalation_reason="",
        avoided_agent_call=True,
        false_negative_rate_sample=0.0,
    )
    response = BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)

    restored_probe = BrowserPreflightProbeResult(**asdict(probe))
    restored_response = BrowserPreflightProbeResponse(
        schema_version=response.schema_version,
        probe=BrowserPreflightProbeResult(**asdict(response.probe)),
    )

    assert restored_probe == probe
    assert restored_response == response
    assert restored_probe.status == "confirmed_direct_pdf"
    assert restored_probe.selected_pdf_url.endswith(".pdf")
    assert restored_probe.evidence_labels
    assert restored_response.probe.avoided_agent_call is True


def test_browser_preflight_confirms_js_rendered_pdf_without_full_agent(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://example.com/rendered-report"
    pdf_url = "https://example.com/assets/rendered-report.pdf"

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 rendered pdf",
                headers={"Content-Type": "application/pdf"},
                url=pdf_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Rendered publisher report</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=pdf_url),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("full browser-use agent should not load after preflight")
        ),
    )
    caplog.set_level(logging.INFO, logger=preflight_runtime.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.route_family == "browser_preflight_js_pdf_probe"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(response.downloaded_file_path).read_bytes().startswith(b"%PDF-")
    assert response.route_steps[1].target_url == pdf_url
    assert response.route_steps[1].verification_status == "verified"
    assert (
        "browser_preflight_js_pdf_probe" in response.terminal_evidence.evidence_labels
    )
    assert_no_defaulted_required_fields(response)
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == preflight_runtime.logger.name
    ]
    complete_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_complete"
    ]
    assert complete_events
    fields = complete_events[-1]["fields"]
    assert fields["status"] == "confirmed_direct_pdf"
    assert fields["avoided_agent_call"] is True
    assert fields["preflight_duration_seconds"] >= 0


def test_browser_preflight_escalates_cleanly_when_evidence_is_insufficient(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/report-with-hidden-route"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body><h1>Report with hidden route</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=None),
    )
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
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert full_agent_loaded["value"] is True
    assert response.outcome == "downloaded"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    outcome_events = [
        event
        for event in events
        if event.get("event")
        == "browser_report_download_browser_preflight_agent_outcome"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["escalation_reason"] == (
        "no_rendered_pdf_candidate"
    )
    assert outcome_events
    assert outcome_events[-1]["fields"]["false_negative_rate_sample"] == 1.0


def test_browser_preflight_rejects_rendered_legal_pdf_candidate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/guides-whitepapers/marketing-success-metrics"
    legal_pdf_url = "https://example.com/legal/MARMIND_Online_Terms_and_DPA.pdf"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Escalated past unrelated legal PDF and used the full route.",
        create_pdf=True,
        email_submission_completed=None,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == legal_pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 legal terms dpa",
                headers={"Content-Type": "application/pdf"},
                url=legal_pdf_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Marketing Success Metrics</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=legal_pdf_url),
    )
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
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert full_agent_loaded["value"] is True
    assert response.outcome == "downloaded"
    assert response.route_family != "browser_preflight_js_pdf_probe"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["escalation_reason"] == (
        "no_rendered_pdf_candidate"
    )


def test_browser_preflight_rejects_title_mismatched_pdf_candidate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/insights/food-and-drink/global-food-and-drink-trends"
    unrelated_pdf_url = "https://assets.example.com/Mintel_Gender_Pay_Gap_Report_2025.pdf"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Escalated past unrelated rendered PDF and used the full route.",
        create_pdf=True,
        email_submission_completed=None,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == unrelated_pdf_url:
            raise AssertionError("title-mismatched PDF must not be downloaded")
        return _FakeResponse(
            content=(
                b"<html><body><h1>2026 Global Food & Drink Predictions</h1></body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=unrelated_pdf_url),
    )
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
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            report_title="2026 Global Food & Drink Predictions",
        ),
        run_context,
    )

    assert full_agent_loaded["value"] is True
    assert response.outcome == "downloaded"
    assert response.route_family != "browser_preflight_js_pdf_probe"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["candidate_pdf_url_count"] == 0
