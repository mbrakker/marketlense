from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.contracts.cover_images import CoverImageRenderRequest, CoverImageRenderResponse
from src.contracts.report_cards import GEOMETRY_FAMILIES
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_image_service")
FONT_SIZE_STEP = 2
RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]
Point = Tuple[int, int]


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _parse_hex_color(value: str, label: str) -> RGB:
    text = _normalize_text(value)
    if not text.startswith("#"):
        raise AppError(
            code="cover_color_invalid",
            message=f"{label} must be hex color",
            retryable=False,
        )
    hex_value = text[1:]
    if len(hex_value) == 3:
        hex_value = "".join(character * 2 for character in hex_value)
    if len(hex_value) != 6:
        raise AppError(
            code="cover_color_invalid",
            message=f"{label} must be 3 or 6 hex digits",
            retryable=False,
        )
    try:
        return (
            int(hex_value[0:2], 16),
            int(hex_value[2:4], 16),
            int(hex_value[4:6], 16),
        )
    except ValueError as exc:
        raise AppError(
            code="cover_color_invalid",
            message=f"{label} has invalid hex digits",
            cause=exc,
            retryable=False,
        ) from exc


def _rgba(color: RGB, alpha: int) -> RGBA:
    return color[0], color[1], color[2], alpha


def _load_font(path: str, size: int, label: str) -> ImageFont.FreeTypeFont:
    if not path:
        raise AppError(
            code="cover_font_missing",
            message=f"Missing font path for {label}",
            retryable=False,
        )
    try:
        return ImageFont.truetype(path, size=size)
    except OSError as exc:
        raise AppError(
            code="cover_font_invalid",
            message=f"Unable to load font: {path}",
            cause=exc,
            retryable=False,
        ) from exc


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(
    text: str,
    max_width: int,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if _text_bbox(draw, candidate, font)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if _text_bbox(draw, word, font)[0] <= max_width:
            current = word
            continue
        fragments = re.findall(r"[^-]+-?", word)
        if len(fragments) <= 1:
            current = word
            continue
        for fragment in fragments:
            candidate = f"{current}{fragment}"
            if current and _text_bbox(draw, candidate, font)[0] > max_width:
                lines.append(current)
                current = fragment
            else:
                current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_multiline_text(
    *,
    text: str,
    label: str,
    overflow_code: str,
    size_name: str,
    font_path: str,
    max_width: int,
    max_height: int,
    max_size: int,
    min_size: int,
    line_spacing: float,
    draw: ImageDraw.ImageDraw,
) -> tuple[ImageFont.FreeTypeFont, List[str], int, int]:
    for size in range(max_size, min_size - 1, -FONT_SIZE_STEP):
        font = _load_font(font_path, size, label)
        lines = _wrap_text(text, max_width, draw, font)
        if not lines:
            continue
        line_height = _text_bbox(draw, "Ag", font)[1]
        spacing = int(line_height * line_spacing)
        text_height = line_height * len(lines) + spacing * (len(lines) - 1)
        max_line = max(_text_bbox(draw, line, font)[0] for line in lines)
        if text_height <= max_height and max_line <= max_width:
            return font, lines, line_height, spacing
    raise AppError(
        code=overflow_code,
        message=f"Complete {label} text does not fit the {size_name} zone",
        retryable=False,
        context={"field": label, "text": text, "size": size_name},
    )


def _fit_single_line(
    *,
    text: str,
    font_path: str,
    max_width: int,
    max_size: int,
    min_size: int,
    draw: ImageDraw.ImageDraw,
    label: str,
) -> ImageFont.FreeTypeFont:
    for size in range(max_size, min_size - 1, -FONT_SIZE_STEP):
        font = _load_font(font_path, size, label)
        if _text_bbox(draw, text, font)[0] <= max_width:
            return font
    raise AppError(
        code="cover_text_overflow",
        message=f"Complete {label} text does not fit its approved zone",
        retryable=False,
        context={"field": label, "text": text},
    )


def _draw_line_primitive(
    draw: ImageDraw.ImageDraw,
    points: List[Point],
    color: RGBA,
    *,
    width: int,
    dot_radius: int = 0,
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    if dot_radius > 0:
        for x, y in (points[0], points[-1]):
            draw.ellipse(
                [x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius],
                fill=color,
            )


def _draw_band_primitive(
    draw: ImageDraw.ImageDraw,
    points: List[Point],
    color: RGBA,
    *,
    thickness: int,
) -> None:
    if len(points) < 2:
        return
    upper = [(x, y - thickness) for x, y in points]
    lower = [(x, y + thickness) for x, y in reversed(points)]
    draw.polygon(upper + lower, fill=color)


def _draw_field_primitive(
    draw: ImageDraw.ImageDraw,
    bounds: Tuple[int, int, int, int],
    rng: random.Random,
    color: RGBA,
    *,
    count: int,
) -> None:
    left, top, right, bottom = bounds
    for _ in range(count):
        x = rng.randint(left, right)
        y = rng.randint(top, bottom)
        radius = rng.randint(2, 6)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def _draw_node_primitive(
    draw: ImageDraw.ImageDraw,
    center: Point,
    radius: int,
    color: RGBA,
) -> None:
    x, y = center
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def _draw_orbit_primitive(
    draw: ImageDraw.ImageDraw,
    bounds: Tuple[int, int, int, int],
    color: RGBA,
    *,
    width: int,
    node_at: float,
) -> None:
    draw.ellipse(bounds, outline=color, width=width)
    left, top, right, bottom = bounds
    x = int(left + (right - left) * node_at)
    y = int((top + bottom) / 2)
    _draw_node_primitive(draw, (x, y), max(4, width * 2), color)


def _draw_envelope_primitive(
    draw: ImageDraw.ImageDraw,
    upper: List[Point],
    lower: List[Point],
    fill: RGBA,
    outline: RGBA,
    *,
    width: int,
) -> None:
    draw.polygon(upper + list(reversed(lower)), fill=fill)
    _draw_line_primitive(draw, upper, outline, width=width)
    _draw_line_primitive(draw, lower, outline, width=width)


def _draw_matrix_primitive(
    draw: ImageDraw.ImageDraw,
    bounds: Tuple[int, int, int, int],
    base: RGBA,
    highlight: RGBA,
    rng: random.Random,
) -> None:
    left, top, right, bottom = bounds
    rows, columns = 7, 8
    cell_width = max(1, (right - left) // columns)
    cell_height = max(1, (bottom - top) // rows)
    for row in range(rows):
        for column in range(columns):
            inset = 5
            x1 = left + column * cell_width + inset
            y1 = top + row * cell_height + inset
            x2 = left + (column + 1) * cell_width - inset
            y2 = top + (row + 1) * cell_height - inset
            draw.rounded_rectangle(
                [x1, y1, x2, y2],
                radius=5,
                fill=highlight if rng.random() > 0.82 else base,
            )


def _geometry_bounds(request: CoverImageRenderRequest) -> Tuple[int, int, int, int]:
    width = request.layout.width
    height = request.layout.height
    if request.size == "small":
        return (
            int(width * 0.54),
            int(height * 0.10),
            int(width * 0.97),
            int(height * 0.86),
        )
    return int(width * 0.16), int(height * 0.11), int(width * 0.96), int(height * 0.83)


def _series_points(
    bounds: Tuple[int, int, int, int],
    rng: random.Random,
    *,
    mode: str,
) -> List[Point]:
    left, top, right, bottom = bounds
    count = 7
    points: List[Point] = []
    for index in range(count):
        progress = index / (count - 1)
        x = int(left + (right - left) * progress)
        if mode == "rising":
            baseline = bottom - int((bottom - top) * 0.72 * progress)
        elif mode == "falling":
            baseline = top + int((bottom - top) * 0.72 * progress)
        else:
            baseline = int((top + bottom) / 2)
            baseline += int((bottom - top) * (0.18 if index % 2 else -0.18))
        points.append((x, baseline + rng.randint(-22, 22)))
    return points


def _draw_geometry(
    image: Image.Image,
    request: CoverImageRenderRequest,
    rng: random.Random,
    geometry: RGB,
    highlight: RGB,
) -> None:
    family = request.fingerprint.geometry_family
    if family not in GEOMETRY_FAMILIES:
        raise AppError(
            code="cover_fingerprint_invalid",
            message="Unknown cover geometry family",
            retryable=False,
            context={"geometry_family": family},
        )
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    bounds = _geometry_bounds(request)
    left, top, right, bottom = bounds
    base = _rgba(geometry, 92)
    strong = _rgba(highlight, 178)
    soft = _rgba(geometry, 42)
    width = max(3, request.layout.width // 300)

    if family in {
        "ascending_trajectory",
        "descending_trajectory",
        "volatility_corridor",
    }:
        mode = {
            "ascending_trajectory": "rising",
            "descending_trajectory": "falling",
            "volatility_corridor": "volatile",
        }[family]
        points = _series_points(bounds, rng, mode=mode)
        _draw_band_primitive(draw, points, soft, thickness=max(16, width * 5))
        _draw_line_primitive(draw, points, strong, width=width, dot_radius=width * 2)
    elif family in {"convergence_funnel", "divergence_fan", "parallel_bands"}:
        for index in range(5):
            start_y = top + int((bottom - top) * (index + 1) / 6)
            if family == "convergence_funnel":
                end_y = int((top + bottom) / 2) + (index - 2) * 10
            elif family == "divergence_fan":
                start_y = int((top + bottom) / 2) + (index - 2) * 10
                end_y = top + int((bottom - top) * (index + 1) / 6)
            else:
                end_y = start_y - int((bottom - top) * 0.08)
            points = [(left, start_y), (right, end_y)]
            _draw_band_primitive(draw, points, base, thickness=max(6, width * 2))
            _draw_line_primitive(draw, points, strong, width=max(2, width - 1))
    elif family in {"ranked_strata", "hierarchy_terraces"}:
        for index in range(6):
            y = bottom - index * max(34, (bottom - top) // 8)
            start = left + (index * 26 if family == "hierarchy_terraces" else 0)
            end = right - index * max(24, (right - left) // 14)
            draw.rounded_rectangle(
                [start, y - 14, end, y + 14],
                radius=12,
                fill=strong if index == 5 else base,
            )
    elif family == "distribution_field":
        _draw_field_primitive(draw, bounds, rng, base, count=88)
        _draw_field_primitive(draw, bounds, rng, strong, count=12)
    elif family == "concentration_core":
        center = (int((left + right) / 2), int((top + bottom) / 2))
        for radius in range(min(right - left, bottom - top) // 2, 40, -70):
            draw.ellipse(
                [
                    center[0] - radius,
                    center[1] - radius,
                    center[0] + radius,
                    center[1] + radius,
                ],
                outline=base,
                width=width,
            )
        _draw_node_primitive(draw, center, 28, strong)
        _draw_field_primitive(draw, bounds, rng, base, count=36)
    elif family == "flow_channels":
        for index in range(5):
            offset = index * max(28, (bottom - top) // 12)
            points = [
                (left, top + offset),
                (int((left + right) / 2), top + offset + rng.randint(30, 90)),
                (right, top + offset + rng.randint(-20, 40)),
            ]
            _draw_band_primitive(draw, points, soft, thickness=14)
            _draw_line_primitive(draw, points, strong, width=width)
    elif family == "network_constellation":
        nodes = [
            (rng.randint(left, right), rng.randint(top, bottom)) for _ in range(18)
        ]
        for index, node in enumerate(nodes):
            nearest = sorted(
                nodes[index + 1 :],
                key=lambda other: (node[0] - other[0]) ** 2 + (node[1] - other[1]) ** 2,
            )[:2]
            for other in nearest:
                _draw_line_primitive(draw, [node, other], base, width=max(1, width - 2))
        for index, node in enumerate(nodes):
            _draw_node_primitive(draw, node, 8 if index % 4 else 14, strong)
    elif family == "cycle_orbit":
        inset = 0
        for index in range(4):
            orbit = (left + inset, top + inset, right - inset, bottom - inset)
            _draw_orbit_primitive(
                draw,
                orbit,
                strong if index == 0 else base,
                width=width,
                node_at=0.22 + index * 0.16,
            )
            inset += max(34, min(right - left, bottom - top) // 12)
    elif family in {"forecast_horizon", "uncertainty_envelope"}:
        center_series = _series_points(bounds, rng, mode="rising")
        spread = [int((bottom - top) * (0.05 + index * 0.018)) for index in range(7)]
        upper = [(x, y - spread[index]) for index, (x, y) in enumerate(center_series)]
        lower = [(x, y + spread[index]) for index, (x, y) in enumerate(center_series)]
        _draw_envelope_primitive(draw, upper, lower, soft, base, width=width)
        if family == "forecast_horizon":
            _draw_line_primitive(
                draw,
                center_series,
                strong,
                width=width,
                dot_radius=width * 2,
            )
        else:
            midline = [
                (upper_point[0], int((upper_point[1] + lower_point[1]) / 2))
                for upper_point, lower_point in zip(upper, lower)
            ]
            _draw_line_primitive(draw, midline, strong, width=width)
    else:
        _draw_matrix_primitive(draw, bounds, base, strong, rng)

    image.alpha_composite(overlay)


def _draw_background_planes(
    image: Image.Image,
    elevated: RGB,
    geometry: RGB,
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    draw.polygon(
        [
            (int(width * 0.42), 0),
            (width, 0),
            (width, int(height * 0.72)),
            (int(width * 0.64), height),
        ],
        fill=_rgba(elevated, 132),
    )
    grid_color = _rgba(geometry, 22)
    step = max(48, min(width, height) // 14)
    for x in range(0, width + step, step):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height + step, step):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)
    image.alpha_composite(overlay)


def _save_png(image: Image.Image, output_path: str) -> None:
    path = Path(output_path)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(temporary_path, format="PNG")
        temporary_path.replace(path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            # Cleanup is best-effort here so the original render failure remains primary.
            logger.debug(
                "Cover-render temp cleanup failed",
                extra={
                    "event": "cover_render_temp_cleanup_failed",
                    "path": str(temporary_path),
                    "error_type": type(cleanup_error).__name__,
                },
            )
        raise AppError(
            code="cover_render_failed",
            message=f"Unable to write cover image: {output_path}",
            cause=exc,
            retryable=True,
            context={"output_path": output_path},
        ) from exc


def render_cover_image(
    request: CoverImageRenderRequest,
    ctx: RunContext,
) -> CoverImageRenderResponse:
    title = _normalize_text(request.title)
    publisher = _normalize_text(request.publisher)
    period = _normalize_text(request.time_period)
    if not title:
        raise AppError(
            code="cover_title_missing",
            message="Report title is required",
            retryable=False,
        )
    layout = request.layout
    style = request.style
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cover_render_start",
            module=logger.name,
            fields={
                "output_path": request.output_path,
                "family": request.fingerprint.geometry_family,
                "size": request.size,
                "seed": request.fingerprint.seed,
                "width": layout.width,
                "height": layout.height,
            },
        )
    )

    background = _parse_hex_color(style.background_color, "background")
    elevated = _parse_hex_color(style.background_elevated_color, "background_elevated")
    geometry = _parse_hex_color(style.geometry_color, "geometry")
    highlight = _parse_hex_color(style.geometry_highlight_color, "geometry_highlight")
    text_color = _parse_hex_color(style.text_color, "text")
    image = Image.new("RGBA", (layout.width, layout.height), _rgba(background, 255))
    _draw_background_planes(image, elevated, geometry)
    rng = random.Random(request.fingerprint.seed)
    _draw_geometry(image, request, rng, geometry, highlight)
    draw = ImageDraw.Draw(image)

    publisher_font = _fit_single_line(
        text=publisher,
        font_path=style.font_regular_path,
        max_width=layout.publisher_width,
        max_size=layout.publisher_font_max,
        min_size=layout.publisher_font_min,
        draw=draw,
        label="publisher",
    )
    title_font, title_lines, line_height, spacing = _fit_multiline_text(
        text=title,
        label="cover title",
        overflow_code="cover_title_overflow",
        size_name=request.size,
        font_path=style.font_bold_path,
        max_width=layout.title_width,
        max_height=layout.title_height,
        max_size=layout.title_font_max,
        min_size=layout.title_font_min,
        line_spacing=layout.title_line_spacing,
        draw=draw,
    )
    if period:
        (
            period_font,
            period_lines,
            period_line_height,
            period_spacing,
        ) = _fit_multiline_text(
            text=period,
            label="covered period",
            overflow_code="cover_text_overflow",
            size_name=request.size,
            font_path=style.font_regular_path,
            max_width=layout.period_width,
            max_height=layout.period_height,
            max_size=layout.period_font_max,
            min_size=layout.period_font_min,
            line_spacing=0.15,
            draw=draw,
        )
    else:
        period_font = _load_font(
            style.font_regular_path,
            layout.period_font_max,
            "covered period",
        )
        period_lines = []
        period_line_height = 0
        period_spacing = 0

    if publisher:
        draw.text(
            (layout.publisher_x, layout.publisher_y),
            publisher,
            font=publisher_font,
            fill=_rgba(text_color, 230),
        )
    current_y = layout.title_y
    for index, line in enumerate(title_lines):
        draw.text(
            (layout.title_x, current_y),
            line,
            font=title_font,
            fill=_rgba(text_color, 255),
        )
        if index < len(title_lines) - 1:
            current_y += line_height + spacing
    period_y = layout.period_y
    for index, line in enumerate(period_lines):
        draw.text(
            (layout.period_x, period_y),
            line,
            font=period_font,
            fill=_rgba(text_color, 218),
        )
        if index < len(period_lines) - 1:
            period_y += period_line_height + period_spacing
    if period_lines:
        period_height = period_line_height * len(period_lines)
        period_height += period_spacing * (len(period_lines) - 1)
        underline_y = layout.period_y + period_height + 12
        draw.line(
            [
                (layout.period_x, underline_y),
                (layout.period_x + min(layout.period_width, 190), underline_y),
            ],
            fill=_rgba(highlight, 170),
            width=max(2, layout.width // 500),
        )
        draw.ellipse(
            [
                layout.period_x + min(layout.period_width, 190) - 5,
                underline_y - 5,
                layout.period_x + min(layout.period_width, 190) + 5,
                underline_y + 5,
            ],
            fill=_rgba(highlight, 220),
        )

    _save_png(image, request.output_path)
    title_font_size = int(getattr(title_font, "size", layout.title_font_min))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cover_render_complete",
            module=logger.name,
            fields={
                "output_path": request.output_path,
                "family": request.fingerprint.geometry_family,
                "size": request.size,
                "seed": request.fingerprint.seed,
                "title": title,
                "title_font_size": title_font_size,
            },
        )
    )
    return CoverImageRenderResponse(
        schema_version="2.0",
        output_path=request.output_path,
        width=layout.width,
        height=layout.height,
        title_font_size=title_font_size,
    )
