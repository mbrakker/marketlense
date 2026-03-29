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

    payload = {
        "route_kind": "browser_render",
        "route_summary": "Open the page in headed mode and extract the report cards.",
        "final_page_url": "https://example.com/insights",
        "pages": [
            {"page_number": 1, "page_url": "https://example.com/insights"},
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
        last_instance = None

        def __init__(self, downloads_path, headless, auto_download_pdfs):
            self.downloads_path = downloads_path
            self.headless = headless
            self.auto_download_pdfs = auto_download_pdfs
            self.url = "https://example.com/insights"
            FakeBrowser.last_instance = self

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
    assert FakeBrowser.last_instance is not None
    assert FakeBrowser.last_instance.headless is False
    assert import_attempts == [False, True]
    assert http_calls == ["https://example.com/insights"]


def test_discover_publisher_inventory_browser_supplements_candidates_from_http_page_html(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html><body>
      <a href="/reports/report-one.pdf">Report One 2026</a>
      <a href="/reports/report-two.pdf">Report Two 2026</a>
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

    payload = {
        "route_kind": "browser_render",
        "route_summary": "Open the page in headed mode and extract the report cards.",
        "final_page_url": "https://example.com/insights",
        "pages": [
            {"page_number": 1, "page_url": "https://example.com/insights"},
        ],
        "candidates": [
            {
                "url": "https://example.com/insights/download-now",
                "title": "Technology & Media Outlook - Download now",
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
            self.url = "https://example.com/insights"

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
    assert [candidate.title for candidate in response.candidates] == [
        "Report One 2026",
        "Report Two 2026",
    ]
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one.pdf",
        "https://example.com/reports/report-two.pdf",
    ]
