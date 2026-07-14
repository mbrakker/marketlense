"""Coordinates source reading, pure aggregation, and WordPress projection persistence."""

from __future__ import annotations

# ruff: noqa: E501
import logging
from dataclasses import dataclass, field
from typing import Callable

from src.contracts.run_context import RunContext
from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressIntelligenceBuildRequest,
    WordPressIntelligenceProjection,
    WordPressIntelligenceProjectionWriteRequest,
    WordPressIntelligenceProjectionWriteResponse,
    WordPressIntelligenceSourceReadRequest,
    WordPressIntelligenceSourceReadResponse,
    WordPressIntelligenceSyncRequest,
    WordPressIntelligenceSyncResponse,
)
from src.generators.wordpress_intelligence_projection_generator import (
    build_wordpress_intelligence_projection,
)
from src.services.wordpress_service import (
    read_published_intelligence_source,
    write_wordpress_intelligence_projection,
)
from src.utils.logging import child_context, log_event

logger = logging.getLogger(
    "market_lense.wordpress_intelligence_projection_orchestrator"
)


@dataclass(frozen=True)
class WordPressIntelligenceProjectionDependencies:
    """External boundaries used by the projection control plane."""

    read_source: Callable[
        [WordPressIntelligenceSourceReadRequest, RunContext],
        WordPressIntelligenceSourceReadResponse,
    ] = field(metadata={"doc": "WordPress source service boundary."})
    build_projection: Callable[
        [WordPressIntelligenceBuildRequest], WordPressIntelligenceProjection
    ] = field(metadata={"doc": "Pure projection generator boundary."})
    write_projection: Callable[
        [WordPressIntelligenceProjectionWriteRequest, RunContext],
        WordPressIntelligenceProjectionWriteResponse,
    ] = field(metadata={"doc": "WordPress projection persistence boundary."})

    @classmethod
    def default(cls) -> "WordPressIntelligenceProjectionDependencies":
        return cls(
            read_source=read_published_intelligence_source,
            build_projection=build_wordpress_intelligence_projection,
            write_projection=write_wordpress_intelligence_projection,
        )


def sync_wordpress_intelligence_projection(
    request: WordPressIntelligenceSyncRequest,
    ctx: RunContext,
    *,
    dependencies: WordPressIntelligenceProjectionDependencies | None = None,
) -> WordPressIntelligenceSyncResponse:
    """Persists one fully specified projection after the source is read successfully."""
    deps = dependencies or WordPressIntelligenceProjectionDependencies.default()
    projection_ctx = child_context(
        ctx, task_id=f"{ctx.task_id}:wordpress_intelligence_projection"
    )
    logger.info(
        log_event(
            projection_ctx,
            role="orchestrator",
            event="wordpress_intelligence_projection_sync_start",
            module=logger.name,
            fields={"site_url": request.source_request.base_url},
        )
    )
    source = deps.read_source(request.source_request, projection_ctx)
    projection = deps.build_projection(
        WordPressIntelligenceBuildRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            source=source,
            generated_at_utc=request.generated_at_utc,
        )
    )
    write_response = deps.write_projection(
        WordPressIntelligenceProjectionWriteRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            base_url=request.source_request.base_url,
            auth_header=request.source_request.auth_header,
            projection=projection,
            ssl_verify=request.source_request.ssl_verify,
            ca_bundle_path=request.source_request.ca_bundle_path,
        ),
        projection_ctx,
    )
    response = WordPressIntelligenceSyncResponse(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        entity_count=len(source.entities),
        projection=projection,
        write_response=write_response,
    )
    logger.info(
        log_event(
            projection_ctx,
            role="orchestrator",
            event="wordpress_intelligence_projection_sync_complete",
            module=logger.name,
            fields={
                "entity_count": response.entity_count,
                "generated_at_utc": projection.generated_at_utc,
            },
        )
    )
    return response
