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
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
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
    assert response.candidates[0].provenance == "http_parse"
    assert response.candidates[0].confidence is not None
    assert response.candidates[0].confidence >= 0.60
    assert response.candidates[1].discovered_on_page_number == 2
    assert (
        response.candidates[1].source_page_url == "https://example.com/insights?page=2"
    )
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_events(caplog))


def test_discover_publisher_inventory_http_parse_stops_on_duplicate_page_fingerprint(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    html_page = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
      <a href="https://example.com/insights?page=2" rel="next">Next</a>
    </body></html>
    """
    requested_urls: list[str] = []

    def _get(url, timeout, headers):
        requested_urls.append(url)
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        if url.endswith("page=2"):
            return _FakeResponse(
                url="https://example.com/insights?page=2",
                text=html_page,
            )
        return _FakeResponse(url="https://example.com/insights", text=html_page)

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

    assert requested_urls == [
        "https://example.com/insights",
        "https://example.com/insights?page=2",
    ]
    assert response.route_kind == "http_parse"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one"
    ]
    duplicate_events = [
        event
        for event in _events(caplog)
        if event.get("event") == "publisher_inventory_http_duplicate_page_fingerprint"
    ]
    assert len(duplicate_events) == 1
    assert_logs_have_required_fields(_events(caplog))


def test_discover_publisher_inventory_http_parse_rejects_low_confidence_candidates(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    html = """
    <html><body>
      <a href="/insights/customer-trends-2026">Customer Trends 2026</a>
    </body></html>
    """

    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(url="https://example.com/insights", text=html)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

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

    assert_app_error(err.value, code="publisher_inventory_http_empty", retryable=False)


def test_discover_publisher_inventory_http_parse_recovers_wordpress_ajax_archives(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_html = """
    <html>
      <head>
        <title>Resources - Example</title>
        <script>var wpajax = {"url":"https://example.com/wp-admin/admin-ajax.php","nonce":"nonce-123"};</script>
        <script src="https://example.com/wp-content/themes/example/script.js"></script>
      </head>
      <body>
        <main><a href="/resources/">Resources</a></main>
      </body>
    </html>
    """
    script_js = """
    function ajax_filter() {
      var data_ajax = {
        action: 'resources_filter',
        nonce: wpajax.nonce,
        paged: curentPage
      };
    }
    """
    ajax_page_1 = json.dumps(
        {
            "max_num_pages": 2,
            "posts": (
                '<a href="https://example.com/lp/retail-benchmark-2026">'
                "Retail Benchmark 2026"
                "</a>"
            ),
        }
    )
    ajax_page_2 = json.dumps(
        {
            "max_num_pages": 2,
            "posts": (
                '<a href="https://example.com/lp/customer-retention-playbook">'
                "Customer Retention Playbook"
                "</a>"
            ),
        }
    )

    def _get(url, timeout, headers):
        normalized_url = str(url).rstrip("/")
        if normalized_url == "https://example.com/resources":
            return _FakeResponse(url="https://example.com/resources", text=page_html)
        if normalized_url == "https://example.com/wp-content/themes/example/script.js":
            return _FakeResponse(url=normalized_url, text=script_js)
        raise AssertionError(f"Unexpected GET url: {url}")

    def _post(url, timeout, headers, data):
        assert url == "https://example.com/wp-admin/admin-ajax.php"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        if data["paged"] == "1":
            return _FakeResponse(url=url, text=ajax_page_1)
        if data["paged"] == "2":
            return _FakeResponse(url=url, text=ajax_page_2)
        raise AssertionError(f"Unexpected AJAX payload: {data}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    external_boundary_mocks_only.setattr(service.requests, "post", _post)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert "WordPress AJAX action `resources_filter`" in response.route_summary
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/retail-benchmark-2026",
        "https://example.com/lp/customer-retention-playbook",
    ]


def test_discover_publisher_inventory_http_parse_retries_with_trailing_slash(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers):
        if str(url) == "https://example.com/resources":
            raise service.requests.RequestException("redirect timeout")
        if str(url) == "https://example.com/resources/":
            return _FakeResponse(
                url="https://example.com/resources/",
                text=(
                    "<html><body>"
                    "<a href='/lp/retail-benchmark-2026'>Retail Benchmark 2026</a>"
                    "</body></html>"
                ),
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/retail-benchmark-2026"
    ]


def test_discover_publisher_inventory_http_parse_supplements_sparse_archive_with_wordpress_ajax(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_html = """
    <html>
      <head>
        <title>Resources - Example</title>
        <script>var wpajax = {"url":"https://example.com/wp-admin/admin-ajax.php","nonce":"nonce-123"};</script>
        <script src="https://example.com/wp-content/themes/example/script.js"></script>
      </head>
      <body>
        <main>
          <a href="/resources/">Resources</a>
          <a href="/lp/featured-retail-benchmark">Featured Retail Benchmark</a>
        </main>
      </body>
    </html>
    """
    script_js = """
    var data_ajax = {
      action: 'resources_filter',
      nonce: wpajax.nonce,
      paged: curentPage
    };
    """
    ajax_page_1 = json.dumps(
        {
            "max_num_pages": 1,
            "posts": (
                '<a href="https://example.com/lp/featured-retail-benchmark">'
                "Featured Retail Benchmark"
                "</a>"
                '<a href="https://example.com/lp/customer-retention-playbook">'
                "Customer Retention Playbook"
                "</a>"
            ),
        }
    )

    def _get(url, timeout, headers):
        normalized_url = str(url).rstrip("/")
        if normalized_url == "https://example.com/resources":
            return _FakeResponse(url="https://example.com/resources/", text=page_html)
        if normalized_url == "https://example.com/wp-content/themes/example/script.js":
            return _FakeResponse(url=normalized_url, text=script_js)
        raise AssertionError(f"Unexpected GET url: {url}")

    def _post(url, timeout, headers, data):
        assert url == "https://example.com/wp-admin/admin-ajax.php"
        return _FakeResponse(url=url, text=ajax_page_1)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    external_boundary_mocks_only.setattr(service.requests, "post", _post)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert "WordPress AJAX action `resources_filter`" in response.route_summary
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/featured-retail-benchmark",
        "https://example.com/lp/customer-retention-playbook",
    ]


def test_select_tab_labels_for_traversal_prefers_report_focused_tabs() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/resources/blog",
        page_title="Example Resources",
        anchors=[],
        load_more_labels=[],
        tab_labels=["All", "Articles", "Research"],
        active_tab_label="All",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    selected = service._select_tab_labels_for_traversal(
        "https://example.com/resources/blog",
        state,
    )

    assert selected == ["Research"]


def test_requires_archive_surface_recovery_for_detail_page_drift() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/resources/blog/cloud-cost-guide",
        page_title="Cloud Cost Guide",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert service._requires_archive_surface_recovery(
        state=state,
        page_candidates=[],
        normalized_url="https://example.com/resources/blog",
    )


def test_is_archive_surface_accepts_small_set_of_substantive_cards() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.psfk.com/insights",
        page_title="PSFK | Living Intelligence & AI Foresight",
        anchors=[
            {
                "href": "https://psfk.gumroad.com/l/coffee-machine-innovation-report",
                "text": "Coffee Maker Innovation An essential snapshot of the ideas reshaping coffee machines.",
                "rel": "",
            },
            {
                "href": "https://newsletter.psfk.com/p/about-your-health",
                "text": "About Your Health Healthcare now runs through homes, workplaces, communities, devices and apps.",
                "rel": "",
            },
            {
                "href": "https://newsletter.psfk.com/p/future-of-wellness",
                "text": "Future of Wellness A strategic thinking brief on changing consumer wellness expectations.",
                "rel": "",
            },
        ],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert service._is_archive_surface(state) is True


def test_terminal_results_page_accepts_page_count_hints() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/library",
        page_title="Example Library",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
        page_index_hint=12,
        page_total_hint=12,
    )

    assert service._is_terminal_results_page(state) is True


def test_should_follow_report_listing_requires_archive_like_target() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.publicissapient.com/resources/blog",
        page_title="Publicis Sapient Blog",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url="https://www.publicissapient.com/resources/blog/cloud-cost-management-guide",
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert (
        service._should_follow_report_listing(
            "https://www.publicissapient.com/resources/blog",
            state,
        )
        is False
    )


def test_should_expand_archive_library_for_small_archive_preview() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.psfk.com/insights",
        page_title="Reports & Strategic Thinking",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )
    page_candidates = [
        service.PublisherInventoryRawCandidate(
            schema_version="1.0",
            url="https://psfk.gumroad.com/l/coffee-machine-innovation-report",
            title="Coffee Maker Innovation",
            source_page_url="https://www.psfk.com/insights",
            discovered_on_page_number=1,
        ),
        service.PublisherInventoryRawCandidate(
            schema_version="1.0",
            url="https://psfk.gumroad.com/l/2026-trends-report",
            title="To Be In 2026",
            source_page_url="https://www.psfk.com/insights",
            discovered_on_page_number=1,
        ),
    ]

    assert service._should_expand_archive_library(state, page_candidates) is True


def test_should_apply_report_filter_generically_for_visible_report_filter() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.transunion.com/insights",
        page_title="Insights | TransUnion",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=True,
        has_apply_button=False,
    )

    assert (
        service._should_apply_report_filter(
            "https://www.transunion.com/insights",
            state,
        )
        is True
    )


def test_select_anchor_title_prefers_heading_over_noisy_card_text() -> None:
    selected = service._select_anchor_title(
        {
            "text": "Amazon Prime Day Trends Report 2024 Margaux Logan 22 / 07 / 2024 MARKETING AND THOUGHT LEADERSHIP Read more",
            "heading_text": "Amazon Prime Day Trends Report 2024",
            "aria_label": "",
            "title_attr": "",
            "img_alt": "",
        }
    )

    assert selected == "Amazon Prime Day Trends Report 2024"


def test_select_anchor_title_uses_card_context_for_generic_cta_links() -> None:
    selected = service._select_anchor_title(
        {
            "text": "Learn more",
            "heading_text": "",
            "aria_label": "",
            "title_attr": "",
            "img_alt": "",
            "context_text": (
                "Retail Data & Trends, Seasonal Retail Advice "
                "Black Friday Benchmarks 2025 "
                "Discover Bluecore's annual Black Friday benchmarks report. "
                "Learn more"
            ),
        }
    )

    assert selected.startswith(
        "Retail Data & Trends, Seasonal Retail Advice Black Friday Benchmarks 2025"
    )


def test_extract_candidates_from_html_uses_heading_for_cta_only_links() -> None:
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "https://www.bluecore.com/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "Black Friday Benchmarks 2025",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "BFCM Benchmarks",
            }
        ],
        page_url="https://www.bluecore.com/resources/",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]
    assert candidates[0].title == "Black Friday Benchmarks 2025"


def test_extract_candidates_from_html_resolves_relative_links_to_origin_host_when_browser_drifts() -> (
    None
):
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "Black Friday Benchmarks 2025",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "",
            }
        ],
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_extract_candidates_from_html_uses_card_context_for_generic_cta_links() -> None:
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "https://www.bluecore.com/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "",
                "context_text": (
                    "Retail Data & Trends, Seasonal Retail Advice "
                    "Black Friday Benchmarks 2025 "
                    "Discover Bluecore's annual Black Friday benchmarks report. "
                    "Learn more"
                ),
                "rel": "",
            }
        ],
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_extract_candidates_from_html_keeps_direct_report_library_pages_on_archive_surfaces() -> (
    None
):
    candidates = service._extract_candidates_from_html(
        anchors=[],
        page_url="https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx",
        page_title="Active Capital: The Report",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx"
    ]
    assert candidates[0].title == "Active Capital: The Report"


def test_inventory_html_parser_preserves_container_text_for_generic_cta_links() -> None:
    parser = service._InventoryHtmlParser()
    parser.feed(
        """
        <html><body>
          <div class="resource-card">
            <div>Retail Data &amp; Trends</div>
            <div>Black Friday Benchmarks 2025</div>
            <div>Discover Bluecore's annual Black Friday benchmarks report.</div>
            <a href="https://www.bluecore.com/black-friday-benchmarks-2025/">Learn more</a>
          </div>
        </body></html>
        """
    )

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_discover_publisher_inventory_browser_applies_generic_report_dropdown_filter(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.transunion.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.transunion.com/insights",
                "page_title": "Insights | TransUnion",
                "anchors": [
                    {
                        "href": "https://www.transunion.com/blog/example-blog",
                        "text": "Example Blog",
                        "rel": "",
                    }
                ],
                "has_report_filter": True,
                "has_apply_button": False,
                "has_pagination_next": True,
            },
            "apply_filter_next_state": "filtered",
        },
        "filtered": {
            "payload": {
                "page_url": "https://www.transunion.com/insights",
                "page_title": "Insights | TransUnion",
                "anchors": [
                    {
                        "href": "https://www.transunion.com/report/example-industry-report",
                        "text": "Example Industry Report 2026",
                        "rel": "",
                    }
                ],
                "has_report_filter": True,
                "has_apply_button": False,
                "has_pagination_next": False,
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.transunion.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.transunion.com/report/example-industry-report"
    ]
    assert response.candidates[0].provenance == "browser_dom"
    assert "Applied the report format filter." in response.route_summary


def test_discover_publisher_inventory_direct_pdf_source_short_circuits_browser(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _unexpected_runtime(_name: str):
        raise AssertionError(
            "browser runtime should not be loaded for direct PDF sources"
        )

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
    assert (
        response.candidates[0].pdf_url
        == "https://example.com/reports/state-of-retail-2026.pdf"
    )
    assert response.candidates[0].provenance == "direct_pdf_source"
    assert response.candidates[0].confidence == 1.0


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
            }
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
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


def test_close_unexpected_blank_pages_keeps_active_page_when_target_id_is_missing(
    run_context,
) -> None:
    browser = _FakeBrowser(
        downloads_path=".",
        headless=True,
        auto_download_pdfs=False,
        states={
            "initial": {
                "payload": {
                    "page_url": "about:blank",
                    "page_title": "",
                    "anchors": [],
                }
            }
        },
        start_state="initial",
        extra_page_urls=["about:blank"],
    )
    browser.page = _FakeBrowserPage(browser, "initial", browser._states, target_id="")

    asyncio.run(
        service._close_unexpected_blank_pages(
            browser=browser,
            active_page=browser.page,
            ctx=run_context,
            reason="test_blank_identity_guard",
        )
    )

    assert browser.closed_page_ids == ["aux-1"]


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
                    {
                        "href": "https://www.bain.com/insights/books",
                        "text": "Bain Books",
                        "rel": "",
                    }
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
        candidate.url
        == "https://www.bain.com/insights/private-equitys-reality-check-gp-outlook-2026"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_stops_before_recording_inert_duplicate_load_more_states(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.alixpartners.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    shared_anchors = [
        {
            "href": "https://www.alixpartners.com/insights/report-one",
            "text": "Report One",
            "rel": "",
        },
        {
            "href": "https://www.alixpartners.com/insights/report-two",
            "text": "Report Two",
            "rel": "",
        },
    ]
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors[:1],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors,
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors,
                "load_more_labels": ["Load more"],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.alixpartners.com/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-two",
    ]
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
                {
                    "label": "show more results",
                    "next_state": "wrong_surface",
                    "candidate_hits": 1,
                    "top": 1100,
                },
                {
                    "label": "show more",
                    "next_state": "page_2",
                    "candidate_hits": 6,
                    "top": 900,
                },
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
                {
                    "label": "show more results",
                    "next_state": "wrong_surface",
                    "candidate_hits": 1,
                    "top": 1200,
                }
            ],
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
        candidate.url
        == "https://www.algolia.com/resources/asset/ebook-why-agentic-ai-is-your-next-priority"
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
    assert response.candidates[0].provenance == "http_supplement"


def test_discover_publisher_inventory_browser_uses_http_supplement_for_archive_root_only_candidate(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(
            url="https://ecdb.com/whitepapers-and-reports",
            text=(
                "<html><body>"
                "<a href='https://ecdb.com/reports/global-marketplaces-report'>"
                "Global Marketplaces Report"
                "</a>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://ecdb.com/whitepapers-and-reports",
                "page_title": "Whitepapers and Reports",
                "anchors": [
                    {
                        "href": "https://ecdb.com/whitepapers-and-reports",
                        "text": "Whitepapers and Reports",
                        "rel": "",
                    }
                ],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://ecdb.com/whitepapers-and-reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://ecdb.com/reports/global-marketplaces-report"
    ]
    assert response.candidates[0].provenance == "http_supplement"


def test_discover_publisher_inventory_browser_invalid_http_supplement_html_fails_cleanly(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    def _get(url, timeout, headers):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(
            url="https://example.com/insights",
            text='<![\ufffd"\ufffd(\u001c\ufffd\u001c\ufffdB\ufffdo\u0011IRD\ufffd\\\\',
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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

    assert_app_error(
        err.value, code="publisher_inventory_browser_incomplete", retryable=True
    )


def test_discover_publisher_inventory_browser_pagination_limit_falls_back_to_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text=(
                "<html><body>"
                "<a href='/reports/consumer-benchmark-2026'>Consumer Benchmark 2026</a>"
                "</body></html>"
            ),
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
                        "rel": "",
                    }
                ],
                "has_pagination_next": True,
            },
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(_settings(tmp_path), pagination_max_pages=1),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/consumer-benchmark-2026"
    ]


def test_discover_publisher_inventory_browser_returns_bounded_result_after_multi_page_pagination_limit(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("http fallback not expected")
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
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
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/reports/retail-outlook-2026",
                        "text": "Retail Outlook 2026",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(_settings(tmp_path), pagination_max_pages=2),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert (
        response.candidates[0].url
        == "https://example.com/reports/consumer-benchmark-2026"
    )
    assert (
        response.candidates[-1].url == "https://example.com/reports/retail-outlook-2026"
    )
    assert {candidate.url for candidate in response.candidates} == {
        "https://example.com/reports/consumer-benchmark-2026",
        "https://example.com/reports/retail-outlook-2026",
    }
    assert "pagination limit" in response.route_summary.lower()


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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
    assert response.candidates[0].provenance == "browser_rendered_html_supplement"


def test_discover_publisher_inventory_browser_extracts_custom_component_links_from_rendered_html(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.juliusbaer.com/en/insights",
            text="<html><body></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.juliusbaer.com/en/insights",
                "page_title": "Insights | Julius Baer",
                "anchors": [],
            },
            "rendered_html": (
                "<html><body>"
                "<jb-article-card "
                'link="{&quot;href&quot;:&quot;\\/en\\/insights\\/market-insights\\/market-outlook\\/iran-war-dominates-markets-what-now\\/&quot;}" '
                'teaserHeader="{&quot;headline&quot;:&quot;Iran war dominates markets: What now?&quot;}">'
                "</jb-article-card>"
                "</body></html>"
            ),
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.juliusbaer.com/en/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.juliusbaer.com/en/insights/market-insights/market-outlook/iran-war-dominates-markets-what-now"
    ]
    assert response.candidates[0].title == "Iran war dominates markets: What now?"
    assert response.candidates[0].provenance == "browser_rendered_html_supplement"


def test_discover_publisher_inventory_browser_seeds_direct_report_page_when_dom_has_only_navigation(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/2026-garden-trends-report",
                "page_title": "2026 Garden Trends Report",
                "anchors": [
                    {
                        "href": "https://example.com/expertise",
                        "text": "Expertise",
                        "rel": "",
                    },
                    {"href": "https://example.com/blog", "text": "Blog", "rel": ""},
                ],
            },
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/2026-garden-trends-report",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/2026-garden-trends-report"
    ]
    assert response.candidates[0].title == "2026 Garden Trends Report"


def test_discover_publisher_inventory_browser_preserves_pre_cookie_archive_candidates_when_dismissal_degrades_page(
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
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [
                    {
                        "href": "https://www.bluecore.com/lp/customer-movement-benchmarks/",
                        "text": "Benchmarks for Identification, Conversion, and Retention",
                        "rel": "",
                    }
                ],
            },
            "cookie_banner_next_state": "drifted",
        },
        "drifted": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": "<html><body></body></html>",
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )

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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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


def test_discover_publisher_inventory_browser_falls_back_to_direct_http_when_browser_path_stays_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    call_counts: dict[str, int] = {}

    def _get(url, timeout, headers):
        key = str(url)
        call_counts[key] = call_counts.get(key, 0) + 1
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        if "wordpress.bluecore.app" in key:
            raise service.requests.ConnectTimeout("mirror timeout")
        if key == "https://www.bluecore.com/resources" and call_counts[key] == 1:
            raise service.requests.ConnectTimeout("origin supplement timeout")
        if key == "https://www.bluecore.com/resources":
            return _FakeResponse(
                url="https://www.bluecore.com/resources",
                text=(
                    "<html><body>"
                    "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                    "Benchmarks for Identification, Conversion, and Retention"
                    "</a>"
                    "</body></html>"
                ),
            )
        raise AssertionError(f"Unexpected URL: {url}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": "<html><body></body></html>",
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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

    assert response.route_kind == "http_parse"
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
    assert (
        response.pages[1].page_url
        == "https://business.adobe.com/resources/reports.html?page=2"
    )
    assert [candidate.title for candidate in response.candidates] == [
        "Adobe Report One 2026",
        "Adobe Report Two 2026",
    ]
    assert "Clicked button pagination 1 time(s)." in response.route_summary
    assert "Expanded load-more pagination" not in response.route_summary


def test_discover_publisher_inventory_browser_stops_on_load_more_state_change_without_new_unique_candidates(
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
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
    assert len(response.pages) == 1
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
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
    assert len(response.pages) == 2
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-two",
    ]
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_skips_duplicate_same_url_page_states(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.alixpartners.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/insights/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/insights/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/about",
                        "text": "About",
                        "rel": "",
                    },
                ],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.alixpartners.com/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-two",
    ]
    assert "Expanded load-more pagination 2 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_breaks_same_url_load_more_cycles(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.askattest.com/our-research",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.askattest.com/research/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.askattest.com/our-research",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.askattest.com/research/report-one",
        "https://www.askattest.com/research/report-one",
        "https://www.askattest.com/research/report-two",
    ]
    assert "Expanded load-more pagination 2 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_breaks_cross_url_signature_cycles(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://datareportal.com/reports",
            text="<html><body><a href='/reports?offset=34'>Next</a></body></html>",
        ),
    )
    shared_anchors = [
        {
            "href": "https://datareportal.com/reports/report-one",
            "text": "Report One",
            "rel": "",
        },
        {
            "href": "https://datareportal.com/reports/report-two",
            "text": "Report Two",
            "rel": "",
        },
    ]
    states = {
        "initial": {
            "payload": {
                "page_url": "https://datareportal.com/reports",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=34"],
            },
            "goto_states": {
                "https://datareportal.com/reports?offset=34": "page_2",
            },
        },
        "page_2": {
            "payload": {
                "page_url": "https://datareportal.com/reports?offset=34",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=68"],
            },
            "goto_states": {
                "https://datareportal.com/reports?offset=68": "page_3",
            },
        },
        "page_3": {
            "payload": {
                "page_url": "https://datareportal.com/reports?offset=68",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=102"],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://datareportal.com/reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [page.page_url for page in response.pages] == [
        "https://datareportal.com/reports",
    ]
    assert [candidate.url for candidate in response.candidates] == [
        "https://datareportal.com/reports/report-one",
        "https://datareportal.com/reports/report-two",
    ]


def test_wait_for_inventory_growth_probe_detects_same_page_anchor_growth(
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    class _ProbePage:
        def __init__(self) -> None:
            self._counts = [1, 3]

        async def evaluate(self, script: str, *args):
            assert "pageUrl" in script
            count = self._counts.pop(0)
            return json.dumps(
                {
                    "pageUrl": "https://example.com/insights",
                    "anchorCount": count,
                }
            )

    previous_state = service._RenderedInventoryState(
        page_url="https://example.com/insights",
        page_title="Insights",
        anchors=[
            {"href": "https://example.com/report-one", "text": "Report One", "rel": ""}
        ],
        load_more_labels=["Load more"],
        tab_labels=[],
        active_tab_label=None,
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
        has_pagination_next=False,
        result_range_end=None,
        result_range_total=None,
        page_index_hint=None,
        page_total_hint=None,
    )

    observed = asyncio.run(
        service._wait_for_inventory_growth_probe(
            _ProbePage(),
            previous_state=previous_state,
            delay_seconds=0.1,
            timeout_seconds=0.25,
        )
    )

    assert observed is True


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
    assert_app_error(err.value, code="publisher_inventory_http_empty", retryable=False)


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
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
                ],
            }
        }
    }
    runtime = _runtime_for_states(states)
    vendored_root = str(
        (
            Path(service.__file__).resolve().parents[2] / "tools" / "browser-use"
        ).resolve()
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
                    {
                        "href": "https://www.salesforce.com/eu/form/gartner-report",
                        "text": "2025 Gartner Report",
                        "rel": "",
                    }
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
                    {
                        "href": "https://www.salesforce.com/eu/form/forrester-report",
                        "text": "2025 Forrester Wave",
                        "rel": "",
                    }
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
                    {
                        "href": "https://www.salesforce.com/eu/form/idc-report",
                        "text": "2025 IDC MarketScape",
                        "rel": "",
                    }
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "IDC",
            }
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
    assert response.route_trace is not None
    assert response.route_trace.selected_tab_labels == ["Gartner", "Forrester", "IDC"]
    assert response.route_trace.pagination_mode == "tabbed"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.salesforce.com/eu/form/gartner-report",
        "https://www.salesforce.com/eu/form/forrester-report",
        "https://www.salesforce.com/eu/form/idc-report",
    ]
    assert "tabbed publisher section(s)" in response.route_summary


def test_discover_publisher_inventory_preflight_short_circuits_direct_detail(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        force_browser=False,
        enable_preflight_classifier_and_direct_detail=True,
    )

    def _get(url, timeout, headers, allow_redirects=True):
        return _FakeResponse(
            url="https://example.com/research-library/ai-perspectives-2026",
            text=(
                "<html><head><title>AI Perspectives 2026</title></head>"
                "<body><a href='/files/ai-perspectives.pdf'>Download the research brief</a></body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/research-library/ai-perspectives-2026",
            settings=settings,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.scenario_summary is not None
    assert response.scenario_summary.scenario_class == "direct_detail_html"
    assert response.candidates[0].provenance == "direct_detail_source"


def test_discover_publisher_inventory_preflight_prefers_direct_detail_path_over_archive_terms(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        force_browser=True,
        enable_preflight_classifier_and_direct_detail=True,
    )

    def _get(url, timeout, headers, allow_redirects=True):
        return _FakeResponse(
            url="https://example.com/insights/research-library/ai-perspectives-2026",
            text=(
                "<html><head><title>AI Perspectives 2026</title></head>"
                "<body><h1>AI Perspectives 2026</h1>"
                "<p>Research library entry with related insights and latest research links.</p>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights/research-library/ai-perspectives-2026",
            settings=settings,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.scenario_summary is not None
    assert response.scenario_summary.scenario_class == "direct_detail_html"
    assert response.candidates[0].provenance == "direct_detail_source"


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
                    {
                        "href": "https://www.gfk-media-measurement.com/global/en/insights/commentary/2025/example/",
                        "text": "Commentary",
                        "rel": "",
                    }
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
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
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
    assert (
        response.final_page_url
        == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports"
    )
    assert (
        response.candidates[0].url
        == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/q2-audience-report"
    )
    assert "report listing route" in response.route_summary


def test_discover_publisher_inventory_browser_follows_whitepaper_listing_route(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://onclusive.com/fr/expertise/insights/",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://onclusive.com/fr/expertise/insights/article-one/",
                        "text": "Article",
                        "rel": "",
                    }
                ],
                "report_link_url": "https://onclusive.com/fr/ressources/livres-blancs/",
            }
        },
        "report_listing": {
            "payload": {
                "page_url": "https://onclusive.com/fr/ressources/livres-blancs/",
                "page_title": "Livres Blancs",
                "anchors": [
                    {
                        "href": "https://onclusive.com/fr/ressources/livres-blancs/barometre-medias-2026/",
                        "text": "Baromètre médias 2026",
                        "rel": "",
                    }
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://onclusive.com/fr/expertise/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert (
        response.final_page_url == "https://onclusive.com/fr/ressources/livres-blancs"
    )
    assert (
        response.candidates[0].url
        == "https://onclusive.com/fr/ressources/livres-blancs/barometre-medias-2026"
    )


def test_extract_candidates_from_html_filters_false_positive_hub_and_social_links() -> (
    None
):
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


def test_extract_candidates_from_html_allows_original_host_when_rendered_page_uses_hosted_subdomain() -> (
    None
):
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


def test_extract_candidates_from_html_accepts_archive_surface_cards_without_report_keywords() -> (
    None
):
    html = """
    <html><body>
      <a href="https://www.publicissapient.com/resources/blog/modernization-risks-regulated-industries">
        <h3>Modernization Risks in Regulated Industries</h3>
        <span>Research</span>
      </a>
      <a href="https://www.publicissapient.com/resources/blog/the-ai-powered-investment-firm">
        <h3>The AI-Powered Investment Firm</h3>
        <span>Research</span>
      </a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.publicissapient.com/resources/blog",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.publicissapient.com/resources/blog",
        page_title="Publicis Sapient Blog | Articles and Research",
        active_tab_label="Research",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.publicissapient.com/resources/blog/modernization-risks-regulated-industries",
        "https://www.publicissapient.com/resources/blog/the-ai-powered-investment-firm",
    ]


