from __future__ import annotations

"""Routing helpers for publication orchestration."""

import copy
import hashlib
import json
import logging
from dataclasses import replace

from src.contracts.files import ReadBytesRequest, ReadTextRequest
from src.contracts.publish import (
    PublishEntityMetadata,
    PublishSettings,
)
from src.contracts.report_store import (
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators._publish_orchestrator.models import (
    _PUBLISH_ENTITY_ROUTES,
    _PUBLISH_ROUTES_BY_INTENT,
    _PublishCandidate,
    _PublishEntityRoute,
)
from src.orchestrators.publish_shared import canonicalize_html_path
from src.services.file_service import read_bytes, read_text
from src.services.report_store_service import list_metadata
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from src.utils.logging import child_context, log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_orchestrator")


def report_publish_package_checksum(
    *, html_path: str, readiness_reference: str, ctx: RunContext
) -> str:
    """Hash the exact immutable Report surfaces approved for queue publication."""

    html = read_bytes(ReadBytesRequest(schema_version="1.0", path=html_path), ctx)
    readiness = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=readiness_reference), ctx
    )
    payload = {
        "schema_version": "1.0",
        "entity_type": "report",
        "html_sha256": hashlib.sha256(html.content).hexdigest(),
        "readiness_sha256": hashlib.sha256(readiness.content).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _metadata_index(
    settings: PublishSettings, ctx: RunContext
) -> tuple[dict[str, str], dict[str, ReportMetadataGetResponse]]:
    response = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=settings.reports_db),
        ctx,
    )
    html_file_id_map: dict[str, str] = {}
    metadata_by_file_id: dict[str, ReportMetadataGetResponse] = {}
    records = sorted(
        response.records,
        key=lambda row: int(getattr(row, "updated_at", 0) or 0),
        reverse=True,
    )
    for row in records:
        file_id = str(row.file_id or "").strip()
        html_path = str(row.html_path or "").strip()
        if file_id and file_id not in metadata_by_file_id:
            metadata_by_file_id[file_id] = row
        if html_path and file_id:
            key = canonicalize_html_path(html_path)
            if key not in html_file_id_map:
                html_file_id_map[key] = file_id
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publish_preflight_metadata_loaded",
            module=logger.name,
            fields={
                "records": len(response.records),
                "mapped_html_paths": len(html_file_id_map),
                "mapped_file_ids": len(metadata_by_file_id),
            },
        )
    )
    return html_file_id_map, metadata_by_file_id


def _sort_auto_discovered_html_paths(
    html_paths: list[str],
    *,
    html_file_id_map: dict[str, str],
    metadata_by_file_id: dict[str, ReportMetadataGetResponse],
) -> list[str]:
    indexed_paths: list[tuple[int, int, int, str]] = []
    for index, html_path in enumerate(html_paths):
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
        metadata = metadata_by_file_id.get(file_id)
        updated_at = int(getattr(metadata, "updated_at", 0) or 0) if metadata else 0
        indexed_paths.append(
            (0 if updated_at > 0 else 1, -updated_at, index, html_path)
        )
    return [html_path for _, _, _, html_path in sorted(indexed_paths)]


def _publish_settings_for_post_type(
    settings: PublishSettings,
    post_type: str,
) -> PublishSettings:
    if post_type == settings.wp.post_type:
        return settings

    try:
        route_wp_settings = replace(settings.wp, post_type=post_type)
    except TypeError:
        route_wp_settings = copy.copy(settings.wp)
        object.__setattr__(route_wp_settings, "post_type", post_type)

    try:
        return replace(settings, wp=route_wp_settings)
    except TypeError:
        route_settings = copy.copy(settings)
        object.__setattr__(route_settings, "wp", route_wp_settings)
        return route_settings


def _require_publish_settings(settings: PublishSettings | None) -> PublishSettings:
    if settings is None:
        raise AppError(
            code="cross_report_publish_settings_missing",
            message="Cross-report live publishing requires WordPress publish settings.",
            retryable=False,
            severity="error",
            context={},
        )
    return settings


def _publish_entity_error(
    *,
    code: str,
    message: str,
    html_path: str,
    metadata: PublishEntityMetadata | None,
    context: dict[str, object] | None = None,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        retryable=False,
        severity="error",
        context={
            "html_path": html_path,
            "entity_type": metadata.entity_type if metadata else "",
            "canonical_route_intent": metadata.canonical_route_intent
            if metadata
            else "",
            **dict(context or {}),
        },
    )


