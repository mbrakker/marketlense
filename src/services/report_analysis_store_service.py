from __future__ import annotations

import json
import logging
from pathlib import Path

from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisPackPathResponse,
    AnalysisStorePackRequest,
    AnalysisStorePackResponse,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.report_analysis_store_service")


def _legacy_base_dir(output_dir: str) -> Path:
    return Path(output_dir) / "report_analysis"


def _report_base_dir(output_dir: str, report_slug: str) -> Path:
    return Path(output_dir) / report_slug / "report_analysis"


def pack_path(request: AnalysisPackPathRequest, ctx: RunContext) -> AnalysisPackPathResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_pack_path_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "pack_name": request.pack_name,
            "report_slug": request.report_slug or "",
        },
    ))
    path: Path
    if request.report_slug:
        slug = slugify(request.report_slug)
        path = _report_base_dir(request.output_dir, slug) / f"{request.pack_name}.json"
    else:
        path = _legacy_base_dir(request.output_dir) / request.report_id / f"{request.pack_name}.json"
    response = AnalysisPackPathResponse(schema_version="1.0", output_path=str(path))
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_pack_path_complete",
        module=logger.name,
        fields={"path": response.output_path},
    ))
    return response


def store_pack(request: AnalysisStorePackRequest, ctx: RunContext) -> AnalysisStorePackResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "pack_name": request.pack_name,
            "report_slug": request.report_slug or "",
            "mirror_legacy": request.mirror_legacy,
        },
    ))

    primary_path = Path(pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=request.output_dir,
            report_id=request.report_id,
            pack_name=request.pack_name,
            report_slug=request.report_slug,
        ),
        ctx,
    ).output_path)
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(request.payload, ensure_ascii=False, indent=2)
    primary_path.write_text(payload_json, encoding="utf-8")

    legacy_path = None
    if request.report_slug and request.mirror_legacy:
        legacy_path = Path(pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=request.output_dir,
                report_id=request.report_id,
                pack_name=request.pack_name,
                report_slug=None,
            ),
            ctx,
        ).output_path)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        if legacy_path != primary_path:
            legacy_path.write_text(payload_json, encoding="utf-8")

    response = AnalysisStorePackResponse(
        schema_version="1.0",
        output_path=str(primary_path),
        legacy_output_path=str(legacy_path) if legacy_path else None,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="analysis_store_complete",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "pack_name": request.pack_name,
            "path": response.output_path,
            "legacy_path": response.legacy_output_path or "",
        },
    ))
    return response
