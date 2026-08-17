"""Capture public Adobe InDesign Publish Online report text assets."""

from __future__ import annotations

import html
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

import requests

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponse,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download._http.config import (
    _HTML_FETCH_HEADERS,
    _HTML_FETCH_MAX_BYTES,
)
from src.services._browser_report_download._http.html_evidence import (
    _extract_html_title,
    _extract_text_excerpt,
    _html_to_text,
)
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_ADOBE_INDESIGN_VIEW_URL_PATTERN = re.compile(
    r"https?://indd\.adobe\.com/view/"
    r"(?P<publication_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})(?:[/?#].*)?",
    re.IGNORECASE,
)
_ADOBE_INDESIGN_VERSION_PREFIX_PATTERN = re.compile(
    r'(?:\\?"|\")VERSION_PREFIX(?:\\?"|\")\s*:\s*'
    r'(?:\\?"|\")(?P<version>[A-Za-z0-9_-]+)',
)
_ADOBE_INDESIGN_CONTENT_MAX_BYTES = 20 * 1024 * 1024
_ADOBE_INDESIGN_MIN_PAGE_COUNT = 2
_ADOBE_INDESIGN_MIN_TEXT_LENGTH = 1_000


class _AdobeInDesignIframeParser(HTMLParser):
    """Extract iframe source URLs without treating visible text as an embed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.iframe_sources: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "iframe":
            return
        for name, value in attrs:
            if name.casefold() == "src" and value:
                self.iframe_sources.append(value)


def try_embedded_adobe_indesign_capture(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    source_page_url: str,
    source_page_html: str,
    http_acquisition_executor: Callable[..., HttpAcquisitionResponse] = (
        execute_http_acquisition
    ),
) -> BrowserReportDownloadResult | None:
    """Capture the complete text asset behind a public Adobe InDesign embed."""
    publication_id = _extract_embedded_adobe_indesign_publication(source_page_html)
    if publication_id is None:
        return None
    viewer_url = f"https://indd.adobe.com/view/{publication_id}"
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_adobe_indesign_capture_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "source_page_url": source_page_url,
                "viewer_url": viewer_url,
            },
        )
    )
    try:
        viewer_response = http_acquisition_executor(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_adobe_indesign_viewer",
                method="GET",
                url=viewer_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=request.settings.timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_HTML_FETCH_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_adobe_indesign_viewer_fetch_failed",
                error_message="Failed to fetch the public Adobe InDesign report viewer",
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "source_page_url": source_page_url,
                    "viewer_url": viewer_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError:
        return None
    if viewer_response.status_code >= 400:
        return None
    version_prefix = _extract_adobe_indesign_version_prefix(
        str(viewer_response.text_body or "")
    )
    if version_prefix is None:
        return None
    content_url = (
        "https://indd.adobe.com/view/publication/"
        f"{publication_id}/{version_prefix}/content.json"
    )
    try:
        content_response = http_acquisition_executor(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_adobe_indesign_content",
                method="GET",
                url=content_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=request.settings.timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("json",),
                    max_body_bytes=_ADOBE_INDESIGN_CONTENT_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_adobe_indesign_content_fetch_failed",
                error_message=(
                    "Failed to fetch the public Adobe InDesign report content"
                ),
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "source_page_url": source_page_url,
                    "viewer_url": viewer_url,
                    "content_url": content_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError:
        return None
    if content_response.status_code >= 400 or content_response.body_truncated:
        return None
    raw_content = str(content_response.text_body or "")
    pages = _adobe_indesign_pages(raw_content)
    rendered_html = _render_adobe_indesign_capture_html(pages)
    if (
        len(pages) < _ADOBE_INDESIGN_MIN_PAGE_COUNT
        or len(_html_to_text(rendered_html)) < _ADOBE_INDESIGN_MIN_TEXT_LENGTH
    ):
        return None

    raw_capture_path = download_dir / "adobe_indesign_content.json"
    raw_capture_path.write_text(raw_content, encoding="utf-8")
    capture_path = download_dir / "adobe_indesign_capture.html"
    capture_path.write_text(rendered_html, encoding="utf-8")
    final_page_url = str(viewer_response.final_url or viewer_url).strip() or viewer_url
    result = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="onsite_report",
        route_family="browser_onsite_report",
        route_status="verified",
        outcome="captured",
        route_summary=(
            "Open the publisher report page, follow its public Adobe InDesign "
            "embed, and capture the verified complete text asset locally."
        ),
        final_page_url=final_page_url,
        resolved_target_url=final_page_url,
        used_route_hint=bool(request.route_hint),
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=source_page_url,
                target_role="url",
                target_url=source_page_url,
                result="Fetched the publisher report page",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="extract",
                target_text=viewer_url,
                target_role="iframe",
                target_url=viewer_url,
                result="Verified the public Adobe InDesign report embed",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=2,
                action="extract",
                target_text=content_url,
                target_role="document",
                target_url=content_url,
                result="Captured the complete Adobe InDesign text asset",
            ),
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=(source_page_url != final_page_url),
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_page_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_page_url,
            final_page_title=_extract_html_title(str(viewer_response.text_body or "")),
            terminal_text_excerpt=_extract_text_excerpt(rendered_html),
            artifact_url=content_url,
            artifact_kind="onsite_report",
            artifact_validation_status="verified",
            artifact_validation_detail=(
                "Captured the public Adobe InDesign content asset with "
                f"{len(pages)} text-bearing pages; raw audit artifact: "
                f"{raw_capture_path.name}."
            ),
            confirmation_signal_count=1,
            traversed_page_urls=[source_page_url, final_page_url, content_url],
            evidence_labels=[
                "publisher_embedded_adobe_indesign",
                "public_content_asset",
                "complete_text_capture",
            ],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=bool(request.source_page_url_hint),
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=str(capture_path),
        onsite_capture_format="html",
        onsite_page_count=len(pages),
        onsite_completeness_status="complete",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_adobe_indesign_capture_complete",
            module=logger.name,
            fields={
                **browser_download_result_log_fields(result),
                "raw_capture_path": str(raw_capture_path),
                "page_count": len(pages),
            },
        )
    )
    return result


def _extract_embedded_adobe_indesign_publication(html_source: str) -> str | None:
    parser = _AdobeInDesignIframeParser()
    try:
        parser.feed(str(html_source or ""))
        parser.close()
    except (TypeError, ValueError):
        return None
    for source in parser.iframe_sources:
        match = _ADOBE_INDESIGN_VIEW_URL_PATTERN.fullmatch(source.strip())
        if match is not None:
            return str(match.group("publication_id")).strip() or None
    return None


def _extract_adobe_indesign_version_prefix(viewer_html: str) -> str | None:
    match = _ADOBE_INDESIGN_VERSION_PREFIX_PATTERN.search(str(viewer_html or ""))
    return str(match.group("version") if match else "").strip() or None


def _adobe_indesign_pages(raw_content: str) -> list[tuple[int, list[str]]]:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError:
        return []
    raw_pages = payload.get("framesData") if isinstance(payload, dict) else None
    if not isinstance(raw_pages, list):
        return []
    page_fragments: dict[int, list[str]] = {}
    for raw_page in raw_pages:
        if not isinstance(raw_page, dict):
            continue
        page_number, frame_data = raw_page.get("pageNo"), raw_page.get("frameData")
        if not isinstance(page_number, int) or not isinstance(frame_data, list):
            continue
        fragments: list[str] = []
        for frame in frame_data:
            if isinstance(frame, dict):
                fragments.extend(
                    _adobe_indesign_text_fragments(frame.get("textBoundary"))
                )
        page_text = _normalize_adobe_indesign_text(" ".join(fragments))
        if page_text:
            page_fragments.setdefault(page_number, []).append(page_text)
    return [
        (page_number, [_normalize_adobe_indesign_text(" ".join(fragments))])
        for page_number, fragments in sorted(page_fragments.items())
    ]


def _adobe_indesign_text_fragments(value: object) -> list[str]:
    if isinstance(value, str):
        return (
            [value]
            if any(
                character.isprintable() and not character.isspace()
                for character in value
            )
            else []
        )
    if not isinstance(value, list):
        return []
    return [
        fragment for item in value for fragment in _adobe_indesign_text_fragments(item)
    ]


def _normalize_adobe_indesign_text(value: str) -> str:
    without_controls = "".join(
        character if character.isprintable() or character in "\n\t" else " "
        for character in str(value or "")
    )
    return re.sub(r"\s+", " ", without_controls).strip()


def _render_adobe_indesign_capture_html(pages: list[tuple[int, list[str]]]) -> str:
    document = ['<!doctype html><html><head><meta charset="utf-8"></head><body>']
    for page_number, fragments in pages:
        document.append(
            f'<section data-page-number="{page_number}"><h2>Page {page_number}</h2>'
        )
        document.extend(f"<p>{html.escape(fragment)}</p>" for fragment in fragments)
        document.append("</section>")
    document.append("</body></html>")
    return "".join(document)


__all__ = ["try_embedded_adobe_indesign_capture"]