def test_extract_candidates_from_html_accepts_external_report_host_on_archive_surface() -> (
    None
):
    html = """
    <html><body>
      <a href="https://psfk.gumroad.com/l/coffee-machine-innovation-report-psfk-for-waldo">
        Report January 2026 Coffee Maker Innovation Download Report
      </a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.psfk.com/insights",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.psfk.com/insights",
        page_title="Thought Leadership Archive",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://psfk.gumroad.com/l/coffee-machine-innovation-report-psfk-for-waldo"
    ]


def test_browser_named_control_selector_covers_anchor_button_controls() -> None:
    selector = service._browser_named_control_selector()
    inventory_script = service._browser_inventory_state_script()
    click_script = service._browser_click_named_control_script()
    cookie_click_script = service._browser_click_cookie_banner_script()
    pagination_click_script = service._browser_click_pagination_next_script()
    archive_expander_script = service._browser_click_archive_expander_script()

    assert "a.btn" in selector
    assert 'a[class*="btn"]' in selector
    assert "a.wp-block-button__link" in selector
    assert ".load-more" in selector
    assert "a.btn" in inventory_script
    assert "a.wp-block-button__link" in inventory_script
    assert "a.btn" in click_script
    assert "a.wp-block-button__link" in click_script
    assert "candidate_urls" in click_script
    assert "scrollIntoView" in click_script
    assert "aria-disabled" in inventory_script
    assert "aria-disabled" in click_script
    assert "cookie" in cookie_click_script
    assert "consent" in cookie_click_script
    assert "aria-disabled" in pagination_click_script
    assert "has_pagination_next" in inventory_script
    assert "const pageCountMatch =" in pagination_click_script
    assert "explore" in archive_expander_script
    assert "library" in archive_expander_script


def test_discover_publisher_inventory_browser_timeout_is_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    states = {
        "page1": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )

    def _raise_timeout(_awaitable):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError("timed out")

    external_boundary_mocks_only.setattr(service.asyncio, "run", _raise_timeout)

    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=replace(
                    _settings(tmp_path),
                    force_browser=True,
                    timeout_seconds=1.0,
                ),
                route_kind_hint=None,
                route_hint=None,
            ),
            run_context,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_browser_timeout",
        retryable=True,
    )


def test_discover_publisher_inventory_browser_timeout_falls_back_to_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
    </body></html>
    """

    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda url, timeout, headers: _FakeResponse(
            url="https://example.com/insights",
            text=html,
        ),
    )

    def _raise_timeout(_awaitable):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError("timed out")

    external_boundary_mocks_only.setattr(service.asyncio, "run", _raise_timeout)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(
                _settings(tmp_path),
                force_browser=True,
                timeout_seconds=1.0,
            ),
            route_kind_hint=None,
            route_hint=None,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one"
    ]


