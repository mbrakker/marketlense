"""Inspectable browser helper surface for browser report downloads.

This module owns the approved Marketlense helper surface adapted from the
browser-harness `page_info`, `capture_screenshot`, `js`, `wait_for_load`,
`ensure_real_tab`, and `http_get` patterns. It stays inside the existing
`browser_report_download_service` boundary, returns typed contracts, and does
not read prompts, choose routes, decide retries, or orchestrate workflows.

Approved helpers:
- `browser_helper_page_info`: bounded user-facing page URL/title/HTML metadata.
- `browser_helper_capture_screenshot`: screenshot-first evidence capture.
- `browser_helper_js`: bounded JavaScript inspection with typed failures.
- `browser_helper_form_autocomplete`: keyboard-style form autocomplete recovery.
- `browser_helper_wait_for_load`: one bounded load-state wait.
- `browser_helper_ensure_real_tab`: real-tab diagnostics excluding internals.
- `browser_helper_http_get`: bounded static HTTP fetch for inspection.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperAutocompleteResult,
    BrowserHelperHttpGetResult,
    BrowserHelperJsResult,
    BrowserHelperPageInfo,
    BrowserHelperRealTabResult,
    BrowserHelperScreenshot,
    BrowserHelperWaitResult,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    call_browser_download_cdp,
    capture_terminal_screenshot_via_cdp,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

_HELPER_SCHEMA_VERSION = "1.0"
_HTML_EXCERPT_CHARS = 800
_JS_SNIPPET_CHARS = 240
_HELPER_AWAIT_TIMEOUT_SECONDS = 8.0
_INTERNAL_TARGET_URL_PREFIXES = (
    "about:",
    "brave://",
    "chrome://",
    "chrome-error://",
    "chrome-extension://",
    "chrome-search://",
    "chrome-untrusted://",
    "devtools://",
    "edge://",
    "opera://",
    "vivaldi://",
)


class _JavaScriptEvaluationError(Exception):
    def __init__(
        self,
        *,
        error: str,
        error_line: int | None = None,
        error_column: int | None = None,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.error_line = error_line
        self.error_column = error_column


def get_browser_helper_surface() -> dict[str, str]:
    return {
        "page_info": "Read bounded URL/title/HTML metadata from the active page.",
        "capture_screenshot": "Persist a screenshot through browser, page, or CDP hooks.",
        "js": "Run bounded JavaScript inspection and return structured values.",
        "form_autocomplete": "Recover required form autocompletes with keyboard-style input and verified selection.",
        "wait_for_load": "Perform one explicit browser/page load-state wait.",
        "ensure_real_tab": "Diagnose a user-facing page tab and reject internal targets.",
        "http_get": "Fetch a static page through the shared bounded HTTP executor.",
    }


def browser_helper_page_info(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserHelperPageInfo:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_page_info_start",
            module=logger.name,
            fields={"normalized_url": normalized_url},
        )
    )
    source_labels: list[str] = []
    url, url_source = _first_non_empty(
        (
            ("browser.url", _read_browser_url(browser)),
            ("browser.current_page_url", _read_browser_current_page_url(browser)),
            ("page.url", _read_page_url(page)),
        )
    )
    title, title_source = _first_non_empty(
        (
            ("browser.title", _read_browser_title(browser)),
            (
                "browser.current_page_title",
                _read_browser_current_page_title(browser),
            ),
            ("page.title", _read_page_title(page)),
        )
    )
    html, html_source = _first_non_empty(
        (
            ("browser.html", _read_browser_html(browser)),
            ("page.html", _read_page_html(page)),
        )
    )
    for source in (url_source, title_source, html_source):
        if source:
            source_labels.append(source)
    result = BrowserHelperPageInfo(
        schema_version=_HELPER_SCHEMA_VERSION,
        url=url,
        title=title,
        html_size=len(html),
        html=html,
        html_excerpt=_excerpt(html, _HTML_EXCERPT_CHARS),
        is_real_tab=_is_real_tab_url(url),
        source_labels=tuple(source_labels),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_page_info_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": result.url,
                "title": result.title,
                "html_size": result.html_size,
                "is_real_tab": result.is_real_tab,
                "source_labels": list(result.source_labels),
            },
        )
    )
    return result


def browser_helper_capture_screenshot(
    *,
    browser: Any,
    page: Any,
    screenshot_path: Path,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperScreenshot:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
                "required": required,
            },
        )
    )
    candidates = (
        ("browser", getattr(browser, "take_screenshot", None)),
        ("page", getattr(page, "screenshot", None) if page is not None else None),
        (
            "page_take_screenshot",
            getattr(page, "take_screenshot", None) if page is not None else None,
        ),
    )
    for source, candidate in candidates:
        if _try_screenshot_call(candidate=candidate, screenshot_path=screenshot_path):
            return _screenshot_result(
                ctx=ctx,
                normalized_url=normalized_url,
                screenshot_path=screenshot_path,
                source=source,
            )
    if capture_terminal_screenshot_via_cdp(
        browser=browser,
        screenshot_path=screenshot_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    ):
        return _screenshot_result(
            ctx=ctx,
            normalized_url=normalized_url,
            screenshot_path=screenshot_path,
            source="cdp",
        )
    if required:
        raise AppError(
            code="browser_helper_screenshot_failed",
            message="Browser helper could not capture a required screenshot",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
            },
        )
    result = BrowserHelperScreenshot(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        path="",
        source="",
        size_bytes=0,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_failed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
                "required": required,
            },
        )
    )
    return result


def browser_helper_js(
    *,
    page: Any,
    expression: str,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperJsResult:
    snippet = _snippet(expression)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_start",
            module=logger.name,
            fields={"normalized_url": normalized_url, "snippet": snippet},
        )
    )
    evaluate = getattr(page, "evaluate", None) if page is not None else None
    if not callable(evaluate):
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error="page.evaluate is unavailable",
            required=required,
        )
    try:
        raw_result = _maybe_await(
            evaluate(_wrap_js_expression(expression)),
            timeout_seconds=_HELPER_AWAIT_TIMEOUT_SECONDS,
        )
        result_value, serializable = _adapt_js_result_value(raw_result)
    except AppError:
        raise
    except _JavaScriptEvaluationError as exc:
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error=exc.error,
            required=required,
            error_line=exc.error_line,
            error_column=exc.error_column,
        )
    except Exception as exc:
        error_line, error_column = _extract_error_location(str(exc))
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error=str(exc),
            required=required,
            error_line=error_line,
            error_column=error_column,
        )
    result = BrowserHelperJsResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        result=result_value,
        result_type=type(result_value).__name__,
        snippet=snippet,
        result_serializable=serializable,
        error="",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "result_type": result.result_type,
                "result_serializable": result.result_serializable,
            },
        )
    )
    return result


def browser_helper_form_autocomplete(
    *,
    page: Any,
    field_values: list[dict[str, object]],
    ctx: RunContext,
    normalized_url: str,
    submit: bool = True,
) -> BrowserHelperAutocompleteResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_form_autocomplete_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "field_value_count": len(field_values),
                "submit": submit,
            },
        )
    )
    script_payload = {
        "fields": field_values,
        "submit": bool(submit),
    }
    js_result = browser_helper_js(
        page=page,
        expression=f"""
        return (() => {{
          const payload = {json.dumps(script_payload, ensure_ascii=True)};
          const normalize = (value) =>
            String(value ?? '').replace(/\\s+/g, ' ').trim();
          const keyToken = (value) => normalize(value).toLowerCase();
          const isVisible = (node) => Boolean(
            node &&
            !node.hidden &&
            node.getClientRects &&
            node.getClientRects().length > 0
          );
          const fieldEntries = (payload.fields || [])
            .map((field) => ({{
              label: normalize(field.label || field.key || ''),
              value: normalize(field.value || ''),
              aliases: [
                field.key,
                field.label,
                ...(Array.isArray(field.aliases) ? field.aliases : []),
              ].map(keyToken).filter(Boolean),
            }}))
            .filter((field) => field.value);
          const labelsFor = (control) => {{
            const values = [];
            const id = control.getAttribute('id') || '';
            if (id) {{
              const label = document.querySelector(`label[for="${{CSS.escape(id)}}"]`);
              if (label) values.push(label.textContent || '');
            }}
            values.push(
              control.getAttribute('aria-label') || '',
              control.getAttribute('placeholder') || '',
              control.getAttribute('name') || '',
              control.getAttribute('id') || ''
            );
            const labelledBy = control.getAttribute('aria-labelledby') || '';
            for (const token of labelledBy.split(/\\s+/).filter(Boolean)) {{
              const node = document.getElementById(token);
              if (node) values.push(node.textContent || '');
            }}
            const wrapper = control.closest(
              '.lookupFormFieldBlock, .form-field, .field, label, div, li'
            );
            if (wrapper) {{
              const wrapperText = normalize(wrapper.textContent || '');
              if (wrapperText.length <= 160) values.push(wrapperText);
            }}
            return values.map(keyToken).filter(Boolean);
          }};
          const matchField = (control) => {{
            const labels = labelsFor(control);
            const joined = labels.join(' ');
            for (const field of fieldEntries) {{
              if (field.aliases.some((alias) => joined.includes(alias))) {{
                return field;
              }}
            }}
            const currentValue = normalize(control.value || '');
            if (currentValue) {{
              return {{ label: labels[0] || 'Autocomplete', value: currentValue }};
            }}
            return null;
          }};
          const controls = Array.from(document.querySelectorAll([
            'input[role="combobox"]',
            'input[aria-autocomplete]',
            'input.lookup-behavior',
            '.lookupFormFieldBlock input',
            '[role="combobox"] input',
            'select',
          ].join(','))).filter((control, index, collection) =>
            collection.indexOf(control) === index && isVisible(control)
          );
          const visibleOptions = () => Array.from(document.querySelectorAll([
            '[role="option"]',
            '[role="listbox"] [role="option"]',
            '.ui-menu-item-wrapper',
            '.ui-menu-item',
            '[data-value]',
            '[data-testid*="option" i]',
          ].join(','))).filter((node) =>
            isVisible(node) && normalize(node.innerText || node.textContent)
          );
          const dispatchKey = (control, type, key) => {{
            control.dispatchEvent(new KeyboardEvent(type, {{
              key,
              bubbles: true,
              cancelable: true,
            }}));
          }};
          const typeText = (control, value) => {{
            control.focus();
            control.click();
            control.value = '';
            control.dispatchEvent(new Event('input', {{ bubbles: true }}));
            for (const char of value) {{
              dispatchKey(control, 'keydown', char);
              control.value = `${{control.value || ''}}${{char}}`;
              control.dispatchEvent(new InputEvent('beforeinput', {{
                inputType: 'insertText',
                data: char,
                bubbles: true,
                cancelable: true,
              }}));
              control.dispatchEvent(new InputEvent('input', {{
                inputType: 'insertText',
                data: char,
                bubbles: true,
              }}));
              dispatchKey(control, 'keyup', char);
            }}
            control.dispatchEvent(new Event('change', {{ bubbles: true }}));
          }};
          const clickOption = (node) => {{
            node.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
            node.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true }}));
            node.click();
          }};
          const selectNativeOption = (control, field) => {{
            const wanted = keyToken(field.value);
            control.focus();
            control.click();
            for (const char of field.value) {{
              dispatchKey(control, 'keydown', char);
              dispatchKey(control, 'keyup', char);
            }}
            const options = Array.from(control.options || []).filter((option) =>
              !option.disabled && keyToken(option.textContent || option.value)
            );
            const option = options.find((node) =>
              keyToken(node.textContent || node.value) === wanted
            ) || options.find((node) =>
              keyToken(node.textContent || node.value).includes(wanted)
            ) || options.find((node) =>
              wanted.includes(keyToken(node.textContent || node.value))
            );
            if (option) {{
              control.value = option.value;
              option.selected = true;
              control.dispatchEvent(new InputEvent('input', {{
                inputType: 'insertReplacementText',
                data: option.textContent || option.value,
                bubbles: true,
              }}));
              control.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            dispatchKey(control, 'keydown', 'Tab');
            dispatchKey(control, 'keyup', 'Tab');
            control.blur();
            const persisted = keyToken(
              (control.selectedOptions && control.selectedOptions[0]
                ? control.selectedOptions[0].textContent || ''
                : '') ||
              control.value ||
              control.getAttribute('value') ||
              ''
            );
            const invalid = String(control.getAttribute('aria-invalid') || '')
              .toLowerCase() === 'true';
            return !invalid && persisted && (
              persisted === wanted ||
              persisted.includes(wanted) ||
              wanted.includes(persisted)
            );
          }};
          const selectedFields = [];
          const unresolvedFields = [];
          let attemptedCount = 0;
          for (const control of controls) {{
            const field = matchField(control);
            if (!field || !field.value) continue;
            const label = normalize(field.label || labelsFor(control)[0] || 'Autocomplete');
            attemptedCount += 1;
            if (control.tagName && control.tagName.toLowerCase() === 'select') {{
              if (selectNativeOption(control, field)) {{
                selectedFields.push(label);
              }} else {{
                unresolvedFields.push(label);
              }}
              continue;
            }}
            typeText(control, field.value);
            const wanted = keyToken(field.value);
            const options = visibleOptions();
            const option = options.find((node) =>
              keyToken(node.innerText || node.textContent) === wanted
            ) || options.find((node) =>
              keyToken(node.innerText || node.textContent).includes(wanted)
            );
            if (option) {{
              clickOption(option);
            }} else {{
              dispatchKey(control, 'keydown', 'Enter');
              dispatchKey(control, 'keyup', 'Enter');
            }}
            dispatchKey(control, 'keydown', 'Tab');
            dispatchKey(control, 'keyup', 'Tab');
            control.blur();
            const persisted = keyToken(
              control.value ||
              control.getAttribute('value') ||
              control.getAttribute('aria-label') ||
              ''
            );
            const invalid = String(control.getAttribute('aria-invalid') || '')
              .toLowerCase() === 'true';
            if (!invalid && persisted && (
              persisted === wanted ||
              persisted.includes(wanted) ||
              wanted.includes(persisted)
            )) {{
              selectedFields.push(label);
            }} else {{
              unresolvedFields.push(label);
            }}
          }}
          let submitted = false;
          if (payload.submit && selectedFields.length > 0 && unresolvedFields.length === 0) {{
            const submitButton = Array.from(document.querySelectorAll(
              'button[type="submit"], input[type="submit"], button'
            )).find((node) => {{
              const text = keyToken(node.innerText || node.textContent || node.value || '');
              return isVisible(node) && (
                text === 'submit' ||
                text.includes('submit') ||
                text.includes('download') ||
                text.includes('send')
              );
            }});
            if (submitButton) {{
              submitButton.click();
              submitted = true;
            }}
          }}
          return {{
            attempted_count: attemptedCount,
            selected_count: selectedFields.length,
            selected_fields: selectedFields,
            unresolved_fields: unresolvedFields,
            submitted,
            final_url: window.location.href || '',
          }};
        }})();
        """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return _autocomplete_result(
            ctx=ctx,
            normalized_url=normalized_url,
            status="failed",
            error=js_result.error,
        )
    payload = js_result.result if isinstance(js_result.result, dict) else {}
    unresolved_fields = tuple(
        normalize
        for item in payload.get("unresolved_fields", [])
        if (normalize := str(item or "").strip())
    )
    selected_fields = tuple(
        normalize
        for item in payload.get("selected_fields", [])
        if (normalize := str(item or "").strip())
    )
    if not selected_fields and int(payload.get("selected_count") or 0) > 0:
        selected_fields = ("Autocomplete",)
    status = "ok" if selected_fields and not unresolved_fields else "blocked"
    return _autocomplete_result(
        ctx=ctx,
        normalized_url=normalized_url,
        status=status,
        attempted_count=int(payload.get("attempted_count") or 0),
        selected_count=int(payload.get("selected_count") or 0),
        submitted=bool(payload.get("submitted")),
        unresolved_fields=unresolved_fields,
        selected_fields=selected_fields,
        final_url=str(payload.get("final_url") or "").strip(),
        blocker_code=(
            "blocked_unknown_required_enum" if unresolved_fields else None
        ),
    )


def _autocomplete_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    status: str,
    attempted_count: int = 0,
    selected_count: int = 0,
    submitted: bool = False,
    unresolved_fields: tuple[str, ...] = (),
    selected_fields: tuple[str, ...] = (),
    final_url: str = "",
    blocker_code: str | None = None,
    error: str = "",
) -> BrowserHelperAutocompleteResult:
    result = BrowserHelperAutocompleteResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status=status,
        attempted_count=attempted_count,
        selected_count=selected_count,
        submitted=submitted,
        unresolved_fields=unresolved_fields,
        selected_fields=selected_fields,
        final_url=final_url,
        blocker_code=blocker_code,
        error=_excerpt(error, _HTML_EXCERPT_CHARS),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_form_autocomplete_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "attempted_count": result.attempted_count,
                "selected_count": result.selected_count,
                "submitted": result.submitted,
                "unresolved_fields": list(result.unresolved_fields),
                "selected_fields": list(result.selected_fields),
                "blocker_code": result.blocker_code or "",
                "error": result.error,
            },
        )
    )
    return result


async def browser_helper_js_async(
    *,
    page: Any,
    expression: str,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
    timeout_seconds: float = _HELPER_AWAIT_TIMEOUT_SECONDS,
) -> BrowserHelperJsResult:
    snippet = _snippet(expression)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_start",
            module=logger.name,
            fields={"normalized_url": normalized_url, "snippet": snippet},
        )
    )
    evaluate = getattr(page, "evaluate", None) if page is not None else None
    if not callable(evaluate):
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error="page.evaluate is unavailable",
            required=required,
        )
    try:
        raw_result = await asyncio.wait_for(
            _await_async(evaluate(_wrap_js_expression(expression))),
            timeout=timeout_seconds,
        )
        result_value, serializable = _adapt_js_result_value(raw_result)
    except AppError:
        raise
    except _JavaScriptEvaluationError as exc:
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error=exc.error,
            required=required,
            error_line=exc.error_line,
            error_column=exc.error_column,
        )
    except Exception as exc:
        error_line, error_column = _extract_error_location(str(exc))
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error=str(exc),
            required=required,
            error_line=error_line,
            error_column=error_column,
        )
    result = BrowserHelperJsResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        result=result_value,
        result_type=type(result_value).__name__,
        snippet=snippet,
        result_serializable=serializable,
        error="",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "result_type": result.result_type,
                "result_serializable": result.result_serializable,
            },
        )
    )
    return result


def browser_helper_wait_for_load(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
    state: str = "networkidle",
    timeout_seconds: float = 8.0,
    required: bool = False,
) -> BrowserHelperWaitResult:
    waited_for = str(state or "networkidle").strip() or "networkidle"
    started = time.monotonic()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_wait_for_load_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "state": waited_for,
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        wait_for_load_state = (
            getattr(page, "wait_for_load_state", None) if page is not None else None
        )
        if callable(wait_for_load_state):
            try:
                value = wait_for_load_state(
                    waited_for,
                    timeout=int(timeout_seconds * 1000),
                )
            except TypeError:
                value = wait_for_load_state(waited_for)
            _maybe_await(value, timeout_seconds=timeout_seconds)
        else:
            wait = getattr(browser, "wait", None)
            if callable(wait):
                _maybe_await(wait(min(max(timeout_seconds, 0.0), 2.0)))
            elif _looks_like_browser_use_session(browser):
                time.sleep(min(max(timeout_seconds, 0.0), 2.0))
            else:
                raise RuntimeError(
                    "no browser or page load wait primitive is available"
                )
    except Exception as exc:
        elapsed = round(time.monotonic() - started, 3)
        if required:
            raise AppError(
                code="browser_helper_wait_for_load_failed",
                message="Browser helper wait_for_load failed",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url, "state": waited_for},
            ) from exc
        result = BrowserHelperWaitResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="failed",
            waited_for=waited_for,
            elapsed_seconds=elapsed,
            error=str(exc),
        )
        _log_wait_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    result = BrowserHelperWaitResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        waited_for=waited_for,
        elapsed_seconds=round(time.monotonic() - started, 3),
        error="",
    )
    _log_wait_result(ctx=ctx, normalized_url=normalized_url, result=result)
    return result


def browser_helper_ensure_real_tab(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperRealTabResult:
    page_info = browser_helper_page_info(
        browser=browser,
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if page_info.is_real_tab:
        result = BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="ok",
            is_real_tab=True,
            url=page_info.url,
            title=page_info.title,
            target_id="",
            error="",
        )
        _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    result = _find_real_tab_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if result.is_real_tab:
        _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    if required:
        raise AppError(
            code="browser_helper_real_tab_unavailable",
            message="Browser helper could not find a user-facing browser tab",
            retryable=True,
            context={"normalized_url": normalized_url, "error": result.error},
        )
    _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
    return result


def browser_helper_http_get(
    *,
    url: str,
    ctx: RunContext,
    normalized_url: str,
    timeout_seconds: float = 20.0,
    max_body_bytes: int = 262144,
) -> BrowserHelperHttpGetResult:
    token = str(url or "").strip()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_http_get_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": token,
                "timeout_seconds": timeout_seconds,
                "max_body_bytes": max_body_bytes,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_helper_http_get",
                method="GET",
                url=token,
                headers={
                    "User-Agent": "MarketlenseBrowserHelper/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout_seconds=max(float(timeout_seconds), 1.0),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_binary=False,
                    capture_content_type_markers=(),
                    max_body_bytes=max(int(max_body_bytes), 1),
                    truncate_body=True,
                ),
                error_code="browser_helper_http_get_failed",
                error_message="Browser helper HTTP GET failed",
                allow_redirects=True,
                context_fields={"normalized_url": normalized_url},
            ),
            ctx=ctx,
        )
    except AppError as exc:
        result = BrowserHelperHttpGetResult(
            schema_version="1.0",
            status="failed",
            request_url=token,
            final_url="",
            status_code=0,
            content_type="",
            body_size_bytes=0,
            body_excerpt="",
            body_truncated=False,
            error=exc.message,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_helper_http_get_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "url": token,
                    "error_code": exc.code,
                    "error": exc.message,
                },
            )
        )
        return result
    body = str(response.text_body or "")
    result = BrowserHelperHttpGetResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        request_url=response.request_url,
        final_url=response.final_url,
        status_code=response.status_code,
        content_type=response.content_type,
        body_size_bytes=len(body.encode("utf-8")),
        body_excerpt=_excerpt(body, _HTML_EXCERPT_CHARS),
        body_truncated=response.body_truncated,
        error=None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_http_get_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": result.request_url,
                "final_url": result.final_url,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "body_size_bytes": result.body_size_bytes,
                "body_truncated": result.body_truncated,
            },
        )
    )
    return result


def _screenshot_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    screenshot_path: Path,
    source: str,
) -> BrowserHelperScreenshot:
    result = BrowserHelperScreenshot(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        path=str(screenshot_path),
        source=source,
        size_bytes=screenshot_path.stat().st_size if screenshot_path.exists() else 0,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "path": result.path,
                "source": result.source,
                "size_bytes": result.size_bytes,
            },
        )
    )
    return result


def _try_screenshot_call(*, candidate: Any, screenshot_path: Path) -> bool:
    if not callable(candidate):
        return False
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    call_shapes = (
        {"path": str(screenshot_path), "full_page": True},
        {"path": str(screenshot_path), "fullPage": True},
        {"path": str(screenshot_path)},
    )
    for kwargs in call_shapes:
        try:
            value = _maybe_await(candidate(**kwargs))
        except TypeError:
            continue
        except Exception:
            return False
        if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
            return True
        if isinstance(value, bytes) and value:
            screenshot_path.write_bytes(value)
            return screenshot_path.exists() and screenshot_path.stat().st_size > 0
        if isinstance(value, str) and value.strip():
            screenshot_path.write_text(value, encoding="utf-8")
            return screenshot_path.exists() and screenshot_path.stat().st_size > 0
    try:
        value = _maybe_await(candidate(str(screenshot_path)))
    except Exception:
        return False
    if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
        return True
    if isinstance(value, bytes) and value:
        screenshot_path.write_bytes(value)
        return screenshot_path.exists() and screenshot_path.stat().st_size > 0
    return False


def _js_failure(
    *,
    ctx: RunContext,
    normalized_url: str,
    snippet: str,
    error: str,
    required: bool,
    error_line: int | None = None,
    error_column: int | None = None,
) -> BrowserHelperJsResult:
    sanitized_error = _excerpt(error, _HTML_EXCERPT_CHARS)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_failed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "error": sanitized_error,
                "error_line": error_line,
                "error_column": error_column,
                "required": required,
            },
        )
    )
    if required:
        raise AppError(
            code="browser_helper_js_failed",
            message="Browser helper JavaScript evaluation failed",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "error": sanitized_error,
                "error_line": error_line,
                "error_column": error_column,
            },
        )
    return BrowserHelperJsResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        result=None,
        result_type="NoneType",
        snippet=snippet,
        result_serializable=True,
        error=sanitized_error,
        error_line=error_line,
        error_column=error_column,
    )


async def _await_async(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _adapt_js_result_value(raw_result: object) -> tuple[object, bool]:
    raw_result = _coerce_json_envelope(raw_result)
    if _is_js_error_envelope(raw_result):
        raise _JavaScriptEvaluationError(
            error=str(raw_result.get("error") or "JavaScript evaluation failed"),
            error_line=_coerce_optional_int(raw_result.get("line")),
            error_column=_coerce_optional_int(raw_result.get("column")),
        )
    result_value = _unwrap_js_success_envelope(raw_result)
    serializable = _is_json_serializable(result_value)
    if not serializable:
        return _excerpt(repr(result_value), _HTML_EXCERPT_CHARS), False
    return result_value, True


def _coerce_json_envelope(raw_result: object) -> object:
    if not isinstance(raw_result, str):
        return raw_result
    token = raw_result.strip()
    if "__marketlense_js_helper" not in token:
        return raw_result
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return raw_result
    return parsed if isinstance(parsed, dict) else raw_result


def _wrap_js_expression(expression: str) -> str:
    token = str(expression or "").strip()
    if not token:
        body = "return null;"
    elif _looks_like_js_function(token):
        body = f"return await ({token})();"
    elif _looks_like_statement_script(token):
        body = token
    else:
        body = f"return ({token});"
    return f"""
    (...args) => {{
      const __marketlenseSnippet = {json.dumps(_snippet(token))};
      return (async () => {{
        try {{
          const __marketlenseValue = await (async () => {{
            {body}
          }})();
          return {{
            __marketlense_js_helper: true,
            ok: true,
            result: __marketlenseValue,
            result_type: typeof __marketlenseValue
          }};
        }} catch (__marketlenseError) {{
          const __marketlenseStack = String(__marketlenseError?.stack || '');
          const __marketlenseLocation =
            __marketlenseStack.match(/<anonymous>:(\\d+):(\\d+)/)
            || __marketlenseStack.match(/:(\\d+):(\\d+)\\)?$/m);
          return {{
            __marketlense_js_helper: true,
            ok: false,
            error: String(__marketlenseError?.message || __marketlenseError || 'JavaScript evaluation failed'),
            name: String(__marketlenseError?.name || 'Error'),
            line: Number(__marketlenseError?.lineNumber || (__marketlenseLocation && __marketlenseLocation[1]) || 0) || null,
            column: Number(__marketlenseError?.columnNumber || (__marketlenseLocation && __marketlenseLocation[2]) || 0) || null,
            snippet: __marketlenseSnippet
          }};
        }}
      }})();
    }}
    """


def _looks_like_js_function(token: str) -> bool:
    stripped = token.lstrip()
    return (
        stripped.startswith("()")
        or stripped.startswith("async")
        or stripped.startswith("function")
        or bool(re.match(r"^\([^)]*\)\s*=>", stripped))
    )


def _looks_like_statement_script(token: str) -> bool:
    stripped = token.lstrip()
    return (
        bool(re.search(r"\breturn\b", stripped))
        or stripped.startswith("throw ")
        or stripped.startswith("throw\n")
        or stripped.endswith(";")
    )


def _is_js_error_envelope(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("__marketlense_js_helper") is True
        and value.get("ok") is False
    )


def _unwrap_js_success_envelope(value: object) -> object:
    if (
        isinstance(value, dict)
        and value.get("__marketlense_js_helper") is True
        and value.get("ok") is True
    ):
        return value.get("result")
    return value


def _is_json_serializable(value: object) -> bool:
    try:
        json.dumps(value, ensure_ascii=True)
    except (TypeError, ValueError):
        return False
    return True


def _coerce_optional_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _extract_error_location(error: str) -> tuple[int | None, int | None]:
    line_match = re.search(r"['\"]lineNumber['\"]\s*:\s*(\d+)", str(error or ""))
    column_match = re.search(r"['\"]columnNumber['\"]\s*:\s*(\d+)", str(error or ""))
    if line_match or column_match:
        return (
            _coerce_optional_int(line_match.group(1)) if line_match else None,
            _coerce_optional_int(column_match.group(1)) if column_match else None,
        )
    match = re.search(r":(\d+):(\d+)\)?", str(error or ""))
    if not match:
        return None, None
    return _coerce_optional_int(match.group(1)), _coerce_optional_int(match.group(2))


def _log_wait_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserHelperWaitResult,
) -> None:
    event = (
        "browser_helper_wait_for_load_complete"
        if result.status == "ok"
        else "browser_helper_wait_for_load_failed"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "waited_for": result.waited_for,
                "elapsed_seconds": result.elapsed_seconds,
                "error": result.error,
            },
        )
    )


def _find_real_tab_via_cdp(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserHelperRealTabResult:
    try:
        call_result = call_browser_download_cdp(
            browser=browser,
            method="Target.getTargets",
            params={},
            ctx=ctx,
            normalized_url=normalized_url,
            required=False,
        )
    except Exception as exc:
        return BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="failed",
            is_real_tab=False,
            url="",
            title="",
            target_id="",
            error=str(exc),
        )
    targets = call_result.result.get("targetInfos")
    if not isinstance(targets, list):
        targets = []
    for raw_target in reversed(targets):
        if not isinstance(raw_target, dict):
            continue
        target_type = str(raw_target.get("type") or "").strip()
        url = str(raw_target.get("url") or "").strip()
        if target_type != "page" or not _is_real_tab_url(url):
            continue
        return BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="ok",
            is_real_tab=True,
            url=url,
            title=str(raw_target.get("title") or "").strip(),
            target_id=str(raw_target.get("targetId") or "").strip(),
            error="",
        )
    return BrowserHelperRealTabResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        is_real_tab=False,
        url="",
        title="",
        target_id="",
        error="no user-facing page target found",
    )


def _log_real_tab_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserHelperRealTabResult,
) -> None:
    event = (
        "browser_helper_real_tab_complete"
        if result.status == "ok"
        else "browser_helper_real_tab_failed"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "is_real_tab": result.is_real_tab,
                "url": result.url,
                "title": result.title,
                "target_id": result.target_id,
                "error": result.error,
            },
        )
    )


def _first_non_empty(candidates: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    for label, value in candidates:
        token = str(value or "")
        if token.strip():
            return token, label
    return "", ""


def _looks_like_browser_use_session(browser: Any) -> bool:
    return callable(getattr(browser, "navigate_to", None)) and callable(
        getattr(browser, "get_current_page", None)
    )


def _read_browser_url(browser: Any) -> str:
    token = str(getattr(browser, "url", "") or "").strip()
    return "" if token in {"", "about:blank"} else token


def _read_browser_title(browser: Any) -> str:
    return str(getattr(browser, "title", "") or "").strip()


def _read_browser_html(browser: Any) -> str:
    return str(getattr(browser, "html", "") or "")


def _read_browser_current_page_url(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_url", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    return "" if token in {"", "about:blank"} else token


def _read_browser_current_page_title(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_title", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    return "" if token in {"", "Unknown page title"} else token


def _read_page_url(page: Any) -> str:
    if page is None:
        return ""
    try:
        candidate = getattr(page, "url", "")
        if callable(candidate):
            candidate = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(candidate or "").strip()
    return "" if token in {"", "about:blank"} else token


def _read_page_title(page: Any) -> str:
    if page is None:
        return ""
    for attribute in ("title", "get_title"):
        try:
            candidate = getattr(page, attribute, None)
        except Exception:
            continue
        if candidate is None:
            continue
        try:
            value = _maybe_await(candidate()) if callable(candidate) else candidate
        except Exception:
            continue
        token = str(value or "").strip()
        if token:
            return token
    return ""


def _read_page_html(page: Any) -> str:
    if page is None:
        return ""
    for attribute in ("content", "get_content"):
        try:
            candidate = getattr(page, attribute, None)
        except Exception:
            continue
        if candidate is None:
            continue
        try:
            value = _maybe_await(candidate()) if callable(candidate) else candidate
        except Exception:
            continue
        token = str(value or "")
        if token.strip():
            return token
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            value = _maybe_await(
                evaluate("() => document.documentElement?.outerHTML || ''")
            )
        except Exception:
            return ""
        token = str(value or "")
        if token.strip():
            return token
    return str(getattr(page, "html", "") or "")


def _is_real_tab_url(url: str) -> bool:
    token = str(url or "").strip()
    if not token:
        return False
    return not any(token.startswith(prefix) for prefix in _INTERNAL_TARGET_URL_PREFIXES)


def _maybe_await(value: Any, *, timeout_seconds: float | None = None) -> Any:
    if not inspect.isawaitable(value):
        return value
    timeout = timeout_seconds or _HELPER_AWAIT_TIMEOUT_SECONDS
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    async def awaitable() -> Any:
        return await value

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(
                asyncio.wait_for(awaitable(), timeout=timeout)
            )
        except BaseException as exc:
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(awaitable(), timeout=timeout))

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("browser helper operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _snippet(expression: str) -> str:
    return _excerpt(
        re.sub(r"\s+", " ", str(expression or "")).strip(), _JS_SNIPPET_CHARS
    )


def _excerpt(value: str, max_chars: int) -> str:
    token = str(value or "").strip()
    if len(token) <= max_chars:
        return token
    return f"{token[: max_chars - 3]}..."
