from __future__ import annotations

"""Cross Report helpers for publication orchestration."""

import hashlib
import json
from dataclasses import asdict
from typing import Callable, cast
from urllib.parse import urlparse

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
    CrossReportPublishResultSummary,
    CrossReportPublishStatus,
    PublicationMode,
)
from src.contracts.publish import (
    PublishEntityMetadata,
    PublishOutcome,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressTagEnsureRequest,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
    WordPressTaxonomyTerm,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPublishProjection,
)
from src.orchestrators._publish_orchestrator.models import (
    _CROSS_REPORT_WORDPRESS_POST_TYPES,
    _PUBLISH_ROUTES_BY_INTENT,
    _CrossReportResultFields,
    _CrossReportWordPressClassification,
)
from src.orchestrators._publish_orchestrator.routing import (
    _publish_settings_for_post_type,
)
from src.utils.errors import AppError
from src.utils.html_utils import (
    ensure_publish_entity_metadata_html,
    extract_publish_entity_metadata,
)
from src.utils.slugify import slugify


def _cross_report_post_type_for_target_route(target_route: str) -> str:
    normalized_route = str(target_route).strip()
    post_type = _CROSS_REPORT_WORDPRESS_POST_TYPES.get(normalized_route)
    if post_type is None:
        raise AppError(
            code="publish_entity_metadata_unsupported",
            message=(
                "Cross-report package declares an unsupported WordPress target route."
            ),
            retryable=False,
            severity="error",
            context={"target_route": normalized_route},
        )
    return post_type


def _cross_report_settings_for_target_route(
    settings: PublishSettings,
    target_route: str,
) -> PublishSettings:
    post_type = _cross_report_post_type_for_target_route(target_route)
    return _publish_settings_for_post_type(settings, post_type)


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
    post_type: str,
) -> _CrossReportWordPressClassification:
    return _CrossReportWordPressClassification(
        post_type=post_type,
        slug=str(package.slug or "").strip() or slugify(package.title),
        category_terms=_unique_terms_from_labels(package.category_labels),
        tag_slugs=[term.slug for term in _unique_terms_from_labels(package.tag_labels)],
        taxonomy_terms={
            "ml_publisher": _unique_terms_from_labels(
                _cross_report_publisher_labels(package)
            )
        },
    )


def _publish_entity_metadata_for_route(
    *,
    source_artifact_id: str,
    canonical_route_intent: str,
    publish_eligible: bool = True,
) -> PublishEntityMetadata:
    route = _PUBLISH_ROUTES_BY_INTENT.get(str(canonical_route_intent or "").strip())
    if route is None:
        raise AppError(
            code="publish_entity_metadata_unsupported",
            message=(
                "Generated artifact declares an unsupported WordPress route intent."
            ),
            retryable=False,
            severity="error",
            context={"canonical_route_intent": canonical_route_intent},
        )
    return PublishEntityMetadata(
        schema_version="1.0",
        entity_type=route.entity_type,
        source_artifact_id=source_artifact_id,
        canonical_route_intent=route.canonical_route_intent,
        publish_eligible=publish_eligible,
    )


def _cross_report_result_fields(
    classification: _CrossReportWordPressClassification,
) -> _CrossReportResultFields:
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


def _signal_projection_package(
    projection: SignalPublishProjection,
    signal_card: dict[str, object],
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
    candidate_manifest_sha256 = str(projection.candidate_manifest_sha256 or "")
    manifest_valid = len(candidate_manifest_sha256) == 64 and all(
        character in "0123456789abcdef" for character in candidate_manifest_sha256
    )
    signal_publishable = bool(
        projection.validation_status == "approved"
        and projection.candidate_group_id
        and manifest_valid
    )
    signal_publishability_issues = (
        []
        if signal_publishable
        else [
            issue
            for issue in (
                "signal_not_approved"
                if projection.validation_status != "approved"
                else "",
                "signal_candidate_manifest_missing"
                if not projection.candidate_group_id or not manifest_valid
                else "",
            )
            if issue
        ]
    )
    publish_entity_metadata = _publish_entity_metadata_for_route(
        source_artifact_id=stable_file_id,
        canonical_route_intent=projection.target_route,
        publish_eligible=signal_publishable,
    )
    signal_html_text = projection.html_text or (
        f"<html><body>{projection.body_html}</body></html>"
    )
    embedded_metadata = extract_publish_entity_metadata(signal_html_text)
    if embedded_metadata is not None and embedded_metadata != publish_entity_metadata:
        raise AppError(
            code="publish_entity_metadata_mismatch",
            message=(
                "Signal HTML entity metadata conflicts with its publishability decision"
            ),
            retryable=False,
            severity="error",
            context={"source_artifact_id": stable_file_id},
        )
    if embedded_metadata is None:
        signal_html_text = ensure_publish_entity_metadata_html(
            signal_html_text,
            publish_entity_metadata,
        )
    publisher_by_report_id = {
        attribution.report_id: attribution.publisher
        for attribution in projection.source_attributions
    }
    return CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id=stable_file_id,
        file_id=stable_file_id,
        target_route=projection.target_route,
        title=projection.title,
        slug=projection.slug,
        excerpt=projection.summary_html,
        body_html=projection.body_html,
        html_text=signal_html_text,
        html_path=f"signal_posts/{projection.slug}.html",
        canonical_artifact_path=f"signal_posts/{projection.slug}.json",
        artifact_sha256=content_hash,
        validation_sha256=_signal_validation_sha256(projection.validation_status),
        selected_theme_id=projection.candidate_group_id or projection.slug,
        selected_report_ids=list(projection.source_report_ids),
        source_metadata=[
            {
                "report_id": report_id,
                "publisher": publisher_by_report_id.get(report_id, ""),
            }
            for report_id in projection.source_report_ids
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
            "candidate_group_id": projection.candidate_group_id,
            "candidate_manifest_sha256": candidate_manifest_sha256,
            "selected_report_ids": list(projection.source_report_ids),
            "publishability": {
                "publishable": signal_publishable,
                "diagnostic": False,
                "override_applied": False,
                "issues": signal_publishability_issues,
                "selected_theme_id": projection.candidate_group_id or projection.slug,
                "selected_report_ids": list(projection.source_report_ids),
                "candidate_group_id": projection.candidate_group_id,
                "candidate_manifest_sha256": candidate_manifest_sha256,
            },
            "confidence": projection.confidence,
            "uncertainty": projection.uncertainty,
            "public_entity_metadata": asdict(publish_entity_metadata),
        },
        signal_card=signal_card,
    )


def _signal_validation_sha256(validation_status: str) -> str:
    """Return the version-compatible validation identity used by Signals."""

    return hashlib.sha256(
        f"signal-validation\x1f{validation_status}".encode("utf-8")
    ).hexdigest()
