from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.contracts.cover_images import (
    CoverImageGenerationOutcome,
    CoverImageGenerationRequest,
    CoverImageOrchestratorRequest,
    CoverImageReport,
)
from src.contracts.files import ReadTextRequest
from src.contracts.report_cards import CoverFingerprintProjectionRequest
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataListRequest,
)
from src.contracts.run_context import RunContext
from src.generators.cover_image_generator import generate_cover_images
from src.generators.report_card_projection import build_cover_fingerprint
from src.services import file_service
from src.services.report_store_service import get_metadata, list_metadata
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.slugify import slugify
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.cover_image_orchestrator")


def _report_slug_from_metadata(metadata) -> str:
    html_path = str(getattr(metadata, "html_path", "") or "").strip()
    if html_path:
        stem = Path(html_path).stem.strip()
        if stem:
            return stem
    file_name = str(getattr(metadata, "file_name", "") or "").strip()
    if file_name:
        file_slug = slugify(file_name)
        if file_slug:
            return file_slug
    return slugify(f"{str(metadata.title or '').strip()}.pdf")


def _load_cover_fingerprint(
    metadata,
    output_dir: str,
    ctx: RunContext,
):
    report_slug = _report_slug_from_metadata(metadata)
    artifact_path = (
        Path(output_dir) / report_slug / "report_analysis" / "artifacts.json"
    )
    try:
        response = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=str(artifact_path)),
            ctx,
        )
    except AppError as exc:
        if exc.code != "file_not_found":
            raise
        raise AppError(
            code="cover_artifacts_missing",
            message=f"Artifacts are required for cover generation: {artifact_path}",
            cause=exc,
            retryable=False,
            context={"file_id": metadata.file_id, "path": str(artifact_path)},
        ) from exc
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="cover_artifacts_invalid",
            message=f"Artifacts JSON is invalid: {artifact_path}",
            cause=exc,
            retryable=False,
            context={"file_id": metadata.file_id, "path": str(artifact_path)},
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "3.0":
        raise AppError(
            code="cover_artifacts_invalid",
            message="Cover generation requires artifact schema version 3.0",
            retryable=False,
            context={"file_id": metadata.file_id, "path": str(artifact_path)},
        )
    cover_semantics = payload.get("cover_semantics")
    if not isinstance(cover_semantics, dict):
        raise AppError(
            code="cover_fingerprint_invalid",
            message="Artifacts do not contain grounded cover semantics",
            retryable=False,
            context={"file_id": metadata.file_id, "path": str(artifact_path)},
        )
    return build_cover_fingerprint(
        CoverFingerprintProjectionRequest(
            schema_version="1.0",
            file_id=metadata.file_id,
            artifact_hash=sha256_json(payload),
            region=str(metadata.region or ""),
            cover_semantics=cover_semantics,
        )
    )


def _report_from_metadata(
    metadata,
    output_dir: str,
    ctx: RunContext,
) -> CoverImageReport:
    return CoverImageReport(
        schema_version="2.0",
        file_id=metadata.file_id,
        title=metadata.title,
        publisher=metadata.publisher or "",
        report_slug=_report_slug_from_metadata(metadata),
        categories=list(metadata.categories or []),
        time_period=metadata.time_period,
        region=metadata.region,
        fingerprint=_load_cover_fingerprint(metadata, output_dir, ctx),
    )


def run_cover_image_generation(
    request: CoverImageOrchestratorRequest,
    *,
    ctx: Optional[RunContext] = None,
) -> List[CoverImageGenerationOutcome]:
    root_ctx = ctx or new_run_context(task_id="cover_images")
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="cover_orchestrator_start",
            module=logger.name,
            fields={
                "reports_db": request.reports_db,
                "output_dir": request.output_dir,
                "style_config_path": request.style_config_path,
                "limit": request.limit,
                "file_id": request.file_id or "",
            },
        )
    )

    list_ctx = child_context(root_ctx, task_id="cover_list_reports")
    reports: List[CoverImageReport] = []
    if request.file_id:
        single_response = get_metadata(
            ReportMetadataGetRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                file_id=request.file_id,
            ),
            list_ctx,
        )
        if single_response is None:
            raise AppError(
                code="cover_report_not_found",
                message=f"Report metadata not found for file_id: {request.file_id}",
                retryable=False,
                context={"file_id": request.file_id, "reports_db": request.reports_db},
            )
        reports.append(
            _report_from_metadata(single_response, request.output_dir, list_ctx)
        )
    else:
        list_response = list_metadata(
            ReportMetadataListRequest(schema_version="1.0", db_path=request.reports_db),
            list_ctx,
        )
        for metadata in list_response.records:
            reports.append(
                _report_from_metadata(metadata, request.output_dir, list_ctx)
            )

    if request.limit is not None:
        reports = reports[: max(request.limit, 0)]

    logger.info(
        log_event(
            list_ctx,
            role="orchestrator",
            event="cover_orchestrator_reports_loaded",
            module=logger.name,
            fields={"count": len(reports)},
        )
    )

    gen_ctx = child_context(root_ctx, task_id="cover_generate")
    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=request.output_dir,
            style_config_path=request.style_config_path,
            reports=reports,
        ),
        gen_ctx,
    )

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="cover_orchestrator_complete",
            module=logger.name,
            fields={"outcome_count": len(outcomes)},
        )
    )
    return outcomes
