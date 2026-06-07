from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import logging
import time
import json
from pathlib import Path
from typing import Callable, List, Optional, TypedDict, cast
from urllib.parse import urlparse
from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
    CrossReportPublishResultSummary,
    CrossReportPublishStatus,
    PublicationMode,
    validate_cross_report_contract,
)
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.publish import (
    PublishEntityMetadata,
    PublishHtmlSnapshot,
    PublishOutcome,
    PublishRequest,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.report_store import (
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateGetRequest,
    StateGetResponse,
    StatePublishCheckRequest,
    StatePublishRecordRequest,
)
from src.contracts.validation import ValidationReport
from src.contracts.wordpress import (
    WordPressPostLookupBatchItem,
    WordPressPostLookupBatchRequest,
    WordPressPostLookupRequest,
    WordPressPostLookupResponse,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
    WordPressTaxonomyTerm,
    WordPressTagEnsureRequest,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
)
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.file_service import list_html, read_text
from src.services.report_store_service import list_metadata
from src.services.state_service import already_published as state_already_published
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.generators.publish_generator import publish_html
from src.orchestrators.publish_shared import canonicalize_html_path
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services import idempotency_service
from src.services.wordpress_service import (
    ensure_tags,
    ensure_taxonomy_terms,
    find_post_by_file_id,
    find_posts_by_file_id_batch,
)
from src.utils.html_utils import build_publish_html_snapshot
from src.utils.html_utils import ensure_publish_entity_metadata_html
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.slugify import slugify
from src.utils.validation import parse_validation_report_payload
from src.utils.wp_auth import build_auth_header

from src.orchestrators._publish_orchestrator.models import (
    _CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
    _CROSS_REPORT_WORDPRESS_POST_TYPES,
    _CrossReportResultFields,
    _CrossReportWordPressClassification,
    _PUBLISH_ENTITY_ROUTES,
    _PUBLISH_IDEMPOTENCY_SCOPE,
    _PUBLISH_ROUTES_BY_INTENT,
    _PublishCandidate,
    _PublishEntityRoute,
    _PublishPreflightEntry,
)

from src.orchestrators._publish_orchestrator.routing import (
    _metadata_index,
    _normalize_string_list,
    _normalize_tag_slugs,
    _publish_entity_error,
    _publish_settings_for_post_type,
    _require_publish_settings,
    _resolve_publish_candidates,
    _route_publish_entity_metadata,
    _sort_auto_discovered_html_paths,
)

from src.orchestrators._publish_orchestrator.preflight import (
    _batch_lookup_existing_posts,
    _build_publish_preflight_entries,
    _load_validation_report,
    _resolve_batch_term_assignments,
    _validation_paths,
    _with_validation,
)

from src.orchestrators._publish_orchestrator.idempotency import (
    _cross_report_publish_checksum,
    _cross_report_publish_idempotency_key,
    _lookup_cross_report_publish_idempotency,
    _lookup_publish_idempotency,
    _publish_checksum,
    _publish_idempotency_key,
    _record_cross_report_publish_idempotency,
    _record_publish_idempotency,
)

from src.orchestrators._publish_orchestrator.cross_report import (
    _briefing_url_is_in_section,
    _cross_report_post_type_for_target_route,
    _cross_report_publisher_labels,
    _cross_report_result_fields,
    _cross_report_result_from_outcome,
    _cross_report_settings_for_target_route,
    _cross_report_wordpress_classification,
    _publish_entity_metadata_for_route,
    _resolve_cross_report_terms,
    _signal_projection_package,
    _signal_url_is_in_section,
    _unique_terms_from_labels,
)

logger = logging.getLogger("market_lense.publish_orchestrator")


def publish_cross_report_package(
    package: CrossReportPublishPackage,
    settings: PublishSettings | None,
    ctx: RunContext,
    *,
    dry_run: bool = False,
    publish_html_fn: Callable[
        [PublishRequest, PublishSettings, RunContext], PublishOutcome
    ] = publish_html,
    find_post_by_file_id_fn: Callable[
        [WordPressPostLookupRequest, RunContext], WordPressPostLookupResponse
    ] = find_post_by_file_id,
    ensure_taxonomy_terms_fn: Callable[
        [WordPressTaxonomyEnsureRequest, RunContext], WordPressTaxonomyEnsureResponse
    ] = ensure_taxonomy_terms,
    ensure_tags_fn: Callable[
        [WordPressTagEnsureRequest, RunContext], WordPressTagEnsureResponse
    ] = ensure_tags,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrossReportPublishResultSummary:
    validate_cross_report_contract(package)
    publication_mode = "publish_dry_run" if dry_run else "publish_live"
    route_post_type = _cross_report_post_type_for_target_route(package.target_route)
    classification = _cross_report_wordpress_classification(package, route_post_type)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_publish_start",
            module=logger.name,
            fields={
                "package_id": package.package_id,
                "publication_mode": publication_mode,
                "target_route": package.target_route,
                "target_post_type": classification.post_type,
                "target_slug": classification.slug,
                "selected_theme_id": package.selected_theme_id,
                "selected_report_ids": package.selected_report_ids,
                "validation_sha256": package.validation_sha256,
            },
        )
    )
    if dry_run:
        result = CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_dry_run",
            status="dry_run",
            target_route=package.target_route,
            idempotency_reused=False,
            **_cross_report_result_fields(classification),
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_complete",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "status": result.status,
                    "dry_run": True,
                },
            )
        )
        return result

    route_settings = _cross_report_settings_for_target_route(
        _require_publish_settings(settings), package.target_route
    )
    checksum = _cross_report_publish_checksum(package, route_settings)
    reused = _lookup_cross_report_publish_idempotency(
        package=package,
        settings=route_settings,
        checksum=checksum,
        ctx=ctx,
    )
    if reused is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_idempotency_reused",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "target_route": package.target_route,
                    "status": reused.status,
                    "post_id": reused.post_id or 0,
                },
            )
        )
        return reused

    base_url = route_settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=route_settings.wp.username,
        app_password=route_settings.wp.app_password,
        bearer_token=route_settings.wp.bearer_token,
    )

    def _publish_attempt() -> CrossReportPublishResultSummary:
        lookup = find_post_by_file_id_fn(
            WordPressPostLookupRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                file_id=package.file_id,
                ssl_verify=route_settings.wp.ssl_verify,
                ca_bundle_path=route_settings.wp.ca_bundle_path,
                post_type=route_settings.wp.post_type,
            ),
            ctx,
        )
        if lookup.found and lookup.post_id and lookup.link:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="cross_report_publish_existing_post_checksum_mismatch",
                    module=logger.name,
                    fields={
                        "package_id": package.package_id,
                        "file_id": package.file_id,
                        "post_id": lookup.post_id,
                        "post_url": lookup.link,
                        "checksum": checksum,
                    },
                )
            )
            raise AppError(
                code="cross_report_publish_existing_post_checksum_mismatch",
                message=(
                    "WordPress already contains this cross-report file_id, but no "
                    "matching publish checksum was recorded for the current package."
                ),
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "file_id": package.file_id,
                    "post_id": lookup.post_id,
                    "post_url": lookup.link,
                    "checksum": checksum,
                },
            )
        resolved_terms = _resolve_cross_report_terms(
            classification=classification,
            settings=route_settings,
            base_url=base_url,
            auth_header=auth_header,
            ctx=ctx,
            ensure_taxonomy_terms_fn=ensure_taxonomy_terms_fn,
            ensure_tags_fn=ensure_tags_fn,
        )
        outcome = publish_html_fn(
            PublishRequest(
                schema_version="1.0",
                html_path=package.html_path,
                auth_header=auth_header,
                file_id=package.file_id,
                slug=classification.slug,
                html_snapshot=PublishHtmlSnapshot(
                    schema_version="1.0",
                    html_text=package.html_text,
                    file_id=package.file_id,
                    title=package.title,
                    body_html=package.body_html,
                    image_sources=[],
                    preview_image_src=None,
                    entity_metadata=_publish_entity_metadata_for_route(
                        source_artifact_id=package.file_id,
                        canonical_route_intent=package.target_route,
                    ),
                ),
                resolved_terms=resolved_terms,
            ),
            route_settings,
            ctx,
        )
        if (
            package.target_route == "wordpress:ml_briefing"
            and outcome.status == "published"
            and outcome.post_url
            and not _briefing_url_is_in_section(outcome.post_url)
        ):
            raise AppError(
                code="cross_report_briefing_url_mismatch",
                message="Published cross-report Briefing URL is outside /briefings/.",
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "post_id": outcome.post_id,
                    "post_url": outcome.post_url,
                    "target_route": package.target_route,
                    "target_post_type": classification.post_type,
                },
            )
        if (
            package.target_route == "wordpress:ml_signal"
            and outcome.status == "published"
            and outcome.post_url
            and not _signal_url_is_in_section(outcome.post_url)
        ):
            raise AppError(
                code="signal_publish_url_mismatch",
                message="Published Signal URL is outside /signals/.",
                retryable=False,
                severity="error",
                context={
                    "package_id": package.package_id,
                    "post_id": outcome.post_id,
                    "post_url": outcome.post_url,
                    "target_route": package.target_route,
                    "target_post_type": classification.post_type,
                },
            )
        return _cross_report_result_from_outcome(
            package=package,
            publication_mode="publish_live",
            outcome=outcome,
            idempotency_reused=False,
            classification=classification,
        )

    try:
        result = run_with_retry(
            step_name="publish_cross_report_package",
            operation=_publish_attempt,
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=RetryPolicy(
                retries=2,
                base_delay_seconds=1.0,
                backoff_step_seconds=1.0,
                jitter_seconds=0.25,
            ),
            retry_event="cross_report_publish_retry",
            retry_fields_builder=lambda exc, attempt: {
                "package_id": package.package_id,
                "attempt": attempt + 1,
                "code": exc.code if isinstance(exc, AppError) else "",
            },
            is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
            sleep_fn=sleep_fn,
        )
    except AppError as exc:
        result = CrossReportPublishResultSummary(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            publication_mode="publish_live",
            status="error",
            target_route=package.target_route,
            idempotency_reused=False,
            **_cross_report_result_fields(classification),
            error_code=exc.code,
            error_message=exc.message,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="cross_report_publish_error",
                module=logger.name,
                fields={
                    "package_id": package.package_id,
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "error": exc.message,
                },
            )
        )
        return result

    if result.status in {"published", "skipped"}:
        _record_cross_report_publish_idempotency(
            package=package,
            settings=route_settings,
            result=result,
            checksum=checksum,
            ctx=ctx,
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cross_report_publish_complete",
            module=logger.name,
            fields={
                "package_id": package.package_id,
                "status": result.status,
                "post_id": result.post_id or 0,
                "post_url": result.post_url or "",
            },
        )
    )
    return result


