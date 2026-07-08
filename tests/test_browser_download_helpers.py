from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
    browser_helper_js,
    browser_helper_page_info,
    browser_helper_standard_form_submit,
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
    ) -> None:
        self.url = url
        self._title = title
        self._html = html
        self._evaluate_error = evaluate_error

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


def test_helper_surface_documents_owned_approved_helpers() -> None:
    surface = get_browser_helper_surface()

    assert surface == {
        "page_info": "Read bounded URL/title/HTML metadata from the active page.",
        "capture_screenshot": "Persist a screenshot through browser, page, or CDP hooks.",
        "js": "Run bounded JavaScript inspection and return structured values.",
        "form_autocomplete": "Recover required form autocompletes with keyboard-style input and verified selection.",
        "standard_form_submit": "Repair safe standard HTML fields, selects, and mandatory legal/report-delivery checkboxes before resubmitting.",
    }


class AutocompleteSuccessPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        assert "KeyboardEvent" in expression
        assert "InputEvent" in expression
        assert "blur()" in expression
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": {
                "attempted_count": 1,
                "selected_count": 1,
                "selected_fields": ["Location"],
                "unresolved_fields": [],
                "submitted": True,
                "final_url": "https://publisher.example/thanks",
            },
            "result_type": "object",
        }


class AutocompleteBlockedPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        assert "KeyboardEvent" in expression
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": {
                "attempted_count": 1,
                "selected_count": 0,
                "selected_fields": [],
                "unresolved_fields": ["Country"],
                "submitted": False,
                "final_url": "https://publisher.example/form",
            },
            "result_type": "object",
        }


class NativeSelectSuccessPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        assert "'select'" in expression
        assert "insertReplacementText" in expression
        assert "option_aliases" in expression
        assert "optionAliases" in expression
        assert "passIndex < 1" in expression
        assert ".slice(0, 120)" in expression
        assert "blur()" in expression
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": {
                "attempted_count": 1,
                "selected_count": 1,
                "selected_fields": ["Country"],
                "unresolved_fields": [],
                "submitted": False,
                "final_url": "https://publisher.example/form",
            },
            "result_type": "object",
        }


class NativeSelectFallbackPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        script_text = str(expression)
        assert "looksLikePlaceholderOption" in script_text
        assert "exactOption || fallbackOption" in script_text
        assert 'input[name*="state" i]' in script_text
        assert "sameOriginDocuments" in script_text
        assert "frame.contentDocument" in script_text
        assert "root.querySelectorAll" in script_text
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": {
                "attempted_count": 1,
                "selected_count": 1,
                "selected_fields": ["State"],
                "unresolved_fields": [],
                "submitted": False,
                "final_url": "https://publisher.example/form",
            },
            "result_type": "object",
        }


class StandardFormAlreadyResolvedPage(FakePage):
    def evaluate(self, expression: str) -> dict[str, Any]:
        script_text = str(expression)
        assert "standardFormSubmit" in script_text
        assert "resolvedControlCount" in script_text
        assert "progressCount > 0 || resolvedControlCount > 0" in script_text
        return {
            "__marketlense_js_helper": True,
            "ok": True,
            "result": {
                "attempted_count": 0,
                "filled_count": 0,
                "selected_count": 0,
                "mandatory_agreement_checked_count": 0,
                "resolved_control_count": 3,
                "submitted": True,
                "final_url": "https://publisher.example/form",
                "resolved_fields": ["Email", "Country", "Privacy agreement"],
                "unresolved_fields": [],
            },
            "result_type": "object",
        }


def test_form_autocomplete_helper_verifies_selection_and_submission(
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    result = browser_helper_form_autocomplete(
        page=AutocompleteSuccessPage(),
        field_values=[
            {
                "key": "location",
                "label": "Location",
                "value": "Austria",
                "aliases": ["country"],
            }
        ],
        ctx=run_context,
        normalized_url="https://publisher.example/form",
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.selected_count == 1
    assert result.submitted is True
    assert result.selected_fields == ("Location",)
    assert result.blocker_code is None


def test_form_autocomplete_helper_handles_native_select_controls(
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    result = browser_helper_form_autocomplete(
        page=NativeSelectSuccessPage(),
        field_values=[
            {
                "key": "country",
                "label": "Country",
                "value": "Austria",
                "aliases": ["location"],
                "option_aliases": ["Republic of Austria"],
            }
        ],
        ctx=run_context,
        normalized_url="https://publisher.example/form",
        submit=False,
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.selected_count == 1
    assert result.submitted is False
    assert result.selected_fields == ("Country",)


def test_form_autocomplete_helper_allows_first_non_placeholder_fallback(
    run_context,
) -> None:
    result = browser_helper_form_autocomplete(
        page=NativeSelectFallbackPage(),
        field_values=[
            {
                "key": "state_region",
                "label": "State",
                "value": "California",
                "aliases": ["state", "province"],
                "option_aliases": ["CA"],
            }
        ],
        ctx=run_context,
        normalized_url="https://publisher.example/form",
        submit=False,
    )

    assert result.status == "ok"
    assert result.selected_count == 1
    assert result.unresolved_fields == ()
    assert result.selected_fields == ("State",)


def test_standard_form_submit_helper_submits_when_controls_already_resolved(
    run_context,
) -> None:
    result = browser_helper_standard_form_submit(
        page=StandardFormAlreadyResolvedPage(),
        field_values=[
            {
                "key": "work_email",
                "label": "Email",
                "value": "reports@marketbearing.eu",
                "aliases": ["email", "business email"],
            },
            {
                "key": "country",
                "label": "Country",
                "value": "Austria",
                "aliases": ["country"],
                "option_aliases": ["Austria"],
            },
        ],
        ctx=run_context,
        normalized_url="https://publisher.example/form",
    )

    assert result.status == "ok"
    assert result.submitted is True
    assert result.unresolved_fields == ()
    assert result.resolved_fields == ("Email", "Country", "Privacy agreement")


def test_form_autocomplete_helper_reports_unresolved_enum_blocker(
    run_context,
) -> None:
    result = browser_helper_form_autocomplete(
        page=AutocompleteBlockedPage(),
        field_values=[
            {
                "key": "country",
                "label": "Country",
                "value": "Austria",
                "aliases": ["location"],
            }
        ],
        ctx=run_context,
        normalized_url="https://publisher.example/form",
    )

    assert result.status == "blocked"
    assert result.selected_count == 0
    assert result.unresolved_fields == ("Country",)
    assert result.blocker_code == "blocked_unknown_required_enum"


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

