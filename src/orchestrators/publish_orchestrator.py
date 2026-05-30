from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import logging
import time
import json
from pathlib import Path
from typing import Callable, List, Optional, cast
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
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.slugify import slugify
from src.utils.validation import parse_validation_report_payload
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_orchestrator")
_PUBLISH_IDEMPOTENCY_SCOPE = "publish_orchestrator.publish_html"
_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE = "publish_orchestrator.cross_report_package"
_CROSS_REPORT_WORDPRESS_POST_TYPES = {
    "wordpress:ml_report": "ml_report",
    "wordpress:ml_briefing": "ml_briefing",
    "wordpress:ml_signal": "ml_signal",
}


@dataclass(frozen=True)
class _PublishCandidate:
    html_path: str
    file_id: Optional[str]
    html_snapshot: Optional[PublishHtmlSnapshot]


@dataclass(frozen=True)
class _PublishPreflightEntry:
    candidate: _PublishCandidate
    state_row: StateGetResponse | None
    validation_status: str
    validation_issues: List[str] = field(default_factory=list)
    existing_post_lookup: WordPressPostLookupBatchItem | None = None
    resolved_terms: PublishResolvedTerms | None = None


@dataclass(frozen=True)
class _CrossReportWordPressClassification:
    post_type: str
    slug: str
    category_terms: list[WordPressTaxonomyTerm]
    tag_slugs: list[str]
    taxonomy_terms: dict[str, list[WordPressTaxonomyTerm]]


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


