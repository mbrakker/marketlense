from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
from dataclasses import asdict
from hashlib import sha1
from importlib import import_module
from pathlib import Path
from shutil import rmtree
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from pydantic import BaseModel, Field, ValidationError

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.browser_report_download_service")

_ROUTE_KINDS = {"pdf_download", "email_delivery"}
_PDF_SIGNATURE = b"%PDF-"
_PDF_URL_PATTERN = re.compile(r"""(?P<quote>['"])(?P<url>[^'"]+?\.pdf(?:\?[^'"]*)?)(?P=quote)""", re.IGNORECASE)


class _BrowserUseAgentResult(BaseModel):
    route_kind: str = Field(description="Either `pdf_download` or `email_delivery`.")
    route_summary: str = Field(
        description="Short description of the working clicks/forms for this URL."
    )
    final_page_url: str = Field(
        default="",
        description="Final browser URL after the task completed.",
    )
    email_submission_completed: bool | None = Field(
        default=None,
        description="True only when an email-gated form was actually submitted.",
    )
    downloaded_file_path: str | None = Field(
        default=None,
        description="Absolute local path of the downloaded file when one was saved.",
    )
    downloaded_file_name: str | None = Field(
        default=None,
        description="Downloaded file name when available.",
    )
    downloaded_mime_type: str | None = Field(
        default=None,
        description="Downloaded file MIME type when known.",
    )
    encountered_form_fields: list[str] = Field(
        default_factory=list,
        description="Distinct form field labels or names encountered during the route.",
    )
    post_submit_message: str = Field(
        default="",
        description="Visible confirmation or status text shown after a form submission attempt.",
    )


def download_report_with_browser_use(
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
) -> BrowserReportDownloadResult:
    normalized_url = _validate_and_normalize_url(request.url)
    _validate_request(request, normalized_url)
    delivery_email_value = _resolve_delivery_email_value(request)
    download_dir = _prepare_download_dir(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    task_prompt = _build_task_prompt(
        normalized_url=normalized_url,
        download_dir=download_dir,
        delivery_email=delivery_email_value,
        route_hint=request.route_hint,
        route_kind_hint=request.route_kind_hint,
        identity_profile=request.settings.identity_profile,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_start",
            module=logger.name,
            fields={
                "url": request.url,
                "normalized_url": normalized_url,
                "output_dir": request.settings.output_dir,
                "download_dir": str(download_dir),
                "state_db": request.settings.state_db,
                "identity_config_path": request.settings.identity_config_path,
                "identity_field_count": len(request.settings.identity_profile.fields),
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "headed": request.settings.headed,
                "has_delivery_email": bool(request.delivery_email),
                "has_effective_delivery_email": bool(delivery_email_value),
                "has_route_hint": bool(request.route_hint),
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_request",
            module=logger.name,
            fields={"task_prompt": task_prompt},
        )
    )

    browser_use = _load_browser_use_runtime(normalized_url)
    browser = browser_use.Browser(
        downloads_path=str(download_dir),
        headless=not request.settings.headed,
        auto_download_pdfs=True,
    )
    llm = browser_use.ChatOpenRouter(
        model=request.settings.model,
        api_key=request.settings.openrouter_api_key,
        http_referer=request.settings.openrouter_http_referer,
        temperature=request.settings.temperature,
        timeout=request.settings.timeout_seconds,
    )
    agent = browser_use.Agent(
        task=task_prompt,
        llm=llm,
        browser=browser,
        output_model_schema=_BrowserUseAgentResult,
    )

    history: Any = None
    raw_model_response = ""
    final_page_url = ""
    downloaded_files: list[str] = []
    try:
        history = agent.run_sync(max_steps=request.settings.max_steps)
        raw_model_response = str(history.final_result() or "").strip()
        final_page_url = str(getattr(browser, "url", "") or "").strip()
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": str(exc)},
            )
        )
        raise AppError(
            code="browser_download_agent_failed",
            message="browser-use failed to complete the report download task",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    finally:
        _kill_browser(browser)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
                "downloaded_files": downloaded_files,
                "browser_final_url": final_page_url,
            },
        )
    )

    if not raw_model_response:
        raise AppError(
            code="browser_download_empty_result",
            message="browser-use returned no structured result",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    try:
        agent_result = _BrowserUseAgentResult.model_validate_json(raw_model_response)
    except ValidationError as exc:
        raise AppError(
            code="browser_download_invalid_result",
            message="browser-use returned an invalid structured result",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
            },
        ) from exc

    route_kind = _resolve_route_kind(
        agent_result.route_kind,
        downloaded_files,
        agent_result.post_submit_message,
    )
    downloaded_path = _resolve_downloaded_file(
        explicit_path=agent_result.downloaded_file_path,
        browser_downloaded_files=downloaded_files,
        download_dir=download_dir,
    )
    downloaded_path = _ensure_downloaded_pdf(
        downloaded_path=downloaded_path,
        ctx=ctx,
        normalized_url=normalized_url,
        document_url=str(
            final_page_url or agent_result.final_page_url or normalized_url
        ).strip(),
        timeout_seconds=request.settings.timeout_seconds,
    )
    if route_kind == "pdf_download" and downloaded_path is None:
        raise AppError(
            code="browser_download_missing_file",
            message="browser-use classified the route as a PDF download but no local file was found",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "download_dir": str(download_dir),
            },
        )
    if route_kind == "email_delivery" and delivery_email_value:
        if agent_result.email_submission_completed is not True:
            raise AppError(
                code="browser_download_email_submission_missing",
                message="browser-use identified an email-delivery route but did not confirm form submission",
                retryable=True,
                context={"normalized_url": normalized_url},
            )

    route_summary = str(agent_result.route_summary or "").strip()
    if not route_summary:
        raise AppError(
            code="browser_download_missing_route_summary",
            message="browser-use returned an empty route summary",
            retryable=True,
            context={"normalized_url": normalized_url},
        )

    final_url = str(
        final_page_url or agent_result.final_page_url or normalized_url
    ).strip()
    outcome = _resolve_outcome(
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        delivery_email=delivery_email_value,
    )
    downloaded_file_name = downloaded_path.name if downloaded_path else None
    downloaded_mime_type = (
        str(agent_result.downloaded_mime_type).strip()
        if agent_result.downloaded_mime_type
        else _guess_mime_type(downloaded_path)
    )
    downloaded_size_bytes = downloaded_path.stat().st_size if downloaded_path else None

    response = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind=route_kind,
        outcome=outcome,
        route_summary=route_summary,
        final_page_url=final_url,
        used_route_hint=bool(request.route_hint),
        encountered_form_fields=_normalize_encountered_form_fields(
            agent_result.encountered_form_fields
        ),
        downloaded_file_path=str(downloaded_path) if downloaded_path else None,
        downloaded_file_name=downloaded_file_name,
        downloaded_mime_type=downloaded_mime_type,
        downloaded_size_bytes=downloaded_size_bytes,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response


