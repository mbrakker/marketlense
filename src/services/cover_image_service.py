from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.contracts.cover_images import CoverImageRenderRequest, CoverImageRenderResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_image_service")

FONT_SIZE_STEP = 2


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _parse_hex_color(value: str, label: str) -> Tuple[int, int, int]:
    text = _normalize_text(value)
    if not text.startswith("#"):
        raise AppError(code="cover_color_invalid", message=f"{label} must be hex color", retryable=False)
    hex_value = text[1:]
    if len(hex_value) == 3:
        hex_value = "".join(ch * 2 for ch in hex_value)
    if len(hex_value) != 6:
        raise AppError(code="cover_color_invalid", message=f"{label} must be 3 or 6 hex digits", retryable=False)
    try:
        return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise AppError(code="cover_color_invalid", message=f"{label} has invalid hex digits", cause=exc, retryable=False) from exc


def _load_font(path: str, size: int, label: str) -> ImageFont.FreeTypeFont:
    if not path:
        raise AppError(code="cover_font_missing", message=f"Missing font path for {label}", retryable=False)
    try:
        return ImageFont.truetype(path, size=size)
    except OSError as exc:
        raise AppError(code="cover_font_invalid", message=f"Unable to load font: {path}", cause=exc, retryable=False) from exc


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _split_long_word(word: str, max_width: int, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> List[str]:
    if not word:
        return []
    chunks: List[str] = []
    current = ""
    for char in word:
        candidate = f"{current}{char}"
        if _text_bbox(draw, candidate, font)[0] <= max_width:
            current = candidate
        else:
            if current:
                chunks.append(current)
                current = char
            else:
                chunks.append(char)
                current = ""
    if current:
        chunks.append(current)
    return chunks


def _wrap_text(text: str, max_width: int, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if _text_bbox(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if _text_bbox(draw, word, font)[0] <= max_width:
            current = word
            continue
        for chunk in _split_long_word(word, max_width, draw, font):
            lines.append(chunk)
        current = ""
    if current:
        lines.append(current)
    return lines


def _fit_multiline_text(
    text: str,
    font_path: str,
    max_width: int,
    max_height: int,
    max_size: int,
    min_size: int,
    line_spacing: float,
    draw: ImageDraw.ImageDraw,
) -> tuple[ImageFont.FreeTypeFont, List[str]]:
    for size in range(max_size, min_size - 1, -FONT_SIZE_STEP):
        font = _load_font(font_path, size, "title")
        lines = _wrap_text(text, max_width, draw, font)
        if not lines:
            continue
        line_height = _text_bbox(draw, "Ag", font)[1]
        spacing = int(line_height * line_spacing)
        text_height = line_height * len(lines) + spacing * (len(lines) - 1)
        max_line = max(_text_bbox(draw, line, font)[0] for line in lines)
        if text_height <= max_height and max_line <= max_width:
            return font, lines
    font = _load_font(font_path, min_size, "title")
    return font, _wrap_text(text, max_width, draw, font)


def _fit_single_line(
    text: str,
    font_path: str,
    max_width: int,
    base_size: int,
    min_size: int,
    draw: ImageDraw.ImageDraw,
    label: str,
) -> ImageFont.FreeTypeFont:
    for size in range(base_size, min_size - 1, -FONT_SIZE_STEP):
        font = _load_font(font_path, size, label)
        if _text_bbox(draw, text, font)[0] <= max_width:
            return font
    return _load_font(font_path, min_size, label)


def _normalize_time_period(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _load_background(style_path: str | None, size: tuple[int, int]) -> Image.Image:
    if not style_path:
        raise AppError(code="cover_background_missing", message="Background image path not provided", retryable=False)
    path = Path(style_path)
    if not path.exists():
        raise AppError(code="cover_background_missing", message=f"Background image not found: {style_path}", retryable=False)
    try:
        image = Image.open(path)
    except OSError as exc:
        raise AppError(code="cover_background_invalid", message=f"Unable to open background image: {style_path}", cause=exc, retryable=False) from exc
    return image.convert("RGB").resize(size, Image.LANCZOS)


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def render_cover_image(request: CoverImageRenderRequest, ctx: RunContext) -> CoverImageRenderResponse:
    title = _normalize_text(request.title)
    publisher = _normalize_text(request.publisher)
    if not title:
        raise AppError(code="cover_title_missing", message="Report title is required", retryable=False)
    if not publisher:
        raise AppError(code="cover_publisher_missing", message="Publisher is required", retryable=False)

    layout = request.layout
    style = request.style
    logger.info(log_event(
        ctx,
        role="service",
        event="cover_render_start",
        module=logger.name,
        fields={
            "output_path": request.output_path,
            "width": layout.width,
            "height": layout.height,
            "accent_width": layout.accent_width,
        },
    ))

    bg_color = _parse_hex_color(style.background_color, "background_color")
    accent_color = _parse_hex_color(style.accent_color, "accent_color")
    text_color = _parse_hex_color(style.text_color, "text_color")
    pill_fill = _parse_hex_color(layout.pill_fill_color, "pill_fill_color")
    pill_text = _parse_hex_color(layout.pill_text_color, "pill_text_color")
    pill_border = _parse_hex_color(layout.pill_border_color, "pill_border_color")

    size = (layout.width, layout.height)
    if style.background_image_path:
        base_image = _load_background(style.background_image_path, size)
    else:
        base_image = Image.new("RGB", size, bg_color)

    draw = ImageDraw.Draw(base_image)
    draw.rectangle([0, 0, layout.accent_width, layout.height], fill=accent_color)

    content_left = layout.accent_width + layout.margin_x
    content_right = layout.width - layout.margin_x
    max_width = max(content_right - content_left, 0)

    label_text = _normalize_text(request.category_label)
    label_font = _fit_single_line(
        label_text,
        style.font_regular_path,
        max_width,
        layout.label_font_size,
        max(12, layout.label_font_size // 2),
        draw,
        "category_label",
    )

    label_y = layout.margin_y
    if label_text:
        draw.text((content_left, label_y), label_text, font=label_font, fill=text_color)

    publisher_font = _fit_single_line(
        publisher,
        style.font_regular_path,
        max_width,
        layout.publisher_font_size,
        max(12, layout.publisher_font_size // 2),
        draw,
        "publisher",
    )

    publisher_width, publisher_height = _text_bbox(draw, publisher, publisher_font)
    publisher_y = layout.height - layout.margin_y - publisher_height

    time_period = _normalize_time_period(request.time_period)
    pill_height = 0
    pill_width = 0
    pill_y = publisher_y - layout.footer_gap
    if time_period:
        time_font = _fit_single_line(
            time_period,
            style.font_regular_path,
            max_width,
            layout.time_font_size,
            max(12, layout.time_font_size // 2),
            draw,
            "time_period",
        )
        time_text_width, time_text_height = _text_bbox(draw, time_period, time_font)
        pill_width = time_text_width + layout.pill_padding_x * 2
        pill_height = time_text_height + layout.pill_padding_y * 2
        pill_y = publisher_y - layout.footer_gap - pill_height

    title_top = label_y + _text_bbox(draw, label_text or "Ag", label_font)[1] + layout.label_gap
    title_bottom = pill_y - layout.footer_gap if time_period else publisher_y - layout.footer_gap
    title_height = max(title_bottom - title_top, layout.title_font_min)
    title_font, title_lines = _fit_multiline_text(
        title,
        style.font_bold_path,
        max_width,
        title_height,
        layout.title_font_max,
        layout.title_font_min,
        layout.title_line_spacing,
        draw,
    )
    line_height = _text_bbox(draw, "Ag", title_font)[1]
    spacing = int(line_height * layout.title_line_spacing)
    current_y = title_top
    for index, line in enumerate(title_lines):
        draw.text((content_left, current_y), line, font=title_font, fill=text_color)
        if index < len(title_lines) - 1:
            current_y += line_height + spacing

    draw.text((content_left, publisher_y), publisher, font=publisher_font, fill=text_color)

    if time_period:
        pill_x = content_left
        pill_box = [pill_x, pill_y, pill_x + pill_width, pill_y + pill_height]
        draw.rounded_rectangle(
            pill_box,
            radius=layout.pill_radius,
            fill=pill_fill,
            outline=pill_border,
            width=layout.pill_border_width,
        )
        text_x = pill_x + layout.pill_padding_x
        text_y = pill_y + layout.pill_padding_y
        draw.text((text_x, text_y), time_period, font=time_font, fill=pill_text)

    _ensure_dir(request.output_path)
    base_image.save(request.output_path, format="PNG")

    logger.info(log_event(
        ctx,
        role="service",
        event="cover_render_complete",
        module=logger.name,
        fields={"output_path": request.output_path},
    ))
    return CoverImageRenderResponse(
        schema_version="1.0",
        output_path=request.output_path,
        width=layout.width,
        height=layout.height,
    )
