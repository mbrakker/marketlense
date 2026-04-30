from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
import logging
import mimetypes
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from src.contracts.files import FileExistsRequest, ReadBytesRequest, ReadTextRequest
from src.contracts.publish import (
    PublishOutcome,
    PublishRequest,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.report_store import ReportMetadataGetRequest
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressTagEnsureRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.contracts.categories import CategoryMappingLoadRequest
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.file_service import file_exists, read_bytes, read_text
from src.services.report_store_service import get_metadata
from src.services.wordpress_service import (
    create_post,
    ensure_taxonomy_terms,
    ensure_tags,
    upload_media,
)
from src.utils.errors import AppError
from src.utils.html_utils import (
    extract_body_html,
    extract_file_id,
    extract_image_sources,
    extract_preview_image,
    extract_title,
    replace_image_sources,
    strip_image_srcset_and_sizes,
)
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_generator")


@dataclass(frozen=True)
class _MediaUploadJob:
    src: str
    local_path: str
    is_preview: bool


@dataclass(frozen=True)
class _MediaUploadResult:
    src: str
    media_id: int


def publish_html(
    request: PublishRequest,
    settings: PublishSettings,
    ctx: RunContext,
) -> PublishOutcome:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_start",
            module=logger.name,
            fields={"html_path": request.html_path},
        )
    )

    if request.html_text is None:
        html_text = read_text(
            ReadTextRequest(schema_version="1.0", path=request.html_path), ctx
        ).content
        html_source = "path"
    else:
        html_text = request.html_text
        html_source = "request"
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_html_source",
            module=logger.name,
            fields={
                "html_path": request.html_path,
                "source": html_source,
                "length": len(html_text),
            },
        )
    )
    file_id = request.file_id or extract_file_id(html_text)
    if not file_id:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publish_missing_file_id",
                module=logger.name,
                fields={"html_path": request.html_path},
            )
        )
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=None,
            status="error",
            error="missing_file_id",
        )

    auth_header = str(request.auth_header or "").strip()
    if not auth_header:
        raise AppError(
            code="wp_auth_missing",
            message="Publish request must include a resolved WordPress auth header",
            retryable=False,
        )
    base_url = settings.wp.site_url.rstrip("/")

    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.1", db_path=settings.reports_db, file_id=file_id
        ),
        ctx,
    ) if request.resolved_terms is None else None
    resolved_terms = request.resolved_terms or _resolve_term_assignments(
        metadata=metadata,
        settings=settings,
        base_url=base_url,
        auth_header=auth_header,
        ctx=ctx,
    )
    category_ids_for_wp = list(resolved_terms.category_ids)
    tag_ids_for_wp = list(resolved_terms.tag_ids)
    publisher_term_ids_for_wp = list(
        (resolved_terms.taxonomy_terms or {}).get("ml_publisher", [])
    )

    image_map, featured_media_id = _upload_images(
        html_text,
        request.html_path,
        settings.output_dir,
        base_url,
        auth_header,
        settings.wp.ssl_verify,
        settings.wp.ca_bundle_path,
        settings.media_upload_workers,
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_images_uploaded",
            module=logger.name,
            fields={"count": len(image_map), "featured_media": featured_media_id or 0},
        )
    )
    rendered_html = replace_image_sources(html_text, image_map)
    # Proxy-backed digest images stay more reliable on the WP frontend without
    # responsive srcset/sizes candidates that still point at synthetic query URLs.
    rendered_html = strip_image_srcset_and_sizes(rendered_html)
    body_html, file_id_marker_inserted = _ensure_hidden_file_id_marker(
        extract_body_html(rendered_html),
        file_id,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_file_id_marker",
            module=logger.name,
            fields={
                "file_id": file_id,
                "inserted": file_id_marker_inserted,
            },
        )
    )

    title = extract_title(rendered_html) or Path(request.html_path).stem
    slug = slugify(title)

    post_resp = create_post(
        WordPressPostCreateRequest(
            schema_version="1.0",
            base_url=base_url,
            auth_header=auth_header,
            title=title,
            content_html=body_html,
            status=settings.wp.post_status,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            slug=slug,
            featured_media=featured_media_id,
            categories=category_ids_for_wp if category_ids_for_wp else None,
            tags=tag_ids_for_wp if tag_ids_for_wp else None,
            taxonomy_terms=resolved_terms.taxonomy_terms or None,
            post_type=settings.wp.post_type,
        ),
        ctx,
    )

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_complete",
            module=logger.name,
            fields={
                "file_id": file_id,
                "post_id": post_resp.post_id,
                "post_url": post_resp.link,
            },
        )
    )

    return PublishOutcome(
        schema_version="1.0",
        html_path=request.html_path,
        file_id=file_id,
        status="published",
        post_id=post_resp.post_id,
        post_url=post_resp.link,
    )