def _resolve_publish_candidates(
    *,
    html_paths: list[str],
    html_file_id_map: dict[str, str],
    ctx: RunContext,
) -> list[_PublishCandidate]:
    candidates: list[_PublishCandidate] = []
    for html_path in html_paths:
        file_ctx = child_context(ctx, task_id=html_path)
        html_snapshot: Optional[PublishHtmlSnapshot] = None
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
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
                        "source": "reports_db",
                    },
                )
            )
        else:
            html_text = read_text(
                ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
            ).content
            html_snapshot = build_publish_html_snapshot(html_text)
            file_id = str(html_snapshot.file_id or "").strip()
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
                            "source": "html",
                        },
                    )
                )
        candidates.append(
            _PublishCandidate(
                html_path=html_path,
                file_id=file_id or None,
                html_snapshot=html_snapshot,
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


def _batch_lookup_existing_posts(
    *,
    settings: PublishSettings,
    base_url: str,
    auth_header: str,
    candidates: list[_PublishCandidate],
    state_rows_by_file_id: dict[str, StateGetResponse],
    ctx: RunContext,
) -> dict[str, WordPressPostLookupBatchItem]:
    eligible_file_ids = [
        candidate.file_id
        for candidate in candidates
        if candidate.file_id and candidate.file_id in state_rows_by_file_id
    ]
    if not eligible_file_ids:
        return {}
    response = find_posts_by_file_id_batch(
        WordPressPostLookupBatchRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            file_ids=eligible_file_ids,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            post_type=settings.wp.post_type,
        ),
        ctx,
    )
    return {
        item.file_id: item for item in response.items if str(item.file_id or "").strip()
    }


def _resolve_batch_term_assignments(
    *,
    settings: PublishSettings,
    metadata_by_file_id: dict[str, ReportMetadataGetResponse],
    selected_file_ids: list[str],
    base_url: str,
    auth_header: str,
    ctx: RunContext,
) -> dict[str, PublishResolvedTerms]:
    selected_metadata = {
        file_id: metadata_by_file_id[file_id]
        for file_id in selected_file_ids
        if file_id in metadata_by_file_id
    }
    if not selected_metadata:
        return {}

    needs_category_labels = any(
        _normalize_string_list(record.categories)
        for record in selected_metadata.values()
    )
    category_labels: dict[str, str] = {}
    if needs_category_labels:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
                reload_if_changed=True,
            ),
            ctx,
        )
        category_labels = {
            category.id: category.label or category.id
            for category in mappings_resp.mappings.categories
        }

    category_cache: dict[tuple[str, ...], list[int]] = {}
    tag_cache: dict[tuple[str, ...], list[int]] = {}
    publisher_cache: dict[str, list[int]] = {}
    resolved_terms_by_file_id: dict[str, PublishResolvedTerms] = {}

    for file_id, record in selected_metadata.items():
        file_ctx = child_context(ctx, task_id=file_id)
        categories = _normalize_string_list(record.categories)
        category_ids: list[int] = []
        if categories:
            category_key = tuple(categories)
            if category_key not in category_cache:
                terms = [
                    WordPressTaxonomyTerm(
                        schema_version="1.0",
                        slug=category_id,
                        name=category_labels.get(category_id, category_id),
                    )
                    for category_id in categories
                ]
                try:
                    response = ensure_taxonomy_terms(
                        WordPressTaxonomyEnsureRequest(
                            schema_version="1.0",
                            base_url=base_url,
                            auth_header=auth_header,
                            taxonomy_rest_base="categories",
                            terms=terms,
                            ssl_verify=settings.wp.ssl_verify,
                            ca_bundle_path=settings.wp.ca_bundle_path,
                        ),
                        file_ctx,
                    )
                    category_cache[category_key] = [
                        response.slug_to_id[category_id]
                        for category_id in categories
                        if category_id in response.slug_to_id
                    ]
                except AppError as exc:
                    logger.info(
                        log_event(
                            file_ctx,
                            role="orchestrator",
                            event="publish_preflight_category_resolution_failed",
                            module=logger.name,
                            fields={
                                "file_id": file_id,
                                "categories": categories,
                                "code": exc.code,
                                "error": exc.message,
                            },
                        )
                    )
                    continue
            category_ids = list(category_cache.get(category_key, []))

        publisher_taxonomy_terms: dict[str, list[int]] = {}
        publisher_name = str(record.publisher or "").strip()
        if publisher_name:
            publisher_slug = slugify(publisher_name)
            if publisher_slug:
                if publisher_slug not in publisher_cache:
                    try:
                        response = ensure_taxonomy_terms(
                            WordPressTaxonomyEnsureRequest(
                                schema_version="1.0",
                                base_url=base_url,
                                auth_header=auth_header,
                                taxonomy_rest_base="ml_publisher",
                                terms=[
                                    WordPressTaxonomyTerm(
                                        schema_version="1.0",
                                        slug=publisher_slug,
                                        name=publisher_name,
                                    )
                                ],
                                ssl_verify=settings.wp.ssl_verify,
                                ca_bundle_path=settings.wp.ca_bundle_path,
                            ),
                            file_ctx,
                        )
                        publisher_cache[publisher_slug] = (
                            [response.slug_to_id[publisher_slug]]
                            if publisher_slug in response.slug_to_id
                            else []
                        )
                    except AppError as exc:
                        logger.info(
                            log_event(
                                file_ctx,
                                role="orchestrator",
                                event="publish_preflight_publisher_resolution_failed",
                                module=logger.name,
                                fields={
                                    "file_id": file_id,
                                    "publisher": publisher_name,
                                    "code": exc.code,
                                    "error": exc.message,
                                },
                            )
                        )
                        continue
                publisher_ids = list(publisher_cache.get(publisher_slug, []))
                if publisher_ids:
                    publisher_taxonomy_terms["ml_publisher"] = publisher_ids

        tag_slugs = _normalize_tag_slugs(record.taxonomy)
        tag_ids: list[int] = []
        if tag_slugs:
            tag_key = tuple(tag_slugs)
            if tag_key not in tag_cache:
                try:
                    tag_response = ensure_tags(
                        WordPressTagEnsureRequest(
                            schema_version="1.0",
                            base_url=base_url,
                            auth_header=auth_header,
                            tags=tag_slugs,
                            ssl_verify=settings.wp.ssl_verify,
                            ca_bundle_path=settings.wp.ca_bundle_path,
                        ),
                        file_ctx,
                    )
                    tag_cache[tag_key] = [
                        tag_response.slug_to_id[tag_slug]
                        for tag_slug in tag_slugs
                        if tag_slug in tag_response.slug_to_id
                    ]
                except AppError as exc:
                    logger.info(
                        log_event(
                            file_ctx,
                            role="orchestrator",
                            event="publish_preflight_tag_resolution_failed",
                            module=logger.name,
                            fields={
                                "file_id": file_id,
                                "tags": tag_slugs,
                                "code": exc.code,
                                "error": exc.message,
                            },
                        )
                    )
                    continue
            tag_ids = list(tag_cache.get(tag_key, []))

        resolved_terms_by_file_id[file_id] = PublishResolvedTerms(
            schema_version="1.0",
            category_ids=category_ids,
            tag_ids=tag_ids,
            taxonomy_terms=publisher_taxonomy_terms,
        )

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publish_preflight_term_resolution_complete",
            module=logger.name,
            fields={
                "selected_file_count": len(selected_file_ids),
                "resolved_file_count": len(resolved_terms_by_file_id),
                "category_set_count": len(category_cache),
                "publisher_count": len(publisher_cache),
                "tag_set_count": len(tag_cache),
            },
        )
    )
    return resolved_terms_by_file_id


