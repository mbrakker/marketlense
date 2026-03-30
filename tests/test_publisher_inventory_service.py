from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.publisher_inventory import (
    PublisherInventoryServiceRequest,
    PublisherInventorySettings,
)
from src.services import publisher_inventory_service as service
from src.utils.errors import AppError


class _FakeResponse:
    def __init__(self, *, url: str, text: str, status_code: int = 200) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


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
        if "readyState" in script and "anchorCount" in script:
            payload = self._payload()
            return json.dumps(
                {
                    "readyState": "complete",
                    "title": str(payload.get("page_title") or ""),
                    "anchorCount": len(payload.get("anchors", [])),
                }
            )
        if script == service._browser_inventory_state_script():
            return json.dumps(self._payload())
        if script == service._browser_rendered_html_script():
            return str(self._states[self._state_id].get("rendered_html", ""))
        if script == service._browser_click_named_control_script():
            payload = args[0]
            if isinstance(payload, dict):
                labels = [str(label).strip().lower() for label in payload.get("labels", [])]
                candidate_urls = [str(url).strip() for url in payload.get("candidate_urls", [])]
                require_candidate_surface = bool(payload.get("require_candidate_surface"))
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
                    if any(label == wanted or label.find(wanted) >= 0 for wanted in labels):
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
                        min_relevant_hits = 1 if len(candidate_urls) <= 4 else min(3, -(-len(candidate_urls) // 4))
                        if (
                            require_candidate_surface
                            and int(matched_choices[0].get("candidate_hits", 0)) < min_relevant_hits
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
        normalized = service._normalize_absolute_url(str(url).strip()) or str(url).strip()
        for state_id, state in self._states.items():
            payload = state["payload"]
            assert isinstance(payload, dict)
            payload_url = service._normalize_absolute_url(str(payload.get("page_url"))) or str(payload.get("page_url"))
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
        self.page = _FakeBrowserPage(self, self._start_state, self._states, target_id="main")
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


def test_discover_publisher_inventory_http_parse_handles_multipage(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    html_page_1 = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
      <a href="/insights?page=2" rel="next">Next</a>
    </body></html>
    """
    html_page_2 = """
    <html><body>
      <a href="/reports/report-two">Report Two 2026</a>
    </body></html>
    """

    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("MarketLensePublisherInventory/")
        if url.endswith("page=2"):
            return _FakeResponse(
                url="https://example.com/insights?page=2",
                text=html_page_2,
            )
        return _FakeResponse(url="https://example.com/insights", text=html_page_1)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.used_route_hint is False
    assert len(response.pages) == 2
    assert len(response.candidates) == 2
    assert response.candidates[1].discovered_on_page_number == 2
    assert response.candidates[1].source_page_url == "https://example.com/insights?page=2"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_events(caplog))


def test_discover_publisher_inventory_direct_pdf_source_short_circuits_browser(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _unexpected_runtime(_name: str):
        raise AssertionError("browser runtime should not be loaded for direct PDF sources")

    external_boundary_mocks_only.setattr(service, "import_module", _unexpected_runtime)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/reports/state-of-retail-2026.pdf",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/state-of-retail-2026.pdf"
    ]
    assert response.candidates[0].pdf_url == "https://example.com/reports/state-of-retail-2026.pdf"


def test_discover_publisher_inventory_browser_fallback_when_http_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://example.com/reports/report-one", "text": "Report One 2026", "rel": ""}
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://example.com/reports/report-one", "text": "Report One 2026", "rel": ""},
                    {"href": "https://example.com/reports/report-two", "text": "Report Two 2026", "rel": ""},
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_hint="Click the next pagination control after scanning page one.",
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert response.used_route_hint is True
    assert len(response.pages) == 2
    assert any(
        candidate.url == "https://example.com/reports/report-two"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )
    assert_no_defaulted_required_fields(response)


def test_discover_publisher_inventory_browser_closes_stray_blank_pages(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://example.com/reports/report-one", "text": "Report One 2026", "rel": ""}
                ],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service,
        "import_module",
        lambda _name: _runtime_for_states(
            states,
            extra_page_urls=["about:blank", "chrome://newtab"],
        ),
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert _FakeBrowser.last_instance is not None
    assert _FakeBrowser.last_instance.closed_page_ids == ["aux-1", "aux-2"]


def test_discover_publisher_inventory_browser_scrolls_to_hydrate_load_more(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bain.com/insights?filters=|types(424%2C420)",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://www.bain.com/insights/books", "text": "Bain Books", "rel": ""}
                ],
            },
            "scroll_next_state": "scrolled",
        },
        "scrolled": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.bain.com/insights/asia-pacific-private-equity-report-2026",
                        "text": "Asia-Pacific Private Equity Report 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.bain.com/insights/asia-pacific-private-equity-report-2026",
                        "text": "Asia-Pacific Private Equity Report 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://www.bain.com/insights/private-equitys-reality-check-gp-outlook-2026",
                        "text": "Private Equity's Reality Check: The GP Outlook for 2026",
                        "rel": "",
                    },
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bain.com/insights?filters=|types(424%2C420)",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert any(
        candidate.url == "https://www.bain.com/insights/private-equitys-reality-check-gp-outlook-2026"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_prefers_candidate_dense_load_more_surface(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.algolia.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-understanding-ai-transparency",
                        "text": "Understanding AI transparency",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/the-roi-of-relevance-algolia-shopify",
                        "text": "The ROI of Relevance: Algolia + Shopify",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Show more results", "Show More"],
            },
            "named_click_choices": [
                {"label": "show more results", "next_state": "wrong_surface", "candidate_hits": 1, "top": 1100},
                {"label": "show more", "next_state": "page_2", "candidate_hits": 6, "top": 900},
            ],
        },
        "wrong_surface": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/products/ai-search",
                        "text": "AI Search",
                        "rel": "",
                    }
                ],
            }
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-understanding-ai-transparency",
                        "text": "Understanding AI transparency",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/the-roi-of-relevance-algolia-shopify",
                        "text": "The ROI of Relevance: Algolia + Shopify",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-why-agentic-ai-is-your-next-priority",
                        "text": "Why agentic AI is your next priority ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-retail-media-trends-2026",
                        "text": "Retail media trends 2026 ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-black-friday-data-playbook",
                        "text": "Black Friday data playbook ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-b2c-ecommerce-ai-trends-2026",
                        "text": "2026 B2C ecommerce AI trends ebook",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Show more results"],
            },
            "named_click_choices": [
                {"label": "show more results", "next_state": "wrong_surface", "candidate_hits": 1, "top": 1200}
            ],
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.algolia.com/resources?reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert any(
        candidate.url == "https://www.algolia.com/resources/asset/ebook-why-agentic-ai-is-your-next-priority"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )


def test_discover_publisher_inventory_browser_resets_empty_results_filters(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.contentful.com/resources/",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.contentful.com/resources/",
                "page_title": "Resources | Contentful",
                "anchors": [
                    {
                        "href": "https://www.contentful.com/resources/the-great-content-collapse/",
                        "text": "The Great Content Collapse",
                        "rel": "",
                    }
                ],
                "empty_results_visible": True,
                "reset_filter_labels": ["Reset all filters"],
            },
            "named_clicks": {"reset all filters": "listing"},
        },
        "listing": {
            "payload": {
                "page_url": "https://www.contentful.com/resources/",
                "page_title": "Resources | Contentful",
                "anchors": [
                    {
                        "href": "https://www.contentful.com/resources/composable-commerce-for-growth/",
                        "text": "Composable commerce for growth report",
                        "rel": "",
                    }
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.contentful.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.contentful.com/resources/composable-commerce-for-growth"
    ]


def test_discover_publisher_inventory_browser_uses_http_supplement_when_browser_candidates_are_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("MarketLensePublisherInventory/")
        return _FakeResponse(
            url="https://wordpress.bluecore.app/resources",
            text=(
                "<html><body>"
                "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                "Benchmarks for Identification, Conversion, and Retention"
                "</a>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            }
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]


def test_discover_publisher_inventory_browser_invalid_http_supplement_html_fails_cleanly(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("MarketLensePublisherInventory/")
        return _FakeResponse(
            url="https://example.com/insights",
            text="<![\ufffd\"\ufffd(\u001c\ufffd\u001c\ufffdB\ufffdo\u0011IRD\ufffd\\\\",
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [],
            },
        }
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=_settings(tmp_path),
                route_kind_hint="browser_render",
            ),
            run_context,
        )

    assert_app_error(err.value, code="publisher_inventory_browser_incomplete", retryable=True)


def test_discover_publisher_inventory_browser_uses_rendered_html_supplement_when_visible_anchors_are_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bluecore.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": (
                "<html><body>"
                "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                "Benchmarks for Identification, Conversion, and Retention"
                "</a>"
                "</body></html>"
            ),
        }
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]


def test_discover_publisher_inventory_browser_recovers_from_cross_apex_host_drift(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bluecore.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources/",
                "page_title": "Resources - Bluecore",
                "anchors": [
                    {
                        "href": "https://www.bluecore.com/lp/customer-movement-benchmarks/",
                        "text": "Benchmarks for Identification, Conversion, and Retention",
                        "rel": "",
                    }
                ],
            },
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert response.pages[0].page_url == "https://www.bluecore.com/resources"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]


def test_browser_scripts_coerce_non_string_dom_values_before_normalizing() -> None:
    scripts = [
        service._browser_inventory_state_script(),
        service._browser_click_named_control_script(),
        service._browser_click_pagination_next_script(),
        service._browser_click_tab_script(),
        service._browser_apply_report_filter_script(),
    ]
    for script in scripts:
        assert "String(value ?? '')" in script
        assert "(value || '').replace" not in script


def test_discover_publisher_inventory_browser_prioritizes_button_pagination_over_hero_load_more(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://business.adobe.com/resources/reports.html",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-one.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report One 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
                "has_pagination_next": True,
            },
            "named_clicks": {"load more": "hero_load_more"},
            "pagination_next_state": "page_2",
        },
        "hero_load_more": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-one.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://business.adobe.com/resources/reports/report-hero.html",
                        "text": "Read now",
                        "heading_text": "Hero Spotlight Report",
                        "rel": "",
                    },
                ],
            }
        },
        "page_2": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html?page=2",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-two.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report Two 2026",
                        "rel": "",
                    }
                ],
                "has_pagination_next": True,
                "result_range_end": 18,
                "result_range_total": 18,
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://business.adobe.com/resources/reports.html",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert response.pages[1].page_url == "https://business.adobe.com/resources/reports.html?page=2"
    assert [candidate.title for candidate in response.candidates] == [
        "Adobe Report One 2026",
        "Adobe Report Two 2026",
    ]
    assert "Clicked button pagination 1 time(s)." in response.route_summary
    assert "Expanded load-more pagination" not in response.route_summary


def test_discover_publisher_inventory_browser_tracks_load_more_state_change_without_new_unique_candidates(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/about",
                        "text": "About",
                        "rel": "",
                    },
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert response.pages[1].page_number == 2
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_treats_inert_load_more_as_exhausted(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/reports/report-two",
                        "text": "Report Two 2026",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-two",
    ]
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_http_hint_empty_is_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/contact'>Contact</a></body></html>",
        ),
    )
    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=_settings(tmp_path),
                route_kind_hint="http_parse",
            ),
            run_context,
        )
    assert_app_error(err.value, code="publisher_inventory_http_empty", retryable=True)


def test_discover_publisher_inventory_force_browser_skips_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = PublisherInventorySettings(
        schema_version=settings.schema_version,
        openrouter_api_key=settings.openrouter_api_key,
        model=settings.model,
        temperature=settings.temperature,
        timeout_seconds=settings.timeout_seconds,
        max_steps=settings.max_steps,
        output_dir=settings.output_dir,
        reports_db=settings.reports_db,
        google_sa_path=settings.google_sa_path,
        prompt_namespace=settings.prompt_namespace,
        pagination_max_pages=settings.pagination_max_pages,
        http_timeout_seconds=settings.http_timeout_seconds,
        drive_auth_mode=settings.drive_auth_mode,
        google_oauth_client_path=settings.google_oauth_client_path,
        google_oauth_token_path=settings.google_oauth_token_path,
        openrouter_http_referer=settings.openrouter_http_referer,
        headed=True,
        force_browser=True,
        retry_retries=settings.retry_retries,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        retry_backoff_step_seconds=settings.retry_backoff_step_seconds,
        retry_jitter_seconds=settings.retry_jitter_seconds,
    )
    http_calls: list[str] = []
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda url, timeout, headers: (
            http_calls.append(url)
            or _FakeResponse(
                url="https://example.com/insights",
                text="<html><body><a href='/reports/report-one'>Report One 2026</a></body></html>",
                )
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://example.com/reports/report-one", "text": "Report One 2026", "rel": ""}
                ],
            }
        }
    }
    runtime = _runtime_for_states(states)
    vendored_root = str(
        (Path(service.__file__).resolve().parents[2] / "tools" / "browser-use").resolve()
    )
    original_sys_path = list(service.sys.path)
    import_attempts: list[bool] = []

    def _import_module(_name: str):
        has_vendored_root = vendored_root in service.sys.path
        import_attempts.append(has_vendored_root)
        if not has_vendored_root:
            raise ModuleNotFoundError("No module named 'browser_use'")
        return runtime

    external_boundary_mocks_only.setattr(service, "import_module", _import_module)
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    try:
        service.sys.path[:] = [
            entry for entry in service.sys.path if str(entry) != vendored_root
        ]
        response = service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=settings,
            ),
            run_context,
        )
    finally:
        service.sys.path[:] = original_sys_path

    assert response.route_kind == "browser_render"
    assert _FakeBrowser.last_instance is not None
    assert _FakeBrowser.last_instance.headless is False
    assert import_attempts == [False, True]
    assert http_calls == []


def test_discover_publisher_inventory_browser_traverses_tabs(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {"href": "https://www.salesforce.com/eu/form/gartner-report", "text": "2025 Gartner Report", "rel": ""}
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "Gartner",
            },
            "tab_clicks": {"forrester": "forrester", "idc": "idc"},
        },
        "forrester": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {"href": "https://www.salesforce.com/eu/form/forrester-report", "text": "2025 Forrester Wave", "rel": ""}
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "Forrester",
            },
            "tab_clicks": {"idc": "idc"},
        },
        "idc": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {"href": "https://www.salesforce.com/eu/form/idc-report", "text": "2025 IDC MarketScape", "rel": ""}
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "IDC",
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
            settings=PublisherInventorySettings(
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
                headed=True,
                force_browser=True,
                retry_retries=1,
                retry_base_delay_seconds=0.1,
                retry_backoff_step_seconds=0.0,
                retry_jitter_seconds=0.0,
            ),
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 3
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.salesforce.com/eu/form/gartner-report",
        "https://www.salesforce.com/eu/form/forrester-report",
        "https://www.salesforce.com/eu/form/idc-report",
    ]
    assert "tabbed publisher section(s)" in response.route_summary


def test_discover_publisher_inventory_browser_follows_report_listing_route(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.gfk-media-measurement.com/global/en/insights/",
                "page_title": "Insights",
                "anchors": [
                    {"href": "https://www.gfk-media-measurement.com/global/en/insights/commentary/2025/example/", "text": "Commentary", "rel": ""}
                ],
                "report_link_url": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/",
            }
        },
        "report_listing": {
            "payload": {
                "page_url": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/",
                "page_title": "Reports",
                "anchors": [
                    {
                        "href": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/q2-audience-report/",
                        "text": "Q2 Audience Report 2025",
                        "rel": "",
                    }
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: _runtime_for_states(states))
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.gfk-media-measurement.com/global/en/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert response.final_page_url == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports"
    assert response.candidates[0].url == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/q2-audience-report"
    assert "report listing route" in response.route_summary


def test_extract_candidates_from_html_filters_false_positive_hub_and_social_links() -> None:
    html = """
    <html><body>
      <a href="/blog/social-media-industry-benchmark-report/">2025 Social Media Industry Benchmark Report</a>
      <a href="/it/insights">Italy (Italiano)</a>
      <a href="/de/insights/type/report">Deutsch</a>
      <a href="https://www.facebook.com/bainandcompany">icon-facebook-f</a>
      <a href="/insights/type/article">Article archive</a>
      <a href="/insights/topic/big-data/">Big Data</a>
      <a href="/">.st0{fill:#FFFFFF;}</a>
      <a href="/global/en/insights/report/2025/reports/">Reports</a>
      <a href="/global/en">02_Elements/Icons/Close</a>
      <a href="/vector-digital/ai-insights-and-solutions">AI, Insights, and Solutions</a>
      <a href="/insights/featured-topics/">View all featured topics</a>
      <a href="/insights/why-agentic-ai-demands-a-new-architecture/">Why Agentic AI Demands a New Architecture</a>
      <a href="/insights/topics/global-private-equity-report/">Global Private Equity Report 2026</a>
      <a href="https://www.weforum.org/stories/2026/03/how-corporate-strategy-is-changing-in-a-world-of-constant-shocks/">Redefining Corporate Strategy in a More Volatile World</a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.bain.com/insights?filters=|types(424%2C420)",
        page_number=1,
        next_page_url=None,
    )

    assert [candidate.title for candidate in candidates] == [
        "2025 Social Media Industry Benchmark Report",
        "Why Agentic AI Demands a New Architecture",
        "Global Private Equity Report 2026",
    ]
    assert [candidate.url for candidate in candidates] == [
        "https://www.bain.com/blog/social-media-industry-benchmark-report",
        "https://www.bain.com/insights/why-agentic-ai-demands-a-new-architecture",
        "https://www.bain.com/insights/topics/global-private-equity-report",
    ]


def test_extract_candidates_from_html_allows_original_host_when_rendered_page_uses_hosted_subdomain() -> None:
    html = """
    <html><body>
      <a href="https://www.bluecore.com/lp/customer-movement-benchmarks/">Benchmarks for Identification, Conversion, and Retention</a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources",
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]


def test_browser_named_control_selector_covers_anchor_button_controls() -> None:
    selector = service._browser_named_control_selector()
    inventory_script = service._browser_inventory_state_script()
    click_script = service._browser_click_named_control_script()
    pagination_click_script = service._browser_click_pagination_next_script()

    assert 'a.btn' in selector
    assert 'a[class*="btn"]' in selector
    assert 'a.wp-block-button__link' in selector
    assert '.load-more' in selector
    assert 'a.btn' in inventory_script
    assert 'a.wp-block-button__link' in inventory_script
    assert 'a.btn' in click_script
    assert 'a.wp-block-button__link' in click_script
    assert 'candidate_urls' in click_script
    assert 'scrollIntoView' in click_script
    assert 'aria-disabled' in inventory_script
    assert 'aria-disabled' in click_script
    assert 'aria-disabled' in pagination_click_script
    assert 'has_pagination_next' in inventory_script
