from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
from io import BytesIO
import json
import logging
import mimetypes
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from PIL import Image

from src.contracts.files import FileExistsRequest, ReadBytesRequest, ReadTextRequest
from src.contracts.publish import (
    PublishHtmlSnapshot,
    PublishOutcome,
    PublishRequest,
    PublishResolvedTerms,
    PublishSettings,
)
from src.contracts.report_store import ReportMetadataGetRequest
from src.contracts.report_cards import ReportCardManifest
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
    build_publish_html_snapshot,
    extract_file_id,
    replace_image_sources,
    strip_image_srcset_and_sizes,
)
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_generator")

_MAX_MEDIA_UPLOAD_BYTES = 8_000_000
_MAX_MEDIA_UPLOAD_DIMENSION_PX = 1800
_MEDIA_JPEG_QUALITY = 85


@dataclass(frozen=True)
class _MediaUploadJob:
    src: str
    local_path: str
    is_preview: bool


@dataclass(frozen=True)
class _MediaUploadResult:
    src: str
    media_id: int


@dataclass(frozen=True)
class _PreparedMediaPayload:
    filename: str
    mime_type: str
    data: bytes
    optimized: bool


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

    html_snapshot, html_source = _resolve_html_snapshot(request, ctx)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_html_source",
            module=logger.name,
            fields={
                "html_path": request.html_path,
                "source": html_source,
                "length": len(html_snapshot.html_text),
            },
        )
    )
    file_id = request.file_id or html_snapshot.file_id
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
    card_manifest = None
    if not file_id.startswith("cross-report:"):
        card_manifest = _load_report_card_manifest(
            request.html_path,
            settings.output_dir,
            ctx,
        )

    metadata = None
    if request.resolved_terms is None:
        reports_db_exists = file_exists(
            FileExistsRequest(schema_version="1.0", path=settings.reports_db),
            ctx,
        ).exists
        if reports_db_exists:
            metadata = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=settings.reports_db, file_id=file_id
                ),
                ctx,
            )
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
        html_snapshot=html_snapshot,
        html_path=request.html_path,
        output_dir=settings.output_dir,
        base_url=base_url,
        auth_header=auth_header,
        ssl_verify=settings.wp.ssl_verify,
        ca_bundle_path=settings.wp.ca_bundle_path,
        media_upload_workers=settings.media_upload_workers,
        ctx=ctx,
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
    card_media_ids: dict[str, int] = {}
    if card_manifest is not None:
        card_media_ids = _upload_report_card_covers(
            manifest=card_manifest,
            html_path=request.html_path,
            output_dir=settings.output_dir,
            base_url=base_url,
            auth_header=auth_header,
            ssl_verify=settings.wp.ssl_verify,
            ca_bundle_path=settings.wp.ca_bundle_path,
            ctx=ctx,
        )
        featured_media_id = card_media_ids["large"]
    rendered_body_html = replace_image_sources(html_snapshot.body_html, image_map)
    # Proxy-backed digest images stay more reliable on the WP frontend without
    # responsive srcset/sizes candidates that still point at synthetic query URLs.
    rendered_body_html = strip_image_srcset_and_sizes(rendered_body_html)
    body_html, file_id_marker_inserted = _ensure_hidden_file_id_marker(
        rendered_body_html,
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

    title = str(html_snapshot.title or "").strip() or Path(request.html_path).stem
    slug = str(request.slug or "").strip() or slugify(title)

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
            meta=(
                _report_card_post_meta(card_manifest, card_media_ids)
                if card_manifest is not None
                else None
            ),
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


def _load_report_card_manifest(
    html_path: str,
    output_dir: str,
    ctx: RunContext,
) -> ReportCardManifest:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(output_dir) / source.name
    manifest_path = source.with_suffix("") / "report-card-manifest.json"
    if not file_exists(
        FileExistsRequest(schema_version="1.0", path=str(manifest_path)), ctx
    ).exists:
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest is required before WordPress publication",
            retryable=False,
            context={"expected_path": str(manifest_path)},
        )
    content = read_text(
        ReadTextRequest(schema_version="1.0", path=str(manifest_path)), ctx
    ).content
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest must contain valid JSON",
            cause=exc,
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Report-card manifest must contain a JSON object",
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        )
    return ReportCardManifest.from_dict(payload)


def _upload_report_card_covers(
    *,
    manifest: ReportCardManifest,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> dict[str, int]:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(output_dir) / source.name
    report_dir = source.with_suffix("").resolve()
    jobs: dict[str, _MediaUploadJob] = {}
    for size in ("small", "medium", "large"):
        asset = getattr(manifest.covers, size)
        local_path = (report_dir / asset.output_path).resolve()
        try:
            local_path.relative_to(report_dir)
        except ValueError as exc:
            raise AppError(
                code="cover_asset_set_incomplete",
                message="Report-card cover path escapes the report directory",
                cause=exc,
                retryable=False,
                context={"size": size, "output_path": asset.output_path},
            ) from exc
        if not file_exists(
            FileExistsRequest(schema_version="1.0", path=str(local_path)), ctx
        ).exists:
            raise AppError(
                code="cover_asset_set_incomplete",
                message="Report-card cover file is missing",
                retryable=False,
                context={"size": size, "output_path": str(local_path)},
            )
        jobs[size] = _MediaUploadJob(
            src=asset.output_path,
            local_path=str(local_path),
            is_preview=size == "large",
        )
    ids: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_size = {
            executor.submit(
                _upload_single_media,
                job=job,
                base_url=base_url,
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
            ): size
            for size, job in jobs.items()
        }
        for future in as_completed(future_to_size):
            ids[future_to_size[future]] = future.result().media_id
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_report_card_covers_uploaded",
            module=logger.name,
            fields={
                "small_id": ids["small"],
                "medium_id": ids["medium"],
                "large_id": ids["large"],
            },
        )
    )
    return ids