def _build_publish_preflight_entries(
    *,
    settings: PublishSettings,
    candidates: list[_PublishCandidate],
    metadata_by_file_id: dict[str, ReportMetadataGetResponse],
    base_url: str,
    auth_header: str,
    ctx: RunContext,
) -> list[_PublishPreflightEntry]:
    state_rows_by_file_id: dict[str, StateGetResponse] = {}
    validation_by_file_id: dict[str, tuple[str, list[str]]] = {}
    eligible_network_preflight_file_ids: list[str] = []

    for candidate in candidates:
        file_id = str(candidate.file_id or "").strip()
        if not file_id:
            continue
        file_ctx = child_context(ctx, task_id=candidate.html_path)
        state_row = state_get(
            StateGetRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
            ),
            file_ctx,
        )
        if state_row is not None:
            state_rows_by_file_id[file_id] = state_row
        validation_report = _load_validation_report(
            file_id=file_id,
            html_path=candidate.html_path,
            settings=settings,
            ctx=file_ctx,
        )
        validation_by_file_id[file_id] = (
            validation_report.status if validation_report else "missing",
            [issue.message for issue in validation_report.issues]
            if validation_report
            else [],
        )
        if state_row is not None and not (
            settings.validation_policy == "block"
            and validation_by_file_id[file_id][0] != "pass"
        ):
            eligible_network_preflight_file_ids.append(file_id)

    existing_posts_by_file_id = _batch_lookup_existing_posts(
        settings=settings,
        base_url=base_url,
        auth_header=auth_header,
        candidates=[
            candidate
            for candidate in candidates
            if str(candidate.file_id or "").strip()
            in eligible_network_preflight_file_ids
        ],
        state_rows_by_file_id={
            file_id: state_rows_by_file_id[file_id]
            for file_id in eligible_network_preflight_file_ids
            if file_id in state_rows_by_file_id
        },
        ctx=ctx,
    )
    resolved_terms_by_file_id = _resolve_batch_term_assignments(
        settings=settings,
        metadata_by_file_id=metadata_by_file_id,
        selected_file_ids=eligible_network_preflight_file_ids,
        base_url=base_url,
        auth_header=auth_header,
        ctx=ctx,
    )

    entries: list[_PublishPreflightEntry] = []
    for candidate in candidates:
        file_id = str(candidate.file_id or "").strip()
        validation_status, validation_issues = validation_by_file_id.get(
            file_id,
            ("missing", []),
        )
        entries.append(
            _PublishPreflightEntry(
                candidate=candidate,
                state_row=state_rows_by_file_id.get(file_id),
                validation_status=validation_status,
                validation_issues=list(validation_issues),
                existing_post_lookup=existing_posts_by_file_id.get(file_id),
                resolved_terms=resolved_terms_by_file_id.get(file_id),
            )
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publish_preflight_complete",
            module=logger.name,
            fields={
                "candidate_count": len(candidates),
                "state_row_count": len(state_rows_by_file_id),
                "existing_post_batch_count": len(existing_posts_by_file_id),
                "resolved_term_count": len(resolved_terms_by_file_id),
            },
        )
    )
    return entries


def _validation_paths(output_dir: str, file_id: str, html_path: str) -> list[Path]:
    """
    Validation path in the per-report folder: out/<report-slug>/report_analysis/validation.json.
    """
    _ = file_id
    html_slug = Path(html_path).stem
    return [Path(output_dir) / html_slug / "report_analysis" / "validation.json"]


def _load_validation_report(
    file_id: str, html_path: str, settings: PublishSettings, ctx
) -> Optional[ValidationReport]:
    candidates = _validation_paths(settings.output_dir, file_id, html_path)
    data = None
    used_path: Optional[Path] = None
    for path in candidates:
        try:
            resp = read_text(ReadTextRequest(schema_version="1.0", path=str(path)), ctx)
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publish_validation_missing",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "path": str(path),
                        "error": exc.message,
                    },
                )
            )
            continue
        try:
            data = json.loads(resp.content)
            used_path = path
            break
        except json.JSONDecodeError:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publish_validation_parse_failed",
                    module=logger.name,
                    fields={"file_id": file_id, "path": str(path)},
                )
            )
            continue
    if data is None or used_path is None:
        return None
    return parse_validation_report_payload(data, source_path=str(used_path))


