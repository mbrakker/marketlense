# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
import fitz

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookExecutionRequest,
    BrowserRoutePlaybookStep,
    BrowserRoutePrivateApiPromotionRequest,
    DownloadTerminalEvidence,
)
from src.services import browser_report_download_service
from src.services._browser_report_download._browser_runtime.action_evidence import (
    capture_browser_execution_route_steps,
)
from src.services._browser_report_download.playbooks import (
    execute_browser_route_playbook,
    execute_browser_route_playbook_async,
    load_browser_route_playbooks,
    promote_private_api_evidence_to_browser_playbook,
    promote_validated_browser_route_result_to_playbook,
)
from src.services._browser_report_download.browser import (
    _DeterministicPlaybookPageDriver,
)
from src.services._browser_report_download.prompt import (
    render_browser_report_download_prompt,
)
from src.utils.browser_route_playbooks import select_browser_route_playbooks
from src.utils.errors import AppError


class _FakePageDriver:
    def __init__(self, *, texts):
        self.calls = []
        self._url = ""
        self._texts = set(texts)

    def open(self, url):
        self.calls.append(("open", url))
        self._url = url
        return url

    def click_css(self, selector):
        self.calls.append(("click_css", selector))
        return selector

    def click_text(self, text):
        self.calls.append(("click_text", text))
        return text

    def click_role(self, role, name):
        self.calls.append(("click_role", role, name))
        return name

    def click_label(self, label):
        self.calls.append(("click_label", label))
        return label

    def click_name(self, name):
        self.calls.append(("click_name", name))
        return name

    def click_data_attribute(self, selector):
        self.calls.append(("click_data_attribute", selector))
        return selector

    def fill_css(self, selector, value):
        self.calls.append(("fill_css", selector, value))
        return selector

    def fill_label(self, label, value):
        self.calls.append(("fill_label", label, value))
        return label

    def fill_name(self, name, value):
        self.calls.append(("fill_name", name, value))
        return name

    def fill_data_attribute(self, selector, value):
        self.calls.append(("fill_data_attribute", selector, value))
        return selector

    def select_css(self, selector, value):
        self.calls.append(("select_css", selector, value))
        return selector

    def select_label(self, label, value):
        self.calls.append(("select_label", label, value))
        return label

    def select_name(self, name, value):
        self.calls.append(("select_name", name, value))
        return name

    def select_data_attribute(self, selector, value):
        self.calls.append(("select_data_attribute", selector, value))
        return selector

    def current_url(self):
        return self._url

    def contains_text(self, text):
        return text in self._texts


class _AsyncRoleFormPageDriver:
    def __init__(self, *, texts: set[str]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._texts = texts
        self._url = "https://example.com/request"

    async def fill_role(self, role: str, name: str, value: str) -> str:
        self.calls.append(("fill_role", role, name, value))
        return "filled"

    async def select_role(self, role: str, name: str, value: str) -> str:
        self.calls.append(("select_role", role, name, value))
        return "selected"

    async def click_role(self, role: str, name: str) -> str:
        self.calls.append(("click_role", role, name))
        self._url = "https://example.com/requested"
        return "clicked"

    async def current_url(self) -> str:
        return self._url

    async def contains_text(self, text: str) -> bool:
        return text in self._texts


def _runtime_history_entry(
    *,
    action: dict[str, object],
    role: str,
    name: str,
    url: str,
    title: str,
    node_name: str,
    attributes: dict[str, str],
) -> SimpleNamespace:
    return SimpleNamespace(
        model_output=SimpleNamespace(
            action=[SimpleNamespace(model_dump=lambda **_kwargs: action)]
        ),
        result=[SimpleNamespace(error=None, success=True)],
        state=SimpleNamespace(
            url=url,
            title=title,
            interacted_element=[
                SimpleNamespace(
                    attributes=attributes,
                    ax_name=name,
                    node_name=node_name,
                )
            ],
        ),
    )


def _request(
    tmp_path: Path,
    *,
    route_playbook_dir: str,
    route_playbook_stale_policy: str = "fallback",
) -> BrowserReportDownloadRequest:
    return BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/research/report",
        settings=BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="openai/gpt-5-mini",
            temperature=0.0,
            timeout_seconds=30.0,
            max_steps=5,
            output_dir=str(tmp_path / "downloads"),
            state_db=str(tmp_path / "state.sqlite"),
            reports_db=str(tmp_path / "reports.sqlite"),
            identity_config_path=str(tmp_path / "identity.yaml"),
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[],
                delivery_emails=[],
            ),
            route_playbook_dir=route_playbook_dir,
            route_playbook_stale_policy=route_playbook_stale_policy,
        ),
        route_family_hint="browser_pdf_click",
    )


def _result(*, route_status: str) -> BrowserReportDownloadResult:
    execution_step = BrowserDownloadRouteStep(
        schema_version="1.0",
        index=0,
        action="click_cta",
        target_text="Download report",
        target_role="button",
        target_url="https://example.com/report.pdf",
        result="opened",
        expected_evidence=["browser_execution"],
        observed_evidence=["browser_execution"],
        verification_status="verified",
        locator_role="button",
        locator_name="Download report",
        expected_url_contains="/report.pdf",
        locator_evidence=["locator:role:button:Download report"],
        postcondition_evidence=["url:/report.pdf"],
    )
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url="https://example.com/research/report",
        normalized_url="https://example.com/research/report",
        route_kind="pdf_download",
        route_family="browser_pdf_click",
        route_status=route_status,
        outcome="downloaded",
        route_summary="Open the report page and use the Download report CTA.",
        final_page_url="https://example.com/research/report",
        resolved_target_url="https://example.com/report.pdf",
        used_route_hint=False,
        route_steps=[execution_step],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="",
            submit_button_state="",
            form_disappeared=False,
            final_page_url="https://example.com/research/report",
            confirmation_score=1,
            signal_labels=["artifact"],
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/research/report",
            final_page_title="Report",
            terminal_text_excerpt="Report",
            artifact_url="https://example.com/report.pdf",
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="local PDF",
            confirmation_signal_count=1,
            evidence_labels=["downloaded_file_path"],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        downloaded_file_path="C:/tmp/report.pdf",
        downloaded_file_name="report.pdf",
        downloaded_mime_type="application/pdf",
        downloaded_size_bytes=1234,
        execution_route_steps=[execution_step],
    )


def _write_playbook(
    path: Path,
    *,
    playbook_id: str,
    updated_at: str,
    stale_after_days: int = 120,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "playbook_id": playbook_id,
                "version": "1.0.0",
                "status": "active",
                "updated_at": updated_at,
                "stale_after_days": stale_after_days,
                "publisher_pattern": "Example",
                "host_patterns": ["example.com"],
                "url_path_markers": ["research", "report"],
                "route_family": "browser_pdf_click",
                "route_kind": "pdf_download",
                "summary": "Use the download CTA.",
                "steps": [
                    {
                        "schema_version": "1.0",
                        "action": "click_cta",
                        "target": "Download report",
                        "verification": "local PDF",
                    }
                ],
                "traps": ["Avoid unrelated navigation."],
                "evidence_notes": ["Seeded test evidence."],
                "source_evidence": ["test"],
                "history": [
                    {
                        "schema_version": "1.0",
                        "changed_at": updated_at,
                        "source": "test_seed",
                        "summary": "Seeded test playbook.",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _service_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != browser_report_download_service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