def _route_publish_entity_metadata(
    *,
    metadata: PublishEntityMetadata | None,
    html_path: str,
) -> _PublishEntityRoute:
    if metadata is None:
        raise _publish_entity_error(
            code="publish_entity_metadata_missing",
            message="Generated HTML artifact is missing public entity metadata.",
            html_path=html_path,
            metadata=None,
        )
    if metadata.schema_version != "1.0":
        raise _publish_entity_error(
            code="publish_entity_metadata_schema_unsupported",
            message="Generated HTML artifact has unsupported entity metadata schema.",
            html_path=html_path,
            metadata=metadata,
            context={"schema_version": metadata.schema_version},
        )
    if not metadata.publish_eligible:
        raise _publish_entity_error(
            code="publish_entity_not_eligible",
            message="Generated HTML artifact is not eligible for publication.",
            html_path=html_path,
            metadata=metadata,
        )
    route_by_entity = _PUBLISH_ENTITY_ROUTES.get(metadata.entity_type)
    route_by_intent = _PUBLISH_ROUTES_BY_INTENT.get(metadata.canonical_route_intent)
    if route_by_entity is None or route_by_intent is None:
        raise _publish_entity_error(
            code="publish_entity_metadata_unsupported",
            message="Generated HTML artifact declares an unsupported public entity route.",
            html_path=html_path,
            metadata=metadata,
        )
    if route_by_entity != route_by_intent:
        raise _publish_entity_error(
            code="publish_entity_metadata_mismatch",
            message="Generated HTML artifact entity type and route intent do not match.",
            html_path=html_path,
            metadata=metadata,
            context={
                "expected_route_intent": route_by_entity.canonical_route_intent,
                "expected_post_type": route_by_entity.post_type,
            },
        )
    return route_by_entity


def _resolve_publish_candidates(
    *,
    html_paths: list[str],
    html_file_id_map: dict[str, str],
    ctx: RunContext,
    skip_unowned_nonpublish_html: bool = False,
) -> list[_PublishCandidate]:
    candidates: list[_PublishCandidate] = []
    for html_path in html_paths:
        file_ctx = child_context(ctx, task_id=html_path)
        html_text = read_text(
            ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
        ).content
        html_snapshot = build_publish_html_snapshot(html_text)
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
        file_id_source = "reports_db" if file_id else ""
        if not file_id:
            file_id = str(
                html_snapshot.file_id
                or (
                    html_snapshot.entity_metadata.source_artifact_id
                    if html_snapshot.entity_metadata
                    else ""
                )
            ).strip()
            if file_id:
                file_id_source = "html" if html_snapshot.file_id else "entity_metadata"
        entity_route: _PublishEntityRoute | None = None
        entity_error: AppError | None = None
        try:
            if (
                html_snapshot.entity_metadata is None
                and file_id
                and file_id_source == "reports_db"
            ):
                # Report HTML intentionally contains no internal source ID or
                # hidden publication marker. The report-store mapping is the
                # authoritative private routing seam.
                entity_route = _PUBLISH_ENTITY_ROUTES["report"]
            else:
                entity_route = _route_publish_entity_metadata(
                    metadata=html_snapshot.entity_metadata,
                    html_path=html_path,
                )
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_entity_metadata_routed",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "entity_type": entity_route.entity_type,
                        "canonical_route_intent": entity_route.canonical_route_intent,
                        "post_type": entity_route.post_type,
                        "front_end_section": entity_route.front_end_section,
                        "template": entity_route.template,
                    },
                )
            )
        except AppError as exc:
            if (
                skip_unowned_nonpublish_html
                and exc.code == "publish_entity_metadata_missing"
                and not file_id
            ):
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_non_entity_html_skipped",
                        module=logger.name,
                        fields={
                            "html_path": html_path,
                            "code": exc.code,
                            "reason": "missing_publish_metadata_and_source_artifact",
                        },
                    )
                )
                continue
            entity_error = exc
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_entity_metadata_invalid",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "code": exc.code,
                        "error": exc.message,
                        **exc.context,
                    },
                )
            )
        if file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_file_id_resolved",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "file_id": file_id,
                        "source": file_id_source,
                    },
                )
            )
        candidates.append(
            _PublishCandidate(
                html_path=html_path,
                file_id=file_id or None,
                html_snapshot=html_snapshot,
                entity_route=entity_route,
                entity_error=entity_error,
            )
        )
    return candidates


def _normalize_string_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_tag_slugs(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        slug = slugify(raw_value)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    return normalized
