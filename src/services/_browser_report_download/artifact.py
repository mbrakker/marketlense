from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    ensure_downloaded_pdf,
    resolve_downloaded_mime_type,
    validate_downloaded_pdf_artifact,
)
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

if TYPE_CHECKING:
    from src.services._browser_report_download.browser import BrowserAgentRunResult

_ROUTE_KINDS = {"pdf_download", "email_delivery", "onsite_report"}
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
_SUCCESS_URL_MARKERS = ("thank", "success", "confirm", "complete", "done")
_EMAIL_DOMAIN_BLOCK_MARKERS = (
    "business email",
    "work email",
    "corporate email",
    "company email",
    "valid business email",
    "professional email",
)
_CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha", "i am human", "not a robot")
_STATIC_ARCHIVE_MARKERS = (
    "archived",
    "archive",
    "no longer available",
    "unavailable",
    "coming soon",
)
_UNKNOWN_ENUM_MARKERS = (
    "select",
    "choose",
    "dropdown",
    "industry",
    "country",
    "state",
    "department",
    "job level",
)
_ONSITE_ROUTE_FAMILIES = {
    "browser_onsite_report",
    "browser_listing_hub",
}


class BrowserUseRouteStep(BaseModel):
    index: int | None = Field(default=None)
    action: str = Field(default="")
    target_text: str = Field(default="")
    target_role: str = Field(default="")
    target_url: str = Field(default="")
    result: str = Field(default="")


