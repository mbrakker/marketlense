"""PDF materialization and verified PDF result adaptation for browser downloads."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlsplit

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
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

from .evidence import (
    _dom_snapshot_sha256,
    _normalize_network_events,
    _normalize_traversed_page_urls,
    _resolve_observed_document_urls,
    _resolve_visited_url_timeline,
)


def _complete_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    downloaded_path: Path | None,
    target_urls: Iterable[str | None],
    trusted_target_urls: Iterable[str | None] = (),
    trusted_extensionless_pdf_urls: Iterable[str | None] = (),
) -> tuple[Path | None, bool]:
    trusted_targets = {
        urljoin(str(request.attempt_url or normalized_url).strip(), str(target_url))
        for target_url in trusted_target_urls
        if str(target_url or "").strip()
    }
    trusted_extensionless_targets = {
        urljoin(str(request.attempt_url or normalized_url).strip(), str(target_url))
        for target_url in trusted_extensionless_pdf_urls
        if str(target_url or "").strip()
    }
    if downloaded_path is not None:
        if not (
            _downloaded_pdf_matches_requested_report(
                request=request, downloaded_path=downloaded_path
            )
            or _downloaded_pdf_matches_browser_observed_target(
                downloaded_path=downloaded_path,
                trusted_target_urls=trusted_targets,
            )
        ):
            return None, False
        try:
            ensured_path = http_runtime.ensure_downloaded_pdf(
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
            require_report_match=(
                urljoin(
                    str(request.attempt_url or normalized_url).strip(),
                    normalized_target,
                )
                not in trusted_targets
            ),
            allow_extensionless_pdf_url=(
                urljoin(
                    str(request.attempt_url or normalized_url).strip(),
                    normalized_target,
                )
                in trusted_extensionless_targets
            ),
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
    require_report_match: bool = True,
    allow_extensionless_pdf_url: bool = False,
) -> Path | None:
    target_url = urljoin(str(request.attempt_url or normalized_url).strip(), target_url)
    if not allow_extensionless_pdf_url and not _looks_like_pdf_url(target_url):
        return None
    if require_report_match and not _pdf_url_matches_requested_report(
        request=request, pdf_url=target_url
    ):
        return None
    destination_name = Path(urlsplit(target_url).path).name or "download.pdf"
    destination_path = download_dir / destination_name
    try:
        http_runtime.download_pdf_from_url(
            pdf_url=target_url,
            destination_path=destination_path,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        ensured_path = http_runtime.ensure_downloaded_pdf(
            downloaded_path=destination_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=target_url,
            timeout_seconds=request.settings.timeout_seconds,
        )
        http_runtime.validate_downloaded_pdf_artifact(
            downloaded_path=ensured_path,
            downloaded_mime_type=http_runtime.resolve_downloaded_mime_type(
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


def _downloaded_pdf_matches_browser_observed_target(
    *,
    downloaded_path: Path,
    trusted_target_urls: Iterable[str],
) -> bool:
    """Keep a local PDF only when its filename ties it to a browser PDF URL."""
    downloaded_names = {
        downloaded_path.name.casefold(),
        unquote(downloaded_path.name).casefold(),
    }
    for target_url in trusted_target_urls:
        target_name = Path(urlsplit(target_url).path).name
        if not target_name:
            continue
        target_names = {target_name.casefold(), unquote(target_name).casefold()}
        if downloaded_names.intersection(target_names):
            return True
    return False


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