def _resolve_term_assignments(
    *,
    metadata,
    settings: PublishSettings,
    base_url: str,
    auth_header: str,
    ctx: RunContext,
) -> PublishResolvedTerms:
    category_ids_for_wp: list[int] = []
    tag_ids_for_wp: list[int] = []
    taxonomy_terms: dict[str, list[int]] = {}
    if metadata and metadata.categories:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
                reload_if_changed=True,
            ),
            ctx,
        )
        id_to_label = {
            cat.id: cat.label or cat.id for cat in mappings_resp.mappings.categories
        }
        terms = [
            WordPressTaxonomyTerm(
                schema_version="1.0", slug=cat_id, name=id_to_label.get(cat_id, cat_id)
            )
            for cat_id in metadata.categories
        ]
        if terms:
            ensure_resp = ensure_taxonomy_terms(
                WordPressTaxonomyEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    taxonomy_rest_base="categories",
                    terms=terms,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            category_ids_for_wp = [
                ensure_resp.slug_to_id[term.slug]
                for term in terms
                if term.slug in ensure_resp.slug_to_id
            ]
    if metadata and metadata.publisher and metadata.publisher.strip():
        publisher_name = metadata.publisher.strip()
        publisher_slug = slugify(publisher_name)
        if publisher_slug:
            publisher_terms = [
                WordPressTaxonomyTerm(
                    schema_version="1.0",
                    slug=publisher_slug,
                    name=publisher_name,
                )
            ]
            ensure_publishers_resp = ensure_taxonomy_terms(
                WordPressTaxonomyEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    taxonomy_rest_base="ml_publisher",
                    terms=publisher_terms,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            publisher_term_ids_for_wp = [
                ensure_publishers_resp.slug_to_id[term.slug]
                for term in publisher_terms
                if term.slug in ensure_publishers_resp.slug_to_id
            ]
            if publisher_term_ids_for_wp:
                taxonomy_terms["ml_publisher"] = publisher_term_ids_for_wp
    if metadata and metadata.taxonomy:
        tag_slugs: list[str] = []
        seen_tag_slugs: set[str] = set()
        for tag in metadata.taxonomy:
            slug = slugify(tag)
            if not slug or slug in seen_tag_slugs:
                continue
            seen_tag_slugs.add(slug)
            tag_slugs.append(slug)
        if tag_slugs:
            ensure_tags_resp = ensure_tags(
                WordPressTagEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    tags=tag_slugs,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                ),
                ctx,
            )
            tag_ids_for_wp = [
                ensure_tags_resp.slug_to_id[slug]
                for slug in tag_slugs
                if slug in ensure_tags_resp.slug_to_id
            ]
    return PublishResolvedTerms(
        schema_version="1.0",
        category_ids=category_ids_for_wp,
        tag_ids=tag_ids_for_wp,
        taxonomy_terms=taxonomy_terms,
    )

def _upload_images(
    html_text: str,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    media_upload_workers: int,
    ctx: RunContext,
) -> Tuple[Dict[str, str], Optional[int]]:
    sources = extract_image_sources(html_text)
    if not sources:
        return {}, None

    preview_src = extract_preview_image(html_text)
    jobs = _collect_media_upload_jobs(
        sources=sources,
        preview_src=preview_src,
        html_path=html_path,
        output_dir=output_dir,
        ctx=ctx,
    )
    if not jobs:
        return {}, None

    max_workers = max(1, min(int(media_upload_workers), len(jobs)))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_media_upload_plan",
            module=logger.name,
            fields={
                "job_count": len(jobs),
                "worker_count": max_workers,
                "has_preview_src": bool(preview_src),
            },
        )
    )

    results_by_src: Dict[str, _MediaUploadResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                _upload_single_media,
                job=job,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
            ): job
            for job in jobs
        }
        for future in as_completed(future_to_job):
            result = future.result()
            results_by_src[result.src] = result

    mapping: Dict[str, str] = {}
    media_ids: Dict[str, int] = {}
    featured_media_id: Optional[int] = None
    for job in jobs:
        result = results_by_src[job.src]
        mapping[job.src] = _wordpress_media_proxy_url(result.media_id)
        media_ids[job.src] = result.media_id
        if job.is_preview:
            featured_media_id = result.media_id

    if not featured_media_id and media_ids:
        first_src = sources[0]
        featured_media_id = media_ids.get(first_src)

    return mapping, featured_media_id


