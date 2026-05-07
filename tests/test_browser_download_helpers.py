from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_ensure_real_tab,
    browser_helper_http_get,
    browser_helper_js,
    browser_helper_page_info,
    browser_helper_wait_for_load,
    get_browser_helper_surface,
)


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://publisher.example/report",
        title: str = "Publisher Report",
        html: str = "<html><title>Publisher Report</title><body>report</body></html>",
        evaluate_error: Exception | None = None,
        wait_error: Exception | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._html = html
        self._evaluate_error = evaluate_error
        self._wait_error = wait_error
        self.waited_for: list[str] = []

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._html

    def evaluate(self, expression: str) -> dict[str, Any]:
        if self._evaluate_error is not None:
            raise self._evaluate_error
        if "__marketlense_js_helper" in str(expression):
            return {
                "__marketlense_js_helper": True,
                "ok": True,
                "result": {"ok": True},
                "result_type": "object",
            }
        return {
            "ok": True,
            "expression_prefix": str(expression)[:16],
        }

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        if self._wait_error is not None:
            raise self._wait_error
        self.waited_for.append(f"{state}:{timeout}")

    def screenshot(self, path: str, full_page: bool = True) -> None:
        Path(path).write_bytes(b"fake-png")


class FailingScreenshotPage(FakePage):
    def screenshot(self, path: str, full_page: bool = True) -> None:
        raise RuntimeError("screenshot failed")


class PromiseJsPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        assert "Promise.resolve" in expression
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": "resolved",
            "result_type": "string",
        }


class ThrowingJsPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        assert "throw new Error" in expression
        return {
            "__marketlense_js_helper": True,
            "ok": False,
            "error": "Publisher script exploded",
            "line": 7,
            "column": 19,
            "snippet": "throw new Error('Publisher script exploded')",
        }


class UnserializableJsPage(FakePage):
    def evaluate(self, expression: str) -> object:
        return object()


class FakeBrowser:
    def __init__(
        self,
        *,
        url: str = "https://publisher.example/report",
        title: str = "Publisher Report",
        html: str = "",
    ) -> None:
        self.url = url
        self.title = title
        self.html = html


class NoWaitPage:
    url = "https://publisher.example/report"


class HelperHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<html><body>publisher helper page</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def helper_http_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HelperHttpHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/publisher"
    finally:
        server.shutdown()
        server.server_close()


def test_helper_surface_documents_owned_approved_helpers() -> None:
    surface = get_browser_helper_surface()

    assert surface == {
        "page_info": "Read bounded URL/title/HTML metadata from the active page.",
        "capture_screenshot": "Persist a screenshot through browser, page, or CDP hooks.",
        "js": "Run bounded JavaScript inspection and return structured values.",
        "wait_for_load": "Perform one explicit browser/page load-state wait.",
        "ensure_real_tab": "Diagnose a user-facing page tab and reject internal targets.",
        "http_get": "Fetch a static page through the shared bounded HTTP executor.",
    }


def test_page_info_positive_and_internal_tab_failure(
    run_context,
    assert_no_defaulted_required_fields,
    assert_logs_have_required_fields,
    caplog,
) -> None:
    caplog.set_level(logging.INFO)

    result = browser_helper_page_info(
        browser=FakeBrowser(),
        page=FakePage(),
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )
    internal = browser_helper_page_info(
        browser=FakeBrowser(url="chrome://settings", title="Settings"),
        page=FakePage(url="chrome://settings", title="Settings"),
        ctx=run_context,
        normalized_url="chrome://settings",
    )

    assert_no_defaulted_required_fields(result)
    assert result.url == "https://publisher.example/report"
    assert result.title == "Publisher Report"
    assert result.is_real_tab is True
    assert result.html_size == len(result.html)
    assert result.source_labels
    assert internal.is_real_tab is False
    assert_logs_have_required_fields(caplog.records)


