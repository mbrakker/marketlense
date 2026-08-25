"""Capture complete public Issuu embeds as rendered PDF artifacts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

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
from src.contracts.pdf_ocr import PdfImageRenderRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download._http.config import _HTML_FETCH_HEADERS
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
)
from src.services._http_acquisition import execute_http_acquisition
from src.services.pdf_service import render_image_pdf
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_ISSUU_EMBED_HOST = "e.issuu.com"
_ISSUU_DOCUMENT_HOST = "issuu.com"
_ISSUU_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,200}$")
_ISSUU_REVISION_PATTERN = re.compile(r'"revisionId"\s*:\s*"(?P<value>\d{12})"')
_ISSUU_PUBLICATION_PATTERN = re.compile(
    r'"publicationId"\s*:\s*"(?P<value>[0-9a-f]{32})"', re.IGNORECASE
)
_ISSUU_PAGE_COUNT_PATTERN = re.compile(r'"pageCount"\s*:\s*(?P<value>\d{1,3})')
_ISSUU_MAX_PAGE_COUNT = 250
_ISSUU_PAGE_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class _IssuuEmbed:
    document_slug: str
    publisher: str

    @property
    def document_url(self) -> str:
        return (
            f"https://{_ISSUU_DOCUMENT_HOST}/{self.publisher}/docs/{self.document_slug}"
        )


class _IssuuIframeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "iframe":
            return
        for name, value in attrs:
            if name.casefold() == "src" and value:
                self.sources.append(value)


def try_embedded_issuu_capture(
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
    """Return a PDF only when a public Issuu embed yields every declared page."""
    embed = _extract_embedded_issuu(source_page_html)
    if embed is None:
        return None
    document_url = embed.document_url
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_issuu_capture_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "source_page_url": source_page_url,
                "document_url": document_url,
            },
        )
    )
    try:
        document_response = http_acquisition_executor(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_issuu_document",
                method="GET",
                url=document_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=request.settings.timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html",),
                    max_body_bytes=4 * 1024 * 1024,
                    truncate_body=True,
                ),
                error_code="browser_download_issuu_document_fetch_failed",
                error_message="Failed to fetch the public Issuu report document",
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "source_page_url": source_page_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError:
        return None
    metadata = _extract_issuu_metadata(str(document_response.text_body or ""))
    if document_response.status_code >= 400 or metadata is None:
        return None
    revision_id, publication_id, page_count = metadata
    page_pattern = (
        f"https://image.isu.pub/{revision_id}-{publication_id}/jpg/page_{{page}}.jpg"
    )
    page_images: list[bytes] = []
    try:
        for page_number in range(1, page_count + 1):
            page_url = page_pattern.format(page=page_number)
            page_response = http_acquisition_executor(
                request=HttpAcquisitionRequest(
                    schema_version="1.0",
                    purpose="browser_report_download_issuu_page",
                    method="GET",
                    url=page_url,
                    headers=_HTML_FETCH_HEADERS,
                    timeout_seconds=request.settings.timeout_seconds,
                    response_policy=HttpAcquisitionResponsePolicy(
                        schema_version="1.0",
                        require_success_status=False,
                        capture_text=False,
                        capture_binary=True,
                        capture_content_type_markers=("image/",),
                        max_body_bytes=_ISSUU_PAGE_MAX_BYTES,
                        truncate_body=False,
                    ),
                    error_code="browser_download_issuu_page_fetch_failed",
                    error_message="Failed to fetch a public Issuu report page",
                    allow_redirects=True,
                    context_fields={
                        "normalized_url": normalized_url,
                        "source_page_url": source_page_url,
                        "page_number": page_number,
                    },
                ),
                ctx=ctx,
                requests_module=requests,
            )
            image = bytes(page_response.body_bytes or b"")
            if (
                page_response.status_code >= 400
                or page_response.body_truncated
                or not page_response.content_type.casefold().startswith("image/")
                or not image
            ):
                return None
            page_images.append(image)
    except AppError:
        return None
    capture_path = download_dir / "issuu_rendered_report.pdf"
    if not _write_rendered_pdf(
        capture_path=capture_path,
        page_images=page_images,
        ctx=ctx,
    ):
        capture_path.unlink(missing_ok=True)
        return None
    final_page_url = (
        str(document_response.final_url or document_url).strip() or document_url
    )
    result = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="onsite_report",
        route_family="browser_onsite_report",
        route_status="verified",
        outcome="captured",
        route_summary=(
            "Follow the publisher's public Issuu embed and preserve every "
            "rendered report page as a local PDF."
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
                target_text=document_url,
                target_role="iframe",
                target_url=document_url,
                result=f"Captured {page_count} public Issuu rendered pages",
            ),
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=source_page_url != final_page_url,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_page_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_page_url,
            final_page_title="Issuu report",
            terminal_text_excerpt="",
            artifact_url=document_url,
            artifact_kind="onsite_report",
            artifact_validation_status="verified",
            artifact_validation_detail=(
                f"Captured all {page_count} public Issuu rendered pages as a PDF."
            ),
            confirmation_signal_count=1,
            traversed_page_urls=[source_page_url, final_page_url],
            evidence_labels=[
                "publisher_embedded_issuu",
                "public_rendered_pages",
                "complete_rendered_pdf_capture",
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
        onsite_capture_format="rendered_onsite_pdf",
        onsite_page_count=page_count,
        onsite_completeness_status="complete",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_issuu_capture_complete",
            module=logger.name,
            fields=browser_download_result_log_fields(result),
        )
    )
    return result


def _extract_embedded_issuu(html_source: str) -> _IssuuEmbed | None:
    parser = _IssuuIframeParser()
    try:
        parser.feed(str(html_source or ""))
        parser.close()
    except (TypeError, ValueError):
        return None
    for source in parser.sources:
        parsed = urlsplit(source)
        if parsed.scheme != "https" or parsed.hostname != _ISSUU_EMBED_HOST:
            continue
        if parsed.path.rstrip("/") != "/embed.html":
            continue
        query = parse_qs(parsed.query)
        document_slug = str((query.get("d") or [""])[0]).strip()
        publisher = str((query.get("u") or [""])[0]).strip()
        if _ISSUU_IDENTIFIER_PATTERN.fullmatch(
            document_slug
        ) and _ISSUU_IDENTIFIER_PATTERN.fullmatch(publisher):
            return _IssuuEmbed(document_slug=document_slug, publisher=publisher)
    return None


def _extract_issuu_metadata(html_source: str) -> tuple[str, str, int] | None:
    token = str(html_source or "").replace(r"\"", '"')
    revision_match = _ISSUU_REVISION_PATTERN.search(token)
    publication_match = _ISSUU_PUBLICATION_PATTERN.search(token)
    page_count_match = _ISSUU_PAGE_COUNT_PATTERN.search(token)
    if not (revision_match and publication_match and page_count_match):
        return None
    page_count = int(page_count_match.group("value"))
    if page_count < 2 or page_count > _ISSUU_MAX_PAGE_COUNT:
        return None
    return (
        revision_match.group("value"),
        publication_match.group("value").casefold(),
        page_count,
    )


def _write_rendered_pdf(
    *, capture_path: Path, page_images: list[bytes], ctx: RunContext
) -> bool:
    try:
        response = render_image_pdf(
            PdfImageRenderRequest(
                schema_version="1.0",
                output_path=capture_path.as_posix(),
                image_bytes=page_images,
            ),
            ctx,
        )
        return response.rendered_page_count == len(page_images) and bool(page_images)
    except AppError:
        return False


__all__ = ["try_embedded_issuu_capture"]