class BrowserUseAgentResult(BaseModel):
    route_kind: str = Field(description="Either `pdf_download`, `email_delivery`, or `onsite_report`.")
    route_summary: str = Field(
        default="",
        description="Short description of the working clicks/forms for this URL.",
    )
    route_family: str = Field(
        default="",
        description="Observed route family for this execution attempt when the agent can classify it.",
    )
    resolved_target_url: str = Field(
        default="",
        description="Resolved target URL that produced the final artifact or email form state.",
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
    route_steps: list[BrowserUseRouteStep] = Field(
        default_factory=list,
        description="Ordered structured action trace for the successful route when the agent can provide it.",
    )
    post_submit_message: str = Field(
        default="",
        description="Visible confirmation or status text shown after a form submission attempt.",
    )
    confirmation_url_changed: bool | None = Field(
        default=None,
        description="Whether the page URL changed after the submission or route-completing action.",
    )
    submit_button_state: str = Field(
        default="",
        description="Observed submit-button state after submission, for example `disabled` or `replaced`.",
    )
    form_disappeared: bool | None = Field(
        default=None,
        description="Whether the form disappeared after submission.",
    )
    blocked_reason: str = Field(
        default="",
        description="Typed blocker code when the flow is blocked instead of completed.",
    )
    blocked_reason_detail: str = Field(
        default="",
        description="Human-readable blocker detail captured from the terminal state when available.",
    )
    final_page_title: str = Field(
        default="",
        description="Observed final page title when available.",
    )
    terminal_text_excerpt: str = Field(
        default="",
        description="Short visible text excerpt captured from the terminal page when available.",
    )
    traversed_page_urls: list[str] = Field(
        default_factory=list,
        description="Distinct page URLs traversed while reaching the terminal state.",
    )
    onsite_capture_path: str | None = Field(
        default=None,
        description="Absolute local path of the captured on-site report artifact when available.",
    )
    onsite_capture_format: str | None = Field(
        default=None,
        description="Stored on-site capture format when available.",
    )
    onsite_page_count: int | None = Field(
        default=None,
        description="Number of distinct pages or scroll segments captured for an on-site report when available.",
    )
    onsite_completeness_status: str = Field(
        default="",
        description="On-site capture completeness verdict when available.",
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
    final_url = str(
        browser_run.final_page_url or request.attempt_url or normalized_url
    ).strip()
    agent_result = _parse_browser_result(
        raw_model_response=browser_run.raw_model_response,
        normalized_url=normalized_url,
    )
    if agent_result is None:
        return _salvage_without_structured_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            final_url=final_url,
            download_dir=download_dir,
            browser_run=browser_run,
        )

    downloaded_path = _resolve_downloaded_file(
        explicit_path=agent_result.downloaded_file_path,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    onsite_capture_path = str(agent_result.onsite_capture_path or "").strip() or None
    if onsite_capture_path and downloaded_path is not None:
        try:
            if downloaded_path.resolve() == Path(onsite_capture_path).expanduser().resolve():
                downloaded_path = None
        except OSError:
            downloaded_path = None
    encountered_form_fields = _normalize_encountered_form_fields(
        agent_result.encountered_form_fields
    )
    resolved_target_url = str(
        agent_result.resolved_target_url
        or final_url
        or request.attempt_url
        or normalized_url
    ).strip()
    downloaded_path, used_candidate_pdf_url = _complete_pdf_artifact(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        downloaded_path=downloaded_path,
        target_urls=[
            request.candidate_trace.pdf_url if request.candidate_trace is not None else "",
            resolved_target_url,
            final_url,
        ],
    )
    route_kind = _resolve_route_kind(
        request=request,
        agent_result=agent_result,
        route_kind=agent_result.route_kind,
        downloaded_path=downloaded_path,
        encountered_form_fields=encountered_form_fields,
        post_submit_message=agent_result.post_submit_message,
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

    confirmation_evidence = _build_confirmation_evidence(
        agent_result=agent_result,
        final_url=final_url,
    )
    route_steps = _resolve_route_steps(
        request=request,
        agent_result=agent_result,
        raw_summary=agent_result.route_summary,
        resolved_target_url=resolved_target_url,
        downloaded_path=downloaded_path,
        confirmation_evidence=confirmation_evidence,
    )
    route_summary = _resolve_route_summary(
        raw_summary=agent_result.route_summary,
        route_steps=route_steps,
        normalized_url=normalized_url,
    )
    final_url = str(agent_result.final_page_url or final_url or normalized_url).strip()
    downloaded_mime_type = resolve_downloaded_mime_type(
        reported_mime_type=str(agent_result.downloaded_mime_type).strip()
        if agent_result.downloaded_mime_type
        else None,
        downloaded_path=downloaded_path,
    )
    blocked_reason = _resolve_blocked_reason(
        request=request,
        delivery_email=delivery_email,
        agent_result=agent_result,
        encountered_form_fields=encountered_form_fields,
        final_url=final_url,
    )
    blocked_reason_detail = _resolve_blocked_reason_detail(
        agent_result=agent_result,
        blocked_reason=blocked_reason,
    )
    onsite_capture_format = str(agent_result.onsite_capture_format or "").strip() or None
    onsite_page_count = agent_result.onsite_page_count
    onsite_completeness_status = (
        str(agent_result.onsite_completeness_status or "").strip() or None
    )
    artifact_validation_status = "none"
    artifact_validation_detail = ""
    if downloaded_path is not None:
        try:
            validate_downloaded_pdf_artifact(
                downloaded_path=downloaded_path,
                downloaded_mime_type=downloaded_mime_type,
                normalized_url=normalized_url,
            )
            artifact_validation_status = "verified"
            artifact_validation_detail = "Validated local PDF artifact."
        except AppError as exc:
            (
                route_kind,
                downloaded_path,
                downloaded_mime_type,
                blocked_reason,
                blocked_reason_detail,
                onsite_capture_path,
                onsite_capture_format,
                onsite_page_count,
                onsite_completeness_status,
                artifact_validation_status,
                artifact_validation_detail,
            ) = _recover_from_invalid_artifact(
                request=request,
                agent_result=agent_result,
                downloaded_path=downloaded_path,
                final_url=final_url,
                resolved_target_url=resolved_target_url,
                confirmation_evidence=confirmation_evidence,
                encountered_form_fields=encountered_form_fields,
                blocked_reason=blocked_reason,
                blocked_reason_detail=blocked_reason_detail,
                delivery_email=delivery_email,
                original_error=exc,
            )
    elif route_kind == "onsite_report":
        artifact_validation_status = "captured"
        artifact_validation_detail = "Captured on-site report content without a local PDF."
    elif blocked_reason:
        artifact_validation_status = "blocked"
        artifact_validation_detail = blocked_reason_detail or blocked_reason

    outcome, route_status, confirmation_signal_count = _classify_route_result(
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        confirmation_evidence=confirmation_evidence,
        encountered_form_fields=encountered_form_fields,
        email_submission_completed=agent_result.email_submission_completed,
        blocked_reason=blocked_reason,
        onsite_capture_path=onsite_capture_path,
        onsite_completeness_status=onsite_completeness_status,
    )
    terminal_evidence = _build_terminal_evidence(
        agent_result=agent_result,
        final_url=final_url,
        resolved_target_url=resolved_target_url,
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        downloaded_mime_type=downloaded_mime_type,
        onsite_capture_path=onsite_capture_path,
        confirmation_signal_count=confirmation_signal_count,
        artifact_validation_status=artifact_validation_status,
        artifact_validation_detail=artifact_validation_detail,
    )
    downloaded_file_name = downloaded_path.name if downloaded_path else None
    downloaded_size_bytes = downloaded_path.stat().st_size if downloaded_path else None
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind=route_kind,
        route_family=_resolve_route_family(
            request=request,
            agent_result=agent_result,
            route_kind=route_kind,
        ),
        route_status=route_status,
        outcome=outcome,
        route_summary=route_summary,
        final_page_url=final_url,
        resolved_target_url=resolved_target_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=confirmation_evidence,
        terminal_evidence=terminal_evidence,
        browser_had_structured_result=True,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=_used_candidate_source_page(request),
        encountered_form_fields=encountered_form_fields,
        blocked_reason=blocked_reason,
        blocked_reason_detail=blocked_reason_detail,
        downloaded_file_path=str(downloaded_path) if downloaded_path else None,
        downloaded_file_name=downloaded_file_name,
        downloaded_mime_type=downloaded_mime_type,
        downloaded_size_bytes=downloaded_size_bytes,
        onsite_capture_path=onsite_capture_path,
        onsite_capture_format=onsite_capture_format,
        onsite_page_count=onsite_page_count,
        onsite_completeness_status=onsite_completeness_status,
    )


def _parse_browser_result(
    *,
    raw_model_response: str,
    normalized_url: str,
) -> BrowserUseAgentResult | None:
    payload = str(raw_model_response or "").strip()
    if not payload:
        return None
    try:
        return BrowserUseAgentResult.model_validate_json(payload)
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


def _salvage_without_structured_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    final_url: str,
    download_dir: Path,
    browser_run: BrowserAgentRunResult,
) -> BrowserReportDownloadResult:
    downloaded_path = _resolve_downloaded_file(
        explicit_path=None,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    downloaded_path, used_candidate_pdf_url = _complete_pdf_artifact(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        downloaded_path=downloaded_path,
        target_urls=[
            request.candidate_trace.pdf_url if request.candidate_trace is not None else "",
            final_url,
            request.attempt_url or "",
        ],
    )
    if downloaded_path is not None:
        return _build_pdf_result(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            resolved_target_url=final_url or request.attempt_url or normalized_url,
            downloaded_path=downloaded_path,
            downloaded_mime_type=resolve_downloaded_mime_type(
                reported_mime_type=None,
                downloaded_path=downloaded_path,
            ),
            browser_had_structured_result=False,
            used_candidate_pdf_url=used_candidate_pdf_url,
        )
    if request.route_family_hint == "browser_email_form" and _url_indicates_confirmation(
        final_url
    ):
        confirmation_evidence = BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=True,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_url,
        )
        return BrowserReportDownloadResult(
            schema_version="1.0",
            source_url=request.url,
            normalized_url=normalized_url,
            route_kind="email_delivery",
            route_family=request.route_family_hint,
            route_status="inferred",
            outcome="email_requested",
            route_summary="Open the form page, submit the delivery request, and verify the confirmation URL.",
            final_page_url=final_url,
            resolved_target_url=final_url or request.attempt_url or normalized_url,
            used_route_hint=bool(request.route_hint),
            route_steps=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="open",
                    target_text=str(request.attempt_url or request.url).strip(),
                    target_role="url",
                    target_url=final_url or request.attempt_url or normalized_url,
                    result="submitted",
                )
            ],
            confirmation_evidence=confirmation_evidence,
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url=final_url,
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url=final_url,
                artifact_kind="email_delivery",
                artifact_validation_status="recovered",
                artifact_validation_detail="Recovered email-delivery terminal state from the final confirmation URL.",
                confirmation_signal_count=1,
                traversed_page_urls=_normalize_traversed_page_urls(
                    raw_urls=[request.attempt_url or "", final_url]
                ),
            ),
            browser_had_structured_result=False,
            used_candidate_pdf_url=used_candidate_pdf_url,
            used_candidate_source_page=_used_candidate_source_page(request),
            encountered_form_fields=[],
            blocked_reason=None,
            blocked_reason_detail=None,
            downloaded_file_path=None,
            downloaded_file_name=None,
            downloaded_mime_type=None,
            downloaded_size_bytes=None,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
        )
    raise AppError(
        code="browser_download_empty_result",
        message="browser-use returned no structured result and no PDF artifact could be salvaged",
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "final_url": final_url,
            "candidate_pdf_url": (
                request.candidate_trace.pdf_url if request.candidate_trace else None
            ),
        },
    )


