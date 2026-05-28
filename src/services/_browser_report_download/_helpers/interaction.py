"""Browser interaction helpers for report-download automation.

This module owns screenshot capture, selector-hostile coordinate fallback, and
form autocomplete recovery. It may consume state readers and JavaScript
inspection but does not own page-state diagnostics or HTTP inspection.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperAutocompleteResult,
    BrowserHelperCoordinateFallbackResult,
    BrowserHelperScreenshot,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    capture_terminal_screenshot_via_cdp,
    dispatch_mouse_click_via_cdp,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .inspection import browser_helper_js
from .state import (
    _HELPER_SCHEMA_VERSION,
    _HTML_EXCERPT_CHARS,
    _excerpt,
    _maybe_await,
    browser_helper_page_info,
)

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

__all__ = (
    "_SELECTOR_HOSTILE_SURFACE_LABELS",
    "browser_helper_capture_screenshot",
    "browser_helper_coordinate_fallback_click",
    "browser_helper_form_autocomplete",
    "_autocomplete_result",
    "_screenshot_result",
    "_coordinate_fallback_result",
    "_coordinate_fallback_policy",
    "_normalize_surface_labels",
    "_has_selector_hostile_surface",
    "_coordinates_are_usable",
    "_after_coordinate_screenshot_path",
    "_try_screenshot_call",
)


_SELECTOR_HOSTILE_SURFACE_LABELS = {
    "autocomplete",
    "canvas",
    "combobox",
    "cross_origin_iframe",
    "custom_dropdown",
    "iframe",
    "map",
    "native_dropdown",
    "pdf_viewer",
    "shadow_dom",
    "virtualized_list",
}


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


def browser_helper_coordinate_fallback_click(
    *,
    browser: Any,
    page: Any,
    screenshot_path: Path,
    coordinate_x: float,
    coordinate_y: float,
    selector_attempted: bool,
    selector_success: bool,
    selector_error: str,
    surface_labels: tuple[str, ...] | list[str],
    ctx: RunContext,
    normalized_url: str,
    target_url: str = "",
    required: bool = False,
) -> BrowserHelperCoordinateFallbackResult:
    labels = _normalize_surface_labels(surface_labels)
    sanitized_selector_error = _excerpt(selector_error, _HTML_EXCERPT_CHARS)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_coordinate_fallback_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": str(target_url or "").strip(),
                "selector_attempted": bool(selector_attempted),
                "selector_success": bool(selector_success),
                "surface_labels": list(labels),
                "coordinate_source": "current_screenshot",
                "required": required,
            },
        )
    )
    before_screenshot = browser_helper_capture_screenshot(
        browser=browser,
        page=page,
        screenshot_path=screenshot_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
    )
    if before_screenshot.status != "ok":
        return _coordinate_fallback_result(
            ctx=ctx,
            normalized_url=normalized_url,
            target_url=target_url,
            status="failed",
            reason="screenshot_required_before_coordinate_click",
            selector_attempted=selector_attempted,
            selector_success=selector_success,
            selector_error=sanitized_selector_error,
            surface_labels=labels,
            before_screenshot_path="",
            after_screenshot_path="",
            verification_status="missing",
            action_source="none",
            error="required pre-action screenshot was unavailable",
            required=required,
        )
    policy_allowed, policy_reason = _coordinate_fallback_policy(
        selector_attempted=selector_attempted,
        selector_success=selector_success,
        selector_error=sanitized_selector_error,
        surface_labels=labels,
        coordinate_x=coordinate_x,
        coordinate_y=coordinate_y,
    )
    if not policy_allowed:
        return _coordinate_fallback_result(
            ctx=ctx,
            normalized_url=normalized_url,
            target_url=target_url,
            status="blocked",
            reason=policy_reason,
            selector_attempted=selector_attempted,
            selector_success=selector_success,
            selector_error=sanitized_selector_error,
            surface_labels=labels,
            before_screenshot_path=before_screenshot.path,
            after_screenshot_path="",
            verification_status="missing",
            action_source="policy",
            error="",
            required=required,
        )
    clicked = dispatch_mouse_click_via_cdp(
        browser=browser,
        coordinate_x=coordinate_x,
        coordinate_y=coordinate_y,
        ctx=ctx,
        normalized_url=normalized_url,
        target_url=target_url,
        required=required,
    )
    if not clicked:
        return _coordinate_fallback_result(
            ctx=ctx,
            normalized_url=normalized_url,
            target_url=target_url,
            status="failed",
            reason="coordinate_click_failed",
            selector_attempted=selector_attempted,
            selector_success=selector_success,
            selector_error=sanitized_selector_error,
            surface_labels=labels,
            before_screenshot_path=before_screenshot.path,
            after_screenshot_path="",
            verification_status="missing",
            action_source="cdp_input_dispatch_mouse_event",
            error="Chrome did not accept the coordinate click",
            required=required,
        )
    after_path = _after_coordinate_screenshot_path(screenshot_path)
    after_screenshot = browser_helper_capture_screenshot(
        browser=browser,
        page=page,
        screenshot_path=after_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    )
    verification_status = "missing"
    after_screenshot_path = ""
    if after_screenshot.status == "ok":
        verification_status = "screenshot"
        after_screenshot_path = after_screenshot.path
    else:
        page_info = browser_helper_page_info(
            browser=browser,
            page=page,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if page_info.url or page_info.title or page_info.html_size > 0:
            verification_status = "page_info"
    return _coordinate_fallback_result(
        ctx=ctx,
        normalized_url=normalized_url,
        target_url=target_url,
        status="ok",
        reason=policy_reason,
        selector_attempted=selector_attempted,
        selector_success=selector_success,
        selector_error=sanitized_selector_error,
        surface_labels=labels,
        before_screenshot_path=before_screenshot.path,
        after_screenshot_path=after_screenshot_path,
        verification_status=verification_status,
        action_source="cdp_input_dispatch_mouse_event",
        error="",
        required=required,
    )


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
        blocker_code=("blocked_unknown_required_enum" if unresolved_fields else None),
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


def _coordinate_fallback_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    target_url: str,
    status: str,
    reason: str,
    selector_attempted: bool,
    selector_success: bool,
    selector_error: str,
    surface_labels: tuple[str, ...],
    before_screenshot_path: str,
    after_screenshot_path: str,
    verification_status: str,
    action_source: str,
    error: str,
    required: bool,
) -> BrowserHelperCoordinateFallbackResult:
    result = BrowserHelperCoordinateFallbackResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status=status,
        reason=reason,
        selector_attempted=bool(selector_attempted),
        selector_success=bool(selector_success),
        selector_error=_excerpt(selector_error, _HTML_EXCERPT_CHARS),
        surface_labels=surface_labels,
        coordinate_source="current_screenshot",
        coordinates_persisted=False,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        verification_status=verification_status,
        action_source=action_source,
        target_url=str(target_url or "").strip(),
        error=_excerpt(error, _HTML_EXCERPT_CHARS),
    )
    event = (
        "browser_helper_coordinate_fallback_complete"
        if status == "ok"
        else "browser_helper_coordinate_fallback_blocked"
        if status == "blocked"
        else "browser_helper_coordinate_fallback_failed"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": result.target_url,
                "status": result.status,
                "reason": result.reason,
                "selector_attempted": result.selector_attempted,
                "selector_success": result.selector_success,
                "surface_labels": list(result.surface_labels),
                "coordinate_source": result.coordinate_source,
                "coordinates_persisted": result.coordinates_persisted,
                "before_screenshot_path": result.before_screenshot_path,
                "after_screenshot_path": result.after_screenshot_path,
                "verification_status": result.verification_status,
                "action_source": result.action_source,
                "error": result.error,
            },
        )
    )
    if required and status == "blocked":
        raise AppError(
            code="browser_helper_coordinate_fallback_blocked",
            message="Browser helper coordinate fallback was blocked by policy",
            retryable=False,
            severity="error",
            context={
                "normalized_url": normalized_url,
                "target_url": result.target_url,
                "reason": result.reason,
                "selector_attempted": result.selector_attempted,
                "selector_success": result.selector_success,
                "surface_labels": list(result.surface_labels),
            },
        )
    if required and status == "failed":
        raise AppError(
            code="browser_helper_coordinate_fallback_failed",
            message="Browser helper coordinate fallback failed",
            retryable=True,
            severity="error",
            context={
                "normalized_url": normalized_url,
                "target_url": result.target_url,
                "reason": result.reason,
                "error": result.error,
            },
        )
    return result


def _coordinate_fallback_policy(
    *,
    selector_attempted: bool,
    selector_success: bool,
    selector_error: str,
    surface_labels: tuple[str, ...],
    coordinate_x: float,
    coordinate_y: float,
) -> tuple[bool, str]:
    if not _coordinates_are_usable(coordinate_x, coordinate_y):
        return False, "invalid_current_screenshot_coordinate"
    if selector_success:
        return False, "selector_already_succeeded"
    if _has_selector_hostile_surface(surface_labels):
        return True, "known_selector_hostile_surface"
    if selector_attempted and str(selector_error or "").strip():
        return True, "selector_failure_to_coordinate_fallback"
    if selector_attempted:
        return True, "selector_attempt_exhausted"
    return False, "selector_or_state_attempt_required"


def _normalize_surface_labels(
    surface_labels: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_label in surface_labels or ():
        label = re.sub(
            r"[^a-z0-9]+", "_", str(raw_label or "").strip().casefold()
        ).strip("_")
        if label and label not in normalized:
            normalized.append(label)
    return tuple(normalized)


def _has_selector_hostile_surface(surface_labels: tuple[str, ...]) -> bool:
    return any(label in _SELECTOR_HOSTILE_SURFACE_LABELS for label in surface_labels)


def _coordinates_are_usable(coordinate_x: float, coordinate_y: float) -> bool:
    try:
        x = float(str(coordinate_x))
        y = float(str(coordinate_y))
    except (TypeError, ValueError):
        return False
    return (
        x >= 0
        and y >= 0
        and x not in {float("inf"), float("-inf")}
        and y
        not in {
            float("inf"),
            float("-inf"),
        }
        and x == x
        and y == y
    )


def _after_coordinate_screenshot_path(screenshot_path: Path) -> Path:
    suffix = screenshot_path.suffix or ".png"
    return screenshot_path.with_name(f"{screenshot_path.stem}-after{suffix}")


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
