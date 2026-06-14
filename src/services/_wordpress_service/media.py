from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path

from PIL import Image

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaPrepareRequest,
    WordPressMediaPrepareResponse,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.wordpress_service")

MAX_MEDIA_UPLOAD_BYTES = 8_000_000
MAX_MEDIA_UPLOAD_DIMENSION_PX = 1800
MEDIA_JPEG_QUALITY = 85


def prepare_media_upload(
    request: WordPressMediaPrepareRequest,
    ctx: RunContext,
) -> WordPressMediaPrepareResponse:
    original_size = len(request.data)
    if not str(request.mime_type or "").startswith("image/"):
        return _response(request, reason="not_image")
    try:
        image = Image.open(BytesIO(request.data))
        image.load()
    except (OSError, ValueError, TypeError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publish_media_optimization_skipped",
                module=logger.name,
                fields={
                    "filename": request.filename,
                    "reason": "image_decode_failed",
                    "error": str(exc),
                    "size": original_size,
                },
            )
        )
        return _response(request, reason="image_decode_failed")

    original_width, original_height = image.size
    if (
        original_size <= MAX_MEDIA_UPLOAD_BYTES
        and max(original_width, original_height) <= MAX_MEDIA_UPLOAD_DIMENSION_PX
    ):
        return _response(request, reason="within_limits")

    image.thumbnail(
        (MAX_MEDIA_UPLOAD_DIMENSION_PX, MAX_MEDIA_UPLOAD_DIMENSION_PX),
        Image.Resampling.LANCZOS,
    )
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        output_image = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        output_image.paste(rgba, mask=rgba.getchannel("A"))
    else:
        output_image = image.convert("RGB")
    output = BytesIO()
    output_image.save(
        output,
        format="JPEG",
        quality=MEDIA_JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    optimized_data = output.getvalue()
    if len(optimized_data) >= original_size:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publish_media_optimization_skipped",
                module=logger.name,
                fields={
                    "filename": request.filename,
                    "reason": "optimized_not_smaller",
                    "original_size": original_size,
                    "prepared_size": len(optimized_data),
                },
            )
        )
        return _response(request, reason="optimized_not_smaller")

    filename = f"{Path(request.filename).stem}.jpg"
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publish_media_optimized",
            module=logger.name,
            fields={
                "filename": request.filename,
                "prepared_filename": filename,
                "original_size": original_size,
                "prepared_size": len(optimized_data),
                "original_width": original_width,
                "original_height": original_height,
                "prepared_width": output_image.size[0],
                "prepared_height": output_image.size[1],
            },
        )
    )
    return WordPressMediaPrepareResponse(
        schema_version="1.0",
        filename=filename,
        mime_type="image/jpeg",
        data=optimized_data,
        optimized=True,
        reason="optimized",
        original_size_bytes=original_size,
        prepared_size_bytes=len(optimized_data),
    )


def _response(
    request: WordPressMediaPrepareRequest,
    *,
    reason: str,
) -> WordPressMediaPrepareResponse:
    return WordPressMediaPrepareResponse(
        schema_version="1.0",
        filename=request.filename,
        mime_type=request.mime_type,
        data=request.data,
        optimized=False,
        reason=reason,
        original_size_bytes=len(request.data),
        prepared_size_bytes=len(request.data),
    )
