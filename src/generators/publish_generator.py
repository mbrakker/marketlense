from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Dict, Optional, Tuple

from src.contracts.files import ReadBytesRequest, ReadTextRequest
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
)
from src.services.file_service import read_bytes, read_text
from src.services.wordpress_service import create_post, upload_media
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
    log_event(
        logger,
        ctx,
        role="generator",
        event="publish_start",
        fields={"html_path": request.html_path},
    )

    html_resp = read_text(ReadTextRequest(schema_version="1.0", path=request.html_path), ctx)
    html_text = html_resp.content
    file_id = request.file_id or extract_file_id(html_text)
    if not file_id:
        log_event(
            logger,
            ctx,
            role="generator",
            event="publish_missing_file_id",
            fields={"html_path": request.html_path},
        )
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=None,
            status="error",
            error="missing_file_id",
        )

    auth_header = _resolve_auth_header(settings, ctx)
    base_url = settings.wp.site_url.rstrip("/")

    image_map, featured_media_id = _upload_images(
        html_text,
        settings.output_dir,
        base_url,
        auth_header,
        ctx,
    )
    log_event(
        logger,
        ctx,
        role="generator",
        event="publish_images_uploaded",
        fields={"count": len(image_map), "featured_media": featured_media_id or 0},
    )
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
        ),
        ctx,
    )

    log_event(
        logger,
        ctx,
        role="generator",
        event="publish_complete",
        fields={"file_id": file_id, "post_id": post_resp.post_id, "post_url": post_resp.link},
    )

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
    log_event(
        logger,
        ctx,
        role="generator",
        event="publish_auth_source",
        fields={"source": source},
    )
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
        local_path = _resolve_local_path(src, output_dir)
        if not local_path:
            if not src.startswith("http://") and not src.startswith("https://"):
                log_event(
                    logger,
                    ctx,
                    role="generator",
                    event="publish_image_missing",
                    fields={"src": src},
                )
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


def _resolve_local_path(src: str, output_dir: str) -> Optional[str]:
    rel = src.lstrip("/").replace("\\", "/")
    if rel.startswith("http://") or rel.startswith("https://"):
        return None
    path = Path(output_dir) / rel
    if not path.exists():
        return None
    return str(path)