def _with_validation(
    outcome: PublishOutcome, status: Optional[str], issues: List[str]
) -> PublishOutcome:
    return PublishOutcome(
        schema_version=outcome.schema_version,
        html_path=outcome.html_path,
        file_id=outcome.file_id,
        status=outcome.status,
        post_id=outcome.post_id,
        post_url=outcome.post_url,
        error=outcome.error,
        validation_status=status,
        validation_issues=issues,
    )


def _publish_idempotency_key(*, file_id: str, post_type: str) -> str:
    return f"{post_type}:{file_id}"


def _publish_checksum(
    *,
    file_id: str,
    html_path: str,
    html_text: str,
    post_type: str,
    validation_status: str,
    validation_issues: List[str],
) -> str:
    html_sha256 = hashlib.sha256((html_text or "").encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "1.0",
        "file_id": file_id,
        "html_path": html_path,
        "html_sha256": html_sha256,
        "post_type": post_type,
        "validation_status": validation_status,
        "validation_issues": list(validation_issues or []),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _lookup_publish_idempotency(
    *,
    settings: PublishSettings,
    file_id: str,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> PublishOutcome | None:
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
        ),
        ctx,
    )
    if not lookup.found or lookup.record is None:
        return None
    return PublishOutcome(**dict(lookup.record.outcome_payload or {}))


def _record_publish_idempotency(
    *,
    settings: PublishSettings,
    outcome: PublishOutcome,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> None:
    if not outcome.file_id:
        return
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=outcome.file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
            outcome_payload=asdict(outcome),
            artifact_references={
                "html_path": outcome.html_path,
                "status": outcome.status,
                "post_id": outcome.post_id,
                "post_url": outcome.post_url,
            },
        ),
        ctx,
    )


def _cross_report_settings_for_target_route(
    settings: PublishSettings,
    target_route: str,
) -> PublishSettings:
    post_type = _CROSS_REPORT_WORDPRESS_POST_TYPES.get(
        str(target_route).strip(),
        settings.wp.post_type,
    )
    if post_type == settings.wp.post_type:
        return settings

    try:
        route_wp_settings = replace(settings.wp, post_type=post_type)
    except TypeError:
        route_wp_settings = copy.copy(settings.wp)
        route_wp_settings.post_type = post_type

    try:
        return replace(settings, wp=route_wp_settings)
    except TypeError:
        route_settings = copy.copy(settings)
        route_settings.wp = route_wp_settings
        return route_settings


def _unique_terms_from_labels(labels: list[str]) -> list[WordPressTaxonomyTerm]:
    terms: list[WordPressTaxonomyTerm] = []
    seen: set[str] = set()
    for label in labels:
        name = str(label or "").strip()
        slug = slugify(name)
        if name == "" or slug == "" or slug in seen:
            continue
        seen.add(slug)
        terms.append(WordPressTaxonomyTerm(schema_version="1.0", slug=slug, name=name))
    return terms


def _cross_report_publisher_labels(package: CrossReportPublishPackage) -> list[str]:
    publishers: list[str] = []
    seen: set[str] = set()
    for item in package.source_metadata:
        publisher = str((item or {}).get("publisher") or "").strip()
        slug = slugify(publisher)
        if publisher == "" or slug == "" or slug in seen:
            continue
        seen.add(slug)
        publishers.append(publisher)
    return publishers


def _cross_report_wordpress_classification(
    package: CrossReportPublishPackage,
    settings: PublishSettings,
) -> _CrossReportWordPressClassification:
    return _CrossReportWordPressClassification(
        post_type=settings.wp.post_type,
        slug=str(package.slug or "").strip() or slugify(package.title),
        category_terms=_unique_terms_from_labels(package.category_labels),
        tag_slugs=[
            term.slug for term in _unique_terms_from_labels(package.tag_labels)
        ],
        taxonomy_terms={
            "ml_publisher": _unique_terms_from_labels(
                _cross_report_publisher_labels(package)
            )
        },
    )


