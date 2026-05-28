"""Browser inspection helpers for report-download automation.

This module owns bounded JavaScript evaluation, result/error adaptation, and
static HTTP inspection through the shared acquisition service. It consumes
state-level await/excerpt helpers without depending on interaction helpers.
"""

from __future__ import annotations

import json
import logging
import re
import asyncio
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperHttpGetResult,
    BrowserHelperJsResult,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

from .state import (
    _HELPER_AWAIT_TIMEOUT_SECONDS,
    _HELPER_SCHEMA_VERSION,
    _HTML_EXCERPT_CHARS,
    _await_async,
    _excerpt,
    _maybe_await,
)

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

__all__ = (
    "_JS_SNIPPET_CHARS",
    "_JavaScriptEvaluationError",
    "browser_helper_js",
    "browser_helper_js_async",
    "browser_helper_http_get",
    "_js_failure",
    "_adapt_js_result_value",
    "_coerce_json_envelope",
    "_wrap_js_expression",
    "_looks_like_js_function",
    "_looks_like_statement_script",
    "_is_js_error_envelope",
    "_unwrap_js_success_envelope",
    "_is_json_serializable",
    "_coerce_optional_int",
    "_extract_error_location",
    "_snippet",
)


_JS_SNIPPET_CHARS = 240


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


def _adapt_js_result_value(raw_result: object) -> tuple[object, bool]:
    raw_result = _coerce_json_envelope(raw_result)
    if isinstance(raw_result, dict) and _is_js_error_envelope(raw_result):
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


def _snippet(expression: str) -> str:
    return _excerpt(
        re.sub(r"\s+", " ", str(expression or "")).strip(), _JS_SNIPPET_CHARS
    )