def _complete_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    downloaded_path: Path | None,
    target_urls: list[str],
) -> tuple[Path | None, bool]:
    if downloaded_path is not None:
        try:
            ensured_path = ensure_downloaded_pdf(
                downloaded_path=downloaded_path,
                ctx=ctx,
                normalized_url=normalized_url,
                document_url=str(request.attempt_url or normalized_url).strip(),
                timeout_seconds=request.settings.timeout_seconds,
            )
            return ensured_path, False
        except AppError as exc:
            if exc.code != "browser_download_invalid_pdf":
                raise
            return downloaded_path, False
    candidate_pdf_url = (
        str(request.candidate_trace.pdf_url or "").strip()
        if request.candidate_trace is not None
        else ""
    )
    for target_url in target_urls:
        normalized_target = str(target_url or "").strip()
        if not normalized_target:
            continue
        fetched_path = _try_fetch_pdf_target(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            target_url=normalized_target,
        )
        if fetched_path is not None:
            return fetched_path, normalized_target == candidate_pdf_url
    return None, False


def _try_fetch_pdf_target(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    target_url: str,
) -> Path | None:
    destination_name = Path(urlsplit(target_url).path).name or "download.pdf"
    destination_path = download_dir / destination_name
    try:
        download_pdf_from_url(
            pdf_url=target_url,
            destination_path=destination_path,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        ensured_path = ensure_downloaded_pdf(
            downloaded_path=destination_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=target_url,
            timeout_seconds=request.settings.timeout_seconds,
        )
        validate_downloaded_pdf_artifact(
            downloaded_path=ensured_path,
            downloaded_mime_type=resolve_downloaded_mime_type(
                reported_mime_type=None,
                downloaded_path=ensured_path,
            ),
            normalized_url=normalized_url,
        )
        return ensured_path
    except AppError:
        destination_path.unlink(missing_ok=True)
        return None


def _build_pdf_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    final_url: str,
    resolved_target_url: str,
    downloaded_path: Path,
    downloaded_mime_type: str | None,
    browser_had_structured_result: bool,
    used_candidate_pdf_url: bool,
) -> BrowserReportDownloadResult:
    route_steps = [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=resolved_target_url,
            target_role="url",
            target_url=resolved_target_url,
            result="downloaded",
        )
    ]
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="pdf_download",
        route_family=request.route_family_hint or "browser_pdf_click",
        route_status="verified",
        outcome="downloaded",
        route_summary="Open the target page or PDF URL and save the downloaded PDF file locally.",
        final_page_url=final_url,
        resolved_target_url=resolved_target_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_url,
            final_page_title="",
            terminal_text_excerpt="",
            artifact_url=resolved_target_url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="Validated local PDF artifact.",
            confirmation_signal_count=0,
            traversed_page_urls=_normalize_traversed_page_urls(
                raw_urls=[resolved_target_url, final_url]
            ),
        ),
        browser_had_structured_result=browser_had_structured_result,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=_used_candidate_source_page(request),
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=str(downloaded_path),
        downloaded_file_name=downloaded_path.name,
        downloaded_mime_type=downloaded_mime_type,
        downloaded_size_bytes=downloaded_path.stat().st_size,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
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


