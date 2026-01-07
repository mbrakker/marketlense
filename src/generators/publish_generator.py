from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.contracts.files import FileExistsRequest, ReadBytesRequest, ReadTextRequest
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.report_store import ReportMetadataGetRequest
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressCategoryEnsureRequest,
    WordPressCategoryTerm,
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressTagEnsureRequest,
)
from src.contracts.categories import CategoryMappingLoadRequest
from src.services.category_mapping_service import load_mappings as load_category_mappings
from src.services.file_service import file_exists, read_bytes, read_text
from src.services.report_store_service import get_metadata
from src.services.wordpress_service import create_post, ensure_categories, ensure_tags, upload_media
from src.utils.errors import AppError
from src.utils.html_utils import (
    extract_body_html,
    extract_file_id,
    extract_image_sources,
    extract_preview_image,
    extract_title,
    replace_image_sources,
)
from src.utils.logging import log_event
from src.utils.slugify import slugify
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_generator")


def publish_html(
    request: PublishRequest,
    settings: PublishSettings,
    ctx: RunContext,
) -> PublishOutcome:
    logger.info(log_event(
        ctx,
        role="generator",
        event="publish_start",
        module=logger.name,
        fields={"html_path": request.html_path},
    ))

    html_resp = read_text(ReadTextRequest(schema_version="1.0", path=request.html_path), ctx)
    html_text = html_resp.content
    file_id = request.file_id or extract_file_id(html_text)
    if not file_id:
        logger.info(log_event(
            ctx,
            role="generator",
            event="publish_missing_file_id",
            module=logger.name,
            fields={"html_path": request.html_path},
        ))
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=None,
            status="error",
            error="missing_file_id",
        )

    auth_header = _resolve_auth_header(settings, ctx)
    base_url = settings.wp.site_url.rstrip("/")

    metadata = get_metadata(
        ReportMetadataGetRequest(schema_version="1.1", db_path=settings.reports_db, file_id=file_id),
        ctx,
    )
    category_ids_for_wp: list[int] = []
    tag_ids_for_wp: list[int] = []
    if metadata and metadata.categories:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(schema_version="1.0", path=settings.category_mapping_path, reload_if_changed=True),
            ctx,
        )
        id_to_label = {cat.id: cat.label or cat.id for cat in mappings_resp.mappings.categories}
        terms = [
            WordPressCategoryTerm(schema_version="1.0", slug=cat_id, name=id_to_label.get(cat_id, cat_id))
            for cat_id in metadata.categories
        ]
        if terms:
            ensure_resp = ensure_categories(
                WordPressCategoryEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    categories=terms,
                ),
                ctx,
            )
            category_ids_for_wp = [
                ensure_resp.slug_to_id[term.slug]
                for term in terms
                if term.slug in ensure_resp.slug_to_id
            ]
    if metadata and metadata.taxonomy:
        tag_slugs = [slugify(tag) for tag in metadata.taxonomy if slugify(tag)]
        if tag_slugs:
            ensure_tags_resp = ensure_tags(
                WordPressTagEnsureRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    tags=tag_slugs,
                ),
                ctx,
            )
            tag_ids_for_wp = [
                ensure_tags_resp.slug_to_id[slug]
                for slug in tag_slugs
                if slug in ensure_tags_resp.slug_to_id
            ]

    image_map, featured_media_id = _upload_images(
        html_text,
        settings.output_dir,
        base_url,
        auth_header,
        ctx,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="publish_images_uploaded",
        module=logger.name,
        fields={"count": len(image_map), "featured_media": featured_media_id or 0},
    ))
    rendered_html = replace_image_sources(html_text, image_map)
    body_html = extract_body_html(rendered_html)

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
            slug=slug,
            featured_media=featured_media_id,
            categories=category_ids_for_wp if category_ids_for_wp else None,
            tags=tag_ids_for_wp if tag_ids_for_wp else None,
        ),
        ctx,
    )

    logger.info(log_event(
        ctx,
        role="generator",
        event="publish_complete",
        module=logger.name,
        fields={"file_id": file_id, "post_id": post_resp.post_id, "post_url": post_resp.link},
    ))

    return PublishOutcome(
        schema_version="1.0",
        html_path=request.html_path,
        file_id=file_id,
        status="published",
        post_id=post_resp.post_id,
        post_url=post_resp.link,
    )


def _resolve_auth_header(settings: PublishSettings, ctx: RunContext) -> str:
    try:
        header = build_auth_header(
            username=settings.wp.username,
            app_password=settings.wp.app_password,
            bearer_token=settings.wp.bearer_token,
        )
    except ValueError as exc:
        raise AppError(
            code="wp_auth_missing",
            message=str(exc),
            retryable=False,
        ) from exc
    source = "bearer_token" if settings.wp.bearer_token else "app_password"
    logger.info(log_event(
        ctx,
        role="generator",
        event="publish_auth_source",
        module=logger.name,
        fields={"source": source},
    ))
    return header


def _upload_images(
    html_text: str,
    output_dir: str,
    base_url: str,
    auth_header: str,
    ctx: RunContext,
) -> Tuple[Dict[str, str], Optional[int]]:
    sources = extract_image_sources(html_text)
    if not sources:
        return {}, None

    preview_src = extract_preview_image(html_text)
    mapping: Dict[str, str] = {}
    media_ids: Dict[str, int] = {}
    featured_media_id: Optional[int] = None

    for src in sources:
        if src in mapping:
            continue
        local_path = _resolve_local_path(src, output_dir, ctx)
        if not local_path:
            if not src.startswith("http://") and not src.startswith("https://"):
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="publish_image_missing",
                    module=logger.name,
                    fields={"src": src},
                ))
            continue
        upload_resp = upload_media(
            _media_upload_request(local_path, src, base_url, auth_header, ctx),
            ctx,
        )
        mapping[src] = upload_resp.source_url
        media_ids[src] = upload_resp.media_id
        if preview_src and src == preview_src:
            featured_media_id = upload_resp.media_id

    if not featured_media_id and media_ids:
        first_src = sources[0]
        featured_media_id = media_ids.get(first_src)

    return mapping, featured_media_id


def _media_upload_request(
    local_path: str,
    src: str,
    base_url: str,
    auth_header: str,
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
        alt_text=alt_text,
    )


def _resolve_local_path(src: str, output_dir: str, ctx: RunContext) -> Optional[str]:
    rel = src.lstrip("/").replace("\\", "/")
    if rel.startswith("http://") or rel.startswith("https://"):
        return None
    path = Path(output_dir) / rel
    exists_resp = file_exists(FileExistsRequest(schema_version="1.0", path=str(path)), ctx)
    if not exists_resp.exists:
        return None
    return str(path)
