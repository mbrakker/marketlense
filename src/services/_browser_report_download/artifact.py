from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import (
    ensure_downloaded_pdf,
    resolve_downloaded_mime_type,
    validate_downloaded_pdf_artifact,
)
from src.utils.errors import AppError

if TYPE_CHECKING:
    from src.services._browser_report_download.browser import BrowserAgentRunResult

_ROUTE_KINDS = {"pdf_download", "email_delivery"}
_ROUTE_SUMMARY_ACTION_MARKERS = (
    "open",
    "click",
    "fill",
    "enter",
    "submit",
    "select",
    "choose",
    "use",
    "wait",
    "download",
    "inspect",
    "apply",
    "expand",
    "navigate",
)
_ROUTE_SUMMARY_TARGET_MARKERS = (
    "button",
    "link",
    "page",
    "form",
    "field",
    "email",
    "report",
    "pdf",
    "cta",
    "tab",
    "filter",
    "modal",
    "screen",
    "prompt",
)


class BrowserUseAgentResult(BaseModel):
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


def finalize_browser_report_download_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    delivery_email: str | None,
    download_dir: Path,
    browser_run: BrowserAgentRunResult,
) -> BrowserReportDownloadResult:
    if not browser_run.raw_model_response:
        raise AppError(
            code="browser_download_empty_result",
            message="browser-use returned no structured result",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    try:
        agent_result = BrowserUseAgentResult.model_validate_json(
            browser_run.raw_model_response
        )
    except ValidationError as exc:
        raise AppError(
            code="browser_download_invalid_result",
            message="browser-use returned an invalid structured result",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "raw_model_response": browser_run.raw_model_response,
            },
        ) from exc

    route_kind = _resolve_route_kind(
        route_kind=agent_result.route_kind,
        explicit_downloaded_file_path=agent_result.downloaded_file_path,
        browser_downloaded_files=browser_run.downloaded_files,
        post_submit_message=agent_result.post_submit_message,
    )
    downloaded_path = _resolve_downloaded_file(
        explicit_path=agent_result.downloaded_file_path,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    downloaded_path = ensure_downloaded_pdf(
        downloaded_path=downloaded_path,
        ctx=ctx,
        normalized_url=normalized_url,
        document_url=str(
            browser_run.final_page_url or agent_result.final_page_url or normalized_url
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
    if route_kind == "email_delivery" and delivery_email:
        if agent_result.email_submission_completed is not True:
            raise AppError(
                code="browser_download_email_submission_missing",
                message="browser-use identified an email-delivery route but did not confirm form submission",
                retryable=True,
                context={"normalized_url": normalized_url},
            )
        if not _message_indicates_email_delivery(agent_result.post_submit_message):
            raise AppError(
                code="browser_download_email_confirmation_missing",
                message="browser-use identified an email-delivery route but did not capture a visible delivery confirmation",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "post_submit_message": agent_result.post_submit_message,
                },
            )

    route_summary = str(agent_result.route_summary or "").strip()
    if not route_summary:
        raise AppError(
            code="browser_download_missing_route_summary",
            message="browser-use returned an empty route summary",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    if not _is_semantic_route_summary(route_summary):
        raise AppError(
            code="browser_download_route_summary_too_weak",
            message="browser-use returned a route summary without enough reusable action detail",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "route_summary": route_summary,
            },
        )

    final_url = str(
        browser_run.final_page_url or agent_result.final_page_url or normalized_url
    ).strip()
    downloaded_mime_type = resolve_downloaded_mime_type(
        reported_mime_type=str(agent_result.downloaded_mime_type).strip()
        if agent_result.downloaded_mime_type
        else None,
        downloaded_path=downloaded_path,
    )
    validate_downloaded_pdf_artifact(
        downloaded_path=downloaded_path,
        downloaded_mime_type=downloaded_mime_type,
        normalized_url=normalized_url,
    )
    downloaded_file_name = downloaded_path.name if downloaded_path else None
    downloaded_size_bytes = downloaded_path.stat().st_size if downloaded_path else None
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind=route_kind,
        outcome=_resolve_outcome(
            route_kind=route_kind,
            downloaded_path=downloaded_path,
            delivery_email=delivery_email,
        ),
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


def _is_semantic_route_summary(route_summary: str) -> bool:
    normalized = " ".join(str(route_summary or "").split()).strip()
    if not normalized:
        return False
    lowered = normalized.casefold()
    tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if token]
    if len(tokens) < 4:
        return False
    has_action = any(marker in lowered for marker in _ROUTE_SUMMARY_ACTION_MARKERS)
    has_target = any(marker in lowered for marker in _ROUTE_SUMMARY_TARGET_MARKERS)
    if not has_action or not has_target:
        return False
    return (
        len(tokens) >= 6
        or bool(
            re.search(
                r"\b(first|second|then|after|until|when|once|final)\b",
                lowered,
            )
        )
        or any(
            marker in lowered
            for marker in ("completion", "finish", "saved", "sent", "submitted")
        )
    )


def _resolve_route_kind(
    *,
    route_kind: str,
    explicit_downloaded_file_path: str | None,
    browser_downloaded_files: list[str],
    post_submit_message: str,
) -> str:
    token = str(route_kind or "").strip().lower()
    if explicit_downloaded_file_path or browser_downloaded_files:
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
