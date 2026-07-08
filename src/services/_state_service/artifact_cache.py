from __future__ import annotations

from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateArtifactAcquisitionCacheGetRequest,
    StateArtifactAcquisitionCacheRecordRequest,
    StateArtifactAcquisitionCacheResponse,
)
from src.services._state_service.common import _state_conn, logger
from src.utils.logging import log_event


def get_artifact_acquisition_cache(
    request: StateArtifactAcquisitionCacheGetRequest,
    ctx: RunContext,
) -> Optional[StateArtifactAcquisitionCacheResponse]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_acquisition_cache_get_start",
            module=logger.name,
            fields={"state_db": request.state_db, "cache_key": request.cache_key},
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        cur = conn.execute(
            "SELECT cache_key, normalized_url, publisher_scope, report_title, "
            "final_artifact_url, artifact_path, artifact_md5, artifact_sha256, "
            "route_kind, route_family, outcome, downloaded_mime_type, size_bytes, "
            "cache_version, expires_at_utc, updated_at "
            "FROM artifact_acquisition_cache WHERE cache_key=?",
            (request.cache_key,),
        )
        row = cur.fetchone()
    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="artifact_acquisition_cache_get_complete",
                module=logger.name,
                fields={
                    "state_db": request.state_db,
                    "cache_key": request.cache_key,
                    "found": False,
                },
            )
        )
        return None
    response = _response_from_row(row)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_acquisition_cache_get_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "cache_key": response.cache_key,
                "found": True,
                "normalized_url": response.normalized_url,
                "route_kind": response.route_kind,
                "outcome": response.outcome,
            },
        )
    )
    return response


def record_artifact_acquisition_cache(
    request: StateArtifactAcquisitionCacheRecordRequest,
    ctx: RunContext,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_acquisition_cache_record_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "cache_key": request.cache_key,
                "normalized_url": request.normalized_url,
                "route_kind": request.route_kind,
                "outcome": request.outcome,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO artifact_acquisition_cache("
            "cache_key, normalized_url, publisher_scope, report_title, "
            "final_artifact_url, artifact_path, artifact_md5, artifact_sha256, "
            "route_kind, route_family, outcome, downloaded_mime_type, size_bytes, "
            "cache_version, expires_at_utc, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))",
            (
                request.cache_key,
                request.normalized_url,
                request.publisher_scope,
                request.report_title,
                request.final_artifact_url,
                request.artifact_path,
                request.artifact_md5,
                request.artifact_sha256,
                request.route_kind,
                request.route_family,
                request.outcome,
                request.downloaded_mime_type,
                int(request.size_bytes),
                request.cache_version,
                request.expires_at_utc,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="artifact_acquisition_cache_record_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "cache_key": request.cache_key,
                "normalized_url": request.normalized_url,
                "artifact_md5": request.artifact_md5,
                "artifact_sha256": request.artifact_sha256,
                "expires_at_utc": request.expires_at_utc,
            },
        )
    )


def _response_from_row(row: tuple) -> StateArtifactAcquisitionCacheResponse:
    (
        cache_key,
        normalized_url,
        publisher_scope,
        report_title,
        final_artifact_url,
        artifact_path,
        artifact_md5,
        artifact_sha256,
        route_kind,
        route_family,
        outcome,
        downloaded_mime_type,
        size_bytes,
        cache_version,
        expires_at_utc,
        updated_at,
    ) = row
    return StateArtifactAcquisitionCacheResponse(
        schema_version="1.0",
        cache_key=str(cache_key),
        normalized_url=str(normalized_url),
        publisher_scope=str(publisher_scope),
        report_title=str(report_title),
        final_artifact_url=str(final_artifact_url),
        artifact_path=str(artifact_path),
        artifact_md5=str(artifact_md5),
        artifact_sha256=str(artifact_sha256),
        route_kind=str(route_kind),
        route_family=str(route_family),
        outcome=str(outcome),
        downloaded_mime_type=str(downloaded_mime_type),
        size_bytes=int(size_bytes),
        cache_version=str(cache_version),
        expires_at_utc=str(expires_at_utc),
        updated_at=int(updated_at),
    )