def _resolve_route_summary(
    *,
    raw_summary: str,
    route_steps: list[BrowserDownloadRouteStep],
    normalized_url: str,
) -> str:
    route_summary = str(raw_summary or "").strip()
    if route_summary and _is_semantic_route_summary(route_summary):
        return route_summary
    if route_steps:
        return _derive_route_summary(route_steps)
    if route_summary:
        raise AppError(
            code="browser_download_route_summary_too_weak",
            message="browser-use returned a route summary without enough reusable action detail",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "route_summary": route_summary,
            },
        )
    raise AppError(
        code="browser_download_missing_route_summary",
        message="browser-use returned no reusable route summary or route steps",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _derive_route_summary(route_steps: list[BrowserDownloadRouteStep]) -> str:
    fragments: list[str] = []
    for step in route_steps[:3]:
        action = step.action or "follow"
        target = step.target_text or step.target_role or step.target_url or "page"
        result = step.result or "completed"
        fragments.append(f"{action} {target} ({result})")
    return "; then ".join(fragments).strip()


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
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    route_kind: str,
    downloaded_path: Path | None,
    encountered_form_fields: list[str],
    post_submit_message: str,
) -> str:
    token = str(route_kind or "").strip().lower()
    if downloaded_path is not None:
        return "pdf_download"
    if (
        agent_result.onsite_capture_path
        or str(agent_result.onsite_completeness_status or "").strip()
        or str(request.route_family_hint or "").strip() in _ONSITE_ROUTE_FAMILIES
    ):
        return "onsite_report"
    if encountered_form_fields or _message_indicates_email_delivery(post_submit_message):
        return "email_delivery"
    if token in _ROUTE_KINDS:
        return token
    raise AppError(
        code="browser_download_route_kind_invalid",
        message="browser-use returned an unsupported route classification",
        retryable=True,
        context={"route_kind": route_kind},
    )