def _validate_request(
    request: BrowserReportDownloadRequest, normalized_url: str
) -> None:
    if not normalized_url:
        raise AppError(
            code="browser_download_url_invalid",
            message="A valid absolute URL is required for browser downloads",
            retryable=False,
        )
    if not request.settings.output_dir or not str(request.settings.output_dir).strip():
        raise AppError(
            code="browser_download_output_dir_missing",
            message="Browser download output directory is required",
            retryable=False,
        )
    if (
        not request.settings.openrouter_api_key
        or not request.settings.openrouter_api_key.strip()
    ):
        raise AppError(
            code="browser_download_api_key_missing",
            message="OPENROUTER_API_KEY is required for local browser-use downloads",
            retryable=False,
        )
    if not request.settings.model or not request.settings.model.strip():
        raise AppError(
            code="browser_download_model_missing",
            message="A browser-download model must be configured",
            retryable=False,
        )
    if request.delivery_email:
        delivery_email = request.delivery_email.strip()
        if "@" not in delivery_email or "." not in delivery_email.split("@")[-1]:
            raise AppError(
                code="browser_download_email_invalid",
                message="delivery_email must be a valid email address when provided",
                retryable=False,
            )


def _validate_and_normalize_url(url: str) -> str:
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized_url


def _build_task_prompt(
    *,
    normalized_url: str,
    download_dir: Path,
    delivery_email: str | None,
    route_hint: str | None,
    route_kind_hint: str | None,
    identity_profile: Any,
) -> str:
    prompt_parts = [
        f"Open this exact URL: {normalized_url}",
        "Find the report acquisition path on the page and complete the route.",
        (
            "Classify the route as `pdf_download` when you obtain a local PDF file in this run. "
            "Classify it as `email_delivery` when the site requires sending the report to an email address instead."
        ),
        f"The browser downloads directory for this run is: {download_dir}",
        (
            "When a PDF is downloaded, include the absolute downloaded_file_path, downloaded_file_name, "
            "and downloaded_mime_type when known."
        ),
        (
            "Always return a concise route_summary describing the successful clicks or form steps so the system can reuse it later."
        ),
        (
            "If you inspect or open a form, return every distinct visible field label or field name in encountered_form_fields."
        ),
        (
            "After any form submission attempt, inspect the visible confirmation/status text and put a concise verbatim summary into post_submit_message."
        ),
    ]
    prompt_parts.append(_render_identity_prompt(identity_profile, delivery_email))
    if route_hint:
        hint_prefix = (
            f"Previously successful route kind: {route_kind_hint}. "
            if route_kind_hint
            else ""
        )
        prompt_parts.append(
            f"{hint_prefix}Previously successful route summary for this URL: {route_hint}"
        )
    if delivery_email:
        prompt_parts.append(
            f"If an email form is required, use this email address and confirm submission: {delivery_email}"
        )
    else:
        prompt_parts.append(
            "If the site requires email delivery and no configured email value is available, do not invent one. Classify the route as `email_delivery` and set email_submission_completed to false."
        )
    prompt_parts.append("Do not return free-text outside the structured result.")
    return "\n".join(prompt_parts)


