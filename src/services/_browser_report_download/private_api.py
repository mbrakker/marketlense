"""Deterministic private-API playbook routes for browser downloads.

This service adapts browser-harness domain-skill practice: durable network
evidence may document private XHR/fetch endpoints so later runs can use HTTP
first. It consumes existing Marketlense browser playbooks and falls back to the
normal browser route whenever endpoint evidence is stale or incomplete.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import requests

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    BrowserRoutePlaybookSelection,
    BrowserRoutePrivateApiEvidence,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import try_direct_pdf_download
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_PRIVATE_API_SCHEMA_VERSION = "1.0"
_PRIVATE_API_MAX_BODY_BYTES = 2 * 1024 * 1024
_PRIVATE_API_FETCH_HEADERS = {
    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


def try_private_api_playbook_download(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
) -> BrowserReportDownloadResult | None:
    for playbook in request.selected_playbooks:
        for evidence in playbook.private_api_evidence:
            result = _try_private_api_evidence(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                download_dir=download_dir,
                playbook=playbook,
                evidence=evidence,
            )
            if result is not None:
                return result
    return None


def _try_private_api_evidence(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    playbook: BrowserRoutePlaybookSelection,
    evidence: BrowserRoutePrivateApiEvidence,
) -> BrowserReportDownloadResult | None:
    endpoint_url = _render_endpoint_url(
        endpoint_pattern=evidence.endpoint_pattern,
        source_url=execution_url or normalized_url,
    )
    common_fields: dict[str, object] = {
        "normalized_url": normalized_url,
        "playbook_id": playbook.playbook_id,
        "version": playbook.version,
        "private_api_evidence_id": evidence.evidence_id,
        "endpoint_pattern": evidence.endpoint_pattern,
        "endpoint_url": endpoint_url,
        "method": evidence.method,
        "fallback_route_family": evidence.fallback_route_family,
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_private_api_playbook_start",
            module=logger.name,
            fields={
                **common_fields,
                "request_shape_summary": evidence.request_shape_summary,
                "response_pdf_url_json_pointer": (
                    evidence.response_pdf_url_json_pointer
                ),
                "success_count": evidence.success_count,
            },
        )
    )
    if evidence.schema_version != _PRIVATE_API_SCHEMA_VERSION:
        _log_private_api_fallback(
            ctx=ctx,
            fields=common_fields,
            validation_result="schema_rejected",
            fallback_reason="unsupported_private_api_evidence_schema",
        )
        return None
    if evidence.method.strip().upper() != "GET":
        _log_private_api_fallback(
            ctx=ctx,
            fields=common_fields,
            validation_result="method_rejected",
            fallback_reason="unsupported_private_api_method",
        )
        return None
    if evidence.success_count < 2:
        _log_private_api_fallback(
            ctx=ctx,
            fields=common_fields,
            validation_result="evidence_rejected",
            fallback_reason="insufficient_repeated_success",
        )
        return None
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_private_api_playbook",
                method=evidence.method,
                url=endpoint_url,
                headers=_PRIVATE_API_FETCH_HEADERS,
                timeout_seconds=min(10.0, max(1.0, request.settings.timeout_seconds)),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    max_body_bytes=_PRIVATE_API_MAX_BODY_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_private_api_fetch_failed",
                error_message="Failed to fetch learned private API endpoint",
                allow_redirects=True,
                context_fields=common_fields,
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        _log_private_api_fallback(
            ctx=ctx,
            fields=common_fields,
            validation_result="fetch_failed",
            fallback_reason=exc.code,
        )
        return None
    status_codes = evidence.expected_status_codes or [200]
    if int(response.status_code) not in status_codes:
        _log_private_api_fallback(
            ctx=ctx,
            fields={
                **common_fields,
                "status_code": int(response.status_code),
                "expected_status_codes": list(status_codes),
            },
            validation_result="status_rejected",
            fallback_reason="unexpected_private_api_status",
        )
        return None
    text = str(response.text_body or "")
    missing_markers = [
        marker
        for marker in evidence.required_response_markers
        if marker.casefold() not in text.casefold()
    ]
    if missing_markers:
        _log_private_api_fallback(
            ctx=ctx,
            fields={**common_fields, "missing_markers": missing_markers},
            validation_result="marker_rejected",
            fallback_reason="required_response_markers_missing",
        )
        return None
    pdf_url = _extract_pdf_url(
        response_text=text,
        json_pointer=evidence.response_pdf_url_json_pointer,
        base_url=response.final_url or endpoint_url,
    )
    if not pdf_url:
        _log_private_api_fallback(
            ctx=ctx,
            fields=common_fields,
            validation_result="shape_rejected",
            fallback_reason="pdf_url_missing_from_private_api_response",
        )
        return None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_private_api_playbook_validation",
            module=logger.name,
            fields={
                **common_fields,
                "status_code": int(response.status_code),
                "validation_result": "accepted",
                "selected_pdf_url": pdf_url,
            },
        )
    )
    direct_result = try_direct_pdf_download(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        probe_url=pdf_url,
        route_family="private_api_playbook_pdf_probe",
        used_candidate_pdf_url=False,
        used_candidate_source_page=bool(request.source_page_url_hint),
    )
    if direct_result is None:
        _log_private_api_fallback(
            ctx=ctx,
            fields={**common_fields, "selected_pdf_url": pdf_url},
            validation_result="artifact_rejected",
            fallback_reason="private_api_pdf_download_failed",
        )
        return None
    result = _adapt_private_api_result(
        direct_result=direct_result,
        playbook=playbook,
        evidence=evidence,
        endpoint_url=endpoint_url,
        pdf_url=pdf_url,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_private_api_playbook_complete",
            module=logger.name,
            fields={
                **common_fields,
                "validation_result": "verified",
                "selected_pdf_url": pdf_url,
                "result": asdict(result),
            },
        )
    )
    return result


def _adapt_private_api_result(
    *,
    direct_result: BrowserReportDownloadResult,
    playbook: BrowserRoutePlaybookSelection,
    evidence: BrowserRoutePrivateApiEvidence,
    endpoint_url: str,
    pdf_url: str,
) -> BrowserReportDownloadResult:
    return replace(
        direct_result,
        route_family="private_api_playbook_pdf_probe",
        route_summary=(
            "Use a validated browser-route playbook private API endpoint, "
            "extract the PDF URL from the documented JSON response shape, and "
            "save the verified PDF locally."
        ),
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="http_private_api",
                target_text=evidence.endpoint_pattern,
                target_role="private_api_endpoint",
                target_url=endpoint_url,
                result="Fetched private API response from selected playbook evidence",
                expected_evidence=["network_event"],
                observed_evidence=["network_event"],
                verification_status="verified",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="extract",
                target_text=evidence.response_pdf_url_json_pointer,
                target_role="json_pointer",
                target_url=pdf_url,
                result="Extracted PDF URL from private API response",
                expected_evidence=["network_event"],
                observed_evidence=["network_event"],
                verification_status="verified",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=2,
                action="open",
                target_text=pdf_url,
                target_role="url",
                target_url=pdf_url,
                result="downloaded",
                expected_evidence=["artifact"],
                observed_evidence=["artifact"],
                verification_status="verified",
            ),
        ],
        terminal_evidence=replace(
            direct_result.terminal_evidence,
            traversed_page_urls=[endpoint_url, pdf_url],
            observed_document_urls=[pdf_url],
            evidence_labels=[
                "private_api_playbook",
                f"{playbook.playbook_id}@{playbook.version}",
                evidence.evidence_id,
                "network_event",
                "verified",
                "application/pdf",
            ],
        ),
    )


def _render_endpoint_url(*, endpoint_pattern: str, source_url: str) -> str:
    parsed = urlsplit(source_url)
    host = str(parsed.netloc or "").strip()
    path = str(parsed.path or "").strip()
    last_segment = next(
        (segment for segment in reversed(path.split("/")) if segment),
        "",
    )
    rendered = str(endpoint_pattern or "").strip()
    replacements = {
        "{source_url}": source_url,
        "{source_url_encoded}": quote(source_url, safe=""),
        "{host}": host,
        "{path}": path,
        "{path_encoded}": quote(path, safe=""),
        "{last_path_segment}": last_segment,
        "{last_path_segment_encoded}": quote(last_segment, safe=""),
    }
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    if rendered.startswith(("http://", "https://")):
        return rendered
    base_url = f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else source_url
    return urljoin(base_url, rendered)


def _extract_pdf_url(*, response_text: str, json_pointer: str, base_url: str) -> str:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return ""
    value = _json_pointer_value(payload, json_pointer)
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str)), "")
    token = str(value or "").strip()
    if ".pdf" not in token.casefold():
        return ""
    return urljoin(base_url, token)


def _json_pointer_value(payload: Any, pointer: str) -> Any:
    token = str(pointer or "").strip()
    if not token:
        return payload
    if not token.startswith("/"):
        return None
    value = payload
    for raw_part in token.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value.get(part)
            continue
        if isinstance(value, list) and part.isdigit():
            index = int(part)
            value = value[index] if index < len(value) else None
            continue
        return None
    return value


def _log_private_api_fallback(
    *,
    ctx: RunContext,
    fields: dict[str, object],
    validation_result: str,
    fallback_reason: str,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_private_api_playbook_fallback",
            module=logger.name,
            fields={
                **fields,
                "validation_result": validation_result,
                "fallback_reason": fallback_reason,
            },
        )
    )