def _build_confirmation_evidence(
    *,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> BrowserDownloadConfirmationEvidence:
    visible_confirmation_text = str(agent_result.post_submit_message or "").strip()
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=bool(agent_result.confirmation_url_changed),
        visible_confirmation_text=visible_confirmation_text,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        final_page_url=str(agent_result.final_page_url or final_url).strip(),
    )


def _build_terminal_evidence(
    *,
    agent_result: BrowserUseAgentResult,
    final_url: str,
    resolved_target_url: str,
    route_kind: str,
    downloaded_path: Path | None,
    downloaded_mime_type: str | None,
    onsite_capture_path: str | None,
    confirmation_signal_count: int,
    artifact_validation_status: str,
    artifact_validation_detail: str,
) -> DownloadTerminalEvidence:
    artifact_url = resolved_target_url if resolved_target_url else final_url
    artifact_kind = route_kind
    if downloaded_path is not None:
        artifact_kind = downloaded_mime_type or "pdf"
    elif onsite_capture_path:
        artifact_kind = "onsite_report"
    return DownloadTerminalEvidence(
        schema_version="1.0",
        final_page_url=final_url,
        final_page_title=str(agent_result.final_page_title or "").strip(),
        terminal_text_excerpt=str(agent_result.terminal_text_excerpt or "").strip(),
        artifact_url=str(artifact_url or "").strip(),
        artifact_kind=str(artifact_kind or "none").strip() or "none",
        artifact_validation_status=str(artifact_validation_status or "none").strip()
        or "none",
        artifact_validation_detail=str(artifact_validation_detail or "").strip(),
        confirmation_signal_count=confirmation_signal_count,
        traversed_page_urls=_normalize_traversed_page_urls(
            raw_urls=[*agent_result.traversed_page_urls, resolved_target_url, final_url]
        ),
    )


def _resolve_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    agent_result: BrowserUseAgentResult,
    encountered_form_fields: list[str],
    final_url: str,
) -> str | None:
    explicit = str(agent_result.blocked_reason or "").strip().lower()
    if explicit:
        return explicit
    haystack = " ".join(
        [
            str(agent_result.post_submit_message or "").strip(),
            str(agent_result.terminal_text_excerpt or "").strip(),
            " ".join(encountered_form_fields),
            str(agent_result.final_page_title or "").strip(),
        ]
    ).casefold()
    if any(marker in haystack for marker in _EMAIL_DOMAIN_BLOCK_MARKERS):
        return "blocked_email_domain"
    if any(marker in haystack for marker in _CAPTCHA_MARKERS):
        return "blocked_captcha"
    if any(marker in haystack for marker in _STATIC_ARCHIVE_MARKERS) or any(
        marker in str(final_url or "").casefold() for marker in _STATIC_ARCHIVE_MARKERS
    ):
        return "blocked_static_archive"
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    if any(marker in haystack for marker in _UNKNOWN_ENUM_MARKERS):
        return "blocked_unknown_required_enum"
    return None


def _resolve_blocked_reason_detail(
    *,
    agent_result: BrowserUseAgentResult,
    blocked_reason: str | None,
) -> str | None:
    detail = str(agent_result.blocked_reason_detail or "").strip()
    if detail:
        return detail
    if blocked_reason:
        return str(agent_result.post_submit_message or agent_result.terminal_text_excerpt or "").strip() or blocked_reason
    return None


