from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from src.contracts.cover_images import (
    CoverImageGenerationOutcome,
    CoverImageGenerationRequest,
    CoverImageRenderRequest,
    CoverImageReport,
    CoverImageStyle,
    CoverImageStyleOverrides,
    CoverStyleLoadRequest,
)
from src.contracts.run_context import RunContext
from src.services.cover_image_service import render_cover_image
from src.services.cover_style_service import load_cover_styles
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.cover_image_generator")


def _normalize_report(report: CoverImageReport) -> CoverImageReport:
    title = str(report.title or "").strip()
    publisher = str(report.publisher or "").strip()
    categories = [str(cat).strip().lower() for cat in report.categories if str(cat).strip()]
    time_period = str(report.time_period).strip() if report.time_period else None
    return CoverImageReport(
        schema_version=report.schema_version,
        file_id=str(report.file_id).strip(),
        title=title,
        publisher=publisher,
        categories=categories,
        time_period=time_period,
    )


def _resolve_category(report: CoverImageReport) -> str:
    return report.categories[0] if report.categories else "default"


def _merge_style(defaults: CoverImageStyle, overrides) -> CoverImageStyle:
    return CoverImageStyle(
        schema_version=defaults.schema_version,
        background_color=overrides.background_color or defaults.background_color,
        accent_color=overrides.accent_color or defaults.accent_color,
        text_color=overrides.text_color or defaults.text_color,
        category_label=overrides.category_label or defaults.category_label,
        font_regular_path=overrides.font_regular_path or defaults.font_regular_path,
        font_bold_path=overrides.font_bold_path or defaults.font_bold_path,
        background_image_path=overrides.background_image_path or defaults.background_image_path,
    )


def _category_label(category: str, style: CoverImageStyle) -> str:
    if style.category_label.strip():
        return style.category_label
    if category == "default":
        return ""
    return category.replace("_", " ").title()


def generate_cover_images(request: CoverImageGenerationRequest, ctx: RunContext) -> List[CoverImageGenerationOutcome]:
    if not str(request.output_dir).strip():
        raise AppError(code="cover_output_missing", message="Output directory is required", retryable=False)
    logger.info(log_event(
        ctx,
        role="generator",
        event="cover_generate_start",
        module=logger.name,
        fields={
            "report_count": len(request.reports),
            "output_dir": request.output_dir,
            "style_config_path": request.style_config_path,
        },
    ))
    style_response = load_cover_styles(
        CoverStyleLoadRequest(schema_version="1.0", path=request.style_config_path),
        ctx,
    )
    config = style_response.config
    outcomes: List[CoverImageGenerationOutcome] = []

    for report in request.reports:
        normalized = _normalize_report(report)
        category = _resolve_category(normalized)
        overrides = config.categories.get(category)
        if overrides is None:
            overrides = config.categories.get("default")
        overrides = overrides or CoverImageStyleOverrides(schema_version="1.0")
        style = _merge_style(config.defaults, overrides)
        label_text = _category_label(category, style)
        label_origin = "style.category_label" if style.category_label.strip() else "derived_from_category"
        category_origin = "report.categories[0]" if normalized.categories else "default_fallback"

        logger.info(log_event(
            ctx,
            role="generator",
            event="cover_generate_resolve_style",
            module=logger.name,
            fields={
                "file_id": normalized.file_id,
                "category": category,
                "label_text": label_text,
            },
        ))
        logger.info(log_event(
            ctx,
            role="generator",
            event="cover_generate_text_sources",
            module=logger.name,
            fields={
                "file_id": normalized.file_id,
                "title": normalized.title,
                "title_source": "CoverImageReport.title",
                "publisher": normalized.publisher,
                "publisher_source": "CoverImageReport.publisher (from upstream DocMap)",
                "category": category,
                "category_source": category_origin,
                "category_label": label_text,
                "category_label_source": label_origin,
                "time_period": normalized.time_period or "",
                "time_period_source": "CoverImageReport.time_period",
                "region": normalized.region or "",
                "region_source": "CoverImageReport.region",
            },
        ))

        if not normalized.title:
            error = "Report title is required"
            logger.info(log_event(
                ctx,
                role="generator",
                event="cover_generate_validation_failed",
                module=logger.name,
                fields={"file_id": normalized.file_id, "error": error},
            ))
            outcomes.append(CoverImageGenerationOutcome(
                schema_version="1.0",
                file_id=normalized.file_id,
                title=normalized.title,
                output_path=None,
                status="error",
                error=error,
            ))
            continue

        # Align cover output directory with other report assets (HTML, evidence packs) which use the slugified PDF name (includes "-pdf").
        report_slug = slugify(f"{normalized.title}.pdf")
        filename_slug = slugify(f"{normalized.publisher} {normalized.title}")
        assets_dir = Path(request.output_dir) / report_slug / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(assets_dir / f"{filename_slug}.png")

        try:
            render_cover_image(
                CoverImageRenderRequest(
                    schema_version="1.0",
                    output_path=output_path,
                    title=normalized.title,
                    publisher=normalized.publisher,
                    time_period=normalized.time_period,
                    category_label=label_text,
                    style=style,
                    layout=config.layout,
                ),
                ctx,
            )
        except AppError as exc:
            logger.info(log_event(
                ctx,
                role="generator",
                event="cover_generate_failed",
                module=logger.name,
                fields={"file_id": normalized.file_id, "error": exc.message, "code": exc.code},
            ))
            outcomes.append(CoverImageGenerationOutcome(
                schema_version="1.0",
                file_id=normalized.file_id,
                title=normalized.title,
                output_path=None,
                status="error",
                error=exc.message,
            ))
            continue

        outcomes.append(CoverImageGenerationOutcome(
            schema_version="1.0",
            file_id=normalized.file_id,
            title=normalized.title,
            output_path=output_path,
            status="generated",
            error=None,
        ))

    logger.info(log_event(
        ctx,
        role="generator",
        event="cover_generate_complete",
        module=logger.name,
        fields={"generated": len([o for o in outcomes if o.status == "generated"]), "total": len(outcomes)},
    ))
    return outcomes
