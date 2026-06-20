from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from src.contracts.cover_images import (
    CoverImageLayout,
    CoverImageProfile,
    CoverImageStyle,
    CoverImageStyleConfig,
    CoverStyleLoadRequest,
    CoverStyleLoadResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_style_service")
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "cover-styles.yaml"
)


def _require_str(value: Any, label: str) -> str:
    if value is None:
        raise AppError(
            code="cover_style_missing",
            message=f"Missing required field: {label}",
            retryable=False,
        )
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        raise AppError(
            code="cover_style_missing",
            message=f"Missing required field: {label}",
            retryable=False,
        )
    return value


def _require_int(value: Any, label: str) -> int:
    if value is None:
        raise AppError(
            code="cover_style_missing",
            message=f"Missing required field: {label}",
            retryable=False,
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="cover_style_invalid",
            message=f"Invalid integer for {label}",
            cause=exc,
            retryable=False,
        ) from exc
    return parsed


def _require_float(value: Any, label: str) -> float:
    if value is None:
        raise AppError(
            code="cover_style_missing",
            message=f"Missing required field: {label}",
            retryable=False,
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="cover_style_invalid",
            message=f"Invalid float for {label}",
            cause=exc,
            retryable=False,
        ) from exc
    return parsed


def _load_yaml(path: str) -> Dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise AppError(
            code="cover_style_missing",
            message=f"Cover style config not found: {path}",
            retryable=False,
        )
    try:
        payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AppError(
            code="cover_style_invalid",
            message=f"Invalid cover style YAML: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="cover_style_invalid",
            message=f"Cover style YAML must be a mapping: {path}",
            retryable=False,
        )
    return payload


def _parse_rect(payload: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(payload, list) or len(payload) != 4:
        raise AppError(
            code="cover_style_invalid",
            message=f"{label} must contain four integers",
            retryable=False,
        )
    values = tuple(_require_int(item, label) for item in payload)
    return values[0], values[1], values[2], values[3]


def _parse_layout(payload: Dict[str, Any], size: str) -> CoverImageLayout:
    publisher_x, publisher_y, publisher_width, publisher_height = _parse_rect(
        payload.get("publisher_rect"), f"layouts.{size}.publisher_rect"
    )
    title_x, title_y, title_width, title_height = _parse_rect(
        payload.get("title_rect"), f"layouts.{size}.title_rect"
    )
    period_x, period_y, period_width, period_height = _parse_rect(
        payload.get("period_rect"), f"layouts.{size}.period_rect"
    )
    return CoverImageLayout(
        schema_version="2.0",
        width=_require_int(payload.get("width"), f"layouts.{size}.width"),
        height=_require_int(payload.get("height"), f"layouts.{size}.height"),
        publisher_x=publisher_x,
        publisher_y=publisher_y,
        publisher_width=publisher_width,
        publisher_height=publisher_height,
        title_x=title_x,
        title_y=title_y,
        title_width=title_width,
        title_height=title_height,
        period_x=period_x,
        period_y=period_y,
        period_width=period_width,
        period_height=period_height,
        title_font_max=_require_int(
            payload.get("title_font_max"), f"layouts.{size}.title_font_max"
        ),
        title_font_min=_require_int(
            payload.get("title_font_min"), f"layouts.{size}.title_font_min"
        ),
        publisher_font_max=_require_int(
            payload.get("publisher_font_max"), f"layouts.{size}.publisher_font_max"
        ),
        publisher_font_min=_require_int(
            payload.get("publisher_font_min"), f"layouts.{size}.publisher_font_min"
        ),
        period_font_max=_require_int(
            payload.get("period_font_max"), f"layouts.{size}.period_font_max"
        ),
        period_font_min=_require_int(
            payload.get("period_font_min"), f"layouts.{size}.period_font_min"
        ),
        title_line_spacing=_require_float(
            payload.get("title_line_spacing"),
            f"layouts.{size}.title_line_spacing",
        ),
    )


def _parse_style(palette: Dict[str, Any], fonts: Dict[str, Any]) -> CoverImageStyle:
    return CoverImageStyle(
        schema_version="2.0",
        background_color=_require_str(palette.get("background"), "palette.background"),
        background_elevated_color=_require_str(
            palette.get("background_elevated"), "palette.background_elevated"
        ),
        geometry_color=_require_str(palette.get("geometry"), "palette.geometry"),
        geometry_highlight_color=_require_str(
            palette.get("geometry_highlight"), "palette.geometry_highlight"
        ),
        text_color=_require_str(palette.get("text"), "palette.text"),
        font_regular_path=_require_str(fonts.get("regular_path"), "fonts.regular_path"),
        font_bold_path=_require_str(fonts.get("bold_path"), "fonts.bold_path"),
    )


def load_cover_styles(
    request: CoverStyleLoadRequest, ctx: RunContext
) -> CoverStyleLoadResponse:
    config_path = request.path.strip() or str(DEFAULT_CONFIG_PATH)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cover_style_load_start",
            module=logger.name,
            fields={"path": config_path},
        )
    )
    data = _load_yaml(config_path)
    if str(data.get("schema_version") or "").strip() != "3.0":
        raise AppError(
            code="cover_style_invalid",
            message="Cover style config must use schema version 3.0",
            retryable=False,
        )
    profiles_raw = data.get("profiles") or {}
    if not isinstance(profiles_raw, dict):
        raise AppError(
            code="cover_style_invalid",
            message="Cover style profiles must be a mapping",
            retryable=False,
        )
    profiles = {}
    for profile_name in ("report", "briefing"):
        profile_raw = profiles_raw.get(profile_name)
        if not isinstance(profile_raw, dict):
            raise AppError(
                code="cover_style_invalid",
                message=f"Missing required cover style profile: {profile_name}",
                retryable=False,
            )
        palette_raw = profile_raw.get("palette") or {}
        fonts_raw = profile_raw.get("fonts") or {}
        layouts_raw = profile_raw.get("layouts") or {}
        if not all(
            isinstance(item, dict) for item in (palette_raw, fonts_raw, layouts_raw)
        ):
            raise AppError(
                code="cover_style_invalid",
                message=f"Cover style profile is invalid: {profile_name}",
                retryable=False,
            )
        profiles[profile_name] = CoverImageProfile(
            schema_version="1.0",
            style=_parse_style(palette_raw, fonts_raw),
            layouts={
                size: _parse_layout(layouts_raw.get(size) or {}, size)
                for size in ("small", "medium", "large")
            },
        )

    config = CoverImageStyleConfig(
        schema_version="3.0",
        profiles=profiles,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cover_style_load_complete",
            module=logger.name,
            fields={
                "path": config_path,
                "profiles": {
                    name: {
                        size: [layout.width, layout.height]
                        for size, layout in profile.layouts.items()
                    }
                    for name, profile in profiles.items()
                },
            },
        )
    )
    return CoverStyleLoadResponse(schema_version="1.0", config=config)
