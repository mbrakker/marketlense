from __future__ import annotations

import logging
from typing import List

from src.contracts.cover_images import (
    CoverImageGenerationOutcome,
    CoverImageGenerationRequest,
    CoverImageRenderRequest,
    CoverImageReport,
    CoverStyleLoadRequest,
)
from src.contracts.report_cards import CardCoverAsset, CardCoverAssetSet
from src.contracts.run_context import RunContext
from src.services import cover_image_service
from src.services.cover_style_service import load_cover_styles
from src.utils.cover_path_utils import build_report_card_asset_path
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cover_image_generator")
CARD_SIZES = ("small", "medium", "large")


def _normalize_report(report: CoverImageReport) -> CoverImageReport:
    return CoverImageReport(
        schema_version="2.0",
        file_id=str(report.file_id).strip(),
        title=" ".join(str(report.title or "").split()),
        publisher=" ".join(str(report.publisher or "").split()),
        report_slug=str(report.report_slug or "").strip() or None,
        categories=[
            str(category).strip()
            for category in report.categories
            if str(category).strip()
        ],
        time_period=(
            " ".join(str(report.time_period).split()) if report.time_period else None
        ),
        region=" ".join(str(report.region).split()) if report.region else None,
        fingerprint=report.fingerprint,
        cover_profile=str(report.cover_profile or "report").strip(),
    )


def _covered_period(report: CoverImageReport) -> str:
    return " ".join(str(report.time_period or "").split())


def _error_outcome(
    report: CoverImageReport, message: str
) -> CoverImageGenerationOutcome:
    return CoverImageGenerationOutcome(
        schema_version="2.0",
        file_id=report.file_id,
        title=report.title,
        status="error",
        assets=None,
        error=message,
    )


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
    config = load_cover_styles(
        CoverStyleLoadRequest(schema_version="2.0", path=request.style_config_path),
        ctx,
    ).config
    outcomes: List[CoverImageGenerationOutcome] = []

    for source_report in request.reports:
        report = _normalize_report(source_report)
        if not report.title:
            outcomes.append(_error_outcome(report, "Report title is required"))
            continue
        if report.fingerprint is None:
            outcomes.append(
                _error_outcome(report, "Semantic cover fingerprint is required")
            )
            continue
        profile = config.profiles.get(report.cover_profile)
        if profile is None:
            outcomes.append(
                _error_outcome(report, "Cover profile is not approved: " + report.cover_profile)
            )
            continue

        rendered: dict[str, CardCoverAsset] = {}
        render_error: AppError | None = None
        for size in CARD_SIZES:
            layout = profile.layouts[size]
            output_path = str(
                build_report_card_asset_path(
                    request.output_dir,
                    report.file_id,
                    report.title,
                    report.report_slug,
                    size,
                )
            )
            try:
                response = cover_image_service.render_cover_image(
                    CoverImageRenderRequest(
                        schema_version="2.0",
                        output_path=output_path,
                        size=size,
                        title=report.title,
                        publisher=report.publisher,
                        time_period=_covered_period(report),
                        style=profile.style,
                        layout=layout,
                        fingerprint=report.fingerprint,
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
                                "file_id": report.file_id,
                                "size": size,
                                "code": exc.code,
                                "error": exc.message,
                            },
                        )
                    )
                    raise
                render_error = exc
                break

            rendered[size] = CardCoverAsset(
                schema_version="1.0",
                size=size,
                output_path=response.output_path,
                width=response.width,
                height=response.height,
            )
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="cover_asset_rendered",
                    module=logger.name,
                    fields={
                        "file_id": report.file_id,
                        "family": report.fingerprint.geometry_family,
                        "size": size,
                        "seed": report.fingerprint.seed,
                        "cover_profile": report.cover_profile,
                        "title_font_size": response.title_font_size,
                        "output_path": response.output_path,
                    },
                )
            )

        if render_error is not None:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="cover_generate_failed",
                    module=logger.name,
                    fields={
                        "file_id": report.file_id,
                        "code": render_error.code,
                        "error": render_error.message,
                    },
                )
            )
            outcomes.append(_error_outcome(report, render_error.message))
            continue

        assets = CardCoverAssetSet(
            schema_version="1.0",
            small=rendered["small"],
            medium=rendered["medium"],
            large=rendered["large"],
        )
        outcomes.append(
            CoverImageGenerationOutcome(
                schema_version="2.0",
                file_id=report.file_id,
                title=report.title,
                status="generated",
                assets=assets,
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
                "generated": len(
                    [outcome for outcome in outcomes if outcome.status == "generated"]
                ),
                "total": len(outcomes),
            },
        )
    )
    return outcomes