def _cross_report_result_fields(
    classification: _CrossReportWordPressClassification,
) -> dict[str, object]:
    return {
        "target_post_type": classification.post_type,
        "target_slug": classification.slug,
        "category_slugs": [term.slug for term in classification.category_terms],
        "tag_slugs": list(classification.tag_slugs),
        "taxonomy_term_slugs": {
            taxonomy: [term.slug for term in terms]
            for taxonomy, terms in classification.taxonomy_terms.items()
            if terms
        },
    }


def _resolve_cross_report_terms(
    *,
    classification: _CrossReportWordPressClassification,
    settings: PublishSettings,
    base_url: str,
    auth_header: str,
    ctx: RunContext,
    ensure_taxonomy_terms_fn: Callable[
        [WordPressTaxonomyEnsureRequest, RunContext], WordPressTaxonomyEnsureResponse
    ],
    ensure_tags_fn: Callable[
        [WordPressTagEnsureRequest, RunContext], WordPressTagEnsureResponse
    ],
) -> PublishResolvedTerms:
    category_ids: list[int] = []
    if classification.category_terms:
        category_response = ensure_taxonomy_terms_fn(
            WordPressTaxonomyEnsureRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                taxonomy_rest_base="categories",
                terms=classification.category_terms,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
            ),
            ctx,
        )
        category_ids = [
            category_response.slug_to_id[term.slug]
            for term in classification.category_terms
            if term.slug in category_response.slug_to_id
        ]

    tag_ids: list[int] = []
    if classification.tag_slugs:
        tag_response = ensure_tags_fn(
            WordPressTagEnsureRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                tags=classification.tag_slugs,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
            ),
            ctx,
        )
        tag_ids = [
            tag_response.slug_to_id[tag_slug]
            for tag_slug in classification.tag_slugs
            if tag_slug in tag_response.slug_to_id
        ]

    taxonomy_term_ids: dict[str, list[int]] = {}
    for taxonomy_rest_base, terms in classification.taxonomy_terms.items():
        if not terms:
            continue
        taxonomy_response = ensure_taxonomy_terms_fn(
            WordPressTaxonomyEnsureRequest(
                schema_version="1.0",
                base_url=base_url,
                auth_header=auth_header,
                taxonomy_rest_base=taxonomy_rest_base,
                terms=terms,
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
            ),
            ctx,
        )
        ids = [
            taxonomy_response.slug_to_id[term.slug]
            for term in terms
            if term.slug in taxonomy_response.slug_to_id
        ]
        if ids:
            taxonomy_term_ids[taxonomy_rest_base] = ids

    return PublishResolvedTerms(
        schema_version="1.0",
        category_ids=category_ids,
        tag_ids=tag_ids,
        taxonomy_terms=taxonomy_term_ids,
    )


def _briefing_url_is_in_section(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    path = parsed.path.strip("/")
    return path == "briefings" or path.startswith("briefings/")


def _signal_url_is_in_section(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    path = parsed.path.strip("/")
    return path == "signals" or path.startswith("signals/")


def _cross_report_publish_checksum(
    package: CrossReportPublishPackage,
    settings: PublishSettings,
) -> str:
    payload = {
        "schema_version": CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        "selected_theme_id": package.selected_theme_id,
        "selected_report_ids": package.selected_report_ids,
        "artifact_sha256": package.artifact_sha256,
        "validation_sha256": package.validation_sha256,
        "prompt_hashes": package.prompt_hashes,
        "target_route": package.target_route,
        "post_type": settings.wp.post_type,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _cross_report_publish_idempotency_key(
    package: CrossReportPublishPackage,
    checksum: str,
) -> str:
    return f"{package.target_route}:{package.file_id}:{checksum}"


def _cross_report_result_from_outcome(
    *,
    package: CrossReportPublishPackage,
    publication_mode: str,
    outcome: PublishOutcome,
    idempotency_reused: bool,
    classification: _CrossReportWordPressClassification,
) -> CrossReportPublishResultSummary:
    status = "published" if outcome.status == "published" else "skipped"
    if outcome.status == "error":
        status = "error"
    return CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode=cast(PublicationMode, publication_mode),
        status=cast(CrossReportPublishStatus, status),
        target_route=package.target_route,
        idempotency_reused=idempotency_reused,
        **_cross_report_result_fields(classification),
        post_id=outcome.post_id,
        post_url=outcome.post_url,
        error_code=outcome.error if status == "error" else None,
        error_message=outcome.error if status == "error" else None,
    )


def _record_cross_report_publish_idempotency(
    *,
    package: CrossReportPublishPackage,
    settings: PublishSettings,
    result: CrossReportPublishResultSummary,
    checksum: str,
    ctx: RunContext,
) -> None:
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_cross_report_publish_idempotency_key(package, checksum),
            input_checksum=checksum,
            outcome_payload=asdict(result),
            artifact_references={
                "html_path": package.html_path,
                "artifact_path": package.canonical_artifact_path,
                "status": result.status,
                "post_id": result.post_id,
                "post_url": result.post_url,
            },
        ),
        ctx,
    )