def _render_identity_prompt(identity_profile: Any, delivery_email: str | None) -> str:
    lines = [
        "Use the following configured identity values when a matching form field is available. Do not invent missing values."
    ]
    for field in identity_profile.fields:
        aliases = ", ".join(field.aliases)
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email.strip()
        if not value:
            continue
        alias_text = f" (aliases: {aliases})" if aliases else ""
        lines.append(f"- {field.label}{alias_text}: {value}")
    if len(lines) == 1:
        lines.append("- No non-empty identity values are configured.")
    lines.append(
        "If a required field has no configured value, stop before submission, still report encountered_form_fields, and do not invent replacement values."
    )
    return "\n".join(lines)


def _normalize_encountered_form_fields(raw_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_field in raw_fields:
        token = str(raw_field or "").strip()
        if not token:
            continue
        dedupe_key = token.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(token)
    return normalized


def _resolve_delivery_email_value(
    request: BrowserReportDownloadRequest,
) -> str | None:
    explicit_email = str(request.delivery_email or "").strip()
    if explicit_email:
        return explicit_email
    for field in request.settings.identity_profile.fields:
        if field.key != "work_email":
            continue
        configured_email = str(field.value or "").strip()
        if configured_email:
            return configured_email
    return None


def _prepare_download_dir(*, root_dir: str, normalized_url: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    host = urlsplit(normalized_url).netloc.replace(":", "_") or "unknown_host"
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    download_dir = (root / host / url_hash).resolve()
    if download_dir != root and root not in download_dir.parents:
        raise AppError(
            code="browser_download_output_dir_invalid",
            message="Resolved browser download directory escapes the configured root",
            retryable=False,
            context={"root_dir": str(root), "download_dir": str(download_dir)},
        )
    if download_dir.exists():
        for child in download_dir.iterdir():
            if child.is_dir():
                rmtree(child)
            else:
                child.unlink()
    else:
        download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    try:
        return import_module("browser_use")
    except Exception as exc:
        raise AppError(
            code="browser_use_unavailable",
            message="The local browser_use runtime is not installed in this environment",
            cause=exc,
            retryable=False,
            context={"normalized_url": normalized_url},
        ) from exc


def _resolve_route_kind(
    route_kind: str,
    downloaded_files: list[str],
    post_submit_message: str,
) -> str:
    token = str(route_kind or "").strip().lower()
    if downloaded_files:
        return "pdf_download"
    if _message_indicates_email_delivery(post_submit_message):
        return "email_delivery"
    if token in _ROUTE_KINDS:
        return token
    raise AppError(
        code="browser_download_route_kind_invalid",
        message="browser-use returned an unsupported route classification",
        retryable=True,
        context={"route_kind": route_kind},
    )


def _message_indicates_email_delivery(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    email_markers = ("email", "inbox", "mailbox", "mail")
    delivery_markers = (
        "check",
        "sent",
        "send",
        "receive",
        "receiving",
        "delivered",
        "delivery",
        "download link",
        "link",
    )
    return any(marker in token for marker in email_markers) and any(
        marker in token for marker in delivery_markers
    )


def _resolve_downloaded_file(
    *,
    explicit_path: str | None,
    browser_downloaded_files: list[str],
    download_dir: Path,
) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    for raw_path in browser_downloaded_files:
        candidates.append(Path(raw_path).expanduser())
    for path in sorted(download_dir.glob("*")):
        if path.is_file():
            candidates.append(path)

    resolved_candidates: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if download_dir not in resolved.parents:
            continue
        resolved_candidates.append(resolved)
    if not resolved_candidates:
        return None
    pdf_candidates = [
        path for path in resolved_candidates if path.suffix.lower() == ".pdf"
    ]
    selected = pdf_candidates or resolved_candidates
    selected.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return selected[0]


def _ensure_downloaded_pdf(
    *,
    downloaded_path: Path | None,
    ctx: RunContext,
    normalized_url: str,
    document_url: str,
    timeout_seconds: float,
) -> Path | None:
    if downloaded_path is None:
        return None
    if _is_pdf_file(downloaded_path):
        return downloaded_path

    wrapper_html = _read_text_if_small(downloaded_path, max_bytes=64 * 1024)
    embedded_pdf_url = _extract_embedded_pdf_url(
        wrapper_html=wrapper_html,
        document_url=document_url,
    )
    if embedded_pdf_url:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_wrapper_detected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "downloaded_file_path": str(downloaded_path),
                    "embedded_pdf_url": embedded_pdf_url,
                },
            )
        )
        _download_pdf_from_url(
            pdf_url=embedded_pdf_url,
            destination_path=downloaded_path,
            timeout_seconds=timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if _is_pdf_file(downloaded_path):
            return downloaded_path

    raise AppError(
        code="browser_download_invalid_pdf",
        message="Downloaded file is not a valid PDF",
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "downloaded_file_path": str(downloaded_path),
            "document_url": document_url,
        },
    )


