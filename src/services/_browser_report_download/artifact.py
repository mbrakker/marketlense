from __future__ import annotations

import json
import logging
from dataclasses import replace
from hashlib import sha256
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, Field, ValidationError

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    ensure_downloaded_pdf,
    extract_embedded_pdf_urls,
    fetch_html_from_url,
    resolve_downloaded_mime_type,
    validate_downloaded_pdf_artifact,
)
from src.services._browser_report_download.request import (
    prepare_download_dir,
    resolve_effective_identity_fields,
)
from src.services._config_service.identity import (
    identity_field_match_tokens,
    normalize_browser_download_identity_key,
)
from src.utils.coercion import (
    is_ambiguous_optional_bool_signal,
    normalize_optional_bool_signal,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

if TYPE_CHECKING:
    from src.services._browser_report_download.browser import BrowserAgentRunResult

_ROUTE_KINDS = {"pdf_download", "email_delivery", "onsite_report"}
_BLOCKED_REASONS = {
    "blocked_email_domain",
    "blocked_captcha",
    "blocked_static_archive",
    "blocked_missing_identity_field",
    "blocked_unknown_required_enum",
}
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
_FORM_SUCCESS_TEXT_MARKERS = (
    "thank you",
    "thanks for",
    "thanks.",
    "submission received",
    "request received",
    "form submitted",
    "successfully submitted",
)
_TRANSIENT_SUBMIT_MESSAGE_MARKERS = (
    "please wait",
    "submitting",
    "processing",
    "loading",
    "one moment",
)
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
    "location",
    "state",
    "region",
    "department",
    "role",
    "job level",
)
_MARKETING_MARKERS = (
    "demo",
    "book a demo",
    "contact sales",
    "get started",
    "request pricing",
    "sign up",
)
_ONSITE_ROUTE_FAMILIES = {
    "browser_onsite_report",
    "browser_listing_hub",
}
_ONPAGE_REPORT_MARKERS = (
    "report",
    "research",
    "insight",
    "analysis",
    "survey",
    "outlook",
)
_NON_REPORT_PAGE_MARKERS = ("blog", "news", "press", "case study", "customer story")
_PAGINATION_END_MARKERS = (
    "last page",
    "final page",
    "end of report",
    "reached the end",
    "no more pages",
    "pagination complete",
)
_SCROLL_GROWTH_MARKERS = (
    "loaded more",
    "expanded",
    "revealed more",
    "appended",
    "new section",
    "new content",
    "end of article",
)
_REPORT_NOT_FOUND_MARKERS = (
    "specific report",
    "not found",
    "0 matches found",
    "zero matches",
    "no matches found",
    "could not find",
    "unable to find",
)
_VERIFIED_EMAIL_SIGNAL_MARKERS = {
    "delivery_text",
    "success_text",
    "success_url",
    "form_disappeared",
    "network_confirmation_request",
}
_ROUTE_STEP_EVIDENCE_CATEGORIES = {
    "screenshot",
    "page_info",
    "network_event",
    "artifact",
    "dom_hash",
    "confirmation_text",
    "dialog",
}
_POST_ACTION_VERIFICATION_ACTIONS = {
    "open",
    "navigate",
    "goto",
    "click",
    "follow",
    "submit",
    "download",
    "save",
    "extract",
    "capture",
    "scroll",
    "wait",
    "select",
    "fill",
    "type",
    "input",
}
_TERMINAL_BOOLEAN_FIELDS = (
    "email_submission_completed",
    "confirmation_url_changed",
    "form_disappeared",
)
logger = logging.getLogger("market_lense.browser_report_download_artifact")


class BrowserUseRouteStep(BaseModel):
    index: int | None = Field(default=None)
    action: str | None = Field(default=None)
    target_text: str | None = Field(default=None)
    target_role: str | None = Field(default=None)
    target_url: str | None = Field(default=None)
    result: str | None = Field(default=None)
    expected_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    verification_status: str | None = Field(default=None)


class BrowserUseAgentResult(BaseModel):
    route_kind: str = Field(
        description="Either `pdf_download`, `email_delivery`, or `onsite_report`."
    )
    route_summary: str | None = Field(
        default=None,
        description="Short description of the working clicks/forms for this URL.",
    )
    route_family: str | None = Field(
        default=None,
        description="Observed route family for this execution attempt when the agent can classify it.",
    )
    resolved_target_url: str | None = Field(
        default=None,
        description="Resolved target URL that produced the final artifact or email form state.",
    )
    final_page_url: str | None = Field(
        default=None,
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
    post_submit_message: str | None = Field(
        default=None,
        description="Visible confirmation or status text shown after a form submission attempt.",
    )
    confirmation_url_changed: bool | None = Field(
        default=None,
        description="Whether the page URL changed after the submission or route-completing action.",
    )
    submit_button_state: str | None = Field(
        default=None,
        description="Observed submit-button state after submission, for example `disabled` or `replaced`.",
    )
    form_disappeared: bool | None = Field(
        default=None,
        description="Whether the form disappeared after submission.",
    )
    blocked_reason: str | None = Field(
        default=None,
        description="Typed blocker code when the flow is blocked instead of completed.",
    )
    blocked_reason_detail: str | None = Field(
        default=None,
        description="Human-readable blocker detail captured from the terminal state when available.",
    )
    final_page_title: str | None = Field(
        default=None,
        description="Observed final page title when available.",
    )
    terminal_text_excerpt: str | None = Field(
        default=None,
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
    onsite_completeness_status: str | None = Field(
        default=None,
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
    final_url = _resolve_terminal_final_url(
        browser_run_final_url=browser_run.final_page_url,
        agent_result_final_url="",
        request_attempt_url=request.attempt_url,
        normalized_url=normalized_url,
    )
    browser_html = _resolve_browser_html(browser_run)
    html_snapshot_path = str(browser_run.html_snapshot_path or "").strip()
    agent_result = _parse_browser_result(
        raw_model_response=browser_run.raw_model_response,
        normalized_url=normalized_url,
        ctx=ctx,
    )
    if agent_result is None:
        return _salvage_without_structured_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            final_url=final_url,
            delivery_email=delivery_email,
            download_dir=download_dir,
            browser_run=browser_run,
        )

    downloaded_path = _resolve_downloaded_file(
        explicit_path=agent_result.downloaded_file_path,
        attachment_paths=browser_run.attachment_paths,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    browser_rendered_capture_path = _resolve_existing_browser_rendered_capture(
        getattr(browser_run, "print_pdf_capture_path", "")
    )
    onsite_capture_path = str(agent_result.onsite_capture_path or "").strip() or None
    if onsite_capture_path is None and browser_rendered_capture_path is not None:
        onsite_capture_path = str(browser_rendered_capture_path)
    if onsite_capture_path and downloaded_path is not None:
        try:
            if (
                downloaded_path.resolve()
                == Path(onsite_capture_path).expanduser().resolve()
            ):
                downloaded_path = None
        except OSError:
            downloaded_path = None
    encountered_form_fields = _normalize_encountered_form_fields(
        agent_result.encountered_form_fields
    )
    final_url = _resolve_terminal_final_url(
        browser_run_final_url=browser_run.final_page_url,
        agent_result_final_url=agent_result.final_page_url,
        request_attempt_url=request.attempt_url,
        normalized_url=normalized_url,
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
            request.candidate_trace.pdf_url
            if request.candidate_trace is not None
            else "",
            *_resolve_observed_document_urls(
                network_resource_urls=list(browser_run.network_resource_urls or []),
                dom_snapshot_html=browser_html,
                candidate_urls=[resolved_target_url, final_url],
            ),
            *list(browser_run.network_resource_urls or []),
            resolved_target_url,
            final_url,
        ],
    )
    blocked_reason = _resolve_blocked_reason(
        request=request,
        delivery_email=delivery_email,
        agent_result=agent_result,
        encountered_form_fields=encountered_form_fields,
        final_url=final_url,
    )
    route_kind = _resolve_route_kind(
        request=request,
        agent_result=agent_result,
        route_kind=agent_result.route_kind,
        downloaded_path=downloaded_path,
        encountered_form_fields=encountered_form_fields,
        post_submit_message=agent_result.post_submit_message,
        blocked_reason=blocked_reason,
    )
    if route_kind == "pdf_download" and downloaded_path is None:
        claimed_artifact_paths = _normalize_string_list(
            [
                str(agent_result.downloaded_file_path or "").strip(),
                *list(browser_run.attachment_paths or []),
                *list(browser_run.downloaded_files or []),
            ]
        )
        error_code = (
            "browser_download_missing_file"
            if claimed_artifact_paths
            else "browser_download_unverified_pdf_claim"
        )
        error_message = (
            "browser-use classified the route as a PDF download but no local file was found"
            if claimed_artifact_paths
            else "browser-use classified the route as a PDF download without producing a verifiable artifact"
        )
        raise AppError(
            code=error_code,
            message=error_message,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "download_dir": str(download_dir),
                "claimed_artifact_paths": claimed_artifact_paths,
            },
        )

    confirmation_evidence = _build_confirmation_evidence(
        agent_result=agent_result,
        final_url=final_url,
        network_events=list(browser_run.network_events or []),
    )
    final_page_title = _resolve_terminal_final_page_title(
        browser_run_final_page_title=browser_run.final_page_title,
        agent_result_final_page_title=agent_result.final_page_title,
    )
    (
        browser_html,
        html_snapshot_path,
    ) = _resolve_terminal_html_and_snapshot(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        route_kind=route_kind,
        final_url=final_url,
        resolved_target_url=resolved_target_url,
        browser_html=browser_html,
        html_snapshot_path=html_snapshot_path,
    )
    if downloaded_path is None:
        downloaded_path, observed_used_candidate_pdf_url = _complete_pdf_artifact(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            downloaded_path=downloaded_path,
            target_urls=[
                request.candidate_trace.pdf_url
                if request.candidate_trace is not None
                else "",
                *_resolve_observed_document_urls(
                    network_resource_urls=list(browser_run.network_resource_urls or []),
                    dom_snapshot_html=browser_html,
                    candidate_urls=[resolved_target_url, final_url],
                ),
                *list(browser_run.network_resource_urls or []),
                resolved_target_url,
                final_url,
            ],
        )
        used_candidate_pdf_url = (
            used_candidate_pdf_url or observed_used_candidate_pdf_url
        )
        if downloaded_path is not None and route_kind != "onsite_report":
            route_kind = "pdf_download"
    confirmation_evidence = _upgrade_confirmation_evidence_from_terminal_html(
        confirmation_evidence=confirmation_evidence,
        email_submission_completed=agent_result.email_submission_completed,
        encountered_form_fields=encountered_form_fields,
        html=browser_html,
    )
    if not final_page_title:
        final_page_title = _extract_html_title(browser_html)
    terminal_text_excerpt = str(
        agent_result.terminal_text_excerpt or ""
    ).strip() or _extract_visible_text_from_html(browser_html)
    blocked_reason_detail = _resolve_blocked_reason_detail(
        agent_result=agent_result,
        blocked_reason=blocked_reason,
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
        route_kind=route_kind,
        blocked_reason=blocked_reason,
    )
    if _looks_like_report_not_found_terminal(
        request=request,
        route_summary=route_summary,
        route_steps=route_steps,
        final_url=final_url,
        terminal_text_excerpt=terminal_text_excerpt,
    ):
        raise AppError(
            code="browser_download_report_not_found",
            message="browser-use reached a listing or search page where the target report was not found",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "final_url": final_url,
                "candidate_title": (
                    request.candidate_trace.title if request.candidate_trace else ""
                ),
                "route_summary": route_summary,
            },
        )
    downloaded_mime_type = resolve_downloaded_mime_type(
        reported_mime_type=str(agent_result.downloaded_mime_type).strip()
        if agent_result.downloaded_mime_type
        else None,
        downloaded_path=downloaded_path,
    )
    onsite_capture_format = (
        str(agent_result.onsite_capture_format or "").strip() or None
    )
    if (
        onsite_capture_format is None
        and browser_rendered_capture_path is not None
        and onsite_capture_path == str(browser_rendered_capture_path)
    ):
        onsite_capture_format = "browser_rendered_pdf"
    if (
        route_kind == "onsite_report"
        and not onsite_capture_path
        and browser_html.strip()
    ):
        onsite_capture_path = str(
            _capture_salvaged_onsite_html(
                request=request,
                normalized_url=normalized_url,
                final_url=final_url,
                html=browser_html,
            )
        )
        onsite_capture_format = onsite_capture_format or "html"
    onsite_page_count = agent_result.onsite_page_count
    if onsite_page_count is None and route_kind == "onsite_report":
        onsite_page_count = max(
            1,
            len(
                _normalize_traversed_page_urls(
                    raw_urls=[*agent_result.traversed_page_urls, final_url]
                )
            ),
        )
    onsite_completeness_status = (
        str(agent_result.onsite_completeness_status or "").strip() or None
    )
    if route_kind == "onsite_report" and not onsite_completeness_status:
        onsite_completeness_status = _infer_onsite_completeness_status(
            html=browser_html,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            page_count=onsite_page_count or 1,
            traversed_page_urls=[*agent_result.traversed_page_urls, final_url],
            route_steps=_resolve_route_steps(
                request=request,
                agent_result=agent_result,
                raw_summary=agent_result.route_summary,
                resolved_target_url=resolved_target_url,
                downloaded_path=downloaded_path,
                confirmation_evidence=confirmation_evidence,
            ),
        )
    if route_kind == "onsite_report":
        (
            onsite_capture_path,
            onsite_capture_format,
        ) = _ensure_onsite_capture_artifact(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            agent_result=agent_result,
            final_url=final_url,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            route_steps=route_steps,
            browser_html=browser_html,
            onsite_capture_path=onsite_capture_path,
            onsite_capture_format=onsite_capture_format,
        )
    (
        route_kind,
        onsite_capture_path,
        onsite_capture_format,
        onsite_page_count,
        onsite_completeness_status,
    ) = _prefer_onsite_capture_over_optional_form_submission(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        agent_result=agent_result,
        browser_html=browser_html,
        route_kind=route_kind,
        final_url=final_url,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
        confirmation_evidence=confirmation_evidence,
        blocked_reason=blocked_reason,
        onsite_capture_path=onsite_capture_path,
        onsite_capture_format=onsite_capture_format,
        onsite_page_count=onsite_page_count,
        onsite_completeness_status=onsite_completeness_status,
        route_steps=route_steps,
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
                ctx=ctx,
                normalized_url=normalized_url,
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
        artifact_validation_detail = _onsite_artifact_validation_detail(
            onsite_capture_format=onsite_capture_format
        )
    elif blocked_reason:
        artifact_validation_status = "blocked"
        artifact_validation_detail = blocked_reason_detail or blocked_reason

    if downloaded_path is not None:
        blocked_reason = None
        blocked_reason_detail = None
    elif route_kind == "onsite_report" and onsite_capture_path:
        blocked_reason = None
        blocked_reason_detail = None
    elif (
        route_kind == "email_delivery"
        and blocked_reason in {None, "blocked_unknown_required_enum"}
        and _confirmation_evidence_verifies_email_delivery(confirmation_evidence)
    ):
        blocked_reason = None
        blocked_reason_detail = None
        artifact_validation_status = "verified"
        artifact_validation_detail = (
            "Verified email-delivery confirmation from terminal page evidence."
        )

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
        route_steps=route_steps,
        final_url=final_url,
        resolved_target_url=resolved_target_url,
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        downloaded_mime_type=downloaded_mime_type,
        onsite_capture_path=onsite_capture_path,
        confirmation_signal_count=confirmation_signal_count,
        artifact_validation_status=artifact_validation_status,
        artifact_validation_detail=artifact_validation_detail,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
        dom_snapshot_html=browser_html,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=str(browser_run.screenshot_path or ""),
        network_resource_urls=list(browser_run.network_resource_urls or []),
        network_events=list(browser_run.network_events or []),
        dialog_evidence=list(browser_run.dialog_evidence or []),
        evidence_labels=[
            *confirmation_evidence.signal_labels,
            "structured_result",
            *_dialog_evidence_labels(list(browser_run.dialog_evidence or [])),
            *_onsite_capture_evidence_labels(onsite_capture_format),
        ],
    )
    route_steps = _verify_post_action_route_steps(
        route_steps=route_steps,
        terminal_evidence=terminal_evidence,
        confirmation_evidence=confirmation_evidence,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    terminal_evidence = _build_terminal_evidence(
        agent_result=agent_result,
        route_steps=route_steps,
        final_url=final_url,
        resolved_target_url=resolved_target_url,
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        downloaded_mime_type=downloaded_mime_type,
        onsite_capture_path=onsite_capture_path,
        confirmation_signal_count=confirmation_signal_count,
        artifact_validation_status=artifact_validation_status,
        artifact_validation_detail=artifact_validation_detail,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
        dom_snapshot_html=browser_html,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=str(browser_run.screenshot_path or ""),
        network_resource_urls=list(browser_run.network_resource_urls or []),
        network_events=list(browser_run.network_events or []),
        dialog_evidence=list(browser_run.dialog_evidence or []),
        evidence_labels=[
            *confirmation_evidence.signal_labels,
            "structured_result",
            *_dialog_evidence_labels(list(browser_run.dialog_evidence or [])),
            *_onsite_capture_evidence_labels(onsite_capture_format),
        ],
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


def _resolve_terminal_final_url(
    *,
    browser_run_final_url: str | None,
    agent_result_final_url: str | None,
    request_attempt_url: str | None,
    normalized_url: str,
) -> str:
    browser_url = str(browser_run_final_url or "").strip()
    if browser_url and browser_url != "about:blank":
        return browser_url
    agent_url = str(agent_result_final_url or "").strip()
    if agent_url and agent_url != "about:blank":
        return agent_url
    return str(request_attempt_url or normalized_url).strip()


def _resolve_terminal_final_page_title(
    *,
    browser_run_final_page_title: str | None,
    agent_result_final_page_title: str | None,
) -> str:
    browser_title = str(browser_run_final_page_title or "").strip()
    if browser_title:
        return browser_title
    return str(agent_result_final_page_title or "").strip()


def _parse_browser_result(
    *,
    raw_model_response: str,
    normalized_url: str,
    ctx: RunContext,
) -> BrowserUseAgentResult | None:
    raw_payload = str(raw_model_response or "").strip()
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="browser_download_invalid_result",
            message="browser-use returned invalid structured JSON",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
            },
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="browser_download_invalid_result",
            message="browser-use structured result root must be an object",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
            },
        )
    payload = _normalize_terminal_boolean_payload(
        payload,
        normalized_url=normalized_url,
        ctx=ctx,
    )
    try:
        return BrowserUseAgentResult.model_validate(payload)
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


