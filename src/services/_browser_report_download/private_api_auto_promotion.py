from __future__ import annotations

import hashlib
import json
import logging
from urllib.parse import quote, urljoin, urlsplit

import requests

from src.contracts.browser_download import (
    BrowserDownloadNetworkEvent,
    BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    BrowserRoutePrivateApiAutoPromotionDetectionResponse,
    BrowserRoutePrivateApiPromotionCandidate,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_MAX_PRIVATE_API_BODY_BYTES = 2 * 1024 * 1024
_PRIVATE_API_FETCH_HEADERS = {
    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}
_PRIVATE_API_URL_MARKERS = (
    "/api/",
    "api.",
    "download",
    "asset",
    "report",
    "resource",
    "document",
)
_STATIC_EXTENSIONS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".pdf",
)


def detect_private_api_promotion_candidates(
    request: BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    ctx: RunContext,
) -> BrowserRoutePrivateApiAutoPromotionDetectionResponse:
    if request.schema_version != "1.0":
        return _empty_response("unsupported_schema")
    result = request.result
    skip_reason = _detection_skip_reason(request)
    if skip_reason:
        _log_detection_complete(ctx=ctx, skipped_reason=skip_reason, candidates=[])
        return _empty_response(skip_reason)

    source_url = result.source_url or result.normalized_url
    artifact_url = _artifact_url(result)
    candidates: list[BrowserRoutePrivateApiPromotionCandidate] = []
    for event in _candidate_network_events(result.terminal_evidence.network_events):
        candidate = _candidate_from_event(
            request=request,
            event=event,
            source_url=source_url,
            artifact_url=artifact_url,
            ctx=ctx,
        )
        if candidate is not None:
            candidates.append(candidate)
            break
    _log_detection_complete(ctx=ctx, skipped_reason="", candidates=candidates)
    return BrowserRoutePrivateApiAutoPromotionDetectionResponse(
        schema_version="1.0",
        candidate_count=len(candidates),
        candidates=candidates,
        skipped_reason="",
    )


def _detection_skip_reason(
    request: BrowserRoutePrivateApiAutoPromotionDetectionRequest,
) -> str:
    mode = str(request.settings.private_api_playbook_promotion_mode or "disabled")
    if mode not in {"dry_run", "write"}:
        return "promotion_disabled"
    result = request.result
    if not str(result.route_family or "").startswith("browser_"):
        return "non_browser_route_family"
    if result.route_status not in {"verified", "recovered"}:
        return "unverified_route_status"
    if result.outcome != "downloaded":
        return "non_downloaded_outcome"
    if result.terminal_evidence.artifact_kind != "pdf":
        return "non_pdf_artifact"
    if result.terminal_evidence.artifact_validation_status not in {
        "verified",
        "recovered",
    }:
        return "artifact_not_verified"
    if not _artifact_url(result):
        return "artifact_url_missing"
    if not result.terminal_evidence.network_events:
        return "network_events_missing"
    return ""


def _candidate_network_events(
    network_events: list[BrowserDownloadNetworkEvent],
) -> list[BrowserDownloadNetworkEvent]:
    candidates: list[BrowserDownloadNetworkEvent] = []
    seen: set[str] = set()
    for event in network_events:
        url = str(event.url or "").strip()
        lowered = url.casefold()
        if not lowered.startswith(("http://", "https://")):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        path = urlsplit(url).path.casefold()
        if path.endswith(_STATIC_EXTENSIONS):
            continue
        if not any(marker in lowered for marker in _PRIVATE_API_URL_MARKERS):
            continue
        if str(event.initiator_type or "").strip().casefold() not in {
            "fetch",
            "xmlhttprequest",
            "other",
        }:
            continue
        candidates.append(event)
    return candidates[-8:]