def _resolve_route_steps(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    raw_summary: str,
    resolved_target_url: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> list[BrowserDownloadRouteStep]:
    steps: list[BrowserDownloadRouteStep] = []
    for index, raw_step in enumerate(agent_result.route_steps):
        action = str(raw_step.action or "").strip() or "follow"
        target_text = str(raw_step.target_text or "").strip()
        target_role = str(raw_step.target_role or "").strip() or "page"
        target_url = str(raw_step.target_url or "").strip()
        result = str(raw_step.result or "").strip() or "completed"
        steps.append(
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=int(raw_step.index) if raw_step.index is not None else index,
                action=action,
                target_text=target_text,
                target_role=target_role,
                target_url=target_url,
                result=result,
            )
        )
    if steps:
        return steps
    if not _is_semantic_route_summary(str(raw_summary or "").strip()):
        return []
    fallback_result = "downloaded" if downloaded_path is not None else "completed"
    if confirmation_evidence.visible_confirmation_text or confirmation_evidence.url_changed:
        fallback_result = "submitted"
    return [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=str(request.attempt_url or request.url).strip(),
            target_role="url",
            target_url=resolved_target_url,
            result=fallback_result,
        )
    ]


def _recover_from_invalid_artifact(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    downloaded_path: Path,
    final_url: str,
    resolved_target_url: str,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    encountered_form_fields: list[str],
    blocked_reason: str | None,
    blocked_reason_detail: str | None,
    delivery_email: str | None,
    original_error: AppError,
) -> tuple[
    str,
    Path | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    int | None,
    str | None,
    str,
    str,
]:
    wrapper_html = _read_text_if_small(downloaded_path, max_bytes=256 * 1024)
    if not wrapper_html:
        raise original_error
    recovered_blocked_reason = blocked_reason or _resolve_blocked_reason(
        request=request,
        delivery_email=delivery_email,
        agent_result=agent_result,
        encountered_form_fields=encountered_form_fields,
        final_url=final_url,
    )
    recovered_blocked_detail = blocked_reason_detail or _resolve_blocked_reason_detail(
        agent_result=agent_result,
        blocked_reason=recovered_blocked_reason,
    )
    lowered_html = wrapper_html.casefold()
    if (
        _message_indicates_email_delivery(wrapper_html)
        or recovered_blocked_reason
        or _url_indicates_confirmation(final_url)
    ):
        return (
            "email_delivery",
            None,
            None,
            recovered_blocked_reason,
            recovered_blocked_detail,
            None,
            None,
            None,
            None,
            "recovered" if _message_indicates_email_delivery(wrapper_html) else "blocked",
            "Recovered an email-delivery or blocked-form terminal state from an HTML artifact.",
        )
    if _looks_like_onsite_report_html(
        wrapper_html=wrapper_html,
        request=request,
        agent_result=agent_result,
        final_url=final_url,
    ):
        capture_path = _resolve_onsite_capture_path(downloaded_path)
        completeness_status = (
            str(agent_result.onsite_completeness_status or "").strip()
            or ("complete" if len(lowered_html) >= 2000 else "partial")
        )
        page_count = agent_result.onsite_page_count or max(
            1,
            len(_normalize_traversed_page_urls(raw_urls=agent_result.traversed_page_urls)),
        )
        return (
            "onsite_report",
            None,
            None,
            None,
            None,
            str(capture_path),
            str(agent_result.onsite_capture_format or "html").strip() or "html",
            page_count,
            completeness_status,
            "captured",
            "Recovered an on-site report capture from an HTML artifact that was misclassified as a PDF.",
        )
    raise original_error