def _normalize_terminal_boolean_payload(
    payload: dict[str, object],
    *,
    normalized_url: str,
    ctx: RunContext,
) -> dict[str, object]:
    normalized = dict(payload)
    raw_summary: dict[str, object] = {}
    normalized_summary: dict[str, bool | None] = {}
    ambiguous_fields: list[str] = []
    for field_name in _TERMINAL_BOOLEAN_FIELDS:
        raw_value = payload.get(field_name)
        normalized_value = normalize_optional_bool_signal(raw_value)
        raw_summary[field_name] = raw_value
        normalized_summary[field_name] = normalized_value
        normalized[field_name] = normalized_value
        if is_ambiguous_optional_bool_signal(raw_value):
            ambiguous_fields.append(field_name)
    if ambiguous_fields:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_terminal_signal_ambiguous",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "raw_signals": raw_summary,
                    "normalized_signals": normalized_summary,
                    "ambiguous_fields": ambiguous_fields,
                },
            )
        )
    return normalized


def _salvage_without_structured_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    final_url: str,
    delivery_email: str | None,
    download_dir: Path,
    browser_run: BrowserAgentRunResult,
) -> BrowserReportDownloadResult:
    browser_html = str(browser_run.final_page_html or "")
    final_page_title = str(browser_run.final_page_title or "").strip()
    (
        browser_html,
        html_snapshot_path,
        final_url,
    ) = _recover_salvaged_terminal_html(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        final_url=final_url,
        browser_html=browser_html,
        html_snapshot_path=str(browser_run.html_snapshot_path or ""),
    )
    if not final_page_title:
        final_page_title = _extract_html_title(browser_html)
    terminal_text_excerpt = _extract_visible_text_from_html(browser_html)
    downloaded_path = _resolve_downloaded_file(
        explicit_path=None,
        attachment_paths=browser_run.attachment_paths,
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
            request.candidate_trace.pdf_url
            if request.candidate_trace is not None
            else "",
            *_resolve_observed_document_urls(
                network_resource_urls=list(browser_run.network_resource_urls or []),
                dom_snapshot_html=browser_html,
                candidate_urls=[final_url, request.attempt_url or ""],
            ),
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
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            dom_snapshot_html=browser_html,
            html_snapshot_path=html_snapshot_path,
            screenshot_path=str(browser_run.screenshot_path or ""),
            network_resource_urls=list(browser_run.network_resource_urls or []),
            network_events=list(browser_run.network_events or []),
        )
    encountered_form_fields = _extract_form_fields_from_html(browser_html)
    confirmation_evidence = _build_salvaged_confirmation_evidence(
        request=request,
        final_url=final_url,
        terminal_text_excerpt=terminal_text_excerpt,
        html=browser_html,
        network_events=list(browser_run.network_events or []),
    )
    if _looks_like_non_report_terminal(
        request=request,
        final_url=final_url,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
    ):
        raise AppError(
            code="browser_download_candidate_rejected_non_report",
            message="The browser reached a deterministic non-report terminal page",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "final_url": final_url,
                "final_page_title": final_page_title,
            },
        )
    if _looks_like_onsite_report_html(
        wrapper_html=browser_html,
        request=request,
        agent_result=BrowserUseAgentResult(
            route_kind="onsite_report",
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
        ),
        final_url=final_url,
    ):
        browser_rendered_capture_path = _resolve_existing_browser_rendered_capture(
            getattr(browser_run, "print_pdf_capture_path", "")
        )
        return _build_salvaged_onsite_result(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            browser_html=browser_html,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            confirmation_evidence=confirmation_evidence,
            used_candidate_pdf_url=used_candidate_pdf_url,
            html_snapshot_path=html_snapshot_path,
            screenshot_path=str(browser_run.screenshot_path or ""),
            network_resource_urls=list(browser_run.network_resource_urls or []),
            network_events=list(browser_run.network_events or []),
            onsite_capture_path=str(browser_rendered_capture_path or ""),
            onsite_capture_format=(
                "browser_rendered_pdf" if browser_rendered_capture_path is not None else ""
            ),
        )
    blocked_reason = _resolve_salvaged_blocked_reason(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
        final_url=final_url,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
    )
    if _confirmation_evidence_verifies_email_delivery(confirmation_evidence):
        return _build_salvaged_email_result(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            confirmation_evidence=confirmation_evidence,
            used_candidate_pdf_url=used_candidate_pdf_url,
            encountered_form_fields=encountered_form_fields,
            blocked_reason=None,
            blocked_reason_detail=None,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            route_status="verified",
            outcome="email_requested",
            artifact_validation_status="recovered",
            artifact_validation_detail="Recovered an email-delivery terminal state from deterministic browser evidence.",
            browser_html=browser_html,
            html_snapshot_path=html_snapshot_path,
            screenshot_path=str(browser_run.screenshot_path or ""),
            network_resource_urls=list(browser_run.network_resource_urls or []),
            network_events=list(browser_run.network_events or []),
        )
    if blocked_reason or encountered_form_fields or _html_contains_form(browser_html):
        return _build_salvaged_email_result(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            confirmation_evidence=confirmation_evidence,
            used_candidate_pdf_url=used_candidate_pdf_url,
            encountered_form_fields=encountered_form_fields,
            blocked_reason=blocked_reason,
            blocked_reason_detail=terminal_text_excerpt or blocked_reason,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            route_status="inferred",
            outcome="email_required",
            artifact_validation_status="blocked" if blocked_reason else "recovered",
            artifact_validation_detail=terminal_text_excerpt
            or blocked_reason
            or "Recovered a gated-form terminal state from browser evidence.",
            browser_html=browser_html,
            html_snapshot_path=html_snapshot_path,
            screenshot_path=str(browser_run.screenshot_path or ""),
            network_resource_urls=list(browser_run.network_resource_urls or []),
            network_events=list(browser_run.network_events or []),
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


def _recover_salvaged_terminal_html(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    final_url: str,
    browser_html: str,
    html_snapshot_path: str,
) -> tuple[str, str, str]:
    current_html = str(browser_html or "")
    current_snapshot = str(html_snapshot_path or "").strip()
    recovered_final_url = str(final_url or "").strip()
    if current_html.strip():
        if current_snapshot:
            return current_html, current_snapshot, recovered_final_url
        return (
            current_html,
            _write_terminal_html_snapshot(download_dir=download_dir, html=current_html),
            recovered_final_url,
        )
    fetch_targets = _normalize_string_list(
        [
            recovered_final_url,
            str(request.attempt_url or "").strip(),
            normalized_url,
        ]
    )
    for fetch_target in fetch_targets:
        fetched_html = _try_fetch_terminal_html(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=fetch_target,
        )
        if not fetched_html.strip():
            continue
        return (
            fetched_html,
            _write_terminal_html_snapshot(download_dir=download_dir, html=fetched_html),
            fetch_target,
        )
    return "", current_snapshot, recovered_final_url


def _complete_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    downloaded_path: Path | None,
    target_urls: Iterable[str | None],
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
            if not _downloaded_pdf_matches_requested_report(
                request=request,
                downloaded_path=ensured_path,
            ):
                return None, False
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
    target_url = urljoin(str(request.attempt_url or normalized_url).strip(), target_url)
    if not _looks_like_pdf_url(target_url):
        return None
    if not _pdf_url_matches_requested_report(request=request, pdf_url=target_url):
        return None
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


def _looks_like_pdf_url(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return lowered.startswith(("http://", "https://")) and (
        lowered.endswith(".pdf") or ".pdf?" in lowered
    )


_PDF_RELEVANCE_STOPWORDS = {
    "and",
    "download",
    "ebook",
    "final",
    "for",
    "from",
    "guide",
    "insight",
    "insights",
    "pdf",
    "report",
    "reports",
    "study",
    "the",
    "whitepaper",
    "with",
}


def _downloaded_pdf_matches_requested_report(
    *,
    request: BrowserReportDownloadRequest,
    downloaded_path: Path | None,
) -> bool:
    if downloaded_path is None:
        return True
    return _pdf_identifier_matches_requested_report(
        request=request,
        pdf_identifier=downloaded_path.name,
    )


def _pdf_url_matches_requested_report(
    *,
    request: BrowserReportDownloadRequest,
    pdf_url: str,
) -> bool:
    return _pdf_identifier_matches_requested_report(
        request=request,
        pdf_identifier=str(urlsplit(str(pdf_url or "")).path or ""),
    )


def _pdf_identifier_matches_requested_report(
    *,
    request: BrowserReportDownloadRequest,
    pdf_identifier: str,
) -> bool:
    pdf_tokens = _report_relevance_tokens(pdf_identifier)
    if len(pdf_tokens) < 3:
        return True
    context_tokens = _requested_report_relevance_tokens(request)
    if len(context_tokens) < 2:
        return True
    return len(pdf_tokens & context_tokens) >= 2


def _requested_report_relevance_tokens(
    request: BrowserReportDownloadRequest,
) -> set[str]:
    values = [
        request.url,
        request.attempt_url or "",
        request.route_hint or "",
    ]
    if request.candidate_trace is not None:
        values.extend(
            [
                request.candidate_trace.title or "",
                request.candidate_trace.canonical_url or "",
            ]
        )
    tokens: set[str] = set()
    for value in values:
        tokens.update(_report_relevance_tokens(value))
    return tokens


def _report_relevance_tokens(value: str | None) -> set[str]:
    parsed = urlsplit(str(value or "").strip())
    source = parsed.path if parsed.scheme or parsed.netloc else str(value or "")
    token = source.casefold()
    tokens = {
        match.group(0)
        for match in re.finditer(r"[a-z0-9]{2,}", token)
        if match.group(0) not in _PDF_RELEVANCE_STOPWORDS
    }
    return {item for item in tokens if len(item) >= 3 or item.isdigit()}


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
    final_page_title: str = "",
    terminal_text_excerpt: str = "",
    dom_snapshot_html: str = "",
    html_snapshot_path: str = "",
    screenshot_path: str = "",
    network_resource_urls: list[str] | None = None,
    network_events: list[BrowserDownloadNetworkEvent] | None = None,
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
            final_page_title=str(final_page_title or "").strip(),
            terminal_text_excerpt=str(terminal_text_excerpt or "").strip(),
            artifact_url=resolved_target_url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="Validated local PDF artifact.",
            confirmation_signal_count=0,
            traversed_page_urls=_normalize_traversed_page_urls(
                raw_urls=[resolved_target_url, final_url]
            ),
            visited_url_timeline=_resolve_visited_url_timeline(
                route_steps=route_steps,
                traversed_page_urls=[resolved_target_url, final_url],
            ),
            observed_document_urls=_resolve_observed_document_urls(
                network_resource_urls=network_resource_urls or [],
                dom_snapshot_html=dom_snapshot_html,
                candidate_urls=[
                    resolved_target_url,
                    final_url,
                    str(downloaded_path),
                ],
            ),
            network_events=_normalize_network_events(network_events or []),
            html_snapshot_path=str(html_snapshot_path or "").strip(),
            screenshot_path=str(screenshot_path or "").strip(),
            dom_snapshot_sha256=_dom_snapshot_sha256(dom_snapshot_html),
            evidence_labels=["pdf_artifact", "verified"],
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


def _build_salvaged_confirmation_evidence(
    *,
    request: BrowserReportDownloadRequest,
    final_url: str,
    terminal_text_excerpt: str,
    html: str,
    network_events: list[BrowserDownloadNetworkEvent],
) -> BrowserDownloadConfirmationEvidence:
    submit_observed = bool(
        (
            (_html_contains_form(html) and not _html_contains_submit_control(html))
            or "please wait" in terminal_text_excerpt.casefold()
            or _url_indicates_confirmation(final_url)
        )
        and str(request.route_family_hint or "").strip()
        in {"browser_email_form", "browser_pdf_click", "browser_tracker_redirect"}
    )
    signal_labels = _build_confirmation_signal_labels(
        visible_confirmation_text=terminal_text_excerpt,
        final_page_url=final_url,
        url_changed=bool(
            final_url and final_url != str(request.attempt_url or request.url).strip()
        ),
        submit_button_state="disabled"
        if "please wait" in terminal_text_excerpt.casefold()
        else "unchanged",
        form_disappeared=not _html_contains_form(html),
        email_submission_completed=True if submit_observed else None,
        network_signal_labels=_build_network_confirmation_signal_labels(
            network_events=network_events,
        ),
    )
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=bool(
            final_url and final_url != str(request.attempt_url or request.url).strip()
        ),
        visible_confirmation_text=terminal_text_excerpt,
        submit_button_state="disabled"
        if "please wait" in terminal_text_excerpt.casefold()
        else "unchanged",
        form_disappeared=not _html_contains_form(html),
        final_page_url=final_url,
        confirmation_score=len(signal_labels),
        signal_labels=signal_labels,
    )


def _build_salvaged_email_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    final_url: str,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    used_candidate_pdf_url: bool,
    encountered_form_fields: list[str],
    blocked_reason: str | None,
    blocked_reason_detail: str | None,
    final_page_title: str,
    terminal_text_excerpt: str,
    route_status: str,
    outcome: str,
    artifact_validation_status: str,
    artifact_validation_detail: str,
    browser_html: str,
    html_snapshot_path: str,
    screenshot_path: str,
    network_resource_urls: list[str],
    network_events: list[BrowserDownloadNetworkEvent],
) -> BrowserReportDownloadResult:
    route_steps = [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=str(request.attempt_url or request.url).strip(),
            target_role="url",
            target_url=final_url or request.attempt_url or normalized_url,
            result="submitted" if outcome == "email_requested" else "blocked",
        )
    ]
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="email_delivery",
        route_family=request.route_family_hint or "browser_email_form",
        route_status=route_status,
        outcome=outcome,
        route_summary="Open the gated report page, inspect the form, and classify the terminal form state from deterministic browser evidence.",
        final_page_url=final_url,
        resolved_target_url=final_url or request.attempt_url or normalized_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=confirmation_evidence,
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_url,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            artifact_url=final_url,
            artifact_kind="email_delivery",
            artifact_validation_status=artifact_validation_status,
            artifact_validation_detail=artifact_validation_detail,
            confirmation_signal_count=confirmation_evidence.confirmation_score,
            traversed_page_urls=_normalize_traversed_page_urls(
                raw_urls=[request.attempt_url or "", final_url]
            ),
            visited_url_timeline=_resolve_visited_url_timeline(
                route_steps=route_steps,
                traversed_page_urls=[request.attempt_url or "", final_url],
            ),
            observed_document_urls=_resolve_observed_document_urls(
                network_resource_urls=network_resource_urls,
                dom_snapshot_html=browser_html,
                candidate_urls=[final_url],
            ),
            network_events=_normalize_network_events(network_events),
            html_snapshot_path=str(html_snapshot_path or "").strip(),
            screenshot_path=str(screenshot_path or "").strip(),
            dom_snapshot_sha256=_dom_snapshot_sha256(browser_html),
            evidence_labels=_normalize_string_list(
                [
                    *confirmation_evidence.signal_labels,
                    "salvaged_browser_terminal",
                    "email_delivery",
                ]
            ),
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=_used_candidate_source_page(request),
        encountered_form_fields=encountered_form_fields,
        blocked_reason=blocked_reason,
        blocked_reason_detail=blocked_reason_detail,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def _build_salvaged_onsite_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    final_url: str,
    browser_html: str,
    final_page_title: str,
    terminal_text_excerpt: str,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    used_candidate_pdf_url: bool,
    html_snapshot_path: str,
    screenshot_path: str,
    network_resource_urls: list[str],
    network_events: list[BrowserDownloadNetworkEvent],
    onsite_capture_path: str = "",
    onsite_capture_format: str = "",
) -> BrowserReportDownloadResult:
    capture_path = Path(onsite_capture_path) if onsite_capture_path else None
    if capture_path is None or not capture_path.is_file():
        capture_path = _capture_salvaged_onsite_html(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            html=browser_html,
        )
        onsite_capture_format = onsite_capture_format or "html"
    page_count = max(
        1,
        len(
            _normalize_traversed_page_urls(
                raw_urls=[request.attempt_url or "", final_url]
            )
        ),
    )
    completeness_status = _infer_onsite_completeness_status(
        html=browser_html,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
        page_count=page_count,
        traversed_page_urls=[request.attempt_url or "", final_url],
        route_steps=[],
    )
    route_status = "verified" if completeness_status == "complete" else "inferred"
    route_steps = [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=str(request.attempt_url or request.url).strip(),
            target_role="url",
            target_url=final_url or request.attempt_url or normalized_url,
            result="captured",
        )
    ]
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="onsite_report",
        route_family=request.route_family_hint or "browser_onsite_report",
        route_status=route_status,
        outcome="captured",
        route_summary="Open the longread report, capture the on-site content locally, and verify completeness from deterministic browser evidence.",
        final_page_url=final_url,
        resolved_target_url=final_url or request.attempt_url or normalized_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=confirmation_evidence,
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_url,
            final_page_title=final_page_title,
            terminal_text_excerpt=terminal_text_excerpt,
            artifact_url=final_url,
            artifact_kind="onsite_report",
            artifact_validation_status="captured",
            artifact_validation_detail=_onsite_artifact_validation_detail(
                onsite_capture_format=onsite_capture_format
            ),
            confirmation_signal_count=confirmation_evidence.confirmation_score,
            traversed_page_urls=_normalize_traversed_page_urls(
                raw_urls=[request.attempt_url or "", final_url]
            ),
            visited_url_timeline=_resolve_visited_url_timeline(
                route_steps=route_steps,
                traversed_page_urls=[request.attempt_url or "", final_url],
            ),
            observed_document_urls=_resolve_observed_document_urls(
                network_resource_urls=network_resource_urls,
                dom_snapshot_html=browser_html,
                candidate_urls=[final_url],
            ),
            network_events=_normalize_network_events(network_events),
            html_snapshot_path=str(html_snapshot_path or "").strip(),
            screenshot_path=str(screenshot_path or "").strip(),
            dom_snapshot_sha256=_dom_snapshot_sha256(browser_html),
            evidence_labels=[
                "onsite_report",
                completeness_status,
                "salvaged_browser_terminal",
                *_onsite_capture_evidence_labels(onsite_capture_format),
            ],
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
        onsite_capture_path=str(capture_path),
        onsite_capture_format=onsite_capture_format or "html",
        onsite_page_count=page_count,
        onsite_completeness_status=completeness_status,
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


