"""PDF transfer, downloaded-wrapper recovery, and artifact validation."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

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
    _PDF_FETCH_FALLBACK_HEADERS,
    _HTML_FETCH_HEADERS,
    _HTML_FETCH_MAX_BYTES,
    _PDF_FETCH_HEADERS,
    _PDF_FETCH_MAX_BYTES,
)
from src.services._browser_report_download._http.html_evidence import (
    _extract_embedded_pdf_url,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_PDF_SIGNATURE = b"%PDF-"
_PDF_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
}
_PDF_BINARY_FALLBACK_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}


def try_direct_pdf_download(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    probe_url: str | None = None,
    route_family: str = "direct_pdf_probe",
    used_candidate_pdf_url: bool = False,
    used_candidate_source_page: bool = False,
) -> BrowserReportDownloadResult | None:
    target_url = str(probe_url or normalized_url).strip() or normalized_url
    destination_name = Path(urlsplit(target_url).path).name or "download.pdf"
    destination_path = download_dir / destination_name
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_pdf_attempt_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "route_family": route_family,
                "destination_path": str(destination_path),
            },
        )
    )
    try:
        download_pdf_from_url(
            pdf_url=target_url,
            destination_path=destination_path,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        downloaded_path = ensure_downloaded_pdf(
            downloaded_path=destination_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=target_url,
            timeout_seconds=request.settings.timeout_seconds,
        )
        downloaded_mime_type = resolve_downloaded_mime_type(
            reported_mime_type=None,
            downloaded_path=downloaded_path,
        )
        validate_downloaded_pdf_artifact(
            downloaded_path=downloaded_path,
            downloaded_mime_type=downloaded_mime_type,
            normalized_url=normalized_url,
        )
    except AppError as exc:
        destination_path.unlink(missing_ok=True)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_direct_pdf_attempt_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        if not exc.retryable:
            raise
        return None

    response = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="pdf_download",
        route_family=route_family,
        route_status="verified",
        outcome="downloaded",
        route_summary="Open the direct PDF URL and save the returned PDF file locally.",
        final_page_url=target_url,
        resolved_target_url=target_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=target_url,
                target_role="url",
                target_url=target_url,
                result="downloaded",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=target_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=target_url,
            final_page_title="",
            terminal_text_excerpt="",
            artifact_url=target_url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="Validated local PDF artifact.",
            confirmation_signal_count=0,
            traversed_page_urls=[target_url],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=used_candidate_source_page,
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=str(destination_path),
        downloaded_file_name=destination_path.name,
        downloaded_mime_type=resolve_downloaded_mime_type(
            reported_mime_type=None,
            downloaded_path=destination_path,
        ),
        downloaded_size_bytes=destination_path.stat().st_size,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_pdf_attempt_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response


def ensure_downloaded_pdf(
    *,
    downloaded_path: Path | None,
    ctx: RunContext,
    normalized_url: str,
    document_url: str,
    timeout_seconds: float,
) -> Path | None:
    if downloaded_path is None:
        return None
    if is_pdf_file(downloaded_path):
        return downloaded_path

    wrapper_html = _read_text_if_small(downloaded_path, max_bytes=64 * 1024)
    embedded_pdf_url = _extract_embedded_pdf_url(
        wrapper_html=wrapper_html,
        document_url=document_url,
    )
    if embedded_pdf_url:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_wrapper_detected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "downloaded_file_path": str(downloaded_path),
                    "embedded_pdf_url": embedded_pdf_url,
                },
            )
        )
        download_pdf_from_url(
            pdf_url=embedded_pdf_url,
            destination_path=downloaded_path,
            timeout_seconds=timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if is_pdf_file(downloaded_path):
            return downloaded_path

    raise AppError(
        code="browser_download_invalid_pdf",
        message="Downloaded file is not a valid PDF",
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "downloaded_file_path": str(downloaded_path),
            "document_url": document_url,
        },
    )


def fetch_html_from_url(
    *,
    page_url: str,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
) -> str:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_fetch_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_url": page_url,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_terminal_html_fetch",
                method="GET",
                url=page_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_HTML_FETCH_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_html_fetch_failed",
                error_message="Failed to fetch terminal HTML for on-site capture recovery",
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "page_url": page_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        raise AppError(
            code="browser_download_html_fetch_failed",
            message="Failed to fetch terminal HTML for on-site capture recovery",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
            },
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_fetch_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "body_truncated": response.body_truncated,
            },
        )
    )
    if response.status_code >= 400:
        raise AppError(
            code="browser_download_html_fetch_failed",
            message="Terminal HTML fetch returned an error status",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "status_code": response.status_code,
            },
        )
    content_type = str(response.content_type or "").casefold()
    if "html" not in content_type and "xml" not in content_type:
        raise AppError(
            code="browser_download_html_fetch_invalid_content_type",
            message="Terminal HTML fetch did not return HTML content",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "content_type": response.content_type,
            },
        )
    return str(response.text_body or "")


def resolve_downloaded_mime_type(
    *,
    reported_mime_type: str | None,
    downloaded_path: Path | None,
) -> str | None:
    if downloaded_path is None:
        return None
    reported = str(reported_mime_type or "").strip().lower() or None
    guessed = _guess_mime_type(downloaded_path)
    if guessed == "application/pdf":
        if (
            reported
            and reported not in _PDF_MIME_TYPES
            and reported not in _PDF_BINARY_FALLBACK_MIME_TYPES
        ):
            return reported
        return guessed
    return reported or guessed


def validate_downloaded_pdf_artifact(
    *,
    downloaded_path: Path | None,
    downloaded_mime_type: str | None,
    normalized_url: str,
) -> None:
    if downloaded_path is None:
        return
    if not is_pdf_file(downloaded_path):
        raise AppError(
            code="browser_download_invalid_pdf",
            message="Downloaded file is not a valid PDF",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
            },
        )
    lowered_mime = str(downloaded_mime_type or "").strip().lower()
    if (
        lowered_mime
        and lowered_mime not in _PDF_MIME_TYPES
        and lowered_mime not in _PDF_BINARY_FALLBACK_MIME_TYPES
    ):
        raise AppError(
            code="browser_download_invalid_pdf_metadata",
            message="Downloaded file metadata does not match a PDF artifact",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
                "downloaded_mime_type": downloaded_mime_type,
            },
        )
    if (
        downloaded_path.suffix.lower() != ".pdf"
        and lowered_mime not in _PDF_MIME_TYPES
        and lowered_mime not in _PDF_BINARY_FALLBACK_MIME_TYPES
    ):
        raise AppError(
            code="browser_download_invalid_pdf_metadata",
            message="Downloaded file is missing PDF-identifying metadata",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
                "downloaded_mime_type": downloaded_mime_type,
            },
        )


def is_pdf_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(_PDF_SIGNATURE)) == _PDF_SIGNATURE
    except OSError:
        return False


def download_pdf_from_url(
    *,
    pdf_url: str,
    destination_path: Path,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pdf_fetch_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
        )
    )
    temp_path = destination_path.with_suffix(destination_path.suffix + ".part")
    response: HttpAcquisitionResponse | None = None
    try:
        for attempt_index, headers in enumerate(
            (_PDF_FETCH_HEADERS, _PDF_FETCH_FALLBACK_HEADERS)
        ):
            try:
                response = _execute_pdf_fetch(
                    pdf_url=pdf_url,
                    temp_path=temp_path,
                    timeout_seconds=timeout_seconds,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    destination_path=destination_path,
                    headers=headers,
                )
                break
            except AppError as exc:
                temp_path.unlink(missing_ok=True)
                if (
                    attempt_index == 0
                    and exc.code == "browser_download_pdf_fetch_failed"
                ):
                    logger.info(
                        log_event(
                            ctx,
                            role="service",
                            event="browser_report_download_pdf_fetch_header_fallback",
                            module=logger.name,
                            fields={
                                "normalized_url": normalized_url,
                                "pdf_url": pdf_url,
                                "error_code": exc.code,
                            },
                        )
                    )
                    continue
                raise
        if response is None:
            raise AppError(
                code="browser_download_pdf_fetch_failed",
                message="Failed to fetch the real PDF from the wrapper page",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "pdf_url": pdf_url,
                    "destination_path": str(destination_path),
                },
            )
        temp_path.replace(destination_path)
    except AppError as exc:
        temp_path.unlink(missing_ok=True)
        raise exc


def _execute_pdf_fetch(
    *,
    pdf_url: str,
    temp_path: Path,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
    destination_path: Path,
    headers: dict[str, str],
) -> HttpAcquisitionResponse:
    response = execute_http_acquisition(
        request=HttpAcquisitionRequest(
            schema_version="1.0",
            purpose="browser_report_download_pdf_fetch",
            method="GET",
            url=pdf_url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            response_policy=HttpAcquisitionResponsePolicy(
                schema_version="1.0",
                require_success_status=True,
                capture_text=False,
                stream_to_path=str(temp_path),
                max_stream_bytes=_PDF_FETCH_MAX_BYTES,
            ),
            error_code="browser_download_pdf_fetch_failed",
            error_message="Failed to fetch the real PDF from the wrapper page",
            context_fields={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
            body_too_large_code="browser_download_pdf_fetch_failed",
            body_too_large_message="Fetched PDF exceeded the configured size cap",
            write_error_code="browser_download_pdf_write_failed",
            write_error_message="Failed to write the fetched PDF to disk",
        ),
        ctx=ctx,
        requests_module=requests,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pdf_fetch_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "streamed_bytes": response.streamed_bytes,
                "used_pooled_session": response.used_pooled_session,
                "used_header_fallback": headers == _PDF_FETCH_FALLBACK_HEADERS,
            },
        )
    )
    return response


def _guess_mime_type(downloaded_path: Path | None) -> str | None:
    if downloaded_path is None:
        return None
    if is_pdf_file(downloaded_path):
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(downloaded_path.name)
    if guessed:
        return guessed
    if downloaded_path.suffix.lower() == ".pdf":
        return "application/pdf"
    return None


def _read_text_if_small(path: Path, *, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