def _lookup_cross_report_publish_idempotency(
    *,
    package: CrossReportPublishPackage,
    settings: PublishSettings,
    checksum: str,
    ctx: RunContext,
) -> CrossReportPublishResultSummary | None:
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_cross_report_publish_idempotency_key(package, checksum),
            input_checksum=checksum,
        ),
        ctx,
    )
    if not lookup.found or lookup.record is None:
        return None
    return replace(
        CrossReportPublishResultSummary(**dict(lookup.record.outcome_payload or {})),
        idempotency_reused=True,
    )


def publish_cross_report_package(
    package: CrossReportPublishPackage,
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
    validate_cross_report_contract(package)
    publication_mode = "publish_dry_run" if dry_run else "publish_live"
    route_settings = _cross_report_settings_for_target_route(
        settings, package.target_route
    )
    classification = _cross_report_wordpress_classification(package, route_settings)
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


def _signal_projection_package(
    projection: SignalPublishProjection,
) -> CrossReportPublishPackage:
    payload = asdict(projection)
    content_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    stable_file_id = projection.file_id or f"signal:{projection.slug}"
    return CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id=stable_file_id,
        file_id=stable_file_id,
        target_route=projection.target_route,
        title=projection.title,
        slug=projection.slug,
        excerpt=projection.summary_html,
        body_html=projection.body_html,
        html_text=projection.html_text
        or f"<html><body>{projection.body_html}</body></html>",
        html_path=f"signal_posts/{projection.slug}.html",
        canonical_artifact_path=f"signal_posts/{projection.slug}.json",
        artifact_sha256=content_hash,
        validation_sha256=content_hash,
        selected_theme_id=projection.slug,
        selected_report_ids=list(projection.source_report_ids),
        source_metadata=[
            {"publisher": publisher} for publisher in projection.publisher_labels
        ],
        category_labels=list(projection.topic_labels or projection.topic_ids),
        tag_labels=list(projection.tag_labels),
        evidence_reference_ids=list(projection.evidence_ids),
        raw_metric_ids=[],
        prompt_hashes={"signal_post_generator": content_hash},
        machine_metadata={
            "schema_version": WORDPRESS_ENTITY_SCHEMA_VERSION,
            "signal_slug": projection.slug,
            "validation_status": projection.validation_status,
            "confidence": projection.confidence,
            "uncertainty": projection.uncertainty,
        },
    )


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

    if html_paths is None:
        list_resp = list_html(
            ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir),
            root_ctx,
        )
        discovered_html_paths = list_resp.html_paths
    else:
        discovered_html_paths = [str(path) for path in html_paths]
    max_n = limit if limit is not None else len(discovered_html_paths)
    selected_html_paths = discovered_html_paths[:max_n]

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

    candidates = _resolve_publish_candidates(
        html_paths=selected_html_paths,
        html_file_id_map=html_file_id_map,
        ctx=root_ctx,
    )
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
        state_row = entry.state_row
        validation_status = entry.validation_status
        validation_issues = list(entry.validation_issues)
        existing_post_lookup = entry.existing_post_lookup
        resolved_terms = entry.resolved_terms

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
            post_type=settings.wp.post_type,
            validation_status=validation_status,
            validation_issues=validation_issues,
        )
        reused_outcome = _lookup_publish_idempotency(
            settings=settings,
            file_id=file_id,
            post_type=settings.wp.post_type,
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
                        "post_type": settings.wp.post_type,
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
                post_type=settings.wp.post_type,
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
                        post_type=settings.wp.post_type,
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
                        post_type=settings.wp.post_type,
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
                settings,
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
                        post_type=settings.wp.post_type,
                    ),
                    file_ctx,
                )
            if outcome.status in {"published", "skipped"}:
                _record_publish_idempotency(
                    settings=settings,
                    outcome=outcome,
                    post_type=settings.wp.post_type,
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