def _extract_form_fields_from_html(html: str) -> list[str]:
    labels: list[str] = []
    for match in re.finditer(r"(?is)<label[^>]*>(.*?)</label>", str(html or "")):
        token = _extract_visible_text_from_html(match.group(1), max_chars=80)
        if token:
            labels.append(token)
    for pattern in (
        r'(?i)\bplaceholder=["\']([^"\']+)["\']',
        r'(?i)\bname=["\']([^"\']+)["\']',
        r'(?i)\baria-label=["\']([^"\']+)["\']',
    ):
        for match in re.finditer(pattern, str(html or "")):
            token = str(match.group(1) or "").strip()
            if token:
                labels.append(token)
    return _normalize_encountered_form_fields(labels)


def _html_contains_form(html: str) -> bool:
    token = str(html or "").casefold()
    return (
        "<form" in token
        or "<input" in token
        or "<select" in token
        or "<textarea" in token
    )


def _html_contains_submit_control(html: str) -> bool:
    token = str(html or "").casefold()
    return 'type="submit"' in token or "type='submit'" in token or ">submit<" in token


def _resolve_route_summary(
    *,
    raw_summary: str | None,
    route_steps: list[BrowserDownloadRouteStep],
    normalized_url: str,
    route_kind: str,
    blocked_reason: str | None,
) -> str:
    route_summary = str(raw_summary or "").strip()
    if route_summary and _is_semantic_route_summary(route_summary):
        return route_summary
    if route_steps:
        return _derive_route_summary(route_steps)
    if route_kind == "email_delivery" and blocked_reason:
        return (
            f"Open the gated page and stop when the form is blocked ({blocked_reason})."
        )
    if route_kind == "onsite_report":
        return "Open the on-site report and capture the available longread content."
    if route_summary:
        if _is_page_load_failure_summary(route_summary):
            raise AppError(
                code="browser_download_page_not_loaded",
                message="browser-use reached an empty or unloaded browser page",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "route_summary": route_summary,
                },
            )
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


