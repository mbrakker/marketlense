"""Terminal evidence adaptation, normalization, verification, and snapshots."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    DownloadTerminalEvidence,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

from . import ARTIFACT_LOGGER_NAME, _VERIFIED_EMAIL_SIGNAL_MARKERS

logger = logging.getLogger(ARTIFACT_LOGGER_NAME)

_TERMINAL_HTML_FETCH_TIMEOUT_SECONDS = 15.0

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
        validation_status = str(item.validation_status or "failed").strip() or "failed"
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
    for raw_url in http_runtime.extract_embedded_pdf_urls(
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
        r"(?is)<(script|style)[^>]*>.*?</\1\b[^>]*>",
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
        return http_runtime.fetch_html_from_url(
            page_url=token,
            timeout_seconds=min(
                _TERMINAL_HTML_FETCH_TIMEOUT_SECONDS,
                max(1.0, float(request.settings.timeout_seconds or 1.0)),
            ),
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
