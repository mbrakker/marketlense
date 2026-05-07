from __future__ import annotations

import asyncio

import json

import logging

from dataclasses import replace

from pathlib import Path

from types import SimpleNamespace

import pytest

from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageInspectionItem,
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryServiceRequest,
    PublisherInventorySettings,
)

from src.services import publisher_inventory_service as service

from src.utils.errors import AppError

class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        text: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")

    def close(self) -> None:
        return None

class _FakeBrowserPage:
    def __init__(
        self,
        browser: "_FakeBrowser",
        start_state: str,
        states: dict[str, dict[str, object]],
        *,
        target_id: str,
    ) -> None:
        self._browser = browser
        self._state_id = start_state
        self._states = states
        self._target_id = target_id

    def _payload(self) -> dict[str, object]:
        payload = dict(self._states[self._state_id]["payload"])
        payload.setdefault("anchors", [])
        payload.setdefault("load_more_labels", [])
        payload.setdefault("tab_labels", [])
        payload.setdefault("active_tab_label", "")
        payload.setdefault("report_link_url", "")
        payload.setdefault("empty_results_visible", False)
        payload.setdefault("reset_filter_labels", [])
        payload.setdefault("has_report_filter", False)
        payload.setdefault("has_apply_button", False)
        payload.setdefault("has_pagination_next", False)
        payload.setdefault("result_range_end", 0)
        payload.setdefault("result_range_total", 0)
        return payload

    async def evaluate(self, script: str, *args):
        script_name = str(self._states[self._state_id].get("script_name", ""))
        if script == service._browser_nested_scroll_probe_script():
            state = self._states[self._state_id]
            configured_payload = state.get("nested_scroll_probe_payload")
            next_state = state.get("nested_scroll_next_state")
            before_payload = self._payload()
            before_anchors = list(before_payload.get("anchors", []))
            if next_state:
                self._state_id = str(next_state)
            after_payload = self._payload()
            after_anchors = list(after_payload.get("anchors", []))
            if isinstance(configured_payload, dict):
                payload = dict(configured_payload)
            else:
                payload = {
                    "scrollSurface": (
                        "nested_container" if next_state else "document"
                    ),
                    "bestSurfaceLabel": (
                        "section.report-list:nth-scroll(1)"
                        if next_state
                        else "document"
                    ),
                    "probedSurfaceCount": 1 if next_state else 0,
                    "consumedSurfaceCount": 1 if next_state else 0,
                    "virtualizedListDetected": False,
                    "anchorCountBefore": len(before_anchors),
                    "anchorCountAfter": len(after_anchors),
                    "candidateGrowth": after_anchors != before_anchors,
                }
            payload.setdefault("pageUrl", str(after_payload.get("page_url") or ""))
            return json.dumps(payload)
        if "readyState" in script and "anchorCount" in script:
            payload = self._payload()
            return json.dumps(
                {
                    "readyState": "complete",
                    "title": str(payload.get("page_title") or ""),
                    "anchorCount": len(payload.get("anchors", [])),
                }
            )
        if "pageUrl" in script and "anchorCount" in script:
            payload = self._payload()
            return json.dumps(
                {
                    "pageUrl": str(payload.get("page_url") or ""),
                    "anchorCount": len(payload.get("anchors", [])),
                }
            )
        if script == service._browser_inventory_state_script():
            return json.dumps(self._payload())
        if script == service._browser_rendered_html_script():
            return str(self._states[self._state_id].get("rendered_html", ""))
        if script == service._browser_click_cookie_banner_script():
            next_state = self._states[self._state_id].get("cookie_banner_next_state")
            if next_state:
                self._state_id = str(next_state)
                return "true"
            return "false"
        if script == service._browser_click_archive_expander_script():
            next_state = self._states[self._state_id].get("archive_expander_next_state")
            if next_state:
                self._state_id = str(next_state)
                return "true"
            return "false"
        if script == service._browser_click_named_control_script():
            payload = args[0]
            if isinstance(payload, dict):
                labels = [
                    str(label).strip().lower() for label in payload.get("labels", [])
                ]
                candidate_urls = [
                    str(url).strip() for url in payload.get("candidate_urls", [])
                ]
                require_candidate_surface = bool(
                    payload.get("require_candidate_surface")
                )
            else:
                labels = [str(label).strip().lower() for label in payload]
                candidate_urls = []
                require_candidate_surface = False
            choices = self._states[self._state_id].get("named_click_choices", [])
            if isinstance(choices, list) and choices:
                matched_choices: list[dict[str, object]] = []
                for choice in choices:
                    assert isinstance(choice, dict)
                    label = str(choice.get("label", "")).strip().lower()
                    if not label:
                        continue
                    if any(
                        label == wanted or label.find(wanted) >= 0 for wanted in labels
                    ):
                        matched_choices.append(choice)
                if matched_choices:
                    if candidate_urls:
                        matched_choices.sort(
                            key=lambda choice: (
                                int(choice.get("candidate_hits", 0)),
                                int(choice.get("top", 0)),
                            ),
                            reverse=True,
                        )
                        min_relevant_hits = (
                            1
                            if len(candidate_urls) <= 4
                            else min(3, -(-len(candidate_urls) // 4))
                        )
                        if (
                            require_candidate_surface
                            and int(matched_choices[0].get("candidate_hits", 0))
                            < min_relevant_hits
                        ):
                            return "not_relevant"
                    self._state_id = str(matched_choices[0]["next_state"])
                    return "true"
            transitions = self._states[self._state_id].get("named_clicks", {})
            assert isinstance(transitions, dict)
            for label in labels:
                if label in transitions:
                    self._state_id = str(transitions[label])
                    return "true"
            return "false"
        if script == service._browser_click_pagination_next_script():
            next_state = self._states[self._state_id].get("pagination_next_state")
            if next_state:
                self._state_id = str(next_state)
                return "true"
            return "false"
        if script == service._browser_click_tab_script():
            target = str(args[0]).strip().lower()
            transitions = self._states[self._state_id].get("tab_clicks", {})
            assert isinstance(transitions, dict)
            if target in transitions:
                self._state_id = str(transitions[target])
                return "true"
            return "false"
        if script == service._browser_apply_report_filter_script():
            next_state = self._states[self._state_id].get("apply_filter_next_state")
            if next_state:
                self._state_id = str(next_state)
                return "true"
            return "false"
        if script == service._browser_scroll_to_ratio_script():
            next_state = self._states[self._state_id].get("scroll_next_state")
            if next_state and float(args[0]) > 0:
                self._state_id = str(next_state)
            return "true"
        raise AssertionError(f"Unexpected script: {script_name or script[:40]}")

    async def get_url(self) -> str:
        return str(self._payload()["page_url"])

    async def goto(self, url: str) -> None:
        normalized = (
            service._normalize_absolute_url(str(url).strip()) or str(url).strip()
        )
        for state_id, state in self._states.items():
            payload = state["payload"]
            assert isinstance(payload, dict)
            payload_url = service._normalize_absolute_url(
                str(payload.get("page_url"))
            ) or str(payload.get("page_url"))
            if payload_url == normalized:
                self._state_id = state_id
                return
        raise AssertionError(f"Unexpected goto url: {url}")

class _FakeAuxPage:
    def __init__(self, *, target_id: str, url: str) -> None:
        self._target_id = target_id
        self._url = url

    async def get_url(self) -> str:
        return self._url

class _FakeBrowser:
    last_instance: "_FakeBrowser | None" = None

    def __init__(
        self,
        downloads_path,
        headless,
        auto_download_pdfs,
        *,
        states: dict[str, dict[str, object]],
        start_state: str,
        extra_page_urls: list[str] | None = None,
    ):
        self.downloads_path = downloads_path
        self.headless = headless
        self.auto_download_pdfs = auto_download_pdfs
        self._states = states
        self._start_state = start_state
        self._started = False
        self.page: _FakeBrowserPage | None = None
        self.closed_page_ids: list[str] = []
        self._extra_pages = [
            _FakeAuxPage(target_id=f"aux-{index + 1}", url=url)
            for index, url in enumerate(extra_page_urls or [])
        ]
        _FakeBrowser.last_instance = self

    async def start(self) -> None:
        self._started = True

    async def new_page(self, url: str):
        assert self._started is True
        self.page = _FakeBrowserPage(
            self, self._start_state, self._states, target_id="main"
        )
        return self.page

    async def get_pages(self):
        pages: list[object] = []
        if self.page is not None:
            pages.append(self.page)
        pages.extend(self._extra_pages)
        return pages

    async def close_page(self, page) -> None:
        target_id = str(getattr(page, "_target_id", "") or "")
        self.closed_page_ids.append(target_id)
        self._extra_pages = [
            candidate
            for candidate in self._extra_pages
            if str(getattr(candidate, "_target_id", "") or "") != target_id
        ]

    async def kill(self) -> None:
        return None

def _runtime_for_states(
    states: dict[str, dict[str, object]],
    start_state: str = "initial",
    *,
    extra_page_urls: list[str] | None = None,
) -> SimpleNamespace:
    class RuntimeBrowser(_FakeBrowser):
        def __init__(self, downloads_path, headless, auto_download_pdfs):
            super().__init__(
                downloads_path,
                headless,
                auto_download_pdfs,
                states=states,
                start_state=start_state,
                extra_page_urls=extra_page_urls,
            )

    return SimpleNamespace(Browser=RuntimeBrowser)

async def _fast_sleep(_seconds: float) -> None:
    return None

def _settings(tmp_path: Path) -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir=str(tmp_path / "publisher_inventory_discovery"),
        reports_db=str(tmp_path / "reports.sqlite"),
        google_sa_path=str(tmp_path / "sa.json"),
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=5,
        http_timeout_seconds=10.0,
        openrouter_http_referer="https://marketlense.local",
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.1,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )

def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows

__all__ = [name for name in globals() if name not in {'__name__', '__annotations__', '__doc__', '__spec__', '__file__', '__package__', '__loader__', '__cached__', '__builtins__'}]

