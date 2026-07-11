"""Coordinator for adapting browser execution output into download results."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from src.contracts.browser_download import (
    BrowserDownloadRequiredSelectEvidence,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.utils.coercion import (
    is_ambiguous_optional_bool_signal,
    normalize_optional_bool_signal,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from ._artifact import ARTIFACT_LOGGER_NAME
from ._artifact.classification import (
    _build_confirmation_evidence,
    _classify_route_result,
    _confirmation_evidence_verifies_email_delivery,
    _looks_like_report_not_found_terminal,
    _normalize_encountered_form_fields,
    _resolve_blocked_reason,
    _resolve_blocked_reason_detail,
    _resolve_route_family,
    _resolve_route_kind,
    _resolve_route_steps,
    _resolve_route_summary,
    _upgrade_confirmation_evidence_from_terminal_html,
)
from ._artifact.evidence import (
    _build_terminal_evidence,
    _dialog_evidence_labels,
    _extract_html_title,
    _extract_visible_text_from_html,
    _normalize_string_list,
    _normalize_traversed_page_urls,
    _resolve_browser_html,
    _resolve_observed_document_urls,
    _resolve_terminal_html_and_snapshot,
    _verify_post_action_route_steps,
)
from ._artifact.onsite import (
    _capture_salvaged_onsite_html,
    _ensure_onsite_capture_artifact,
    _infer_onsite_completeness_status,
    _onsite_artifact_validation_detail,
    _onsite_capture_evidence_labels,
    _prefer_onsite_capture_over_optional_form_submission,
    _resolve_existing_browser_rendered_capture,
)
from ._artifact.pdf import (
    _complete_pdf_artifact,
    _resolve_downloaded_file,
    _used_candidate_source_page,
)
from ._artifact.recovery import (
    _recover_from_invalid_artifact,
    _salvage_without_structured_result,
)

logger = logging.getLogger(ARTIFACT_LOGGER_NAME)

_TERMINAL_BOOLEAN_FIELDS = (
    "email_submission_completed",
    "confirmation_url_changed",
    "form_disappeared",
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
    required_select_evidence = _required_select_evidence(
        agent_result=agent_result,
        fallback_url=normalized_url,
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
    should_materialize_pdf_targets = not (
        str(request.route_family_hint or "").strip() == "browser_email_form"
        and str(agent_result.route_kind or "").strip() == "email_delivery"
    )
    downloaded_path, used_candidate_pdf_url = _complete_pdf_artifact(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        downloaded_path=downloaded_path,
        target_urls=(
            [
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
            ]
            if should_materialize_pdf_targets
            else []
        ),
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
            target_urls=(
                [
                    request.candidate_trace.pdf_url
                    if request.candidate_trace is not None
                    else "",
                    *_resolve_observed_document_urls(
                        network_resource_urls=list(
                            browser_run.network_resource_urls or []
                        ),
                        dom_snapshot_html=browser_html,
                        candidate_urls=[resolved_target_url, final_url],
                    ),
                    *list(browser_run.network_resource_urls or []),
                    resolved_target_url,
                    final_url,
                ]
                if should_materialize_pdf_targets
                else []
            ),
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
    downloaded_mime_type = http_runtime.resolve_downloaded_mime_type(
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
            http_runtime.validate_downloaded_pdf_artifact(
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
        required_select_evidence=required_select_evidence,
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


def _required_select_evidence(
    *, agent_result: BrowserUseAgentResult, fallback_url: str
) -> list[BrowserDownloadRequiredSelectEvidence]:
    evidence: list[BrowserDownloadRequiredSelectEvidence] = []
    source_url = (
        str(agent_result.final_page_url or fallback_url).strip() or fallback_url
    )
    host = str(urlsplit(source_url).hostname or "").strip().lower()
    for item in agent_result.required_select_evidence:
        label = str(item.field_label or "").strip()
        if not label:
            continue
        evidence.append(
            BrowserDownloadRequiredSelectEvidence(
                schema_version="1.0",
                host=host,
                url=source_url,
                field_label=label,
                field_name=str(item.field_name or "").strip(),
                options=[
                    str(option).strip()
                    for option in item.options
                    if str(option).strip()
                ],
                classifier_confidence=max(
                    0.0, min(1.0, float(item.classifier_confidence or 0.0))
                ),
            )
        )
    return evidence


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