def _classify_route_result(
    *,
    route_kind: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    encountered_form_fields: list[str],
    email_submission_completed: bool | None,
    blocked_reason: str | None,
    onsite_capture_path: str | None,
    onsite_completeness_status: str | None,
) -> tuple[str, str, int]:
    confirmation_signal_count = _count_confirmation_signals(confirmation_evidence)
    if downloaded_path is not None:
        return "downloaded", "verified", confirmation_signal_count
    if route_kind == "onsite_report":
        if not onsite_capture_path:
            raise AppError(
                code="browser_download_onsite_capture_missing",
                message="browser-use classified the route as an on-site report but no local capture artifact was found",
                retryable=True,
                context={"final_page_url": confirmation_evidence.final_page_url},
            )
        route_status = (
            "verified"
            if str(onsite_completeness_status or "").strip().lower() == "complete"
            else "inferred"
        )
        return "captured", route_status, confirmation_signal_count
    if route_kind != "email_delivery":
        raise AppError(
            code="browser_download_missing_file",
            message="No PDF artifact was produced for a non-email route",
            retryable=True,
        )
    if confirmation_signal_count >= 2 and _message_indicates_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        return "email_requested", "verified", confirmation_signal_count
    if email_submission_completed is True and _message_indicates_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        return "email_requested", "verified", confirmation_signal_count
    if email_submission_completed is True:
        raise AppError(
            code="browser_download_email_confirmation_missing",
            message="browser-use identified an email-delivery route but did not capture a visible delivery confirmation",
            retryable=True,
            context={"final_page_url": confirmation_evidence.final_page_url},
        )
    if blocked_reason or encountered_form_fields or email_submission_completed is False:
        return "email_required", "inferred", confirmation_signal_count
    raise AppError(
        code="browser_download_email_submission_missing",
        message="browser-use did not produce enough evidence to verify an email-gated route",
        retryable=True,
        context={"final_page_url": confirmation_evidence.final_page_url},
    )


def _count_confirmation_signals(
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> int:
    count = 0
    if _message_indicates_email_delivery(confirmation_evidence.visible_confirmation_text):
        count += 1
    if confirmation_evidence.url_changed and _url_indicates_confirmation(
        confirmation_evidence.final_page_url
    ):
        count += 1
    if confirmation_evidence.submit_button_state in {"disabled", "replaced"}:
        count += 1
    if confirmation_evidence.form_disappeared:
        count += 1
    return count


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


def _url_indicates_confirmation(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return any(marker in lowered for marker in _SUCCESS_URL_MARKERS)


def _resolve_route_family(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    route_kind: str,
) -> str:
    token = str(agent_result.route_family or "").strip()
    if token:
        return token
    if request.route_family_hint:
        return request.route_family_hint
    if route_kind == "onsite_report":
        return "browser_onsite_report"
    if route_kind == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _normalize_traversed_page_urls(*, raw_urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_url in raw_urls:
        token = str(raw_url or "").strip()
        if not token:
            continue
        dedupe_key = normalize_url(token)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(token)
    return normalized


def _has_missing_identity_field(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    encountered_form_fields: list[str],
) -> bool:
    configured_tokens: set[str] = set()
    for field in request.settings.identity_profile.fields:
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email
        if not value:
            continue
        configured_tokens.add(str(field.label or "").strip().casefold())
        for alias in field.aliases:
            configured_tokens.add(str(alias or "").strip().casefold())
        configured_tokens.add(str(field.key or "").strip().casefold())
    for field_name in encountered_form_fields:
        token = str(field_name or "").strip().casefold()
        if not token:
            continue
        if "email" in token and not delivery_email:
            return True
        if any(
            marker in token
            for marker in ("name", "company", "organization", "business", "title", "role", "phone")
        ) and token not in configured_tokens:
            return True
    return False


def _looks_like_onsite_report_html(
    *,
    wrapper_html: str,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> bool:
    lowered = str(wrapper_html or "").casefold()
    route_family = str(request.route_family_hint or agent_result.route_family or "").strip()
    if route_family in _ONSITE_ROUTE_FAMILIES and len(lowered) >= 1200:
        return True
    if "article" in lowered and any(
        marker in lowered for marker in ("report", "insight", "research", "analysis", "survey")
    ):
        return True
    return (
        str(agent_result.route_kind or "").strip() == "onsite_report"
        and len(lowered) >= 800
        and not _message_indicates_email_delivery(lowered)
        and not str(final_url or "").strip().lower().endswith(".pdf")
    )


def _resolve_onsite_capture_path(downloaded_path: Path) -> Path:
    if downloaded_path.suffix.lower() == ".html":
        return downloaded_path
    capture_path = downloaded_path.with_suffix(".html")
    if capture_path.exists():
        capture_path.unlink()
    downloaded_path.replace(capture_path)
    return capture_path


def _used_candidate_source_page(request: BrowserReportDownloadRequest) -> bool:
    attempt_url = str(request.attempt_url or "").strip()
    source_page_url = str(request.source_page_url_hint or "").strip()
    if not attempt_url or not source_page_url:
        return False
    return normalize_url(attempt_url) == normalize_url(source_page_url)


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


def _read_text_if_small(path: Path, *, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
