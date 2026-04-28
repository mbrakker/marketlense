from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisPackPathResponse,
    AnalysisStorePackRequest,
    AnalysisStorePackResponse,
)
from src.contracts.files import WriteBytesRequest
from src.contracts.run_context import RunContext
from src.services import file_service
from src.contracts.schema_validation import SchemaValidateRequest
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.report_analysis_store_service")
_SAFE_PACK_NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PACK_SCHEMA_NAMES: dict[str, str] = {
    "artifacts": "artifacts",
    "context_category_fit": "context_category_fit",
    "contradictions": "contradictions_pack",
    "doc_map": "doc_map",
    "findings": "findings_pack",
    "key_metrics": "key_metrics_pack",
    "limitations": "limitations_pack",
    "methods": "methods_pack",
    "quote_candidates": "quote_candidates_pack",
    "recommendations": "recommendations_pack",
    "risk_register": "risk_register_pack",
    "scope": "scope_pack",
    "taxonomy": "taxonomy",
    "validation": "validation_report",
}


def _report_base_dir(output_dir: str, report_slug: str) -> Path:
    return Path(output_dir) / report_slug / "report_analysis"


def _resolve_report_slug(report_slug: str | None, report_id: str) -> str:
    slug_source = report_slug if report_slug else report_id
    slug = slugify(slug_source)
    return slug or "report"


def _schema_name_for_pack(pack_name: str) -> str:
    normalized = str(pack_name or "").strip()
    if normalized.startswith("artifacts_regen_attempt_"):
        return "artifacts"
    if normalized.startswith("validation_regen_attempt_"):
        return "validation_report"
    return _PACK_SCHEMA_NAMES.get(normalized, "")


def _validate_pack_name(pack_name: str) -> str:
    normalized = str(pack_name or "").strip()
    if normalized and _SAFE_PACK_NAME_RX.fullmatch(normalized):
        return normalized
    raise AppError(
        code="analysis_pack_name_invalid",
        message="Analysis pack name must be a single safe filename segment",
        retryable=False,
        context={"pack_name": pack_name},
    )


def pack_path(
    request: AnalysisPackPathRequest, ctx: RunContext
) -> AnalysisPackPathResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_pack_path_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "report_slug": request.report_slug or "",
            },
        )
    )
    slug = _resolve_report_slug(request.report_slug, request.report_id)
    pack_name = _validate_pack_name(request.pack_name)
    path = _report_base_dir(request.output_dir, slug) / f"{pack_name}.json"
    response = AnalysisPackPathResponse(schema_version="1.0", output_path=str(path))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_pack_path_complete",
            module=logger.name,
            fields={"path": response.output_path},
        )
    )
    return response


def store_pack(
    request: AnalysisStorePackRequest, ctx: RunContext
) -> AnalysisStorePackResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_store_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "report_slug": request.report_slug or "",
            },
        )
    )

    primary_path = Path(
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=request.output_dir,
                report_id=request.report_id,
                pack_name=request.pack_name,
                report_slug=request.report_slug,
            ),
            ctx,
        ).output_path
    )
    schema_name = _schema_name_for_pack(request.pack_name)
    try:
        if schema_name:
            try:
                validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=request.payload,
                        schema_name=schema_name,
                    ),
                    ctx,
                )
            except AppError as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="analysis_store_schema_validation_failed",
                        module=logger.name,
                        fields={
                            "report_id": request.report_id,
                            "pack_name": request.pack_name,
                            "schema_name": schema_name,
                            "path": str(primary_path),
                            "code": exc.code,
                            "message": exc.message,
                        },
                    )
                )
                raise
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="analysis_store_schema_validated",
                    module=logger.name,
                    fields={
                        "report_id": request.report_id,
                        "pack_name": request.pack_name,
                        "schema_name": schema_name,
                        "path": str(primary_path),
                    },
                )
            )
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(request.payload, ensure_ascii=False, indent=2)
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(primary_path),
                content=payload_json.encode("utf-8"),
            ),
            ctx,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="analysis_store_failed",
            message=f"Failed to store analysis pack '{request.pack_name}' for report '{request.report_id}'",
            cause=exc,
            retryable=False,
            context={
                "output_dir": request.output_dir,
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "path": str(primary_path),
            },
        ) from exc

    response = AnalysisStorePackResponse(
        schema_version="1.0",
        output_path=str(primary_path),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_store_complete",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "path": response.output_path,
            },
        )
    )
    return response