def _is_page_load_failure_summary(route_summary: str) -> bool:
    lowered = " ".join(str(route_summary or "").split()).casefold()
    if not lowered:
        return False
    page_markers = ("page", "tab", "url", "content")
    failure_markers = (
        "failed to load",
        "did not load",
        "not load",
        "empty",
        "blank",
        "no content",
        "without content",
    )
    return any(marker in lowered for marker in page_markers) and any(
        marker in lowered for marker in failure_markers
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
    post_submit_message: str | None,
    blocked_reason: str | None,
) -> str:
    token = str(route_kind or "").strip().lower()
    if downloaded_path is not None:
        return "pdf_download"
    if blocked_reason:
        return "email_delivery"
    if token in _BLOCKED_REASONS:
        return "email_delivery"
    if _message_indicates_email_delivery(post_submit_message):
        return "email_delivery"
    if (
        token == "onsite_report"
        or agent_result.onsite_capture_path
        or str(agent_result.onsite_completeness_status or "").strip()
    ):
        return "onsite_report"
    if encountered_form_fields:
        return "email_delivery"
    if str(request.route_family_hint or "").strip() == "browser_onsite_report":
        return "onsite_report"
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
    network_events: list[BrowserDownloadNetworkEvent],
) -> BrowserDownloadConfirmationEvidence:
    visible_confirmation_text = str(agent_result.post_submit_message or "").strip()
    effective_final_url = str(final_url or agent_result.final_page_url or "").strip()
    url_changed = bool(agent_result.confirmation_url_changed) or (
        bool(effective_final_url)
        and bool(str(agent_result.final_page_url or "").strip())
        and normalize_url(effective_final_url)
        != normalize_url(str(agent_result.final_page_url or "").strip())
    )
    signal_labels = _build_confirmation_signal_labels(
        visible_confirmation_text=visible_confirmation_text,
        final_page_url=effective_final_url,
        url_changed=url_changed,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        email_submission_completed=agent_result.email_submission_completed,
        network_signal_labels=_build_network_confirmation_signal_labels(
            network_events=network_events,
        ),
    )
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=url_changed,
        visible_confirmation_text=visible_confirmation_text,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        final_page_url=effective_final_url,
        confirmation_score=len(signal_labels),
        signal_labels=signal_labels,
    )


def _upgrade_confirmation_evidence_from_terminal_html(
    *,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    email_submission_completed: bool | None,
    encountered_form_fields: list[str],
    html: str,
) -> BrowserDownloadConfirmationEvidence:
    if email_submission_completed is not True and not encountered_form_fields:
        return confirmation_evidence
    token = str(html or "").strip()
    if not token:
        return confirmation_evidence
    terminal_confirmation_text = _resolve_terminal_confirmation_text_from_html(
        html=token,
        fallback_text=confirmation_evidence.visible_confirmation_text,
    )
    form_disappeared = confirmation_evidence.form_disappeared or (
        bool(encountered_form_fields) and not _html_contains_form(token)
    )
    if (
        terminal_confirmation_text == confirmation_evidence.visible_confirmation_text
        and form_disappeared == confirmation_evidence.form_disappeared
    ):
        return confirmation_evidence
    signal_labels = _build_confirmation_signal_labels(
        visible_confirmation_text=terminal_confirmation_text,
        final_page_url=confirmation_evidence.final_page_url,
        url_changed=confirmation_evidence.url_changed,
        submit_button_state=confirmation_evidence.submit_button_state,
        form_disappeared=form_disappeared,
        email_submission_completed=(
            True
            if (
                email_submission_completed is True
                or _message_indicates_email_delivery(terminal_confirmation_text)
                or _message_indicates_form_success(terminal_confirmation_text)
            )
            else email_submission_completed
        ),
    )
    return BrowserDownloadConfirmationEvidence(
        schema_version=confirmation_evidence.schema_version,
        url_changed=confirmation_evidence.url_changed,
        visible_confirmation_text=terminal_confirmation_text,
        submit_button_state=confirmation_evidence.submit_button_state,
        form_disappeared=form_disappeared,
        final_page_url=confirmation_evidence.final_page_url,
        confirmation_score=len(signal_labels),
        signal_labels=signal_labels,
    )


def _resolve_terminal_confirmation_text_from_html(
    *,
    html: str,
    fallback_text: str,
) -> str:
    terminal_text = _extract_visible_text_from_html(html, max_chars=800)
    if not terminal_text:
        return fallback_text
    if _message_indicates_email_delivery(
        terminal_text
    ) or _message_indicates_form_success(terminal_text):
        return terminal_text
    if _message_indicates_transient_submit_state(
        fallback_text
    ) and not _message_indicates_transient_submit_state(terminal_text):
        return terminal_text
    return fallback_text


def _build_terminal_evidence(
    *,
    agent_result: BrowserUseAgentResult,
    route_steps: list[BrowserDownloadRouteStep],
    final_url: str,
    resolved_target_url: str,
    route_kind: str,
    downloaded_path: Path | None,
    downloaded_mime_type: str | None,
    onsite_capture_path: str | None,
    confirmation_signal_count: int,
    artifact_validation_status: str,
    artifact_validation_detail: str,
    final_page_title: str,
    terminal_text_excerpt: str,
    dom_snapshot_html: str,
    html_snapshot_path: str,
    screenshot_path: str,
    network_resource_urls: list[str],
    network_events: list[BrowserDownloadNetworkEvent],
    dialog_evidence: list[BrowserDownloadDialogEvidence],
    evidence_labels: list[str],
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
        final_page_title=str(final_page_title or "").strip(),
        terminal_text_excerpt=str(terminal_text_excerpt or "").strip(),
        artifact_url=str(artifact_url or "").strip(),
        artifact_kind=str(artifact_kind or "none").strip() or "none",
        artifact_validation_status=str(artifact_validation_status or "none").strip()
        or "none",
        artifact_validation_detail=str(artifact_validation_detail or "").strip(),
        confirmation_signal_count=confirmation_signal_count,
        traversed_page_urls=_normalize_traversed_page_urls(
            raw_urls=[*agent_result.traversed_page_urls, resolved_target_url, final_url]
        ),
        visited_url_timeline=_resolve_visited_url_timeline(
            route_steps=route_steps,
            traversed_page_urls=[
                *agent_result.traversed_page_urls,
                resolved_target_url,
                final_url,
            ],
        ),
        observed_document_urls=_resolve_observed_document_urls(
            network_resource_urls=network_resource_urls,
            dom_snapshot_html=dom_snapshot_html,
            candidate_urls=[
                resolved_target_url,
                final_url,
                str(downloaded_path) if downloaded_path is not None else "",
                str(onsite_capture_path or "").strip(),
            ],
        ),
        network_events=_normalize_network_events(network_events),
        dialog_evidence=_normalize_dialog_evidence(dialog_evidence),
        html_snapshot_path=str(html_snapshot_path or "").strip(),
        screenshot_path=str(screenshot_path or "").strip(),
        dom_snapshot_sha256=_dom_snapshot_sha256(dom_snapshot_html),
        evidence_labels=_normalize_string_list(
            [*evidence_labels, artifact_validation_status, artifact_kind]
        ),
    )