def _candidate_from_event(
    *,
    request: BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    event: BrowserDownloadNetworkEvent,
    source_url: str,
    artifact_url: str,
    ctx: RunContext,
) -> BrowserRoutePrivateApiPromotionCandidate | None:
    event_url = str(event.url or "").strip()
    if not _same_host(event_url, source_url):
        return None
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_private_api_auto_promotion",
                method="GET",
                url=event_url,
                headers=_PRIVATE_API_FETCH_HEADERS,
                timeout_seconds=min(
                    10.0,
                    max(1.0, float(request.settings.timeout_seconds or 1.0)),
                ),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    max_body_bytes=_MAX_PRIVATE_API_BODY_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_private_api_candidate_fetch_failed",
                error_message="Failed to fetch private-API candidate endpoint",
                allow_redirects=True,
                context_fields={
                    "source_url": source_url,
                    "candidate_url": event_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_private_api_candidate_rejected",
                module=logger.name,
                fields={
                    "source_url": source_url,
                    "candidate_url": event_url,
                    "reason": "fetch_failed",
                    "error": str(exc),
                },
            )
        )
        return None
    if int(response.status_code) != 200:
        return None
    pointer, pdf_url = _first_matching_pdf_pointer(
        response_text=str(response.text_body or ""),
        base_url=response.final_url or event_url,
        artifact_url=artifact_url,
    )
    if not pointer or not pdf_url:
        return None
    endpoint_pattern = _endpoint_pattern(source_url=source_url, endpoint_url=event_url)
    publisher_host = urlsplit(source_url).netloc.casefold()
    required_markers = [_pointer_marker(pointer)]
    fingerprint = _candidate_fingerprint(
        publisher_host=publisher_host,
        endpoint_pattern=endpoint_pattern,
        json_pointer=pointer,
    )
    return BrowserRoutePrivateApiPromotionCandidate(
        schema_version="1.0",
        fingerprint=fingerprint,
        source_url=source_url,
        publisher_host=publisher_host,
        endpoint_pattern=endpoint_pattern,
        endpoint_url=event_url,
        method="GET",
        request_shape_summary=(
            "GET without cookies or auth headers; endpoint was replayed from "
            "browser network evidence and returned a JSON PDF URL."
        ),
        response_pdf_url_json_pointer=pointer,
        selected_pdf_url=pdf_url,
        expected_status_codes=[200],
        required_response_markers=[marker for marker in required_markers if marker],
        fallback_route_family=request.result.route_family,
        route_family=request.result.route_family,
        route_kind=request.result.route_kind,
        evidence_labels=[
            "browser_network_private_api",
            "auto_replayed_no_auth_get",
            "json_pdf_url_pointer",
        ],
    )


def _first_matching_pdf_pointer(
    *, response_text: str, base_url: str, artifact_url: str
) -> tuple[str, str]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return "", ""
    artifact_token = str(artifact_url or "").strip()
    artifact_basename = urlsplit(artifact_token).path.rsplit("/", 1)[-1].casefold()
    for pointer, value in _json_string_values(payload, ""):
        token = str(value or "").strip()
        if ".pdf" not in token.casefold():
            continue
        pdf_url = urljoin(base_url, token)
        pdf_basename = urlsplit(pdf_url).path.rsplit("/", 1)[-1].casefold()
        if pdf_url == artifact_token or (
            artifact_basename and pdf_basename == artifact_basename
        ):
            return pointer, pdf_url
    return "", ""


def _json_string_values(payload: object, pointer: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(payload, str):
        values.append((pointer or "", payload))
        return values
    if isinstance(payload, dict):
        for key, value in payload.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            values.extend(_json_string_values(value, f"{pointer}/{escaped}"))
        return values
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            values.extend(_json_string_values(value, f"{pointer}/{index}"))
    return values


def _endpoint_pattern(*, source_url: str, endpoint_url: str) -> str:
    source = urlsplit(source_url)
    endpoint = urlsplit(endpoint_url)
    rendered = endpoint.path or "/"
    if endpoint.query:
        rendered = f"{rendered}?{endpoint.query}"
    source_last_segment = next(
        (segment for segment in reversed(source.path.split("/")) if segment),
        "",
    )
    if source_last_segment:
        rendered = rendered.replace(source_last_segment, "{last_path_segment}")
        rendered = rendered.replace(
            quote(source_last_segment, safe=""),
            "{last_path_segment_encoded}",
        )
    return rendered


def _pointer_marker(pointer: str) -> str:
    token = str(pointer or "").strip()
    if not token.startswith("/"):
        return ""
    return token.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")


def _candidate_fingerprint(
    *, publisher_host: str, endpoint_pattern: str, json_pointer: str
) -> str:
    payload = json.dumps(
        {
            "publisher_host": publisher_host,
            "method": "GET",
            "endpoint_pattern": endpoint_pattern,
            "json_pointer": json_pointer,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _artifact_url(result) -> str:
    return (
        str(result.terminal_evidence.artifact_url or "").strip()
        or str(result.resolved_target_url or "").strip()
    )


def _same_host(first_url: str, second_url: str) -> bool:
    return (
        urlsplit(first_url).netloc.casefold() == urlsplit(second_url).netloc.casefold()
    )


def _empty_response(
    skipped_reason: str,
) -> BrowserRoutePrivateApiAutoPromotionDetectionResponse:
    return BrowserRoutePrivateApiAutoPromotionDetectionResponse(
        schema_version="1.0",
        candidate_count=0,
        candidates=[],
        skipped_reason=skipped_reason,
    )


def _log_detection_complete(
    *,
    ctx: RunContext,
    skipped_reason: str,
    candidates: list[BrowserRoutePrivateApiPromotionCandidate],
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_private_api_auto_promotion_detected",
            module=logger.name,
            fields={
                "candidate_count": len(candidates),
                "skipped_reason": skipped_reason,
                "candidate_fingerprints": [
                    candidate.fingerprint for candidate in candidates
                ],
            },
        )
    )
