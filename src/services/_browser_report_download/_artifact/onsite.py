"""On-site report capture recognition, materialization, and completeness checks."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

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
from src.services._browser_report_download.artifact_materialization import (
    materialize_external_browser_artifact,
)
from src.services._browser_report_download.artifact_paths import (
    ensure_browser_directory,
    resolve_browser_artifact_path,
    validate_browser_artifact_path,
    validate_browser_download_directory,
)
from src.services._browser_report_download.models import BrowserUseAgentResult
from src.utils.errors import AppError

from .classification import (
    _message_indicates_email_delivery,
    _route_step_haystack,
)
from .evidence import (
    _dom_snapshot_sha256,
    _extract_visible_text_from_html,
    _normalize_network_events,
    _normalize_traversed_page_urls,
    _resolve_observed_document_urls,
    _resolve_visited_url_timeline,
)
from .pdf import _used_candidate_source_page

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
_ONSITE_HTML_FETCH_TIMEOUT_SECONDS = 15.0
_ONSITE_MARKDOWN_FORMATS = {"md", "markdown"}
_ONSITE_HTML_FORMATS = {"html", "html+markdown"}
_ONSITE_PDF_FORMATS = {"browser_rendered_pdf", "rendered_onsite_pdf"}
_ONSITE_CAPTURE_SUFFIXES = {".html", ".md", ".pdf"}


def _build_salvaged_onsite_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    download_dir: Path,
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
    capture_path = None
    if onsite_capture_path:
        resolved_capture_path = _resolve_existing_onsite_capture_path(
            claimed_path=onsite_capture_path,
            download_dir=download_dir,
            onsite_capture_format=onsite_capture_format,
        )
        if resolved_capture_path is not None and resolved_capture_path.is_file():
            capture_path = resolved_capture_path
    if capture_path is None or not capture_path.is_file():
        capture_path = _capture_salvaged_onsite_html(
            download_dir=download_dir,
            normalized_url=normalized_url,
            final_url=final_url,
            html=browser_html,
        )
        onsite_capture_format = _generated_onsite_capture_format(
            onsite_capture_format=onsite_capture_format,
            suffix=".html",
        )
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
    existing_capture_path: Path | None = None
    if existing_path:
        existing_capture_path = _resolve_existing_onsite_capture_path(
            claimed_path=existing_path,
            download_dir=download_dir,
            onsite_capture_format=onsite_capture_format,
        )
        if (
            existing_capture_path is not None
            and existing_capture_path.is_file()
            and str(onsite_capture_format or "").strip().casefold()
            in _ONSITE_PDF_FORMATS
        ):
            return str(existing_capture_path), onsite_capture_format
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
        capture_path = _publish_generated_onsite_capture(
            download_dir=download_dir,
            claimed_path=existing_path,
            final_url=final_url,
            content=capture_html,
            suffix=".html",
        )
        return str(capture_path), _generated_onsite_capture_format(
            onsite_capture_format=onsite_capture_format,
            suffix=".html",
        )
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
        if existing_capture_path is not None and existing_capture_path.is_file():
            return str(existing_capture_path), onsite_capture_format
        return (None if existing_path else onsite_capture_path), onsite_capture_format
    capture_path = _publish_generated_onsite_capture(
        download_dir=download_dir,
        claimed_path=existing_path,
        final_url=final_url,
        content=capture_text,
        suffix=".md",
    )
    return str(capture_path), _generated_onsite_capture_format(
        onsite_capture_format=onsite_capture_format,
        suffix=".md",
    )


def _resolve_existing_onsite_capture_path(
    *,
    claimed_path: str,
    download_dir: Path,
    onsite_capture_format: str | None = None,
) -> Path | None:
    """Resolve a contained claim or materialize an existing external capture."""
    download_root = validate_browser_download_directory(download_dir)
    try:
        source_path = Path(claimed_path).expanduser().resolve()
    except OSError:
        return None
    try:
        source_is_within_workspace = source_path.is_relative_to(download_root)
    except OSError:
        return None
    if source_is_within_workspace:
        try:
            validated_path = validate_browser_artifact_path(
                source_path,
                parent_dir=download_root,
                temporary_suffixes=(".part",),
            )
        except AppError:
            return None
        if not _onsite_capture_path_matches_format(
            validated_path,
            onsite_capture_format=onsite_capture_format,
        ):
            return None
        return validated_path
    if not source_path.is_file():
        return None
    if not _onsite_capture_path_matches_format(
        source_path,
        onsite_capture_format=onsite_capture_format,
    ):
        return None
    materialized_path = materialize_external_browser_artifact(
        source_path=source_path,
        download_dir=download_root,
        preferred_filename=source_path.name,
        source_identity=str(source_path),
    )
    if materialized_path is None:
        return None
    try:
        validated_materialized_path = validate_browser_artifact_path(
            materialized_path,
            parent_dir=download_root,
            temporary_suffixes=(".part",),
        )
    except AppError:
        return None
    return (
        validated_materialized_path
        if _onsite_capture_path_matches_format(
            validated_materialized_path,
            onsite_capture_format=onsite_capture_format,
        )
        else None
    )


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
    download_root = validate_browser_download_directory(download_dir)
    preferred_name = _preferred_onsite_capture_name(
        claimed_path=claimed_path,
        download_root=download_root,
        suffix=suffix,
        final_url=final_url,
    )
    return resolve_browser_artifact_path(
        parent_dir=download_root,
        source_name=preferred_name,
        extension=suffix,
        identity=final_url or "onsite_report",
        temporary_suffixes=(".part",),
    )


def _preferred_onsite_capture_name(
    *,
    claimed_path: str,
    download_root: Path,
    suffix: str,
    final_url: str,
) -> str:
    if claimed_path:
        candidate = Path(claimed_path).expanduser()
        try:
            resolved_candidate = validate_browser_artifact_path(
                candidate,
                parent_dir=download_root,
                temporary_suffixes=(".part",),
            )
            if resolved_candidate.is_relative_to(download_root):
                return _replace_capture_suffix(resolved_candidate.name, suffix)
        except (AppError, OSError, RuntimeError, ValueError):
            pass
    stem = Path(urlsplit(final_url or "onsite_report").path).stem or "onsite_report"
    return f"{stem}{suffix}"


def _replace_capture_suffix(filename: str, suffix: str) -> str:
    stem = Path(filename).stem or "onsite_report"
    return f"{stem}{suffix}"


def _onsite_capture_path_matches_format(
    path: Path,
    *,
    onsite_capture_format: str | None,
) -> bool:
    suffix = path.suffix.casefold()
    normalized_format = str(onsite_capture_format or "").strip().casefold()
    if normalized_format in _ONSITE_MARKDOWN_FORMATS:
        return suffix == ".md"
    if normalized_format in _ONSITE_HTML_FORMATS:
        return suffix == ".html"
    if normalized_format in _ONSITE_PDF_FORMATS:
        return suffix == ".pdf"
    return suffix in _ONSITE_CAPTURE_SUFFIXES


def _generated_onsite_capture_format(
    *,
    onsite_capture_format: str | None,
    suffix: str,
) -> str:
    normalized_format = str(onsite_capture_format or "").strip()
    lowered_format = normalized_format.casefold()
    if suffix == ".md":
        return (
            normalized_format
            if lowered_format in _ONSITE_MARKDOWN_FORMATS
            else "markdown"
        )
    if suffix == ".html":
        return normalized_format if lowered_format in _ONSITE_HTML_FORMATS else "html"
    return normalized_format or "browser_rendered_pdf"


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
    download_dir: Path,
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
    if blocked_reason and blocked_reason != "blocked_unknown_required_enum":
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
                download_dir=download_dir,
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
        return http_runtime.fetch_html_from_url(
            page_url=final_url,
            timeout_seconds=min(
                _ONSITE_HTML_FETCH_TIMEOUT_SECONDS,
                max(1.0, float(request.settings.timeout_seconds or 1.0)),
            ),
            ctx=ctx,
            normalized_url=normalized_url,
        )
    except AppError:
        return ""


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
    download_dir: Path,
    normalized_url: str,
    final_url: str,
    html: str,
) -> Path:
    capture_root = validate_browser_download_directory(download_dir)
    return _publish_generated_onsite_capture(
        download_dir=capture_root,
        claimed_path="",
        final_url=final_url or normalized_url,
        content=str(html or ""),
        suffix=".html",
    )


def _publish_generated_onsite_capture(
    *,
    download_dir: Path,
    claimed_path: str,
    final_url: str,
    content: str,
    suffix: str,
) -> Path:
    capture_root = validate_browser_download_directory(download_dir)
    ensure_browser_directory(capture_root)
    preferred_path = _safe_onsite_capture_path(
        download_dir=capture_root,
        claimed_path=claimed_path,
        final_url=final_url,
        suffix=suffix,
    )
    content_bytes = str(content or "").encode("utf-8")
    stage_path = _write_onsite_capture_stage(
        download_dir=capture_root,
        content=content_bytes,
    )
    try:
        try:
            materialized_path = materialize_external_browser_artifact(
                source_path=stage_path,
                download_dir=capture_root,
                preferred_filename=preferred_path.name,
                source_identity=final_url or "onsite_report",
            )
        except AppError:
            raise
        except OSError as exc:
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Generated on-site capture could not be materialized",
                cause=exc,
                retryable=False,
                context={
                    "path_role": "on-site capture",
                    "next_action": "Choose a writable browser output directory",
                },
            ) from exc
        if materialized_path is None:
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Generated on-site capture could not be materialized",
                retryable=False,
                context={
                    "path_role": "on-site capture",
                    "next_action": "Choose a writable browser output directory",
                },
            )
        validated_path = validate_browser_artifact_path(
            materialized_path,
            parent_dir=capture_root,
            temporary_suffixes=(".part",),
        )
        if validated_path.suffix.casefold() != suffix.casefold():
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Generated on-site capture has an incompatible extension",
                retryable=False,
                context={
                    "path_role": "on-site capture",
                    "next_action": "Choose a compatible capture format",
                },
            )
        try:
            actual_bytes = validated_path.read_bytes()
        except OSError as exc:
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Generated on-site capture could not be reopened",
                cause=exc,
                retryable=False,
                context={
                    "path_role": "on-site capture",
                    "next_action": "Choose a readable browser output directory",
                },
            ) from exc
        if actual_bytes != content_bytes:
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Generated on-site capture bytes do not match the capture",
                retryable=False,
                context={
                    "path_role": "on-site capture",
                    "next_action": "Retry the bounded capture operation",
                },
            )
        return validated_path
    finally:
        _unlink_owned_onsite_stage(stage_path)


def _write_onsite_capture_stage(*, download_dir: Path, content: bytes) -> Path:
    file_descriptor: int | None = None
    stage_path: Path | None = None
    try:
        file_descriptor, stage_name = tempfile.mkstemp(
            prefix="",
            suffix=".part",
            dir=str(download_dir),
        )
        stage_path = Path(stage_name)
        stage_path = validate_browser_artifact_path(
            stage_path,
            parent_dir=download_dir,
        )
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return stage_path
    except AppError:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if stage_path is not None:
            _unlink_owned_onsite_stage(stage_path)
        raise
    except OSError as exc:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if stage_path is not None:
            _unlink_owned_onsite_stage(stage_path)
        raise AppError(
            code="browser_download_artifact_materialization_failed",
            message="Generated on-site capture could not be staged",
            cause=exc,
            retryable=False,
            context={
                "path_role": "on-site capture",
                "next_action": "Choose a writable browser output directory",
            },
        ) from exc


def _unlink_owned_onsite_stage(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


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
        return validate_browser_artifact_path(
            downloaded_path,
            parent_dir=downloaded_path.parent,
            temporary_suffixes=(".part",),
        )
    capture_root = validate_browser_download_directory(downloaded_path.parent)
    downloaded_path = validate_browser_artifact_path(
        downloaded_path,
        parent_dir=capture_root,
        temporary_suffixes=(".part",),
    )
    preferred_path = resolve_browser_artifact_path(
        parent_dir=capture_root,
        source_name=f"{downloaded_path.stem}.html",
        extension=".html",
        identity=str(downloaded_path),
        temporary_suffixes=(".part",),
    )
    try:
        materialized_path = materialize_external_browser_artifact(
            source_path=downloaded_path,
            download_dir=capture_root,
            preferred_filename=preferred_path.name,
            source_identity=str(downloaded_path),
        )
    except AppError:
        raise
    except OSError as exc:
        raise AppError(
            code="browser_download_artifact_materialization_failed",
            message="Recovered on-site HTML could not be materialized",
            cause=exc,
            retryable=False,
            context={
                "path_role": "recovered on-site capture",
                "next_action": "Choose a writable browser output directory",
            },
        ) from exc
    if materialized_path is None:
        raise AppError(
            code="browser_download_artifact_materialization_failed",
            message="Recovered on-site HTML could not be materialized",
            retryable=False,
            context={
                "path_role": "recovered on-site capture",
                "next_action": "Choose a writable browser output directory",
            },
        )
    resolved_path = validate_browser_artifact_path(
        materialized_path,
        parent_dir=capture_root,
        temporary_suffixes=(".part",),
    )
    if resolved_path.suffix.casefold() != ".html":
        raise AppError(
            code="browser_download_artifact_materialization_failed",
            message="Recovered on-site HTML has an incompatible extension",
            retryable=False,
            context={
                "path_role": "recovered on-site capture",
                "next_action": "Choose a compatible browser output directory",
            },
        )
    try:
        if resolved_path.read_bytes() != downloaded_path.read_bytes():
            raise AppError(
                code="browser_download_artifact_materialization_failed",
                message="Recovered on-site HTML bytes do not match the source",
                retryable=False,
                context={
                    "path_role": "recovered on-site capture",
                    "next_action": "Retry the bounded recovery operation",
                },
            )
    except OSError as exc:
        raise AppError(
            code="browser_download_artifact_materialization_failed",
            message="Recovered on-site HTML could not be reopened",
            cause=exc,
            retryable=False,
            context={
                "path_role": "recovered on-site capture",
                "next_action": "Choose a readable browser output directory",
            },
        ) from exc
    return resolved_path


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
