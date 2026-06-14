from __future__ import annotations

from typing import Optional

from src.contracts.config import AppSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport, ValidationRequest
from src.services import llm_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.logging import log_event, new_run_context

from .validation.cache import (
    load_cached_validation,
    store_pack,
    validate_validation_schema,
    validation_cache_key,
    validation_cache_meta,
)
from .validation.models import ValidationRuntime
from .validation.preparation import prepare_validation_inputs
from .validation.registry import run_validation_rule_registry
from .validation.shared import (
    LOGGER_NAME,
    aggregate_severity,
    downgrade_issues_for_data_gap,
    grounding_retrieval_mode,
    has_data_gap,
    logger,
    resolve_grounding_vector_store_mode,
    validation_parallel_workers,
)


def validate_report(
    request: ValidationRequest,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    *,
    prompt_client=prompt_service,
    openai_client=None,
    analysis_store=report_analysis_store_service,
    pack_name: str = "validation",
    report_name: Optional[str] = None,
    md5: Optional[str] = None,
) -> ValidationReport:
    ctx = ctx or new_run_context(task_id=f"validation:{request.report_id}")
    openai_client = openai_client or llm_service.build_client_for_settings(
        settings,
        scope="validation",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="validation_start",
            module=LOGGER_NAME,
            fields={
                "report_id": request.report_id,
                "has_artifacts": bool(request.artifacts),
                "has_evidence_packs": bool(request.evidence_packs),
                "vector_store_id": request.vector_store_id or "",
            },
        )
    )

    grounding_use_vector_store = resolve_grounding_vector_store_mode(
        request=request, settings=settings
    )
    retrieval_mode = grounding_retrieval_mode(grounding_use_vector_store)
    cache_key = ""
    cache_meta = None
    if md5:
        cache_meta = validation_cache_meta(
            request=request,
            settings=settings,
            prompt_client=prompt_client,
            ctx=ctx,
            md5=md5,
            grounding_retrieval_mode=retrieval_mode,
        )
        cache_key = validation_cache_key(cache_meta)
        cached = load_cached_validation(
            output_dir=settings.output_dir,
            report_id=request.report_id,
            pack_name=pack_name,
            report_name=report_name,
            cache_key=cache_key,
            ctx=ctx,
            analysis_store=analysis_store,
        )
        if cached is not None:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="validation_cache_hit",
                    module=LOGGER_NAME,
                    fields={"report_id": request.report_id, "pack_name": pack_name},
                )
            )
            return cached
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_cache_miss",
                module=LOGGER_NAME,
                fields={"report_id": request.report_id, "pack_name": pack_name},
            )
        )

    prepared = prepare_validation_inputs(request, settings, ctx, md5=md5)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="validation_evidence_index_ready",
            module=LOGGER_NAME,
            fields={
                "report_id": request.report_id,
                "evidence_snippets": len(prepared.evidence_texts),
                "windows": len(prepared.evidence_windows),
                "pdf_text_loaded": bool(prepared.pdf_text),
            },
        )
    )

    runtime = ValidationRuntime(
        request=request,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        openai_client=openai_client,
        prepared=prepared,
    )
    issues = run_validation_rule_registry(
        runtime,
        parallel_workers=validation_parallel_workers(settings),
    )

    if (
        has_data_gap(request.artifacts)
        and getattr(settings, "validation_data_gap_policy", "warn") == "warn"
    ):
        issues = downgrade_issues_for_data_gap(issues)
    severity = aggregate_severity(issues)
    status = "pass" if severity != "error" else "fail"
    report = ValidationReport(
        schema_version="1.1",
        status=status,
        issues=issues,
        severity=severity,
    )

    try:
        validate_validation_schema(report, ctx)
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_schema_failed",
                module=LOGGER_NAME,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        raise

    payload = report.to_dict()
    if cache_meta:
        payload["_cache"] = {**cache_meta, "key": cache_key}
    stored_path = store_pack(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=request.report_id,
        pack_name=pack_name,
        payload=payload,
        ctx=ctx,
        report_name=report_name,
    )
    if cache_meta:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_cache_written",
                module=LOGGER_NAME,
                fields={"report_id": request.report_id, "pack_name": pack_name},
            )
        )
    report = ValidationReport(
        schema_version=report.schema_version,
        status=report.status,
        issues=report.issues,
        severity=report.severity,
        source_path=stored_path,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="validation_complete",
            module=LOGGER_NAME,
            fields={
                "report_id": request.report_id,
                "status": status,
                "severity": severity,
                "issue_count": len(issues),
                "path": stored_path,
            },
        )
    )
    return report
