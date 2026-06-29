from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pipeline_preflight import PipelinePreflightReport
from src.contracts.report_generation import ReportGenerationClientBundle
from src.contracts.run_context import RunContext
from src.orchestrators.report_generation_orchestrator import (
    run_report_generation as generate_report_orchestrator,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.orchestrators.pipeline_preflight_orchestrator import (
    assert_expensive_side_effects_allowed,
    preflight_report_pipeline,
)
from src.services import llm_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.coercion import coerce_int

logger = logging.getLogger("market_lense.report_pipeline_orchestrator")


def _doc_map_reason(outcome: IngestOutcome) -> str:
    summary = (
        outcome.doc_map_summary if isinstance(outcome.doc_map_summary, dict) else {}
    )
    reason = str(summary.get("not_found_reason") or "").strip()
    if reason:
        return reason
    error_text = str(outcome.error or "")
    prefix = "doc_map_empty:"
    if error_text.startswith(prefix):
        return error_text[len(prefix) :].strip()
    return ""


def _is_retryable_doc_map_reason(reason: str) -> bool:
    normalized = reason.strip()
    if not normalized:
        return False
    if normalized == "model_returned_no_json":
        return True
    if normalized.startswith("schema_validation_failed:"):
        return True
    return normalized.startswith("retryable_error:")


def _is_retryable_doc_map_outcome(outcome: IngestOutcome, reason: str) -> bool:
    if _is_retryable_doc_map_reason(reason):
        return True
    text_validation_status = str(outcome.text_validation_status or "").strip().lower()
    return reason.strip() == "no_content" and text_validation_status == "pass"


def _invoke_report_fn(
    report_fn: Callable[..., IngestOutcome],
    *,
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    client_bundle: ReportGenerationClientBundle,
    resume_from_stage: Optional[str] = None,
) -> IngestOutcome:
    return report_fn(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        client_bundle=client_bundle.validate(),
        resume_from_stage=resume_from_stage,
    )


def run_report_pipeline(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    retries: int = 2,
    generate_report_fn: Optional[Callable[..., IngestOutcome]] = None,
    openai_client_override=None,
    resume_from_stage: Optional[str] = None,
    preflight_fn: Optional[Callable[..., PipelinePreflightReport]] = None,
) -> IngestOutcome:
    report_fn = generate_report_fn or generate_report_orchestrator
    preflight_report = (
        preflight_fn(settings, ctx)
        if preflight_fn is not None
        else preflight_report_pipeline(settings, ctx)
    )
    assert_expensive_side_effects_allowed(preflight_report, ctx)
    evidence_max_in_flight = coerce_int(
        getattr(settings, "evidence_pack_global_max_in_flight", 2), 2, min_value=1
    )
    evidence_min_interval_ms = coerce_int(
        getattr(settings, "evidence_pack_global_min_interval_ms", 250), 250, min_value=0
    )
    artifact_max_in_flight = coerce_int(
        getattr(settings, "artifact_global_max_in_flight", 2), 2, min_value=1
    )
    artifact_min_interval_ms = coerce_int(
        getattr(settings, "artifact_global_min_interval_ms", 250), 250, min_value=0
    )
    doc_map_max_attempts = coerce_int(
        getattr(settings, "evidence_pack_doc_map_max_attempts", 3), 3, min_value=1
    )
    doc_map_retry_delay_ms = coerce_int(
        getattr(settings, "evidence_pack_doc_map_retry_delay_ms", 500), 500, min_value=0
    )
    configured_retries = max(0, int(retries))
    base_delay_seconds = 1.0
    jitter_seconds = 0.25
    evidence_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="evidence_pack",
        rate_limit_max_in_flight=evidence_max_in_flight,
        rate_limit_min_interval_ms=evidence_min_interval_ms,
        base_client=openai_client_override,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )
    artifact_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="artifact",
        rate_limit_max_in_flight=artifact_max_in_flight,
        rate_limit_min_interval_ms=artifact_min_interval_ms,
        base_client=openai_client_override,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )
    source_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="pdf_text_ocr",
        base_client=openai_client_override,
    )
    taxonomy_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="taxonomy",
        base_client=openai_client_override,
    )
    category_fit_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="context_category_fit",
        base_client=openai_client_override,
    )
    validation_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="validation",
        base_client=openai_client_override,
    )
    regeneration_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="artifact_regeneration",
        base_client=openai_client_override,
    )
    figure_caption_openai_client = llm_service.build_client_for_settings(
        settings,
        scope="figure_caption",
        base_client=openai_client_override,
    )
    client_bundle = ReportGenerationClientBundle(
        schema_version="1.0",
        source_ocr_client=source_openai_client,
        taxonomy_client=taxonomy_openai_client,
        category_fit_client=category_fit_openai_client,
        evidence_pack_client=evidence_openai_client,
        artifact_client=artifact_openai_client,
        validation_client=validation_openai_client,
        regeneration_client=regeneration_openai_client,
        figure_caption_client=figure_caption_openai_client,
    ).validate()
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_pipeline_start",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "md5": md5 or "",
                "local_pdf_path": local_pdf_path,
                "retries": retries,
                "effective_retries": configured_retries,
                "doc_map_max_attempts": doc_map_max_attempts,
                "retry_delay_ms": doc_map_retry_delay_ms,
                "retry_jitter_seconds": jitter_seconds,
                "evidence_pack_global_max_in_flight": evidence_max_in_flight,
                "evidence_pack_global_min_interval_ms": evidence_min_interval_ms,
                "artifact_global_max_in_flight": artifact_max_in_flight,
                "artifact_global_min_interval_ms": artifact_min_interval_ms,
                "resume_from_stage": resume_from_stage or "",
            },
        )
    )

    attempt_state = {"value": 0}

    def _report_attempt() -> IngestOutcome:
        current_attempt = attempt_state["value"]
        attempt_state["value"] += 1
        outcome = _invoke_report_fn(
            report_fn,
            file=file,
            local_pdf_path=local_pdf_path,
            settings=settings,
            md5=md5,
            ctx=ctx,
            client_bundle=client_bundle,
            resume_from_stage=resume_from_stage,
        )
        doc_map_reason = _doc_map_reason(outcome)
        should_retry_doc_map = (
            outcome.status == "error"
            and _is_retryable_doc_map_outcome(outcome, doc_map_reason)
            and current_attempt < doc_map_max_attempts - 1
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_pipeline_complete",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "status": outcome.status,
                    "html_path": outcome.html_path or "",
                    "error": outcome.error or "",
                    "attempt": current_attempt,
                    "doc_map_reason": doc_map_reason,
                    "retry_transition": should_retry_doc_map,
                },
            )
        )
        if should_retry_doc_map:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="report_pipeline_doc_map_retry_transition",
                    module=logger.name,
                    fields={
                        "file_id": file.file_id,
                        "attempt": current_attempt + 1,
                        "max_attempts": doc_map_max_attempts,
                        "reason": doc_map_reason,
                    },
                )
            )
            raise AppError(
                code="doc_map_generation_retry",
                message=f"Retrying report pipeline for doc_map reason: {doc_map_reason}",
                retryable=True,
                context={
                    "file_id": file.file_id,
                    "attempt": current_attempt + 1,
                    "max_attempts": doc_map_max_attempts,
                    "reason": doc_map_reason,
                },
            )
        return outcome

    return run_with_retry(
        step_name="report_pipeline",
        operation=_report_attempt,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=RetryPolicy(
            retries=configured_retries,
            base_delay_seconds=base_delay_seconds,
            backoff_step_seconds=1.0,
            jitter_seconds=jitter_seconds,
        ),
        retry_event="report_pipeline_retry",
        retry_fields_builder=lambda exc, attempt: {
            "file_id": file.file_id,
            "attempt": attempt + 1,
            "code": exc.code if isinstance(exc, AppError) else "",
        },
        failure_event="report_pipeline_failed",
        failure_fields_builder=lambda exc, attempt, retryable: {
            "file_id": file.file_id,
            "code": exc.code if isinstance(exc, AppError) else "",
            "error": exc.message if isinstance(exc, AppError) else str(exc),
            "attempt": attempt,
            "retryable": retryable,
        },
        is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
        sleep_fn=time.sleep,
    )