def test_screenshot_positive_and_required_failure(
    tmp_path: Path,
    run_context,
    assert_no_defaulted_required_fields,
    assert_app_error,
) -> None:
    positive_path = tmp_path / "positive.png"

    result = browser_helper_capture_screenshot(
        browser=FakeBrowser(),
        page=FakePage(),
        screenshot_path=positive_path,
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.source == "page"
    assert positive_path.read_bytes() == b"fake-png"

    with pytest.raises(Exception) as exc_info:
        browser_helper_capture_screenshot(
            browser=object(),
            page=FailingScreenshotPage(),
            screenshot_path=tmp_path / "failed.png",
            ctx=run_context,
            normalized_url="https://publisher.example/report",
            required=True,
        )
    assert_app_error(
        exc_info.value,
        code="browser_helper_screenshot_failed",
        retryable=True,
    )


def test_js_positive_and_required_failure(
    run_context,
    assert_no_defaulted_required_fields,
    assert_app_error,
) -> None:
    result = browser_helper_js(
        page=FakePage(),
        expression="return {ok: true}",
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.result == {"ok": True}
    assert result.result_serializable is True

    with pytest.raises(Exception) as exc_info:
        browser_helper_js(
            page=FakePage(evaluate_error=RuntimeError("js exploded")),
            expression="return window.location.href",
            ctx=run_context,
            normalized_url="https://publisher.example/report",
            required=True,
        )
    assert_app_error(exc_info.value, code="browser_helper_js_failed", retryable=False)


def test_js_promise_exception_and_unserializable_values(
    run_context,
    assert_app_error,
) -> None:
    promise_result = browser_helper_js(
        page=PromiseJsPage(),
        expression="return await Promise.resolve('resolved')",
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )
    thrown_result = browser_helper_js(
        page=ThrowingJsPage(),
        expression="throw new Error('Publisher script exploded')",
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )
    unserializable_result = browser_helper_js(
        page=UnserializableJsPage(),
        expression="window",
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )

    assert promise_result.status == "ok"
    assert promise_result.result == "resolved"
    assert thrown_result.status == "failed"
    assert thrown_result.error == "Publisher script exploded"
    assert thrown_result.error_line == 7
    assert thrown_result.error_column == 19
    assert unserializable_result.status == "ok"
    assert unserializable_result.result_serializable is False
    assert "object object at" in str(unserializable_result.result)

    with pytest.raises(Exception) as exc_info:
        browser_helper_js(
            page=ThrowingJsPage(),
            expression="throw new Error('Publisher script exploded')",
            ctx=run_context,
            normalized_url="https://publisher.example/report",
            required=True,
        )
    assert_app_error(exc_info.value, code="browser_helper_js_failed", retryable=False)
    assert exc_info.value.context["error_line"] == 7
    assert exc_info.value.context["error_column"] == 19


def test_wait_positive_and_required_failure(
    run_context,
    assert_no_defaulted_required_fields,
    assert_app_error,
) -> None:
    page = FakePage()
    result = browser_helper_wait_for_load(
        browser=FakeBrowser(),
        page=page,
        ctx=run_context,
        normalized_url="https://publisher.example/report",
        timeout_seconds=1.0,
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert page.waited_for == ["networkidle:1000"]

    with pytest.raises(Exception) as exc_info:
        browser_helper_wait_for_load(
            browser=object(),
            page=NoWaitPage(),
            ctx=run_context,
            normalized_url="https://publisher.example/report",
            required=True,
        )
    assert_app_error(
        exc_info.value,
        code="browser_helper_wait_for_load_failed",
        retryable=True,
    )


def test_real_tab_positive_and_required_failure(
    run_context,
    assert_no_defaulted_required_fields,
    assert_app_error,
) -> None:
    result = browser_helper_ensure_real_tab(
        browser=FakeBrowser(),
        page=FakePage(),
        ctx=run_context,
        normalized_url="https://publisher.example/report",
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.is_real_tab is True

    with pytest.raises(Exception) as exc_info:
        browser_helper_ensure_real_tab(
            browser=FakeBrowser(url="about:blank", title=""),
            page=FakePage(url="about:blank", title="", html=""),
            ctx=run_context,
            normalized_url="about:blank",
            required=True,
        )
    assert_app_error(
        exc_info.value,
        code="browser_helper_real_tab_unavailable",
        retryable=True,
    )


def test_http_get_positive_and_failure(
    helper_http_url: str,
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    result = browser_helper_http_get(
        url=helper_http_url,
        ctx=run_context,
        normalized_url=helper_http_url,
        max_body_bytes=64,
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.status_code == 200
    assert "publisher helper page" in result.body_excerpt

    failure = browser_helper_http_get(
        url="",
        ctx=run_context,
        normalized_url="",
    )
    assert failure.status == "failed"
    assert failure.error == "HTTP acquisition requires a non-empty absolute URL"
