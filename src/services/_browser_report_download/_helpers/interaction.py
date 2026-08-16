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
    BrowserHelperStandardFormSubmitResult,
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
    "browser_helper_standard_form_submit",
    "_autocomplete_result",
    "_standard_form_submit_result",
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
          const rootDocuments = (() => {{
            const roots = sameOriginDocuments();
            for (let index = 0; index < roots.length; index += 1) {{
              for (const node of Array.from(roots[index].querySelectorAll('*'))) {{
                if (node.shadowRoot && !roots.includes(node.shadowRoot)) {{
                  roots.push(node.shadowRoot);
                }}
              }}
            }}
            return roots;
          }})();
          const rootForControl = new WeakMap();
          const controls = rootDocuments.flatMap((root) =>
            Array.from(root.querySelectorAll([
            'input[role="combobox"]',
            'input[aria-autocomplete]',
            'input.lookup-behavior',
            '.lookupFormFieldBlock input',
            '[role="combobox"]',
            '[aria-haspopup="listbox"]',
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
          const visibleOptions = () => rootDocuments.flatMap((root) => Array.from(root.querySelectorAll([
            '[role="option"]',
            '[role="listbox"] [role="option"]',
            '.ui-menu-item-wrapper',
            '.ui-menu-item',
            'li[role="presentation"]',
            'li',
            '[data-value]',
            '[data-testid*="option" i]',
          ].join(',')))).slice(0, 120).filter((node) =>
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
            // A select value is an identity assertion.  Never turn an unknown
            // required enum into a technically valid submission by choosing its
            // first enabled option.
            const option = exactOption;
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
            const verified = !invalid && persisted && tokenMatchesAny(persisted, field);
            if (verified && option) {{
              field.selectionVerification = {{
                field_label: field.label || 'Select',
                option_text: normalize(option.textContent || option.value),
                mode: 'configured_match',
                persisted: true,
              }};
            }}
            return verified;
          }};
          const selectedFields = [];
          const selectionVerification = [];
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
              }} else if (
                String(control.getAttribute('role') || '').toLowerCase() === 'combobox' ||
                String(control.getAttribute('aria-haspopup') || '').toLowerCase() === 'listbox'
              ) {{
                control.focus();
                control.click();
                const options = visibleOptions();
                const option = options.find((node) =>
                  !looksLikePlaceholderOption(node.innerText || node.textContent) &&
                  tokenMatchesAny(node.innerText || node.textContent, field)
                );
                if (option) clickOption(option);
                dispatchKey(control, 'keydown', 'Tab');
                dispatchKey(control, 'keyup', 'Tab');
                control.blur();
                const persisted = keyToken(
                  control.getAttribute('aria-valuetext') ||
                  control.getAttribute('value') ||
                  control.value ||
                  control.innerText ||
                  control.textContent ||
                  ''
                );
                selected = Boolean(option) && tokenMatchesAny(persisted, field);
                if (selected) {{
                  field.selectionVerification = {{
                    field_label: field.label || label,
                    option_text: normalize(option.innerText || option.textContent),
                    mode: 'configured_custom_select_match',
                    persisted: true,
                  }};
                }}
              }} else {{
                typeText(control, field.value);
                const options = visibleOptions();
                const exactOption = options.find((node) =>
                  tokenMatchesAny(node.innerText || node.textContent, field)
                );
                const option = exactOption;
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
                selected = !invalid && persisted && tokenMatchesAny(persisted, field);
                if (selected && option) {{
                  field.selectionVerification = {{
                    field_label: field.label || label,
                    option_text: normalize(option.innerText || option.textContent),
                    mode: 'configured_match',
                    persisted: true,
                  }};
                }}
              }}
              if (selected) {{
                selectedControls.add(control);
                selectedFields.push(label);
                if (field.selectionVerification) {{
                  selectionVerification.push({{
                    ...field.selectionVerification,
                    field_label: label,
                  }});
                }}
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
                text.includes('send') ||
                text.includes('access') ||
                text.includes('unlock') ||
                text.includes('resource')
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
            selection_verification: selectionVerification,
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
    selection_verification = tuple(
        {
            "field_label": str(item.get("field_label") or "").strip(),
            "option_text": str(item.get("option_text") or "").strip(),
            "mode": str(item.get("mode") or "").strip(),
            "persisted": bool(item.get("persisted")),
        }
        for item in payload.get("selection_verification", [])
        if isinstance(item, dict)
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
        selection_verification=selection_verification,
        final_url=str(payload.get("final_url") or "").strip(),
        blocker_code=("blocked_unknown_required_enum" if unresolved_fields else None),
    )


def browser_helper_standard_form_submit(
    *,
    page: Any,
    field_values: list[dict[str, object]],
    ctx: RunContext,
    normalized_url: str,
    browser: Any | None = None,
) -> BrowserHelperStandardFormSubmitResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_standard_form_submit_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "field_value_count": len(field_values),
            },
        )
    )
    script_payload = {"fields": field_values}
    expression = f"""
        return (() => {{
          const standardFormSubmit = true;
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
          const dispatchChanged = (node) => {{
            node.dispatchEvent(new Event('input', {{ bubbles: true }}));
            node.dispatchEvent(new Event('change', {{ bubbles: true }}));
          }};
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
          const fieldEntries = (payload.fields || [])
            .map((field) => ({{
              key: normalize(field.key || ''),
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
              '.mktoFormRow, .hs-form-field, .form-field, .field, label, div, li'
            );
            if (wrapper) {{
              const wrapperText = normalize(wrapper.textContent || '');
              if (wrapperText.length <= 220) values.push(wrapperText);
            }}
            return values.map(normalize).filter(Boolean);
          }};
          const labelTokenFor = (control, root = control.ownerDocument || document) =>
            labelsFor(control, root).map(keyToken).join(' ');
          const matchField = (control, root = control.ownerDocument || document) => {{
            const joined = labelTokenFor(control, root);
            for (const field of fieldEntries) {{
              if (field.aliases.some((alias) => joined.includes(alias))) {{
                return field;
              }}
            }}
            return null;
          }};
          const placeholderOption = (value) => {{
            const token = keyToken(value);
            if (!token) return true;
            return token === 'select' ||
              token === 'please select' ||
              token === 'select one' ||
              token === 'choose' ||
              token === 'choose one' ||
              token.includes('please select') ||
              token.includes('select...');
          }};
          const optionMatches = (optionText, field) => {{
            const token = keyToken(optionText);
            if (!token || !field) return false;
            return (field.optionAliases || []).some((wanted) =>
              token === wanted || token.includes(wanted) || wanted.includes(token)
            );
          }};
          const requiredLike = (control) =>
            control.required ||
            String(control.getAttribute('aria-required') || '').toLowerCase() === 'true';
          const optionalMarketing = (text) =>
            /\\b(optional|newsletter|marketing|promotion|promotional|demo|sales|contact me|updates?|events?|offers?|communications?)\\b/i.test(text);
          const mandatoryAgreement = (text) =>
            /\\b(agree|agreement|privacy|terms|policy|consent)\\b/i.test(text) &&
            !optionalMarketing(text);
          const roots = sameOriginDocuments();
          const resolvedFields = [];
          const unresolvedFields = [];
          const unresolvedOptions = {{}};
          let attemptedCount = 0;
          let filledCount = 0;
          let selectedCount = 0;
          let mandatoryAgreementCheckedCount = 0;
          let resolvedControlCount = 0;
          const rememberResolved = (label) => {{
            const token = normalize(label || 'Standard form control');
            if (token && !resolvedFields.includes(token)) resolvedFields.push(token);
          }};
          for (const root of roots) {{
            for (const control of Array.from(root.querySelectorAll(
              'input:not([type]), input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input[role="combobox"], textarea'
            ))) {{
              if (!isVisible(control) || control.disabled || control.readOnly) continue;
              const field = matchField(control, root);
              if (!field || !field.value) {{
                if (requiredLike(control)) {{
                  unresolvedFields.push(labelsFor(control, root)[0] || 'text field');
                }}
                continue;
              }}
              const current = normalize(control.value || '');
              const invalid = String(control.getAttribute('aria-invalid') || '').toLowerCase() === 'true';
              if (current && !invalid) {{
                resolvedControlCount += 1;
                rememberResolved(field.label || labelsFor(control, root)[0]);
                continue;
              }}
              attemptedCount += 1;
              control.focus();
              control.value = field.value;
              dispatchChanged(control);
              control.blur();
              const verified = normalize(control.value || '') === field.value;
              if (verified) {{
                filledCount += 1;
                rememberResolved(field.label || labelsFor(control, root)[0]);
              }} else if (requiredLike(control)) {{
                unresolvedFields.push(field.label || labelsFor(control, root)[0] || 'text field');
              }}
            }}
            for (const control of Array.from(root.querySelectorAll('select'))) {{
              if (!isVisible(control) || control.disabled) continue;
              const currentOption = control.selectedOptions && control.selectedOptions[0];
              const currentText = normalize(
                (currentOption ? currentOption.textContent || '' : '') || control.value || ''
              );
              const field = matchField(control, root);
              const mustRepair = requiredLike(control) || placeholderOption(currentText) || Boolean(field);
              if (!mustRepair) continue;
              const options = Array.from(control.options || []).filter((option) =>
                !option.disabled && keyToken(option.textContent || option.value)
              );
              const exact = field ? options.find((option) =>
                optionMatches(option.textContent || option.value, field)
              ) : null;
              const option = exact;
              if (!option) {{
                if (requiredLike(control)) {{
                  const label = labelsFor(control, root)[0] || 'select';
                  unresolvedFields.push(label);
                  unresolvedOptions[label] = options.map((candidate) =>
                    normalize(candidate.textContent || candidate.value || '')
                  ).filter((candidate) => !placeholderOption(candidate));
                }}
                continue;
              }}
              attemptedCount += 1;
              control.focus();
              control.value = option.value;
              option.selected = true;
              dispatchChanged(control);
              control.blur();
              const selectedOption = control.selectedOptions && control.selectedOptions[0];
              const selectedText = normalize(
                (selectedOption ? selectedOption.textContent || '' : '') || control.value || ''
              );
              if (selectedText && !placeholderOption(selectedText)) {{
                selectedCount += 1;
                resolvedControlCount += 1;
                rememberResolved((field && field.label) || labelsFor(control, root)[0] || selectedText);
              }} else if (requiredLike(control)) {{
                unresolvedFields.push((field && field.label) || labelsFor(control, root)[0] || 'select');
              }}
            }}
            for (const control of Array.from(root.querySelectorAll('input[type="checkbox"]'))) {{
              if (!isVisible(control) || control.disabled) continue;
              const label = labelsFor(control, root).join(' ');
              if (!mandatoryAgreement(label)) {{
                if (requiredLike(control)) {{
                  unresolvedFields.push(label || 'checkbox');
                }}
                continue;
              }}
              attemptedCount += 1;
              if (!control.checked) {{
                control.checked = true;
                dispatchChanged(control);
              }}
              if (control.checked) {{
                mandatoryAgreementCheckedCount += 1;
                resolvedControlCount += 1;
                rememberResolved(label || 'Privacy agreement');
              }} else {{
                unresolvedFields.push(label || 'Privacy agreement');
              }}
            }}
          }}
          let submitted = false;
          const progressCount = filledCount + selectedCount + mandatoryAgreementCheckedCount;
          if ((progressCount > 0 || resolvedControlCount > 0) && unresolvedFields.length === 0) {{
            const submitButton = roots.flatMap((root) =>
              Array.from(root.querySelectorAll(
                'button[type="submit"], input[type="submit"], button'
              ))
            ).find((node) => {{
              const text = keyToken(node.innerText || node.textContent || node.value || '');
              return isVisible(node) && !node.disabled && (
                text === 'submit' ||
                text.includes('submit') ||
                text.includes('download') ||
                text.includes('send') ||
                text.includes('request') ||
                text.includes('get') ||
                text.includes('access') ||
                text.includes('unlock') ||
                text.includes('resource')
              );
            }});
            if (submitButton) {{
              submitButton.click();
              submitted = true;
            }}
          }}
          return {{
            attempted_count: attemptedCount,
            filled_count: filledCount,
            selected_count: selectedCount,
            mandatory_agreement_checked_count: mandatoryAgreementCheckedCount,
            mandatoryAgreementCheckedCount,
            resolved_control_count: resolvedControlCount,
            submitted,
            final_url: window.location.href || '',
            resolved_fields: resolvedFields,
            unresolved_fields: unresolvedFields,
            unresolved_options: unresolvedOptions,
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
    if browser is not None and not _is_standard_form_submit_js_payload(
        js_result.result
    ):
        js_result = browser_helper_js(
            page=page,
            expression=expression,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    if js_result.status != "ok":
        return _standard_form_submit_result(
            ctx=ctx,
            normalized_url=normalized_url,
            status="failed",
            error=js_result.error,
        )
    payload = js_result.result if isinstance(js_result.result, dict) else {}
    unresolved_fields = tuple(
        normalized
        for item in payload.get("unresolved_fields", [])
        if (normalized := str(item or "").strip())
    )
    unresolved_options = {
        str(label).strip(): tuple(
            str(option).strip() for option in options if str(option).strip()
        )
        for label, options in dict(payload.get("unresolved_options") or {}).items()
        if str(label).strip() and isinstance(options, list)
    }
    resolved_fields = tuple(
        normalized
        for item in payload.get("resolved_fields", [])
        if (normalized := str(item or "").strip())
    )
    progress_count = (
        int(payload.get("filled_count") or 0)
        + int(payload.get("selected_count") or 0)
        + int(payload.get("mandatory_agreement_checked_count") or 0)
    )
    resolved_control_count = int(payload.get("resolved_control_count") or 0)
    status = (
        "ok"
        if (progress_count > 0 or resolved_control_count > 0) and not unresolved_fields
        else "blocked"
    )
    return _standard_form_submit_result(
        ctx=ctx,
        normalized_url=normalized_url,
        status=status,
        attempted_count=int(payload.get("attempted_count") or 0),
        filled_count=int(payload.get("filled_count") or 0),
        selected_count=int(payload.get("selected_count") or 0),
        mandatory_agreement_checked_count=int(
            payload.get("mandatory_agreement_checked_count") or 0
        ),
        submitted=bool(payload.get("submitted")),
        unresolved_fields=unresolved_fields,
        unresolved_options=unresolved_options,
        resolved_fields=resolved_fields,
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


def _is_standard_form_submit_js_payload(value: object) -> bool:
    return isinstance(value, dict) and any(
        key in value
        for key in (
            "filled_count",
            "selected_count",
            "mandatory_agreement_checked_count",
            "mandatoryAgreementCheckedCount",
            "resolved_fields",
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
    selection_verification: tuple[dict[str, object], ...] = (),
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
        selection_verification=selection_verification,
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
                "selection_verification": list(result.selection_verification),
                "blocker_code": result.blocker_code or "",
                "error": result.error,
            },
        )
    )
    return result


def _standard_form_submit_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    status: str,
    attempted_count: int = 0,
    filled_count: int = 0,
    selected_count: int = 0,
    mandatory_agreement_checked_count: int = 0,
    submitted: bool = False,
    unresolved_fields: tuple[str, ...] = (),
    unresolved_options: dict[str, tuple[str, ...]] | None = None,
    resolved_fields: tuple[str, ...] = (),
    final_url: str = "",
    blocker_code: str | None = None,
    error: str = "",
) -> BrowserHelperStandardFormSubmitResult:
    result = BrowserHelperStandardFormSubmitResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status=status,
        attempted_count=attempted_count,
        filled_count=filled_count,
        selected_count=selected_count,
        mandatory_agreement_checked_count=mandatory_agreement_checked_count,
        submitted=submitted,
        unresolved_fields=unresolved_fields,
        unresolved_options=dict(unresolved_options or {}),
        resolved_fields=resolved_fields,
        final_url=final_url,
        blocker_code=blocker_code,
        error=_excerpt(error, _HTML_EXCERPT_CHARS),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_standard_form_submit_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "attempted_count": result.attempted_count,
                "filled_count": result.filled_count,
                "selected_count": result.selected_count,
                "mandatory_agreement_checked_count": (
                    result.mandatory_agreement_checked_count
                ),
                "submitted": result.submitted,
                "unresolved_fields": list(result.unresolved_fields),
                "resolved_fields": list(result.resolved_fields),
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
