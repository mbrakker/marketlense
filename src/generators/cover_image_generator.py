from __future__ import annotations

import logging
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
from src.services import cover_image_service
from src.services.cover_style_service import load_cover_styles
from src.utils.cover_path_utils import build_cover_asset_path
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_image_generator")


def _normalize_report(report: CoverImageReport) -> CoverImageReport:
    title = str(report.title or "").strip()
    publisher = str(report.publisher or "").strip()
    report_slug = str(report.report_slug or "").strip() or None
    categories = [str(cat).strip() for cat in report.categories if str(cat).strip()]
    time_period = str(report.time_period).strip() if report.time_period else None
    region = str(report.region).strip() if report.region else None
    return CoverImageReport(
        schema_version=report.schema_version,
        file_id=str(report.file_id).strip(),
        title=title,
        publisher=publisher,
        report_slug=report_slug,
        categories=categories,
        time_period=time_period,
        region=region,
    )


def _resolve_style_category(report: CoverImageReport) -> str:
    if report.categories:
        return str(report.categories[0]).strip().lower()
    return "default"


def _merge_style(defaults: CoverImageStyle, overrides) -> CoverImageStyle:
    return CoverImageStyle(
        schema_version=defaults.schema_version,
        background_color=overrides.background_color or defaults.background_color,
        accent_color=overrides.accent_color or defaults.accent_color,
        text_color=overrides.text_color or defaults.text_color,
        category_label=overrides.category_label or defaults.category_label,
        font_regular_path=overrides.font_regular_path or defaults.font_regular_path,
        font_bold_path=overrides.font_bold_path or defaults.font_bold_path,
        background_image_path=overrides.background_image_path
        or defaults.background_image_path,
    )


def _category_label(category: str) -> str:
    return str(category or "").strip()


def _footer_label(time_period: str | None, region: str | None) -> str:
    pieces = [
        str(piece).strip()
        for piece in (region, time_period)
        if piece and str(piece).strip()
    ]
    return " • ".join(pieces)


def generate_cover_images(
    request: CoverImageGenerationRequest, ctx: RunContext
) -> List[CoverImageGenerationOutcome]:
    if not str(request.output_dir).strip():
        raise AppError(
            code="cover_output_missing",
            message="Output directory is required",
            retryable=False,
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cover_generate_start",
            module=logger.name,
            fields={
                "report_count": len(request.reports),
                "output_dir": request.output_dir,
                "style_config_path": request.style_config_path,
            },
        )
    )
    style_response = load_cover_styles(
        CoverStyleLoadRequest(schema_version="1.0", path=request.style_config_path),
        ctx,
    )
    config = style_response.config
    outcomes: List[CoverImageGenerationOutcome] = []

    for report in request.reports:
        normalized = _normalize_report(report)
        style_category = _resolve_style_category(normalized)
        overrides = config.categories.get(style_category)
        if overrides is None:
            overrides = config.categories.get("default")
        overrides = overrides or CoverImageStyleOverrides(schema_version="1.0")
        style = _merge_style(config.defaults, overrides)
        label_text = (
            _category_label(normalized.categories[0]) if normalized.categories else ""
        )
        label_origin = (
            "report.categories[0]"
            if normalized.categories
            else "report.categories[0] (empty)"
        )
        category_origin = (
            "report.categories[0]"
            if normalized.categories
            else "report.categories (empty)"
        )
        footer_label = _footer_label(normalized.time_period, normalized.region)

        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cover_generate_resolve_style",
                module=logger.name,
                fields={
                    "file_id": normalized.file_id,
                    "category": style_category,
                    "label_text": label_text,
                },
            )
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cover_generate_text_sources",
                module=logger.name,
                fields={
                    "file_id": normalized.file_id,
                    "title": normalized.title,
                    "title_source": "CoverImageReport.title",
                    "publisher": normalized.publisher,
                    "publisher_source": "CoverImageReport.publisher",
                    "category": normalized.categories[0]
                    if normalized.categories
                    else "",
                    "category_source": category_origin,
                    "category_label": label_text,
                    "category_label_source": label_origin,
                    "time_period": normalized.time_period or "",
                    "time_period_source": "CoverImageReport.time_period",
                    "region": normalized.region or "",
                    "region_source": "CoverImageReport.region",
                    "footer_label": footer_label,
                },
            )
        )

        if not normalized.title:
            error = "Report title is required"
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="cover_generate_validation_failed",
                    module=logger.name,
                    fields={"file_id": normalized.file_id, "error": error},
                )
            )
            outcomes.append(
                CoverImageGenerationOutcome(
                    schema_version="1.0",
                    file_id=normalized.file_id,
                    title=normalized.title,
                    output_path=None,
                    status="error",
                    error=error,
                )
            )
            continue

        output_path_obj = build_cover_asset_path(
            request.output_dir,
            normalized.file_id,
            normalized.title,
            normalized.publisher,
            normalized.report_slug,
        )
        output_path = str(output_path_obj)

        try:
            cover_image_service.render_cover_image(
                CoverImageRenderRequest(
                    schema_version="1.0",
                    output_path=output_path,
                    title=normalized.title,
                    publisher=normalized.publisher,
                    time_period=footer_label,
                    category_label=label_text,
                    style=style,
                    layout=config.layout,
                ),
                ctx,
            )
        except AppError as exc:
            if exc.retryable:
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="cover_generate_retryable_error_propagated",
                        module=logger.name,
                        fields={
                            "file_id": normalized.file_id,
                            "error": exc.message,
                            "code": exc.code,
                        },
                    )
                )
                raise
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="cover_generate_failed",
                    module=logger.name,
                    fields={
                        "file_id": normalized.file_id,
                        "error": exc.message,
                        "code": exc.code,
                    },
                )
            )
            outcomes.append(
                CoverImageGenerationOutcome(
                    schema_version="1.0",
                    file_id=normalized.file_id,
                    title=normalized.title,
                    output_path=None,
                    status="error",
                    error=exc.message,
                )
            )
            continue

        outcomes.append(
            CoverImageGenerationOutcome(
                schema_version="1.0",
                file_id=normalized.file_id,
                title=normalized.title,
                output_path=output_path,
                status="generated",
                error=None,
            )
        )

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cover_generate_complete",
            module=logger.name,
            fields={
                "generated": len([o for o in outcomes if o.status == "generated"]),
                "total": len(outcomes),
            },
        )
    )
    return outcomes
