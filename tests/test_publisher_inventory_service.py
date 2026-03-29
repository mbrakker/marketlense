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

    payload = {
        "route_kind": "browser_render",
        "route_summary": "Open the landing page, click next pagination, and extract the report cards.",
        "final_page_url": "https://example.com/insights?page=2",
        "pages": [
            {"page_number": 1, "page_url": "https://example.com/insights"},
            {"page_number": 2, "page_url": "https://example.com/insights?page=2"},
        ],
        "candidates": [
            {
                "url": "https://example.com/reports/report-one",
                "title": "Report One 2026",
                "source_page_url": "https://example.com/insights",
                "discovered_on_page_number": 1,
                "pdf_url": None,
                "published_at_text": None,
            }
        ],
    }

    class FakeHistory:
        def final_result(self) -> str:
            return json.dumps(payload)

    class FakeBrowser:
        def __init__(self, downloads_path, headless, auto_download_pdfs):
            self.downloads_path = downloads_path
            self.headless = headless
            self.auto_download_pdfs = auto_download_pdfs
            self.url = "https://example.com/insights?page=2"

        async def kill(self) -> None:
            return None

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        def __init__(self, *, task, llm, browser, output_model_schema):
            self.task = task
            self.llm = llm
            self.browser = browser
            self.output_model_schema = output_model_schema

        def run_sync(self, max_steps: int):
            return FakeHistory()

    runtime = SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenRouter=FakeChatOpenRouter,
        Agent=FakeAgent,
    )
    external_boundary_mocks_only.setattr(service, "import_module", lambda _name: runtime)

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
    assert response.candidates[0].discovered_on_page_number == 1
    assert_no_defaulted_required_fields(response)


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