def publish_signal_projection(
    projection: SignalPublishProjection,
    settings: PublishSettings,
    ctx: RunContext,
    *,
    dry_run: bool = False,
    publish_html_fn: Callable[
        [PublishRequest, PublishSettings, RunContext], PublishOutcome
    ] = publish_html,
    find_post_by_file_id_fn: Callable[
        [WordPressPostLookupRequest, RunContext], WordPressPostLookupResponse
    ] = find_post_by_file_id,
    ensure_taxonomy_terms_fn: Callable[
        [WordPressTaxonomyEnsureRequest, RunContext], WordPressTaxonomyEnsureResponse
    ] = ensure_taxonomy_terms,
    ensure_tags_fn: Callable[
        [WordPressTagEnsureRequest, RunContext], WordPressTagEnsureResponse
    ] = ensure_tags,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrossReportPublishResultSummary:
    if projection.validation_status != "approved":
        raise AppError(
            code="signal_publish_validation_status_invalid",
            message="Only approved Signal projections can be published.",
            retryable=False,
            severity="error",
            context={
                "slug": projection.slug,
                "validation_status": projection.validation_status,
            },
        )
    return publish_cross_report_package(
        _signal_projection_package(projection),
        settings,
        ctx,
        dry_run=dry_run,
        publish_html_fn=publish_html_fn,
        find_post_by_file_id_fn=find_post_by_file_id_fn,
        ensure_taxonomy_terms_fn=ensure_taxonomy_terms_fn,
        ensure_tags_fn=ensure_tags_fn,
        sleep_fn=sleep_fn,
    )


def run_publish(
    settings: PublishSettings,
    *,
    limit: Optional[int] = None,
    html_paths: Optional[List[str]] = None,
    ctx: Optional[RunContext] = None,
) -> List[PublishOutcome]:
    root_ctx = ctx or new_run_context()
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_start",
            module=logger.name,
            fields={
                "limit": limit,
                "explicit_html_paths": len(html_paths) if html_paths is not None else 0,
            },
        )
    )

    auto_discovery = html_paths is None
    if auto_discovery:
        list_resp = list_html(
            ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir),
            root_ctx,
        )
        discovered_html_paths = list_resp.html_paths
    else:
        discovered_html_paths = [str(path) for path in html_paths]  # type: ignore[union-attr]
    outcomes: List[PublishOutcome] = []
    attempted = 0
    published = 0
    base_url = settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_auth_source",
            module=logger.name,
            fields={
                "source": "bearer_token" if settings.wp.bearer_token else "app_password"
            },
        )
    )
    html_file_id_map: dict[str, str] = {}
    metadata_by_file_id: dict[str, ReportMetadataGetResponse] = {}
    mapping_ctx = child_context(root_ctx, task_id="publish_preflight_metadata")
    try:
        html_file_id_map, metadata_by_file_id = _metadata_index(settings, mapping_ctx)
    except Exception as exc:
        logger.info(
            log_event(
                mapping_ctx,
                role="orchestrator",
                event="publish_preflight_metadata_failed",
                module=logger.name,
                fields={"reports_db": settings.reports_db, "error": str(exc)},
            )
        )
        html_file_id_map = {}
        metadata_by_file_id = {}

    if auto_discovery:
        selected_html_paths = _sort_auto_discovered_html_paths(
            discovered_html_paths,
            html_file_id_map=html_file_id_map,
            metadata_by_file_id=metadata_by_file_id,
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="publish_auto_discovery_ordered",
                module=logger.name,
                fields={
                    "count": len(selected_html_paths),
                    "metadata_matched": sum(
                        1
                        for html_path in selected_html_paths
                        if html_file_id_map.get(canonicalize_html_path(html_path), "")
                        in metadata_by_file_id
                    ),
                },
            )
        )
    else:
        max_n = limit if limit is not None else len(discovered_html_paths)
        selected_html_paths = discovered_html_paths[:max_n]

    candidates = _resolve_publish_candidates(
        html_paths=selected_html_paths,
        html_file_id_map=html_file_id_map,
        ctx=root_ctx,
        skip_unowned_nonpublish_html=auto_discovery,
    )
    if auto_discovery and limit is not None:
        candidates = candidates[:limit]
    preflight_entries = _build_publish_preflight_entries(
        settings=settings,
        candidates=candidates,
        metadata_by_file_id=metadata_by_file_id,
        base_url=base_url,
        auth_header=auth_header,
        ctx=root_ctx,
    )

    for entry in preflight_entries:
        attempted += 1
        html_path = entry.candidate.html_path

        file_ctx = child_context(root_ctx, task_id=html_path)
        html_snapshot = entry.candidate.html_snapshot
        file_id = str(entry.candidate.file_id or "")
        entity_route = entry.candidate.entity_route
        state_row = entry.state_row
        validation_status = entry.validation_status
        validation_issues = list(entry.validation_issues)
        existing_post_lookup = entry.existing_post_lookup
        resolved_terms = entry.resolved_terms

        if entry.candidate.entity_error is not None:
            entity_error = entry.candidate.entity_error
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id or None,
                    status="error",
                    error=entity_error.code,
                )
            )
            continue
        if entity_route is None:
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id or None,
                    status="error",
                    error="publish_entity_metadata_missing",
                )
            )
            continue

        if existing_post_lookup and existing_post_lookup.error_code:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_preflight_lookup_fallback",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "code": existing_post_lookup.error_code,
                        "retryable": existing_post_lookup.retryable,
                    },
                )
            )

        if not file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_missing_file_id",
                    module=logger.name,
                    fields={"html_path": html_path},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=None,
                    status="error",
                    error="missing_file_id",
                )
            )
            continue
        if not state_row:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_not_processed",
                    module=logger.name,
                    fields={"file_id": file_id},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="not_processed",
                )
            )
            continue
        if html_snapshot is None:
            html_text = read_text(
                ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
            ).content
            html_snapshot = build_publish_html_snapshot(html_text)
        publish_checksum = _publish_checksum(
            file_id=file_id,
            html_path=html_path,
            html_text=html_snapshot.html_text,
            post_type=entity_route.post_type,
            validation_status=validation_status,
            validation_issues=validation_issues,
        )
        reused_outcome = _lookup_publish_idempotency(
            settings=settings,
            file_id=file_id,
            post_type=entity_route.post_type,
            checksum=publish_checksum,
            ctx=file_ctx,
        )
        if reused_outcome is not None:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_idempotency_reused",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "post_type": entity_route.post_type,
                        "status": reused_outcome.status,
                        "post_id": reused_outcome.post_id,
                    },
                )
            )
            outcomes.append(reused_outcome)
            if reused_outcome.status == "published":
                published += 1
            continue
        if state_already_published(
            StatePublishCheckRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
                post_type=entity_route.post_type,
            ),
            file_ctx,
        ):
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_already_published",
                    module=logger.name,
                    fields={"file_id": file_id},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    error="already_published",
                )
            )
            continue
        if settings.validation_policy == "block" and validation_status != "pass":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_validation_blocked",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "validation_status": validation_status,
                        "issues": validation_issues,
                    },
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="validation_failed",
                    validation_status=validation_status,
                    validation_issues=validation_issues,
                )
            )
            continue
        if validation_status != "pass":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_validation_warning",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "validation_status": validation_status,
                        "issues": validation_issues,
                        "policy": settings.validation_policy,
                    },
                )
            )

        outcome: Optional[PublishOutcome] = None

        def _publish_attempt() -> PublishOutcome:
            nonlocal outcome
            lookup_resp: WordPressPostLookupBatchItem | WordPressPostLookupResponse
            route_settings = _publish_settings_for_post_type(
                settings,
                entity_route.post_type,
            )
            if existing_post_lookup is not None and not existing_post_lookup.error_code:
                lookup_resp = existing_post_lookup
            else:
                lookup_resp = find_post_by_file_id(
                    WordPressPostLookupRequest(
                        schema_version="1.0",
                        base_url=base_url,
                        auth_header=auth_header,
                        file_id=file_id,
                        ssl_verify=settings.wp.ssl_verify,
                        ca_bundle_path=settings.wp.ca_bundle_path,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
            if lookup_resp.found and lookup_resp.post_id and lookup_resp.link:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_existing_post",
                        module=logger.name,
                        fields={"file_id": file_id, "post_id": lookup_resp.post_id},
                    )
                )
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=lookup_resp.post_id,
                        wp_post_url=lookup_resp.link,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
                outcome = PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    post_id=lookup_resp.post_id,
                    post_url=lookup_resp.link,
                    error="already_exists",
                )
                return _with_validation(outcome, validation_status, validation_issues)

            outcome = publish_html(
                PublishRequest(
                    schema_version="1.0",
                    html_path=html_path,
                    auth_header=auth_header,
                    file_id=file_id,
                    html_snapshot=html_snapshot,
                    resolved_terms=resolved_terms,
                ),
                route_settings,
                file_ctx,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
            if outcome.status == "published" and outcome.post_id and outcome.post_url:
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=outcome.post_id,
                        wp_post_url=outcome.post_url,
                        post_type=entity_route.post_type,
                    ),
                    file_ctx,
                )
            if outcome.status in {"published", "skipped"}:
                _record_publish_idempotency(
                    settings=settings,
                    outcome=outcome,
                    post_type=entity_route.post_type,
                    checksum=publish_checksum,
                    ctx=file_ctx,
                )
            return outcome

        try:
            outcome = run_with_retry(
                step_name="publish_html",
                operation=_publish_attempt,
                ctx=file_ctx,
                logger=logger,
                module_name=logger.name,
                policy=RetryPolicy(
                    retries=2,
                    base_delay_seconds=1.0,
                    backoff_step_seconds=1.0,
                    jitter_seconds=0.25,
                ),
                retry_event="publish_retry",
                retry_fields_builder=lambda exc, attempt: {
                    "file_id": file_id,
                    "attempt": attempt + 1,
                    "code": exc.code if isinstance(exc, AppError) else "",
                },
                is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
                sleep_fn=time.sleep,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": exc.message, "code": exc.code},
                )
            )
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=exc.message,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
        except Exception as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": str(exc)},
                )
            )
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=str(exc),
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)

        if outcome is not None:
            outcomes.append(outcome)
            if outcome.status == "published":
                published += 1
            continue
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="publish_error",
                module=logger.name,
                fields={"file_id": file_id, "error": "publish_failed"},
            )
        )
        outcomes.append(
            PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error="publish_failed",
                validation_status=validation_status,
                validation_issues=validation_issues,
            )
        )

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_complete",
            module=logger.name,
            fields={"attempted": attempted, "published": published},
        )
    )
    return outcomes