def _verify_post_action_route_steps(
    *,
    route_steps: list[BrowserDownloadRouteStep],
    terminal_evidence: DownloadTerminalEvidence,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    ctx: RunContext,
    normalized_url: str,
) -> list[BrowserDownloadRouteStep]:
    enriched_steps: list[BrowserDownloadRouteStep] = []
    missing_steps: list[dict[str, object]] = []
    for step in route_steps:
        expected_evidence = _expected_post_action_evidence(step)
        observed_evidence = _observed_post_action_evidence(
            expected_evidence=expected_evidence,
            terminal_evidence=terminal_evidence,
            confirmation_evidence=confirmation_evidence,
        )
        status = (
            "not_applicable"
            if not expected_evidence
            else "verified"
            if observed_evidence
            else "missing"
        )
        enriched_step = replace(
            step,
            expected_evidence=expected_evidence,
            observed_evidence=observed_evidence,
            verification_status=status,
        )
        enriched_steps.append(enriched_step)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_route_step_verification",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "step_index": enriched_step.index,
                    "action": enriched_step.action,
                    "target_text": enriched_step.target_text,
                    "target_role": enriched_step.target_role,
                    "target_url": enriched_step.target_url,
                    "result": enriched_step.result,
                    "expected_evidence": list(expected_evidence),
                    "observed_evidence": list(observed_evidence),
                    "validation_result": status,
                    "verification_status": status,
                },
            )
        )
        if status == "missing":
            missing_steps.append(
                {
                    "index": enriched_step.index,
                    "action": enriched_step.action,
                    "target_text": enriched_step.target_text,
                    "target_role": enriched_step.target_role,
                    "target_url": enriched_step.target_url,
                    "result": enriched_step.result,
                    "expected_evidence": list(expected_evidence),
                }
            )
    if missing_steps:
        raise AppError(
            code="browser_download_route_step_verification_missing",
            message="browser-use route steps are missing required post-action verification evidence",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "missing_steps": missing_steps,
                "terminal_evidence_labels": list(terminal_evidence.evidence_labels),
                "terminal_final_page_url": terminal_evidence.final_page_url,
                "terminal_screenshot_path": terminal_evidence.screenshot_path,
                "terminal_html_snapshot_path": terminal_evidence.html_snapshot_path,
                "terminal_dom_snapshot_sha256": terminal_evidence.dom_snapshot_sha256,
                "terminal_network_event_count": len(terminal_evidence.network_events),
                "confirmation_signal_labels": list(confirmation_evidence.signal_labels),
            },
        )
    return enriched_steps


def _expected_post_action_evidence(step: BrowserDownloadRouteStep) -> list[str]:
    declared = _normalize_evidence_categories(step.expected_evidence)
    if declared:
        return declared
    action = str(step.action or "").strip().casefold()
    result = str(step.result or "").strip().casefold()
    haystack = " ".join(
        [
            action,
            result,
            str(step.target_role or "").strip().casefold(),
            str(step.target_text or "").strip().casefold(),
            str(step.target_url or "").strip().casefold(),
        ]
    )
    if action not in _POST_ACTION_VERIFICATION_ACTIONS and not any(
        marker in haystack
        for marker in (
            "open",
            "navigate",
            "click",
            "submit",
            "download",
            "captured",
            "saved",
            "redirect",
        )
    ):
        return []
    if action in {"download", "save"} or any(
        marker in haystack for marker in ("downloaded", "saved", ".pdf", "pdf")
    ):
        return ["artifact", "network_event", "screenshot"]
    if action in {"submit"} or any(
        marker in haystack
        for marker in ("submitted", "confirmation", "thank", "emailed", "sent")
    ):
        return ["confirmation_text", "network_event", "screenshot"]
    if action in {"extract", "capture"} or any(
        marker in haystack for marker in ("captured", "extracted", "longread")
    ):
        return ["artifact", "dom_hash", "screenshot"]
    return ["page_info", "screenshot", "network_event", "dom_hash", "artifact"]


def _observed_post_action_evidence(
    *,
    expected_evidence: list[str],
    terminal_evidence: DownloadTerminalEvidence,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> list[str]:
    available = set(_available_terminal_evidence_categories(terminal_evidence))
    if confirmation_evidence.visible_confirmation_text.strip() or any(
        label in _VERIFIED_EMAIL_SIGNAL_MARKERS
        for label in confirmation_evidence.signal_labels
    ):
        available.add("confirmation_text")
    return [item for item in expected_evidence if item in available]


def _available_terminal_evidence_categories(
    terminal_evidence: DownloadTerminalEvidence,
) -> list[str]:
    categories: list[str] = []
    if (
        str(terminal_evidence.final_page_url or "").strip()
        or str(terminal_evidence.final_page_title or "").strip()
        or str(terminal_evidence.terminal_text_excerpt or "").strip()
    ):
        categories.append("page_info")
    if _path_exists(terminal_evidence.screenshot_path):
        categories.append("screenshot")
    if terminal_evidence.network_events:
        categories.append("network_event")
    if terminal_evidence.dialog_evidence:
        categories.append("dialog")
    if (
        str(terminal_evidence.artifact_validation_status or "").strip()
        in {"verified", "recovered", "captured", "blocked"}
        or str(terminal_evidence.artifact_kind or "").strip()
        in {"application/pdf", "pdf", "onsite_report"}
        or str(terminal_evidence.artifact_url or "").strip().casefold().endswith(".pdf")
    ):
        categories.append("artifact")
    if str(terminal_evidence.dom_snapshot_sha256 or "").strip() or _path_exists(
        terminal_evidence.html_snapshot_path
    ):
        categories.append("dom_hash")
    return _normalize_evidence_categories(categories)


def _normalize_evidence_categories(raw_values: Iterable[str | None]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        token = str(raw_value or "").strip().casefold().replace("-", "_")
        if token == "network":
            token = "network_event"
        if token == "page":
            token = "page_info"
        if token == "dom":
            token = "dom_hash"
        if token == "confirmation":
            token = "confirmation_text"
        if token not in _ROUTE_STEP_EVIDENCE_CATEGORIES or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _path_exists(raw_path: str | None) -> bool:
    token = str(raw_path or "").strip()
    if not token:
        return False
    try:
        return Path(token).exists()
    except OSError:
        return False


def _normalize_network_events(
    network_events: list[BrowserDownloadNetworkEvent],
) -> list[BrowserDownloadNetworkEvent]:
    normalized: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for event in network_events:
        url = str(event.url or "").strip()
        if not url:
            continue
        initiator_type = str(event.initiator_type or "").strip() or "other"
        signal_kind = str(event.signal_kind or "").strip() or "other"
        marker = (
            url.casefold(),
            initiator_type.casefold(),
            signal_kind.casefold(),
        )
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(
            BrowserDownloadNetworkEvent(
                schema_version=str(event.schema_version or "1.0"),
                url=url,
                initiator_type=initiator_type,
                signal_kind=signal_kind,
            )
        )
    return normalized


def _normalize_dialog_evidence(
    dialog_evidence: list[BrowserDownloadDialogEvidence],
) -> list[BrowserDownloadDialogEvidence]:
    normalized: list[BrowserDownloadDialogEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in dialog_evidence:
        dialog_type = str(item.dialog_type or "unknown").strip() or "unknown"
        message = str(item.message or "").strip()
        page_url = str(item.page_url or "").strip()
        action_taken = str(item.action_taken or "none").strip() or "none"
        validation_status = (
            str(item.validation_status or "failed").strip() or "failed"
        )
        marker = (
            dialog_type.casefold(),
            message.casefold(),
            page_url.casefold(),
            action_taken.casefold(),
        )
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(
            BrowserDownloadDialogEvidence(
                schema_version=str(item.schema_version or "1.0"),
                dialog_type=dialog_type,
                message=message,
                page_url=page_url,
                action_taken=action_taken,
                validation_status=validation_status,
                target_id=str(item.target_id or "").strip(),
                session_id=str(item.session_id or "").strip(),
            )
        )
    return normalized


def _dialog_evidence_labels(
    dialog_evidence: list[BrowserDownloadDialogEvidence],
) -> list[str]:
    if not dialog_evidence:
        return []
    labels = ["javascript_dialog"]
    if any(item.dialog_type == "beforeunload" for item in dialog_evidence):
        labels.append("beforeunload_dialog")
    if any(item.validation_status == "policy_rejected" for item in dialog_evidence):
        labels.append("dialog_policy_rejected")
    if any(item.validation_status == "handled" for item in dialog_evidence):
        labels.append("dialog_handled")
    return labels


def _resolve_visited_url_timeline(
    *,
    route_steps: list[BrowserDownloadRouteStep],
    traversed_page_urls: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for step in route_steps:
        token = str(step.target_url or "").strip()
        if not token:
            continue
        marker = normalize_url(token)
        if marker in seen:
            continue
        seen.add(marker)
        ordered.append(token)
    for raw_url in traversed_page_urls:
        token = str(raw_url or "").strip()
        if not token:
            continue
        marker = normalize_url(token)
        if marker in seen:
            continue
        seen.add(marker)
        ordered.append(token)
    return ordered


def _resolve_observed_document_urls(
    *,
    network_resource_urls: Iterable[str | None],
    dom_snapshot_html: str,
    candidate_urls: Iterable[str | None],
) -> list[str]:
    observed: list[str] = []
    seen: set[str] = set()

    def add(raw_value: str | None) -> None:
        token = str(raw_value or "").strip()
        if not token:
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        observed.append(token)

    for raw_url in network_resource_urls:
        add(raw_url)
    for raw_url in extract_embedded_pdf_urls(
        wrapper_html=dom_snapshot_html,
        document_url="",
    ):
        add(raw_url)
    for raw_value in candidate_urls:
        token = str(raw_value or "").strip()
        lowered = token.casefold()
        if not token:
            continue
        if lowered.endswith(".pdf") or ".pdf?" in lowered or token.startswith("http"):
            add(token)
    return observed


def _build_network_confirmation_signal_labels(
    *,
    network_events: list[BrowserDownloadNetworkEvent],
) -> list[str]:
    labels: list[str] = []
    if any(event.signal_kind == "submission_request" for event in network_events):
        labels.append("network_submission_request")
    if any(event.signal_kind == "confirmation_request" for event in network_events):
        labels.append("network_confirmation_request")
    return labels


def _resolve_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    agent_result: BrowserUseAgentResult,
    encountered_form_fields: list[str],
    final_url: str,
) -> str | None:
    post_submit_message = str(agent_result.post_submit_message or "").strip()
    if _message_indicates_confirmed_email_delivery(post_submit_message):
        return None
    explicit = str(agent_result.blocked_reason or "").strip().lower()
    route_kind_token = str(agent_result.route_kind or "").strip().lower()
    blocker_haystack = " ".join(
        [
            post_submit_message,
            str(agent_result.blocked_reason_detail or "").strip(),
            str(agent_result.final_page_title or "").strip(),
        ]
    ).casefold()
    if explicit:
        normalized_explicit = _normalize_explicit_blocked_reason(
            request=request,
            delivery_email=delivery_email,
            explicit_blocked_reason=explicit,
            encountered_form_fields=encountered_form_fields,
            blocker_haystack=blocker_haystack,
        )
        if normalized_explicit:
            return normalized_explicit
    if route_kind_token in _BLOCKED_REASONS:
        normalized_kind = _normalize_explicit_blocked_reason(
            request=request,
            delivery_email=delivery_email,
            explicit_blocked_reason=route_kind_token,
            encountered_form_fields=encountered_form_fields,
            blocker_haystack=blocker_haystack,
        )
        if normalized_kind:
            return normalized_kind
    if _message_indicates_email_delivery(post_submit_message):
        return None
    if agent_result.email_submission_completed is True:
        return None
    if any(marker in blocker_haystack for marker in _EMAIL_DOMAIN_BLOCK_MARKERS):
        return "blocked_email_domain"
    if any(marker in blocker_haystack for marker in _CAPTCHA_MARKERS):
        return "blocked_captcha"
    if any(marker in blocker_haystack for marker in _STATIC_ARCHIVE_MARKERS) or any(
        marker in str(final_url or "").casefold() for marker in _STATIC_ARCHIVE_MARKERS
    ):
        return "blocked_static_archive"
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_unknown_required_enum"
    if encountered_form_fields and _message_indicates_unknown_required_enum(
        blocker_haystack
    ):
        return "blocked_unknown_required_enum"
    return None


def _resolve_blocked_reason_detail(
    *,
    agent_result: BrowserUseAgentResult,
    blocked_reason: str | None,
) -> str | None:
    if not blocked_reason:
        return None
    detail = str(agent_result.blocked_reason_detail or "").strip()
    if detail:
        return detail
    return (
        str(
            agent_result.post_submit_message or agent_result.terminal_text_excerpt or ""
        ).strip()
        or blocked_reason
    )


def _resolve_route_steps(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    raw_summary: str | None,
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
                expected_evidence=_normalize_evidence_categories(
                    raw_step.expected_evidence
                ),
                observed_evidence=_normalize_evidence_categories(
                    raw_step.observed_evidence
                ),
                verification_status=str(raw_step.verification_status or "").strip(),
            )
        )
    if steps:
        return steps
    if not _is_semantic_route_summary(str(raw_summary or "").strip()):
        return []
    fallback_result = "downloaded" if downloaded_path is not None else "completed"
    if (
        confirmation_evidence.visible_confirmation_text
        or confirmation_evidence.url_changed
    ):
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
            expected_evidence=[],
            observed_evidence=[],
            verification_status="",
        )
    ]


