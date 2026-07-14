"""WordPress REST boundary for pipeline-owned intelligence projections."""

from __future__ import annotations

# ruff: noqa: E501
import json
import logging
from dataclasses import asdict
from typing import Any, Literal, cast

from src.contracts.run_context import RunContext
from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressIntelligenceEntity,
    WordPressIntelligenceProjectionWriteRequest,
    WordPressIntelligenceProjectionWriteResponse,
    WordPressIntelligenceSourceReadRequest,
    WordPressIntelligenceSourceReadResponse,
    WordPressIntelligenceTerm,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .transport import _execute_request, _http_error_context, _safe_json

logger = logging.getLogger("market_lense.wordpress_service")
_ENTITY_TYPES = {"ml_report", "ml_briefing", "ml_signal"}


def _source_term(value: Any) -> WordPressIntelligenceTerm:
    if not isinstance(value, dict) or not str(value.get("name") or "").strip():
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source contains an invalid term",
            retryable=False,
            severity="error",
        )
    return WordPressIntelligenceTerm(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        name=str(value["name"]).strip(),
        url=str(value.get("url") or "").strip(),
        homepage=str(value.get("homepage") or "").strip(),
    )


def _source_entity(value: Any) -> WordPressIntelligenceEntity:
    if not isinstance(value, dict):
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source contains an invalid entity",
            retryable=False,
            severity="error",
        )
    entity_type = str(value.get("entity_type") or "").strip()
    entity_id = str(value.get("entity_id") or "").strip()
    published_at_utc = str(value.get("published_at_utc") or "").strip()
    if entity_type not in _ENTITY_TYPES or not entity_id or not published_at_utc:
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source is missing required entity fields",
            retryable=False,
            severity="error",
            context={"entity_type": entity_type, "has_entity_id": bool(entity_id)},
        )
    publishers = value.get("publishers")
    topics = value.get("topics")
    if not isinstance(publishers, list) or not isinstance(topics, list):
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source taxonomy fields must be lists",
            retryable=False,
            severity="error",
        )
    return WordPressIntelligenceEntity(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entity_id=entity_id,
        entity_type=cast(
            Literal["ml_report", "ml_briefing", "ml_signal"],
            entity_type,
        ),
        published_at_utc=published_at_utc,
        url=str(value.get("url") or "").strip(),
        publishers=[_source_term(term) for term in publishers],
        topics=[_source_term(term) for term in topics],
    )


def read_published_intelligence_source(
    request: WordPressIntelligenceSourceReadRequest, ctx: RunContext
) -> WordPressIntelligenceSourceReadResponse:
    """Reads raw published entities. It never requests a WordPress-side aggregate."""
    url = f"{request.base_url.rstrip('/')}/wp-json/marketlense/v1/intelligence-source"
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_intelligence_source_read_start",
            module=logger.name,
            fields={"url": url, "ssl_verify": request.ssl_verify},
        )
    )
    result = _execute_request(
        method="GET",
        url=url,
        headers={"Authorization": request.auth_header},
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wordpress_intelligence_source_read_error",
        request_error_code="wordpress_intelligence_source_read_failed",
        request_error_message="Failed to read WordPress intelligence source",
    )
    response = result.response
    if int(getattr(response, "status_code", 0) or 0) >= 400:
        raise AppError(
            code="wordpress_intelligence_source_read_failed",
            message="WordPress intelligence source returned an HTTP error",
            retryable=int(getattr(response, "status_code", 0) or 0) >= 500,
            severity="error",
            context={
                "status_code": int(getattr(response, "status_code", 0) or 0),
                **_http_error_context(response),
            },
        )
    payload = _safe_json(response)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != WORDPRESS_INTELLIGENCE_SCHEMA_VERSION
    ):
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source returned an invalid schema",
            retryable=False,
            severity="error",
        )
    raw_entities = payload.get("entities")
    if not isinstance(raw_entities, list):
        raise AppError(
            code="wordpress_intelligence_source_invalid",
            message="WordPress intelligence source did not return an entity list",
            retryable=False,
            severity="error",
        )
    output = WordPressIntelligenceSourceReadResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entities=[_source_entity(item) for item in raw_entities],
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_intelligence_source_read_complete",
            module=logger.name,
            fields={"entity_count": len(output.entities)},
        )
    )
    return output


def write_wordpress_intelligence_projection(
    request: WordPressIntelligenceProjectionWriteRequest, ctx: RunContext
) -> WordPressIntelligenceProjectionWriteResponse:
    """Writes one already-approved projection through the protected plugin endpoint."""
    url = (
        f"{request.base_url.rstrip('/')}/wp-json/marketlense/v1/intelligence-projection"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_intelligence_projection_write_start",
            module=logger.name,
            fields={
                "url": url,
                "projection_version": request.projection.projection_version,
            },
        )
    )
    result = _execute_request(
        method="POST",
        url=url,
        headers={
            "Authorization": request.auth_header,
            "Content-Type": "application/json",
        },
        data=json.dumps({"projection": asdict(request.projection)}),
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wordpress_intelligence_projection_write_error",
        request_error_code="wordpress_intelligence_projection_write_failed",
        request_error_message="Failed to write WordPress intelligence projection",
    )
    response = result.response
    if int(getattr(response, "status_code", 0) or 0) >= 400:
        raise AppError(
            code="wordpress_intelligence_projection_write_failed",
            message="WordPress intelligence projection write returned an HTTP error",
            retryable=int(getattr(response, "status_code", 0) or 0) >= 500,
            severity="error",
            context={
                "status_code": int(getattr(response, "status_code", 0) or 0),
                **_http_error_context(response),
            },
        )
    payload = _safe_json(response)
    if not isinstance(payload, dict) or payload.get("status") != "stored":
        raise AppError(
            code="wordpress_intelligence_projection_write_invalid",
            message="WordPress intelligence projection write returned an invalid response",
            retryable=False,
            severity="error",
        )
    output = WordPressIntelligenceProjectionWriteResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        projection_version=str(payload.get("projection_version") or ""),
        generated_at_utc=str(payload.get("generated_at_utc") or ""),
        status="stored",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_intelligence_projection_write_complete",
            module=logger.name,
            fields={
                "projection_version": output.projection_version,
                "generated_at_utc": output.generated_at_utc,
            },
        )
    )
    return output