def _report_card_post_meta(
    manifest: ReportCardManifest,
    media_ids: dict[str, int],
) -> dict[str, object]:
    return {
        "ml_card_schema_version": manifest.schema_version,
        "ml_card_title_scale": manifest.title_scale,
        "ml_card_tldr_compact": manifest.tldr_compact,
        "ml_card_tldr_standard": manifest.tldr_standard,
        "ml_card_key_insights": list(manifest.key_insights),
        "ml_card_geography_scope": manifest.geography_scope,
        "ml_card_cover_fingerprint": {
            "geometry_family": manifest.fingerprint.geometry_family,
            "seed": manifest.fingerprint.seed,
        },
        "ml_card_cover_small_id": media_ids["small"],
        "ml_card_cover_medium_id": media_ids["medium"],
        "ml_card_cover_large_id": media_ids["large"],
    }


def _resolve_html_snapshot(
    request: PublishRequest, ctx: RunContext
) -> tuple[PublishHtmlSnapshot, str]:
    if request.html_snapshot is not None:
        return request.html_snapshot, "request_snapshot"
    if request.html_text is not None:
        return build_publish_html_snapshot(request.html_text), "request_html_text"
    html_text = read_text(
        ReadTextRequest(schema_version="1.0", path=request.html_path), ctx
    ).content
    return build_publish_html_snapshot(html_text), "path"


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
    *,
    html_snapshot: PublishHtmlSnapshot,
    html_path: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    media_upload_workers: int,
    ctx: RunContext,
) -> Tuple[Dict[str, str], Optional[int]]:
    sources = list(html_snapshot.image_sources)
    if not sources:
        return {}, None

    preview_src = html_snapshot.preview_image_src
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
    prepared = _prepare_media_upload_payload(
        filename=Path(local_path).name,
        mime_type=mime_type or "image/png",
        data=data_resp.content,
        ctx=ctx,
    )
    alt_text = Path(src).stem.replace("-", " ")
    return WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url=base_url,
        auth_header=auth_header,
        filename=prepared.filename,
        mime_type=prepared.mime_type,
        data=prepared.data,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        alt_text=alt_text,
    )


def _prepare_media_upload_payload(
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    ctx: RunContext,
) -> _PreparedMediaPayload:
    original_size = len(data)
    if not str(mime_type or "").startswith("image/"):
        return _PreparedMediaPayload(
            filename=filename,
            mime_type=mime_type,
            data=data,
            optimized=False,
        )
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (OSError, ValueError, TypeError) as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publish_media_optimization_skipped",
                module=logger.name,
                fields={
                    "filename": filename,
                    "reason": "image_decode_failed",
                    "error": str(exc),
                    "size": original_size,
                },
            )
        )
        return _PreparedMediaPayload(
            filename=filename,
            mime_type=mime_type,
            data=data,
            optimized=False,
        )

    original_width, original_height = image.size
    needs_optimization = (
        original_size > _MAX_MEDIA_UPLOAD_BYTES
        or max(original_width, original_height) > _MAX_MEDIA_UPLOAD_DIMENSION_PX
    )
    if not needs_optimization:
        return _PreparedMediaPayload(
            filename=filename,
            mime_type=mime_type,
            data=data,
            optimized=False,
        )

    image.thumbnail(
        (_MAX_MEDIA_UPLOAD_DIMENSION_PX, _MAX_MEDIA_UPLOAD_DIMENSION_PX),
        Image.Resampling.LANCZOS,
    )
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        output_image = background
    else:
        output_image = image.convert("RGB")
    output = BytesIO()
    output_image.save(
        output,
        format="JPEG",
        quality=_MEDIA_JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    optimized_data = output.getvalue()
    if len(optimized_data) >= original_size:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publish_media_optimization_skipped",
                module=logger.name,
                fields={
                    "filename": filename,
                    "reason": "optimized_not_smaller",
                    "original_size": original_size,
                    "optimized_size": len(optimized_data),
                    "width": original_width,
                    "height": original_height,
                },
            )
        )
        return _PreparedMediaPayload(
            filename=filename,
            mime_type=mime_type,
            data=data,
            optimized=False,
        )
    optimized_filename = f"{Path(filename).stem}.jpg"
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publish_media_optimized",
            module=logger.name,
            fields={
                "filename": filename,
                "optimized_filename": optimized_filename,
                "original_size": original_size,
                "optimized_size": len(optimized_data),
                "original_width": original_width,
                "original_height": original_height,
                "optimized_width": output_image.size[0],
                "optimized_height": output_image.size[1],
            },
        )
    )
    return _PreparedMediaPayload(
        filename=optimized_filename,
        mime_type="image/jpeg",
        data=optimized_data,
        optimized=True,
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