def _recover_from_invalid_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
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
    if _agent_result_indicates_report_not_found(
        request=request,
        agent_result=agent_result,
        final_url=final_url,
    ):
        raise AppError(
            code="browser_download_report_not_found",
            message="browser-use reached a listing or search page where the target report was not found",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "final_url": final_url,
                "candidate_title": (
                    request.candidate_trace.title if request.candidate_trace else ""
                ),
                "route_summary": str(agent_result.route_summary or "").strip(),
            },
        )
    wrapper_html = _read_text_if_small(downloaded_path, max_bytes=256 * 1024)
    for recovered_pdf_url in extract_embedded_pdf_urls(
        wrapper_html=wrapper_html,
        document_url=resolved_target_url or final_url,
    ):
        recovered_path = _try_fetch_pdf_target(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=downloaded_path.parent,
            target_url=recovered_pdf_url,
        )
        if recovered_path is None:
            continue
        return (
            "pdf_download",
            recovered_path,
            resolve_downloaded_mime_type(
                reported_mime_type=None,
                downloaded_path=recovered_path,
            ),
            None,
            None,
            None,
            None,
            None,
            None,
            "recovered",
            f"Recovered a real PDF artifact from embedded wrapper metadata: {recovered_pdf_url}",
        )
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
    if _looks_like_onsite_report_html(
        wrapper_html=wrapper_html,
        request=request,
        agent_result=agent_result,
        final_url=final_url,
    ):
        capture_path = _resolve_onsite_capture_path(downloaded_path)
        page_count = agent_result.onsite_page_count or max(
            1,
            len(
                _normalize_traversed_page_urls(
                    raw_urls=agent_result.traversed_page_urls
                )
            ),
        )
        completeness_status = str(
            agent_result.onsite_completeness_status or ""
        ).strip() or _infer_onsite_completeness_status(
            html=wrapper_html,
            final_page_title=str(agent_result.final_page_title or "").strip(),
            terminal_text_excerpt=str(agent_result.terminal_text_excerpt or "").strip(),
            page_count=page_count,
            traversed_page_urls=list(agent_result.traversed_page_urls),
            route_steps=_normalize_agent_route_steps_for_completeness(agent_result),
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
            "recovered"
            if _message_indicates_email_delivery(wrapper_html)
            else "blocked",
            "Recovered an email-delivery or blocked-form terminal state from an HTML artifact.",
        )
    raise original_error


def _looks_like_report_not_found_terminal(
    *,
    request: BrowserReportDownloadRequest,
    route_summary: str,
    route_steps: list[BrowserDownloadRouteStep],
    final_url: str,
    terminal_text_excerpt: str,
) -> bool:
    candidate_title = (
        str(request.candidate_trace.title or "").strip().casefold()
        if request.candidate_trace is not None
        else ""
    )
    haystack = " ".join(
        [
            str(route_summary or ""),
            str(final_url or ""),
            str(terminal_text_excerpt or ""),
            *[_route_step_haystack(step) for step in route_steps],
        ]
    ).casefold()
    if not haystack.strip():
        return False
    has_not_found_marker = any(
        marker in haystack for marker in _REPORT_NOT_FOUND_MARKERS
    )
    explicit_not_found = has_not_found_marker and (
        (
            "not found" in haystack
            and ("specific report" in haystack or "target report" in haystack)
        )
        or "0 matches found" in haystack
        or "no matches found" in haystack
        or "could not find" in haystack
        or "unable to find" in haystack
    )
    if not explicit_not_found:
        return False
    if not candidate_title:
        return True
    return (
        candidate_title in haystack
        or "specific report" in haystack
        or "target report" in haystack
    )


def _agent_result_indicates_report_not_found(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> bool:
    route_steps = _normalize_agent_route_steps_for_completeness(agent_result)
    return _looks_like_report_not_found_terminal(
        request=request,
        route_summary=str(agent_result.route_summary or "").strip(),
        route_steps=route_steps,
        final_url=final_url,
        terminal_text_excerpt=str(agent_result.terminal_text_excerpt or "").strip(),
    )


def _ensure_onsite_capture_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    agent_result: BrowserUseAgentResult,
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
    route_steps: list[BrowserDownloadRouteStep],
    browser_html: str,
    onsite_capture_path: str | None,
    onsite_capture_format: str | None,
) -> tuple[str | None, str | None]:
    existing_path = str(onsite_capture_path or "").strip()
    if existing_path and Path(existing_path).is_file():
        return existing_path, onsite_capture_format
    capture_html = str(browser_html or "")
    if not capture_html.strip():
        fetched_html = _try_fetch_onsite_capture_html(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            final_url=final_url,
        )
        if _looks_like_onsite_report_html(
            wrapper_html=fetched_html,
            request=request,
            agent_result=agent_result,
            final_url=final_url,
        ):
            capture_html = fetched_html
    if capture_html.strip():
        capture_path = _safe_onsite_capture_path(
            download_dir=download_dir,
            claimed_path=existing_path,
            final_url=final_url,
            suffix=".html",
        )
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        capture_path.write_text(capture_html, encoding="utf-8")
        return str(capture_path), str(onsite_capture_format or "html").strip() or "html"
    capture_text = str(terminal_text_excerpt or "").strip()
    extracted_text = _extract_onsite_capture_text_from_steps(route_steps)
    if len(extracted_text) > len(capture_text):
        capture_text = extracted_text
    if not _looks_like_onsite_report_text(
        request=request,
        final_url=final_url,
        final_page_title=final_page_title,
        terminal_text_excerpt=capture_text,
    ):
        return onsite_capture_path, onsite_capture_format
    capture_path = _safe_onsite_capture_path(
        download_dir=download_dir,
        claimed_path=existing_path,
        final_url=final_url,
        suffix=".md",
    )
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(capture_text, encoding="utf-8")
    return str(capture_path), str(
        onsite_capture_format or "markdown"
    ).strip() or "markdown"


def _extract_onsite_capture_text_from_steps(
    route_steps: list[BrowserDownloadRouteStep],
) -> str:
    candidates: list[str] = []
    for step in route_steps:
        action = str(step.action or "").strip().casefold()
        result = str(step.result or "").strip()
        if not result:
            continue
        if action == "extract" or len(result) >= 500:
            candidates.append(result)
    if not candidates:
        return ""
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def _safe_onsite_capture_path(
    *,
    download_dir: Path,
    claimed_path: str,
    final_url: str,
    suffix: str,
) -> Path:
    download_root = download_dir.resolve()
    if claimed_path:
        candidate = Path(claimed_path).expanduser()
        try:
            resolved_candidate = candidate.resolve()
            if resolved_candidate.is_relative_to(download_root):
                return resolved_candidate
        except OSError:
            claimed_path = ""
    stem = Path(urlsplit(final_url or "onsite_report").path).stem or "onsite_report"
    return download_root / f"{stem}{suffix}"


def _looks_like_onsite_report_text(
    *,
    request: BrowserReportDownloadRequest,
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
) -> bool:
    text = str(terminal_text_excerpt or "").strip()
    if len(text) < 500:
        return False
    haystack = " ".join(
        [
            str(final_url or ""),
            str(final_page_title or ""),
            text,
            str(request.candidate_trace.title or "") if request.candidate_trace else "",
        ]
    ).casefold()
    if _contains_non_report_page_marker(haystack):
        return False
    return any(marker in haystack for marker in _ONPAGE_REPORT_MARKERS)


def _contains_non_report_page_marker(text: str) -> bool:
    lowered = str(text or "").casefold()
    if not lowered:
        return False
    for marker in _NON_REPORT_PAGE_MARKERS:
        pattern = rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])"
        if re.search(pattern, lowered):
            return True
    return False


def _prefer_onsite_capture_over_optional_form_submission(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    agent_result: BrowserUseAgentResult,
    browser_html: str,
    route_kind: str,
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    blocked_reason: str | None,
    onsite_capture_path: str | None,
    onsite_capture_format: str | None,
    onsite_page_count: int | None,
    onsite_completeness_status: str | None,
    route_steps: list[BrowserDownloadRouteStep],
) -> tuple[str, str | None, str | None, int | None, str | None]:
    if route_kind != "email_delivery":
        return (
            route_kind,
            onsite_capture_path,
            onsite_capture_format,
            onsite_page_count,
            onsite_completeness_status,
        )
    if blocked_reason:
        return (
            route_kind,
            onsite_capture_path,
            onsite_capture_format,
            onsite_page_count,
            onsite_completeness_status,
        )
    if str(request.route_family_hint or "").strip() != "browser_onsite_report":
        return (
            route_kind,
            onsite_capture_path,
            onsite_capture_format,
            onsite_page_count,
            onsite_completeness_status,
        )
    if _message_indicates_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        return (
            route_kind,
            onsite_capture_path,
            onsite_capture_format,
            onsite_page_count,
            onsite_completeness_status,
        )
    capture_html = browser_html
    if not capture_html.strip() and _likely_onsite_report_context_without_html(
        final_url=final_url,
        final_page_title=final_page_title,
        route_steps=route_steps,
    ):
        capture_html = _try_fetch_onsite_capture_html(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            final_url=final_url,
        )
    if not _looks_like_onsite_report_html(
        wrapper_html=capture_html,
        request=request,
        agent_result=agent_result,
        final_url=final_url,
    ):
        return (
            route_kind,
            onsite_capture_path,
            onsite_capture_format,
            onsite_page_count,
            onsite_completeness_status,
        )
    capture_path = str(onsite_capture_path or "").strip()
    if not capture_path:
        capture_path = str(
            _capture_salvaged_onsite_html(
                request=request,
                normalized_url=normalized_url,
                final_url=final_url,
                html=capture_html,
            )
        )
    page_count = onsite_page_count or max(
        1,
        len(
            _normalize_traversed_page_urls(
                raw_urls=[*agent_result.traversed_page_urls, final_url]
            )
        ),
    )
    completeness = str(
        onsite_completeness_status or ""
    ).strip() or _infer_onsite_completeness_status(
        html=capture_html,
        final_page_title=final_page_title,
        terminal_text_excerpt=terminal_text_excerpt,
        page_count=page_count,
        traversed_page_urls=[*agent_result.traversed_page_urls, final_url],
        route_steps=route_steps,
    )
    return (
        "onsite_report",
        capture_path,
        str(onsite_capture_format or "").strip() or "html",
        page_count,
        completeness,
    )


def _likely_onsite_report_context_without_html(
    *,
    final_url: str,
    final_page_title: str,
    route_steps: list[BrowserDownloadRouteStep],
) -> bool:
    haystack = " ".join(
        [str(final_url or "").strip(), str(final_page_title or "").strip()]
    ).casefold()
    has_report_marker = any(marker in haystack for marker in _ONPAGE_REPORT_MARKERS)
    has_non_report_marker = _contains_non_report_page_marker(haystack)
    if not has_report_marker or has_non_report_marker:
        return False
    scroll_steps = [
        step
        for step in route_steps
        if str(step.action or "").strip().casefold() == "scroll"
        or "scroll" in str(step.result or "").casefold()
    ]
    return bool(scroll_steps or len(route_steps) >= 4)


