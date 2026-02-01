from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from src.contracts.cover_images import (
    CoverImageLayout,
    CoverImageStyle,
    CoverImageStyleConfig,
    CoverImageStyleOverrides,
    CoverStyleLoadRequest,
    CoverStyleLoadResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_style_service")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "cover-styles.yaml"


def _require_str(value: Any, label: str) -> str:
    if value is None:
        raise AppError(code="cover_style_missing", message=f"Missing required field: {label}", retryable=False)
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        raise AppError(code="cover_style_missing", message=f"Missing required field: {label}", retryable=False)
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str if value_str else None


def _require_int(value: Any, label: str) -> int:
    if value is None:
        raise AppError(code="cover_style_missing", message=f"Missing required field: {label}", retryable=False)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(code="cover_style_invalid", message=f"Invalid integer for {label}", cause=exc, retryable=False) from exc
    return parsed


def _require_float(value: Any, label: str) -> float:
    if value is None:
        raise AppError(code="cover_style_missing", message=f"Missing required field: {label}", retryable=False)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise AppError(code="cover_style_invalid", message=f"Invalid float for {label}", cause=exc, retryable=False) from exc
    return parsed


def _load_yaml(path: str) -> Dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise AppError(code="cover_style_missing", message=f"Cover style config not found: {path}", retryable=False)
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AppError(code="cover_style_invalid", message=f"Invalid cover style YAML: {path}", cause=exc, retryable=False) from exc


def _parse_layout(payload: Dict[str, Any]) -> CoverImageLayout:
    return CoverImageLayout(
        schema_version="1.0",
        width=_require_int(payload.get("width"), "layout.width"),
        height=_require_int(payload.get("height"), "layout.height"),
        accent_width=_require_int(payload.get("accent_width"), "layout.accent_width"),
        margin_x=_require_int(payload.get("margin_x"), "layout.margin_x"),
        margin_y=_require_int(payload.get("margin_y"), "layout.margin_y"),
        label_font_size=_require_int(payload.get("label_font_size"), "layout.label_font_size"),
        title_font_max=_require_int(payload.get("title_font_max"), "layout.title_font_max"),
        title_font_min=_require_int(payload.get("title_font_min"), "layout.title_font_min"),
        publisher_font_size=_require_int(payload.get("publisher_font_size"), "layout.publisher_font_size"),
        time_font_size=_require_int(payload.get("time_font_size"), "layout.time_font_size"),
        title_line_spacing=_require_float(payload.get("title_line_spacing"), "layout.title_line_spacing"),
        label_gap=_require_int(payload.get("label_gap"), "layout.label_gap"),
        footer_gap=_require_int(payload.get("footer_gap"), "layout.footer_gap"),
        pill_padding_x=_require_int(payload.get("pill_padding_x"), "layout.pill_padding_x"),
        pill_padding_y=_require_int(payload.get("pill_padding_y"), "layout.pill_padding_y"),
        pill_radius=_require_int(payload.get("pill_radius"), "layout.pill_radius"),
        pill_border_width=_require_int(payload.get("pill_border_width"), "layout.pill_border_width"),
        pill_fill_color=_require_str(payload.get("pill_fill_color"), "layout.pill_fill_color"),
        pill_text_color=_require_str(payload.get("pill_text_color"), "layout.pill_text_color"),
        pill_border_color=_require_str(payload.get("pill_border_color"), "layout.pill_border_color"),
    )


def _parse_style(payload: Dict[str, Any]) -> CoverImageStyle:
    return CoverImageStyle(
        schema_version="1.0",
        background_color=_require_str(payload.get("background_color"), "defaults.background_color"),
        accent_color=_require_str(payload.get("accent_color"), "defaults.accent_color"),
        text_color=_require_str(payload.get("text_color"), "defaults.text_color"),
        category_label=_optional_str(payload.get("category_label")) or "",
        font_regular_path=_require_str(payload.get("font_regular_path"), "defaults.font_regular_path"),
        font_bold_path=_require_str(payload.get("font_bold_path"), "defaults.font_bold_path"),
        background_image_path=_optional_str(payload.get("background_image_path")),
    )


def _parse_overrides(payload: Dict[str, Any]) -> CoverImageStyleOverrides:
    return CoverImageStyleOverrides(
        schema_version="1.0",
        background_color=_optional_str(payload.get("background_color")),
        accent_color=_optional_str(payload.get("accent_color")),
        text_color=_optional_str(payload.get("text_color")),
        category_label=_optional_str(payload.get("category_label")),
        font_regular_path=_optional_str(payload.get("font_regular_path")),
        font_bold_path=_optional_str(payload.get("font_bold_path")),
        background_image_path=_optional_str(payload.get("background_image_path")),
    )


def load_cover_styles(request: CoverStyleLoadRequest, ctx: RunContext) -> CoverStyleLoadResponse:
    config_path = request.path.strip() or str(DEFAULT_CONFIG_PATH)
    logger.info(log_event(
        ctx,
        role="service",
        event="cover_style_load_start",
        module=logger.name,
        fields={"path": config_path},
    ))
    data = _load_yaml(config_path)
    layout_raw = data.get("layout") or {}
    defaults_raw = data.get("defaults") or {}
    categories_raw = data.get("categories") or {}

    layout = _parse_layout(layout_raw)
    defaults = _parse_style(defaults_raw)
    categories: Dict[str, CoverImageStyleOverrides] = {}
    if isinstance(categories_raw, dict):
        for key, value in categories_raw.items():
            key_str = str(key).strip().lower()
            if not key_str:
                continue
            if not isinstance(value, dict):
                raise AppError(
                    code="cover_style_invalid",
                    message=f"Category style must be a mapping: {key_str}",
                    retryable=False,
                )
            categories[key_str] = _parse_overrides(value)

    config = CoverImageStyleConfig(
        schema_version=str(data.get("schema_version", "1.0")),
        defaults=defaults,
        categories=categories,
        layout=layout,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="cover_style_load_complete",
        module=logger.name,
        fields={
            "path": config_path,
            "category_count": len(categories),
            "width": layout.width,
            "height": layout.height,
        },
    ))
    return CoverStyleLoadResponse(schema_version="1.0", config=config)
