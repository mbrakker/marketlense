from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.contracts.files import ReadTextRequest
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.validation import ValidationIssue, ValidationReport, ValidationRequest
from src.services import file_service, report_analysis_store_service
from src.services.schema_validator_service import validate_schema
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import resolve_model

from .shared import LOGGER_NAME, ensure_dict, logger


def validation_cache_meta(
    *,
    request: ValidationRequest,
    settings,
    prompt_client,
    ctx: RunContext,
    md5: str,
    grounding_retrieval_mode: str,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/validate/semantic",
        "report_vs/validate/grounding",
    ]
    for namespace in namespaces:
        prompt_set = prompt_client.load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx
        )
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolve_model(
                namespace, getattr(settings, "openai_models", {}), settings.openai_model
            ),
        }
    inputs_hash = sha256_json(
        {
            "report": request.report.to_dict(),
            "artifacts": request.artifacts,
            "evidence_packs": request.evidence_packs,
            "vector_store_id": request.vector_store_id or "",
            "data_gap_policy": getattr(settings, "validation_data_gap_policy", "warn"),
        }
    )
    return {
        "schema_version": "1.0",
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "use_vector_store": bool(request.vector_store_id),
        "grounding_retrieval_mode": grounding_retrieval_mode,
    }


def validation_cache_key(cache_meta: Dict[str, Any]) -> str:
    return sha256_json(cache_meta)


def resolve_pack_path(
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: Optional[str],
    analysis_store,
    ctx: RunContext,
) -> str:
    if hasattr(analysis_store, "pack_path"):
        try:
            response = analysis_store.pack_path(
                AnalysisPackPathRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    report_slug=report_name,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(
                analysis_store.pack_path(
                    output_dir, report_id, pack_name, report_slug=report_name
                )
            )
    return report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx,
    ).output_path


def store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    report_name: Optional[str],
) -> str:
    if hasattr(analysis_store, "store_pack"):
        try:
            response = analysis_store.store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    payload=payload,
                    report_slug=report_name,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(
                analysis_store.store_pack(
                    output_dir,
                    report_id,
                    pack_name,
                    payload,
                    ctx,
                    report_slug=report_name,
                )
            )
    return report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
        ),
        ctx,
    ).output_path


def load_cached_validation(
    *,
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: Optional[str],
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[ValidationReport]:
    if not cache_key:
        return None
    path = resolve_pack_path(
        output_dir, report_id, pack_name, report_name, analysis_store, ctx
    )
    try:
        response = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=path), ctx
        )
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_cache_read_failed",
                module=LOGGER_NAME,
                fields={
                    "report_id": report_id,
                    "pack_name": pack_name,
                    "error": exc.message,
                },
            )
        )
        return None
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    cached = ensure_dict(payload.get("_cache"))
    if cached.get("key") != cache_key:
        return None
    return validation_report_from_payload(payload, path)


def validation_report_from_payload(payload: dict, path: str) -> ValidationReport:
    issues_raw = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    issues: List[ValidationIssue] = []
    for entry in issues_raw:
        if not isinstance(entry, dict):
            continue
        issues.append(
            ValidationIssue(
                schema_version=str(entry.get("schema_version") or "1.0"),
                message=str(entry.get("message") or ""),
                severity=str(entry.get("severity") or "warning"),
                affected_section=str(entry.get("affected_section") or ""),
            )
        )
    return ValidationReport(
        schema_version=str(payload.get("schema_version") or "1.0"),
        status=str(payload.get("status") or "fail"),
        severity=str(payload.get("severity") or "pass"),
        issues=issues,
        source_path=path,
    )


def validate_validation_schema(report: ValidationReport, ctx: RunContext) -> None:
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0",
            payload=report.to_dict(),
            schema_name="validation_report",
        ),
        ctx,
    )

