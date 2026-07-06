"""Browser interaction helpers for report-download automation.

This module owns screenshot capture and form autocomplete recovery. It may
consume JavaScript inspection but does not own page-state diagnostics or HTTP
inspection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperAutocompleteResult,
    BrowserHelperScreenshot,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    capture_terminal_screenshot_via_cdp,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .inspection import browser_helper_js, browser_helper_js_via_cdp
from .state import _HELPER_SCHEMA_VERSION, _HTML_EXCERPT_CHARS, _excerpt, _maybe_await

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

__all__ = (
    "browser_helper_capture_screenshot",
    "browser_helper_form_autocomplete",
    "_autocomplete_result",
    "_screenshot_result",
    "_try_screenshot_call",
)


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


def browser_helper_form_autocomplete(
    *,
    page: Any,
    field_values: list[dict[str, object]],
    ctx: RunContext,
    normalized_url: str,
    submit: bool = True,
    browser: Any | None = None,
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
    expression = f"""
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
              optionAliases: [
                field.value,
                ...(Array.isArray(field.option_aliases) ? field.option_aliases : []),
              ].map(keyToken).filter(Boolean),
            }}))
            .filter((field) => field.value);
          const sameOriginDocuments = () => {{
            const roots = [document];
            for (const frame of Array.from(document.querySelectorAll('iframe'))) {{
              try {{
                const frameDocument = frame.contentDocument;
                if (
                  frameDocument &&
                  frameDocument.documentElement &&
                  !roots.includes(frameDocument)
                ) {{
                  roots.push(frameDocument);
                }}
              }} catch (error) {{
                // Cross-origin frames are intentionally skipped.
              }}
            }}
            return roots;
          }};
          const labelsFor = (control, root = control.ownerDocument || document) => {{
            const values = [];
            const id = control.getAttribute('id') || '';
            if (id) {{
              const label = root.querySelector(`label[for="${{CSS.escape(id)}}"]`);
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
              const node = root.getElementById(token);
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
          const matchField = (control, root = control.ownerDocument || document) => {{
            const labels = labelsFor(control, root);
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
          const rootDocuments = sameOriginDocuments();
          const rootForControl = new WeakMap();
          const controls = rootDocuments.flatMap((root) =>
            Array.from(root.querySelectorAll([
            'input[role="combobox"]',
            'input[aria-autocomplete]',
            'input.lookup-behavior',
            '.lookupFormFieldBlock input',
            '[role="combobox"] input',
            'input[name*="country" i]',
            'input[id*="country" i]',
            'input[name*="state" i]',
            'input[id*="state" i]',
            'input[name*="province" i]',
            'input[id*="province" i]',
            'input[name*="region" i]',
            'input[id*="region" i]',
            'select',
            ].join(','))).map((control) => {{
              rootForControl.set(control, root);
              return control;
            }})
          ).filter((control, index, collection) =>
            collection.indexOf(control) === index && isVisible(control)
          );
          const visibleOptions = (root = document) => Array.from(root.querySelectorAll([
            '[role="option"]',
            '[role="listbox"] [role="option"]',
            '.ui-menu-item-wrapper',
            '.ui-menu-item',
            'li[role="presentation"]',
            'li',
            '[data-value]',
            '[data-testid*="option" i]',
          ].join(','))).slice(0, 120).filter((node) =>
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
          const optionTokensFor = (field) => {{
            const tokens = [];
            const seen = new Set();
            for (const rawToken of [field.value, ...(field.optionAliases || [])]) {{
              const token = keyToken(rawToken);
              if (!token || seen.has(token)) continue;
              seen.add(token);
              tokens.push(token);
            }}
            return tokens;
          }};
          const looksLikePlaceholderOption = (value) => {{
            const token = keyToken(value);
            if (!token) return true;
            return token === 'select' ||
              token === 'please select' ||
              token === 'select one' ||
              token === 'choose' ||
              token === 'choose one' ||
              token === 'none' ||
              token.includes('please select') ||
              token.includes('select...');
          }};
          const tokenMatchesAny = (candidate, field) => {{
            const candidateToken = keyToken(candidate);
            if (!candidateToken) return false;
            return optionTokensFor(field).some((wanted) =>
              candidateToken === wanted ||
              candidateToken.includes(wanted) ||
              wanted.includes(candidateToken)
            );
          }};
          const selectNativeOption = (control, field) => {{
            control.focus();
            control.click();
            for (const char of field.value) {{
              dispatchKey(control, 'keydown', char);
              dispatchKey(control, 'keyup', char);
            }}
            const options = Array.from(control.options || []).filter((option) =>
              !option.disabled && keyToken(option.textContent || option.value)
            );
            const exactOption = options.find((node) =>
              tokenMatchesAny(node.textContent || node.value, field)
            );
            const fallbackOption = options.find((node) =>
              !looksLikePlaceholderOption(node.textContent || node.value)
            );
            const option = exactOption || fallbackOption;
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
              tokenMatchesAny(persisted, field) || Boolean(option && !exactOption)
            );
          }};
          const selectedFields = [];
          const unresolvedFields = [];
          let attemptedCount = 0;
          const selectedControls = new Set();
          let latestUnresolvedFields = [];
          for (let passIndex = 0; passIndex < 1; passIndex += 1) {{
            const passUnresolvedFields = [];
            let passProgress = false;
            for (const control of controls) {{
              if (selectedControls.has(control)) continue;
              const root = rootForControl.get(control) || control.ownerDocument || document;
              const field = matchField(control, root);
              if (!field || !field.value) continue;
              const label = normalize(field.label || labelsFor(control, root)[0] || 'Autocomplete');
              attemptedCount += 1;
              let selected = false;
              if (control.tagName && control.tagName.toLowerCase() === 'select') {{
                selected = selectNativeOption(control, field);
              }} else {{
                typeText(control, field.value);
                const options = visibleOptions(root);
                const exactOption = options.find((node) =>
                  tokenMatchesAny(node.innerText || node.textContent, field)
                );
                const fallbackOption = options.find((node) =>
                  !looksLikePlaceholderOption(node.innerText || node.textContent)
                );
                const option = exactOption || fallbackOption;
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
                selected = !invalid && persisted && (
                  tokenMatchesAny(persisted, field) || Boolean(option && !exactOption)
                );
              }}
              if (selected) {{
                selectedControls.add(control);
                selectedFields.push(label);
                passProgress = true;
              }} else {{
                passUnresolvedFields.push(label);
              }}
            }}
            latestUnresolvedFields = passUnresolvedFields;
            if (!latestUnresolvedFields.length || !passProgress) break;
          }}
          for (const label of latestUnresolvedFields) {{
            if (!unresolvedFields.includes(label)) unresolvedFields.push(label);
          }}
          let submitted = false;
          if (payload.submit && selectedFields.length > 0 && unresolvedFields.length === 0) {{
            const submitButton = rootDocuments.flatMap((root) =>
              Array.from(root.querySelectorAll(
                'button[type="submit"], input[type="submit"], button'
              ))
            ).find((node) => {{
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
        """
    if browser is not None:
        js_result = browser_helper_js_via_cdp(
            browser=browser,
            expression=expression,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    else:
        js_result = browser_helper_js(
            page=page,
            expression=expression,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    if browser is not None and not _is_autocomplete_js_payload(js_result.result):
        js_result = browser_helper_js(
            page=page,
            expression=expression,
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


def _is_autocomplete_js_payload(value: object) -> bool:
    return isinstance(value, dict) and any(
        key in value
        for key in (
            "attempted_count",
            "selected_count",
            "selected_fields",
            "unresolved_fields",
        )
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
