from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
)
from src.generators.analysis_store_adapter import (
    store_pack as store_analysis_pack,
)
from src.services import file_service
from src.services.schema_validator_service import validate_schema
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import resolve_model

from .shared import LOGGER_NAME, logger

VALIDATION_RULESET_VERSION = "7"


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
            "source_text_sha256": sha256_json(str(request.source_text or "")),
            "vector_store_id": request.vector_store_id or "",
            "validation_mode": request.validation_mode,
            "data_gap_policy": getattr(settings, "validation_data_gap_policy", "warn"),
        }
    )
    return {
        "schema_version": "1.0",
        "validation_ruleset_version": VALIDATION_RULESET_VERSION,
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "use_vector_store": bool(request.vector_store_id),
        "grounding_retrieval_mode": grounding_retrieval_mode,
        "validation_mode": request.validation_mode,
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
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


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
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


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
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
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

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: resolve_pack_path(
            output_dir, report_id, pack_name, report_name, analysis_store, ctx
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=lambda payload, path: _adapt_cached_validation_payload(
            payload=payload,
            path=path,
            report_id=report_id,
            pack_name=pack_name,
            ctx=ctx,
        ),
    )
    return result.value if result.status == "hit" else None


def _adapt_cached_validation_payload(
    *,
    payload: Dict[str, Any],
    path: str,
    report_id: str,
    pack_name: str,
    ctx: RunContext,
) -> CachedPackAdaptResult[ValidationReport]:
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=payload,
                schema_name="validation_report",
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_cache_invalid",
                module=LOGGER_NAME,
                fields={
                    "report_id": report_id,
                    "pack_name": pack_name,
                    "path": path,
                    "code": exc.code,
                    "message": exc.message,
                },
            )
        )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="schema_invalid",
            value=None,
        )
    return CachedPackAdaptResult(
        schema_version="1.0",
        status="hit",
        value=validation_report_from_payload(payload, path),
    )


def validation_report_from_payload(payload: dict, path: str) -> ValidationReport:
    raw_issues = payload.get("issues")
    issues_raw: list[Any] = raw_issues if isinstance(raw_issues, list) else []
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
                rule_id=str(entry.get("rule_id") or ""),
                repair_target=str(entry.get("repair_target") or ""),
                entity_id=str(entry.get("entity_id") or ""),
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