def _resolve_outcome(
    *,
    route_kind: str,
    downloaded_path: Path | None,
    delivery_email: str | None,
) -> str:
    if downloaded_path is not None:
        return "downloaded"
    if route_kind == "email_delivery" and delivery_email:
        return "email_requested"
    return "email_required"


def _guess_mime_type(downloaded_path: Path | None) -> str | None:
    if downloaded_path is None:
        return None
    if _is_pdf_file(downloaded_path):
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(downloaded_path.name)
    if guessed:
        return guessed
    if downloaded_path.suffix.lower() == ".pdf":
        return "application/pdf"
    return None


def _is_pdf_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(_PDF_SIGNATURE)) == _PDF_SIGNATURE
    except OSError:
        return False


def _read_text_if_small(path: Path, *, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _extract_embedded_pdf_url(*, wrapper_html: str, document_url: str) -> str | None:
    if not wrapper_html:
        return None
    for match in _PDF_URL_PATTERN.finditer(wrapper_html):
        raw_url = str(match.group("url") or "").strip()
        if not raw_url:
            continue
        return urljoin(document_url, raw_url)
    return None


def _download_pdf_from_url(
    *,
    pdf_url: str,
    destination_path: Path,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    headers = {
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pdf_fetch_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
        )
    )
    temp_path = destination_path.with_suffix(destination_path.suffix + ".part")
    try:
        with requests.get(
            pdf_url,
            headers=headers,
            stream=True,
            timeout=timeout_seconds,
        ) as response:
            content_type = str(response.headers.get("Content-Type", "")).strip()
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pdf_fetch_response",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "pdf_url": pdf_url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                    },
                )
            )
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        handle.write(chunk)
        temp_path.replace(destination_path)
    except requests.RequestException as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise AppError(
            code="browser_download_pdf_fetch_failed",
            message="Failed to fetch the real PDF from the wrapper page",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
        ) from exc
    except OSError as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise AppError(
            code="browser_download_pdf_write_failed",
            message="Failed to write the fetched PDF to disk",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
        ) from exc


def _kill_browser(browser: Any) -> None:
    try:
        asyncio.run(browser.kill())
    except Exception:
        logger.info(
            log_event(
                RunContext(
                    schema_version="1.0",
                    run_id="browser-kill",
                    task_id="browser-kill",
                    span_id="browser-kill",
                ),
                role="service",
                event="browser_report_download_browser_kill_failed",
                module=logger.name,
                fields={},
            )
        )
