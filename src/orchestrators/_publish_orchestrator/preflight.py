"""Preflight helpers for publication orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.files import ReadTextRequest
from src.contracts.publish import (
    PublishOutcome,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.publish_readiness import PublishReadinessArtifact
from src.contracts.report_store import (
    ReportMetadataGetResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateGetRequest,
    StateGetResponse,
)
from src.contracts.wordpress import (
    WordPressPostLookupBatchItem,
    WordPressPostLookupBatchRequest,
    WordPressTagEnsureRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.generators.publish_readiness_generator import (
    parse_publish_readiness_payload,
    verify_publish_readiness,
)
from src.orchestrators._publish_orchestrator.models import (
    _PublishCandidate,
    _PublishPreflightEntry,
)
from src.orchestrators._publish_orchestrator.routing import (
    _normalize_string_list,
    _normalize_tag_slugs,
)
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.file_service import read_text
from src.services.state_service import get as state_get
from src.services.wordpress_service import (
    ensure_tags,
    ensure_taxonomy_terms,
    find_posts_by_file_id_batch,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_orchestrator")


def _batch_lookup_existing_posts(
    *,
    settings: PublishSettings,
    base_url: str,
    auth_header: str,
    candidates: list[_PublishCandidate],
    state_rows_by_file_id: dict[str, StateGetResponse],
    post_type: str,
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
            post_type=post_type,
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
    category_definitions = {}
    if needs_category_labels:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
                reload_if_changed=True,
            ),
            ctx,
        )
        category_definitions = {
            category.id: category for category in mappings_resp.mappings.categories
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
                        schema_version="1.1",
                        slug=category_id,
                        name=(category_definitions[category_id].label or category_id)
                        if category_id in category_definitions
                        else category_id,
                        description=category_definitions[category_id].description
                        if category_id in category_definitions
                        else "",
                        definition=category_definitions[category_id].definition
                        if category_id in category_definitions
                        else "",
                        include_when=list(
                            category_definitions[category_id].include_when
                        )
                        if category_id in category_definitions
                        else [],
                        exclude_when=list(
                            category_definitions[category_id].exclude_when
                        )
                        if category_id in category_definitions
                        else [],
                        semantics_version=category_definitions[
                            category_id
                        ].schema_version
                        if category_id in category_definitions
                        else "",
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
    skip_term_resolution_file_ids: set[str] | None = None,
) -> list[_PublishPreflightEntry]:
    state_rows_by_file_id: dict[str, StateGetResponse] = {}
    validation_by_file_id: dict[str, tuple[str, list[str]]] = {}
    readiness_by_file_id: dict[str, PublishReadinessArtifact | None] = {}
    eligible_network_preflight_file_ids: list[str] = []

    for candidate in candidates:
        if candidate.entity_error is not None:
            continue
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
        if candidate.entity_route and candidate.entity_route.entity_type == "report":
            readiness = _load_publish_readiness(
                file_id=file_id,
                html_path=candidate.html_path,
                settings=settings,
                ctx=file_ctx,
            )
            readiness_by_file_id[file_id] = readiness
            verification = verify_publish_readiness(
                artifact=readiness,
                report_id=file_id,
                final_html=(
                    candidate.html_snapshot.html_text if candidate.html_snapshot else ""
                ),
                configuration_hash=ctx.configuration_hash,
                policy_hash=ctx.policy_hash,
                producer_revision=ctx.producer_commit_sha,
            )
            validation_by_file_id[file_id] = (
                verification.status,
                verification.issues,
            )
        else:
            validation_by_file_id[file_id] = ("pass", [])
        if state_row is not None and validation_by_file_id[file_id][0] == "pass":
            eligible_network_preflight_file_ids.append(file_id)

    eligible_candidates = [
        candidate
        for candidate in candidates
        if str(candidate.file_id or "").strip() in eligible_network_preflight_file_ids
        and candidate.entity_route is not None
    ]
    existing_posts_by_file_id: dict[str, WordPressPostLookupBatchItem] = {}
    eligible_post_types = {
        candidate.entity_route.post_type
        for candidate in eligible_candidates
        if candidate.entity_route
    }
    for post_type in sorted(eligible_post_types):
        post_type_candidates = [
            candidate
            for candidate in eligible_candidates
            if candidate.entity_route and candidate.entity_route.post_type == post_type
        ]
        existing_posts_by_file_id.update(
            _batch_lookup_existing_posts(
                settings=settings,
                base_url=base_url,
                auth_header=auth_header,
                candidates=post_type_candidates,
                state_rows_by_file_id={
                    file_id: state_rows_by_file_id[file_id]
                    for file_id in eligible_network_preflight_file_ids
                    if file_id in state_rows_by_file_id
                },
                post_type=post_type,
                ctx=ctx,
            )
        )
    # A matching publication idempotency record needs no taxonomy work.  Term
    # "ensure" calls can write, so exclude these candidates before the batch
    # resolver runs; the caller still performs the normal authenticated post
    # lookup/readback preflight for every eligible candidate.
    skipped_term_file_ids = skip_term_resolution_file_ids or set()
    resolved_terms_by_file_id = _resolve_batch_term_assignments(
        settings=settings,
        metadata_by_file_id=metadata_by_file_id,
        selected_file_ids=[
            file_id
            for file_id in eligible_network_preflight_file_ids
            if file_id not in skipped_term_file_ids
        ],
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
                publish_readiness=readiness_by_file_id.get(file_id),
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
                "idempotent_term_skip_count": len(skipped_term_file_ids),
            },
        )
    )
    return entries


def _publish_readiness_paths(
    output_dir: str, file_id: str, html_path: str
) -> list[Path]:
    """Readiness path in out/<report-slug>/report_analysis/publish_readiness.json."""
    _ = file_id
    html_slug = Path(html_path).stem
    return [Path(output_dir) / html_slug / "report_analysis" / "publish_readiness.json"]


def _load_publish_readiness(
    file_id: str, html_path: str, settings: PublishSettings, ctx
) -> Optional[PublishReadinessArtifact]:
    candidates = _publish_readiness_paths(settings.output_dir, file_id, html_path)
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
                    event="publish_readiness_missing",
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
                    event="publish_readiness_parse_failed",
                    module=logger.name,
                    fields={"file_id": file_id, "path": str(path)},
                )
            )
            continue
    if data is None or used_path is None:
        return None
    try:
        return parse_publish_readiness_payload(data)
    except (TypeError, ValueError):
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publish_readiness_contract_invalid",
                module=logger.name,
                fields={"file_id": file_id, "path": str(used_path)},
            )
        )
        return None


def _with_validation(
    outcome: PublishOutcome, status: Optional[str], issues: List[str]
) -> PublishOutcome:
    return replace(
        outcome,
        validation_status=status,
        validation_issues=issues,
    )