def test_inspect_publisher_inventory_landing_pages_detects_gated_report_signals(
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    html = """
    <html>
      <head>
        <title>Greek eGrocery S1 2024 | Convert Group</title>
        <meta property="og:title" content="Greek eGrocery S1 2024" />
      </head>
      <body>
        <h1>Greek eGrocery S1 2024</h1>
        <p>You can download the report by filling out the form.</p>
        <p>Contents of the report include market size, trends, and key findings.</p>
        <form><input type="email" /><input type="submit" value="Download report" /></form>
      </body>
    </html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://convertgroup.com/reports_posts/greek-egrocery-s1-2024/",
            text=html,
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.publisher_inventory_service")

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Convert Group",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://convertgroup.com/reports_posts/greek-egrocery-s1-2024/",
                    title="Download report",
                    discovered_on_page_number=1,
                    source_page_url="https://convertgroup.com/reports",
                )
            ],
            timeout_seconds=5.0,
            max_workers=2,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.h1_title == "Greek eGrocery S1 2024"
    assert observation.has_asset_type_term is True
    assert observation.has_download_language is True
    assert observation.has_gated_form is True
    assert observation.has_document_structure is True
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.publisher_inventory_service"
    ]
    assert_logs_have_required_fields(records)


def test_inspect_publisher_inventory_landing_pages_marks_dead_pages(
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html><head><title>Page not found | Example</title></head><body><h1>Page not found</h1></body></html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/resources/missing-report",
            text=html,
            status_code=404,
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/resources/missing-report",
                    title="Missing Report",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.http_status_code == 404
    assert observation.has_dead_page_marker is True


def test_inspect_publisher_inventory_landing_pages_detects_direct_pdf_assets(
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/report.pdf",
            text="",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/report.pdf",
                    title="2026 Outlook",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.is_pdf is True
    assert observation.has_download_language is True
    assert observation.has_dead_page_marker is False


def test_inspect_publisher_inventory_landing_pages_does_not_treat_body_purchase_word_as_product_flow(
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html>
      <head><title>Creating Relevance Through the Convergence of Content, Creators & Commerce</title></head>
      <body>
        <h2>Creating Relevance Through the Convergence of Content, Creators & Commerce</h2>
        <h1>KEY TAKEAWAYS</h1>
        <p>Creators and content can guide consumers from awareness all the way through to purchase with just a click.</p>
        <p>Other Articles</p>
        <p>Colleen Hotchkiss</p>
        <p>30 / 06 / 2023</p>
        <button>Subscribe</button>
      </body>
    </html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.publiciscommerce.com/insights/creating-relevance-through-the-convergence-of-content-creators-and-commerce",
            text=html,
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Publicis Commerce",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://www.publiciscommerce.com/insights/creating-relevance-through-the-convergence-of-content-creators-and-commerce",
                    title="Creating Relevance Through the Convergence of Content",
                    discovered_on_page_number=1,
                    source_page_url="https://www.publiciscommerce.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.has_price_or_purchase is False
    assert observation.has_newsletter_cta is True