def _collect_media_upload_jobs(
    *,
    sources: list[str],
    preview_src: str | None,
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> list[_MediaUploadJob]:
    jobs: list[_MediaUploadJob] = []
    seen: set[str] = set()
    for src in sources:
        if src in seen:
            continue
        seen.add(src)
        local_path = _resolve_local_path(src, html_path, output_dir, ctx)
        if not local_path:
            if not src.startswith("http://") and not src.startswith("https://"):
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="publish_image_missing",
                        module=logger.name,
                        fields={"src": src},
                    )
                )
            continue
        jobs.append(
            _MediaUploadJob(
                src=src,
                local_path=local_path,
                is_preview=bool(preview_src and src == preview_src),
            )
        )
    return jobs


def _upload_single_media(
    *,
    job: _MediaUploadJob,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> _MediaUploadResult:
    upload_resp = upload_media(
        _media_upload_request(
            job.local_path,
            job.src,
            base_url,
            auth_header,
            ssl_verify,
            ca_bundle_path,
            ctx,
        ),
        ctx,
    )
    return _MediaUploadResult(src=job.src, media_id=upload_resp.media_id)


def _wordpress_media_proxy_url(media_id: int) -> str:
    # Same-origin proxy URLs avoid mixed-scheme failures when WP still emits
    # frontend pages on http while media proxy requests are forced to https.
    return f"/?ml_media={int(media_id)}"


def _ensure_hidden_file_id_marker(content_html: str, file_id: str) -> Tuple[str, bool]:
    if extract_file_id(content_html) == file_id:
        return content_html, False
    marker = f"<p hidden>Drive fileId: {html.escape(file_id, quote=True)}</p>"
    if not content_html:
        return marker, True
    return f"{content_html}\n{marker}", True


def _media_upload_request(
    local_path: str,
    src: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> WordPressMediaUploadRequest:
    data_resp = read_bytes(ReadBytesRequest(schema_version="1.0", path=local_path), ctx)
    mime_type, _ = mimetypes.guess_type(local_path)
    filename = Path(local_path).name
    alt_text = Path(src).stem.replace("-", " ")
    return WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url=base_url,
        auth_header=auth_header,
        filename=filename,
        mime_type=mime_type or "image/png",
        data=data_resp.content,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        alt_text=alt_text,
    )


def _resolve_local_path(
    src: str,
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> Optional[str]:
    parsed = urlparse(src)
    if parsed.scheme in {"http", "https", "data"}:
        return None

    raw_path = unquote((parsed.path or src).strip())
    if not raw_path:
        return None

    normalized = raw_path.replace("\\", "/")
    candidates: list[Path] = []
    candidate_path = Path(normalized)

    if candidate_path.is_absolute():
        candidates.append(candidate_path)

    relative = normalized.lstrip("/")
    if relative:
        candidates.append(Path(output_dir) / relative)
        candidates.append(Path(html_path).resolve().parent / relative)

    for candidate in candidates:
        exists_resp = file_exists(
            FileExistsRequest(schema_version="1.0", path=str(candidate)), ctx
        )
        if exists_resp.exists:
            return str(candidate)

    return None