def _try_fetch_onsite_capture_html(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    final_url: str,
) -> str:
    try:
        return fetch_html_from_url(
            page_url=final_url,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    except AppError:
        return ""


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
        if not onsite_capture_path or not Path(onsite_capture_path).is_file():
            raise AppError(
                code="browser_download_onsite_capture_missing",
                message="browser-use classified the route as an on-site report but no local capture artifact was found",
                retryable=True,
                context={"final_page_url": confirmation_evidence.final_page_url},
            )
        completeness = str(onsite_completeness_status or "").strip().lower()
        route_status = "verified" if completeness == "complete" else "inferred"
        return "captured", route_status, confirmation_signal_count
    if route_kind != "email_delivery":
        raise AppError(
            code="browser_download_missing_file",
            message="No PDF artifact was produced for a non-email route",
            retryable=True,
        )
    if blocked_reason:
        return "email_required", "inferred", confirmation_signal_count
    if _confirmation_evidence_verifies_email_delivery(confirmation_evidence):
        return "email_requested", "verified", confirmation_signal_count
    if email_submission_completed is True:
        return "email_required", "inferred", confirmation_signal_count
    if encountered_form_fields or email_submission_completed is False:
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
    if confirmation_evidence.signal_labels:
        return len(confirmation_evidence.signal_labels)
    count = 0
    if _message_indicates_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        count += 1
    elif _message_indicates_form_success(
        confirmation_evidence.visible_confirmation_text
    ):
        count += 1
    if confirmation_evidence.url_changed and _url_indicates_confirmation(
        confirmation_evidence.final_page_url
    ):
        count += 1
    if confirmation_evidence.submit_button_state in {"disabled", "replaced"}:
        count += 1
    if confirmation_evidence.form_disappeared:
        count += 1
    if "network_submission_request" in confirmation_evidence.signal_labels:
        count += 1
    if "network_confirmation_request" in confirmation_evidence.signal_labels:
        count += 1
    return count


def _confirmation_evidence_verifies_email_delivery(
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> bool:
    signal_labels = set(confirmation_evidence.signal_labels)
    if _message_indicates_transient_submit_state(
        confirmation_evidence.visible_confirmation_text
    ) and not (
        signal_labels
        & {
            "delivery_text",
            "success_text",
            "success_url",
            "form_disappeared",
            "network_confirmation_request",
        }
    ):
        return False
    return _count_confirmation_signals(confirmation_evidence) >= 2 and (
        "submit_observed" in signal_labels
        or any(marker in signal_labels for marker in _VERIFIED_EMAIL_SIGNAL_MARKERS)
    )


def _build_confirmation_signal_labels(
    *,
    visible_confirmation_text: str,
    final_page_url: str,
    url_changed: bool,
    submit_button_state: str,
    form_disappeared: bool,
    email_submission_completed: bool | None,
    network_signal_labels: list[str] | None = None,
) -> list[str]:
    labels: list[str] = []
    if email_submission_completed is True:
        labels.append("submit_observed")
    if _message_indicates_email_delivery(visible_confirmation_text):
        labels.append("delivery_text")
    elif _message_indicates_form_success(visible_confirmation_text):
        labels.append("success_text")
    if url_changed and _url_indicates_confirmation(final_page_url):
        labels.append("success_url")
    if submit_button_state in {"disabled", "replaced"}:
        labels.append(f"button_state_{submit_button_state}")
    if form_disappeared:
        labels.append("form_disappeared")
    for label in network_signal_labels or []:
        if label not in labels:
            labels.append(label)
    return labels


def _message_indicates_email_delivery(message: str | None) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if any(
        marker in token
        for marker in (
            "fill out the form",
            "fill out form",
            "form below",
            "complete the form",
            "submit the form",
        )
    ):
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


def _message_indicates_transient_submit_state(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    return any(marker in token for marker in _TRANSIENT_SUBMIT_MESSAGE_MARKERS)


def _message_indicates_confirmed_email_delivery(message: str | None) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    strong_markers = (
        "sent directly to your inbox",
        "sent to your inbox",
        "sent to your email",
        "will be sent to your inbox",
        "will be sent to your email",
        "will be sent directly to your inbox",
        "copy of the report will be sent",
        "check your inbox",
        "download link",
        "emailed to you",
        "inbox shortly",
    )
    return any(marker in token for marker in strong_markers)


def _message_indicates_unknown_required_enum(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    required_markers = (
        "this field is required",
        "required field",
        "selection is required",
        "please select",
        "select an option",
        "choose an option",
        "dropdown",
        "not correctly filled",
        "not correctly selected",
        "did not resolve",
        "not confirmed",
        "valid lookup selection",
        "could not be successfully filled",
        "could not be successfully selected",
        "could not successfully select",
        "could not be selected",
        "failed to submit",
        "preventing form submission",
        "fill this field",
        "заполните это поле",
    )
    return any(marker in token for marker in required_markers) and any(
        marker in token for marker in _UNKNOWN_ENUM_MARKERS
    )


def _message_indicates_form_success(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if _message_indicates_email_delivery(token):
        return True
    return any(marker in token for marker in _FORM_SUCCESS_TEXT_MARKERS)


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
    hinted = str(request.route_family_hint or "").strip()
    canonical = _canonical_route_family(
        route_kind=route_kind,
        route_family=token or hinted,
    )
    if canonical:
        return canonical
    if route_kind == "onsite_report":
        return "browser_onsite_report"
    if route_kind == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _normalize_string_list(values: Iterable[str | None]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        token = str(raw_value or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(token)
    return normalized


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


def _extract_visible_text_from_html(html: str, *, max_chars: int = 320) -> str:
    token = str(html or "").strip()
    if not token:
        return ""
    without_scripts = re.sub(
        r"(?is)<(script|style)[^>]*>.*?</\1>",
        " ",
        token,
    )
    plain = re.sub(r"(?is)<[^>]+>", " ", without_scripts)
    plain = " ".join(plain.split()).strip()
    return plain[:max_chars]


def _dom_snapshot_sha256(html: str) -> str:
    token = str(html or "").strip()
    if not token:
        return ""
    return sha256(token.encode("utf-8", errors="ignore")).hexdigest()


def _has_missing_identity_field(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    encountered_form_fields: list[str],
) -> bool:
    configured_tokens: set[str] = set()
    semantic_families: set[str] = set()
    for field in resolve_effective_identity_fields(request):
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email
        if not value:
            continue
        field_tokens = identity_field_match_tokens(field)
        configured_tokens.update(field_tokens)
        semantic_families.update(_identity_semantic_families(field_tokens))
    for field_name in encountered_form_fields:
        token = normalize_browser_download_identity_key(field_name)
        if not token:
            continue
        field_families = _identity_semantic_families({token})
        if "email" in field_families and "email" not in semantic_families:
            return True
        needs_direct_match = field_families & {
            "name",
            "company",
            "role",
            "phone",
            "website",
            "country",
            "city",
            "region",
        }
        if needs_direct_match and not (
            configured_tokens.intersection({token})
            or semantic_families & needs_direct_match
        ):
            return True
    return False


def _identity_semantic_families(tokens: set[str]) -> set[str]:
    families: set[str] = set()
    lowered = {
        str(token or "").strip().casefold()
        for token in tokens
        if str(token or "").strip()
    }
    if any("email" in token for token in lowered):
        families.add("email")
    if any(
        "name" in token or token in {"given", "surname", "family"} for token in lowered
    ):
        families.add("name")
    if any(
        marker in token
        for token in lowered
        for marker in ("company", "organization", "business", "employer", "workplace")
    ):
        families.add("company")
    if any(marker in token for token in lowered for marker in ("title", "role", "job")):
        families.add("role")
    if any(
        marker in token
        for token in lowered
        for marker in ("phone", "telephone", "mobile")
    ):
        families.add("phone")
    if any(
        marker in token for token in lowered for marker in ("website", "site", "domain")
    ):
        families.add("website")
    if any("country" in token for token in lowered):
        families.add("country")
    if any(marker in token for token in lowered for marker in ("city", "town")):
        families.add("city")
    if any(
        marker in token
        for token in lowered
        for marker in ("state", "region", "province")
    ):
        families.add("region")
    return families


def _normalize_explicit_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    explicit_blocked_reason: str,
    encountered_form_fields: list[str],
    blocker_haystack: str,
) -> str | None:
    token = str(explicit_blocked_reason or "").strip().lower()
    if token not in _BLOCKED_REASONS:
        return None
    if token == "blocked_missing_identity_field" and (
        _message_indicates_unknown_required_enum(blocker_haystack)
        or _message_mentions_enum_selection_failure(blocker_haystack)
    ):
        return "blocked_unknown_required_enum"
    if token != "blocked_unknown_required_enum":
        return token
    if any(marker in blocker_haystack for marker in _UNKNOWN_ENUM_MARKERS):
        return token
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ) or _message_indicates_unknown_required_enum(blocker_haystack):
        return token
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    return None


def _message_mentions_enum_selection_failure(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if not any(marker in token for marker in _UNKNOWN_ENUM_MARKERS):
        return False
    failure_markers = (
        "could not",
        "failed",
        "failure",
        "not confirmed",
        "not properly",
        "not selected",
        "preventing",
        "submission",
        "unsuccessful",
    )
    return any(marker in token for marker in failure_markers)


def _canonical_route_family(*, route_kind: str, route_family: str) -> str:
    token = str(route_family or "").strip()
    if route_kind == "email_delivery" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_email_form"
    if route_kind == "onsite_report" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_onsite_report"
    if route_kind == "pdf_download" and not token:
        return "browser_pdf_click"
    return token


def _has_unconfigured_enum_field(
    *,
    request: BrowserReportDownloadRequest,
    encountered_form_fields: list[str],
) -> bool:
    configured_tokens = {
        str(field.key or "").strip().casefold()
        for field in resolve_effective_identity_fields(request)
        if str(field.value or "").strip()
    }
    for field_name in encountered_form_fields:
        token = str(field_name or "").strip().casefold()
        if not token:
            continue
        if not any(marker in token for marker in _UNKNOWN_ENUM_MARKERS):
            continue
        normalized_token = re.sub(r"[^a-z0-9]+", "_", token).strip("_")
        if normalized_token not in configured_tokens:
            return True
    return False


def _resolve_salvaged_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    encountered_form_fields: list[str],
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
) -> str | None:
    haystack = " ".join(
        [
            str(final_page_title or "").strip(),
            str(terminal_text_excerpt or "").strip(),
            " ".join(encountered_form_fields),
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
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_unknown_required_enum"
    return None


def _looks_like_non_report_terminal(
    *,
    request: BrowserReportDownloadRequest,
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
) -> bool:
    combined = " ".join(
        [
            str(final_url or "").strip(),
            str(final_page_title or "").strip(),
            str(terminal_text_excerpt or "").strip(),
        ]
    ).casefold()
    has_report_signal = any(marker in combined for marker in _ONPAGE_REPORT_MARKERS)
    has_non_report_signal = _contains_non_report_page_marker(combined)
    has_marketing_signal = any(marker in combined for marker in _MARKETING_MARKERS)
    if has_non_report_signal and not has_report_signal:
        return True
    if has_marketing_signal and not has_report_signal:
        return True
    candidate_title = (
        str(request.candidate_trace.title or "").strip().casefold()
        if request.candidate_trace is not None
        else ""
    )
    return (
        bool(candidate_title)
        and _contains_non_report_page_marker(candidate_title)
        and not any(marker in candidate_title for marker in _ONPAGE_REPORT_MARKERS)
    )


def _looks_like_onsite_report_html(
    *,
    wrapper_html: str,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> bool:
    lowered = str(wrapper_html or "").casefold()
    final_title = str(agent_result.final_page_title or "").casefold()
    final_excerpt = str(agent_result.terminal_text_excerpt or "").casefold()
    route_family = str(
        request.route_family_hint or agent_result.route_family or ""
    ).strip()
    if _contains_non_report_page_marker(final_title) and not any(
        marker in final_title for marker in _ONPAGE_REPORT_MARKERS
    ):
        return False
    if route_family in _ONSITE_ROUTE_FAMILIES and len(lowered) >= 1200:
        return (
            any(marker in lowered for marker in _ONPAGE_REPORT_MARKERS)
            or any(marker in final_title for marker in _ONPAGE_REPORT_MARKERS)
            or any(marker in final_excerpt for marker in _ONPAGE_REPORT_MARKERS)
        )
    if "article" in lowered and any(
        marker in lowered for marker in _ONPAGE_REPORT_MARKERS
    ):
        return True
    return (
        str(agent_result.route_kind or "").strip() == "onsite_report"
        and len(lowered) >= 800
        and not _message_indicates_email_delivery(lowered)
        and not str(final_url or "").strip().lower().endswith(".pdf")
    )


def _capture_salvaged_onsite_html(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    final_url: str,
    html: str,
) -> Path:
    capture_root = prepare_download_dir(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    capture_path = (
        capture_root
        / f"{Path(urlsplit(final_url or normalized_url).path).stem or 'onsite-report'}.html"
    )
    capture_path.write_text(str(html or ""), encoding="utf-8")
    return capture_path


def _infer_onsite_completeness_status(
    *,
    html: str,
    final_page_title: str,
    terminal_text_excerpt: str,
    page_count: int,
    traversed_page_urls: list[str],
    route_steps: list[BrowserDownloadRouteStep],
) -> str:
    lowered = str(html or "").casefold()
    heading_count = len(re.findall(r"(?is)<h[1-3][^>]*>", lowered))
    text_length = len(_extract_visible_text_from_html(html, max_chars=4000))
    traversed_count = len(_normalize_traversed_page_urls(raw_urls=traversed_page_urls))
    scroll_actions = sum(
        1 for step in route_steps if str(step.action or "").strip().lower() == "scroll"
    )
    pagination_actions = sum(
        1
        for step in route_steps
        if str(step.action or "").strip().lower() in {"navigate", "click"}
        and any(
            marker in _route_step_haystack(step)
            for marker in ("next", "page=", "?page", "&page", "pagination")
        )
    )
    duplicate_heading_penalty = _duplicate_heading_penalty(html)
    multi_section_body = (
        text_length >= 1800 and heading_count >= 2 and duplicate_heading_penalty < 0.5
    )
    pagination_expected = (
        page_count > 1 or traversed_count > 1 or pagination_actions > 0
    )
    pagination_reached_end = _pagination_reached_end(
        page_count=page_count,
        traversed_count=traversed_count,
        route_steps=route_steps,
    )
    scroll_growth_evidence = _has_scroll_growth_evidence(route_steps)
    if pagination_expected:
        if (
            traversed_count >= max(2, min(page_count, 2))
            and multi_section_body
            and pagination_reached_end
        ):
            return "complete"
        if traversed_count >= 2 and multi_section_body:
            return "partial"
    if (
        scroll_actions >= 3
        and traversed_count <= 1
        and multi_section_body
        and (scroll_growth_evidence or text_length >= 2600)
    ):
        return "complete"
    if (
        not pagination_expected
        and text_length >= 2500
        and heading_count >= 2
        and duplicate_heading_penalty < 0.5
    ):
        return "complete"
    if (
        any(
            marker in str(final_page_title or "").casefold()
            for marker in _ONPAGE_REPORT_MARKERS
        )
        and text_length >= 1200
    ):
        return "partial"
    if (
        any(
            marker in str(terminal_text_excerpt or "").casefold()
            for marker in _ONPAGE_REPORT_MARKERS
        )
        and text_length >= 1200
    ):
        return "partial"
    return "bounded_incomplete"


def _normalize_agent_route_steps_for_completeness(
    agent_result: BrowserUseAgentResult,
) -> list[BrowserDownloadRouteStep]:
    steps: list[BrowserDownloadRouteStep] = []
    for index, raw_step in enumerate(agent_result.route_steps):
        steps.append(
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=int(raw_step.index) if raw_step.index is not None else index,
                action=str(raw_step.action or "").strip() or "follow",
                target_text=str(raw_step.target_text or "").strip(),
                target_role=str(raw_step.target_role or "").strip() or "page",
                target_url=str(raw_step.target_url or "").strip(),
                result=str(raw_step.result or "").strip() or "completed",
                expected_evidence=_normalize_evidence_categories(
                    raw_step.expected_evidence
                ),
                observed_evidence=_normalize_evidence_categories(
                    raw_step.observed_evidence
                ),
                verification_status=str(raw_step.verification_status or "").strip(),
            )
        )
    return steps


def _duplicate_heading_penalty(html: str) -> float:
    headings = [
        _extract_visible_text_from_html(match.group(1), max_chars=120).casefold()
        for match in re.finditer(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", str(html or ""))
    ]
    normalized = [heading for heading in headings if heading]
    if len(normalized) < 2:
        return 0.0
    duplicates = len(normalized) - len(set(normalized))
    return duplicates / len(normalized)


def _route_step_haystack(step: BrowserDownloadRouteStep) -> str:
    return " ".join(
        [
            str(step.target_text or "").strip().casefold(),
            str(step.result or "").strip().casefold(),
            str(step.target_url or "").strip().casefold(),
        ]
    )


def _pagination_reached_end(
    *,
    page_count: int,
    traversed_count: int,
    route_steps: list[BrowserDownloadRouteStep],
) -> bool:
    if page_count > 1 and traversed_count >= page_count:
        return True
    for step in route_steps:
        haystack = _route_step_haystack(step)
        if any(marker in haystack for marker in _PAGINATION_END_MARKERS):
            return True
        match = re.search(r"\bpage\s+(\d+)\s+of\s+(\d+)\b", haystack)
        if match and int(match.group(1)) >= int(match.group(2)) >= 1:
            return True
        fraction_match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", haystack)
        if (
            fraction_match
            and int(fraction_match.group(1)) >= int(fraction_match.group(2)) >= 2
        ):
            return True
    return False


def _has_scroll_growth_evidence(route_steps: list[BrowserDownloadRouteStep]) -> bool:
    for step in route_steps:
        if str(step.action or "").strip().lower() != "scroll":
            continue
        haystack = _route_step_haystack(step)
        if any(marker in haystack for marker in _SCROLL_GROWTH_MARKERS):
            return True
    return False


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
    attachment_paths: list[str],
    browser_downloaded_files: list[str],
    download_dir: Path,
) -> Path | None:
    ignored_runtime_files = {
        "browser_agent_worker_request.json",
        "browser_agent_worker_response.json",
        "terminal_snapshot.html",
        "terminal_screenshot.png",
    }
    external_candidates: list[Path] = []
    local_candidates: list[Path] = []
    seen: set[Path] = set()
    resolved_download_dir = download_dir.expanduser().resolve()

    def add_candidate(raw_path: str | Path | None) -> None:
        if raw_path is None:
            return
        token = str(raw_path).strip()
        if not token:
            return
        try:
            resolved = Path(token).expanduser().resolve()
        except OSError:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        if not resolved.exists() or not resolved.is_file():
            return
        if resolved.name in ignored_runtime_files:
            return
        if _is_within_directory(path=resolved, directory=resolved_download_dir):
            local_candidates.append(resolved)
            return
        external_candidates.append(resolved)

    if explicit_path:
        add_candidate(explicit_path)
    for raw_path in attachment_paths:
        add_candidate(raw_path)
    for raw_path in browser_downloaded_files:
        add_candidate(raw_path)
    for path in sorted(download_dir.glob("*")):
        if path.is_file():
            add_candidate(path)

    selected = _select_download_candidate(local_candidates)
    if selected is not None:
        return selected
    selected = _select_download_candidate(external_candidates)
    if selected is None:
        return None
    return _adopt_external_downloaded_file(
        source_path=selected,
        download_dir=resolved_download_dir,
    )


def _is_within_directory(*, path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _select_download_candidate(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None
    pdf_candidates = [path for path in candidates if path.suffix.lower() == ".pdf"]
    selected = pdf_candidates or candidates
    selected.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return selected[0]


def _adopt_external_downloaded_file(
    *,
    source_path: Path,
    download_dir: Path,
) -> Path | None:
    download_dir.mkdir(parents=True, exist_ok=True)
    target_path = download_dir / source_path.name
    counter = 1
    while target_path.exists():
        try:
            if source_path.samefile(target_path):
                return target_path.resolve()
        except OSError:
            target_path = (
                download_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            )
            counter += 1
            continue
        target_path = download_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
        counter += 1
    try:
        shutil.copy2(source_path, target_path)
    except OSError:
        return None
    try:
        resolved = target_path.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _read_text_if_small(path: Path, *, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _resolve_browser_html(browser_run: "BrowserAgentRunResult") -> str:
    html = str(browser_run.final_page_html or "")
    if html.strip():
        return html
    snapshot_path = str(browser_run.html_snapshot_path or "").strip()
    if not snapshot_path:
        return ""
    return _read_text_if_small(Path(snapshot_path), max_bytes=1024 * 1024)


def _resolve_existing_browser_rendered_capture(raw_path: str | None) -> Path | None:
    token = str(raw_path or "").strip()
    if not token:
        return None
    path = Path(token).expanduser()
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        return None
    return None


def _onsite_artifact_validation_detail(*, onsite_capture_format: str | None) -> str:
    if str(onsite_capture_format or "").strip() == "browser_rendered_pdf":
        return (
            "Captured browser-rendered PDF from printable on-site report page; "
            "this is not a publisher-supplied PDF artifact."
        )
    return "Captured on-site report content without a local PDF."


def _onsite_capture_evidence_labels(onsite_capture_format: str | None) -> list[str]:
    if str(onsite_capture_format or "").strip() == "browser_rendered_pdf":
        return ["browser_rendered_pdf_capture", "not_publisher_supplied_pdf"]
    return []


def _resolve_terminal_html_and_snapshot(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    route_kind: str,
    final_url: str,
    resolved_target_url: str,
    browser_html: str,
    html_snapshot_path: str,
) -> tuple[str, str]:
    current_html = str(browser_html or "")
    current_snapshot = str(html_snapshot_path or "").strip()
    if current_html.strip():
        if current_snapshot:
            return current_html, current_snapshot
        return current_html, _write_terminal_html_snapshot(
            download_dir=download_dir,
            html=current_html,
        )
    if route_kind == "pdf_download":
        return "", current_snapshot
    fetch_targets = _normalize_string_list([final_url, resolved_target_url])
    for fetch_target in fetch_targets:
        fetched_html = _try_fetch_terminal_html(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            page_url=fetch_target,
        )
        if not fetched_html.strip():
            continue
        return fetched_html, _write_terminal_html_snapshot(
            download_dir=download_dir,
            html=fetched_html,
        )
    return "", current_snapshot


def _try_fetch_terminal_html(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    page_url: str,
) -> str:
    token = str(page_url or "").strip()
    if (
        not token
        or token.casefold().endswith(".pdf")
        or not token.casefold().startswith(("http://", "https://"))
    ):
        return ""
    try:
        return fetch_html_from_url(
            page_url=token,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    except AppError:
        return ""


def _write_terminal_html_snapshot(
    *,
    download_dir: Path,
    html: str,
) -> str:
    token = str(html or "")
    if not token.strip():
        return ""
    snapshot_path = download_dir / "terminal_snapshot.html"
    try:
        snapshot_path.write_text(token, encoding="utf-8")
    except OSError:
        return ""
    return str(snapshot_path)


def _extract_html_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if match is None:
        return ""
    return _extract_visible_text_from_html(match.group(1), max_chars=200)
