"""Fallback and invalid-artifact recovery for browser terminal results."""

from __future__ import annotations

from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.utils.errors import AppError

from .classification import (
    _agent_result_indicates_report_not_found,
    _build_confirmation_signal_labels,
    _build_network_confirmation_signal_labels,
    _confirmation_evidence_verifies_email_delivery,
    _extract_form_fields_from_html,
    _html_contains_form,
    _html_contains_submit_control,
    _message_indicates_email_delivery,
    _normalize_agent_route_steps_for_completeness,
    _resolve_blocked_reason,
    _resolve_blocked_reason_detail,
    _resolve_salvaged_blocked_reason,
    _url_indicates_confirmation,
)
from .evidence import (
    _dom_snapshot_sha256,
    _extract_html_title,
    _extract_visible_text_from_html,
    _normalize_network_events,
    _normalize_string_list,
    _normalize_traversed_page_urls,
    _read_text_if_small,
    _resolve_observed_document_urls,
    _resolve_visited_url_timeline,
    _try_fetch_terminal_html,
    _write_terminal_html_snapshot,
)
from .onsite import (
    _build_salvaged_onsite_result,
    _infer_onsite_completeness_status,
    _looks_like_non_report_terminal,
    _looks_like_onsite_report_html,
    _resolve_existing_browser_rendered_capture,
    _resolve_onsite_capture_path,
)
from .pdf import (
    _build_pdf_result,
    _complete_pdf_artifact,
    _resolve_downloaded_file,
    _try_fetch_pdf_target,
    _used_candidate_source_page,
)


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
            downloaded_mime_type=http_runtime.resolve_downloaded_mime_type(
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
                "browser_rendered_pdf"
                if browser_rendered_capture_path is not None
                else ""
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
    for recovered_pdf_url in http_runtime.extract_embedded_pdf_urls(
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
            http_runtime.resolve_downloaded_mime_type(
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
