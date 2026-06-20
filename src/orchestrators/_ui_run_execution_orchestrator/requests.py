from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import hashlib
import json
from typing import Any, cast

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    PublicationMode,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
)
from src.contracts.ui_run_payloads import (
    CrossReportAnalysisUiRunPayload,
    SignalCandidateExtractionUiRunPayload,
    SignalPostUiRunPayload,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPostWorkflowRequest,
)

from .shared import *  # noqa: F401,F403
from .validation import _validate_ui_run_payload


def _stable_request_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:16]}"


def _cross_report_analysis_request(
    payload: CrossReportAnalysisUiRunPayload,
    settings: Any,
) -> CrossReportAnalysisOrchestratorRequest:
    material = {
        "topic": payload.topic,
        "auto_theme": payload.auto_theme,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": payload.max_source_reports,
        "max_evidence_items": payload.max_evidence_items,
        "max_prompt_chars": payload.max_prompt_chars,
        "publication_mode": payload.publication_mode,
    }
    max_source_reports = payload.max_source_reports or int(
        getattr(settings, "cross_report_analysis_max_source_reports", 6)
    )
    max_evidence_items = payload.max_evidence_items or int(
        getattr(settings, "cross_report_analysis_max_evidence_items", 48)
    )
    max_prompt_chars = payload.max_prompt_chars or int(
        getattr(settings, "cross_report_analysis_max_prompt_chars", 60000)
    )
    request_id = payload.request_id or _stable_request_id("ui-cross-report", material)
    analysis_request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=payload.topic,
        auto_theme=payload.auto_theme,
        category_filters=list(payload.category_filters),
        tag_filters=list(payload.tag_filters),
        publisher_filters=list(payload.publisher_filters),
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        max_source_reports=max_source_reports,
        diagnostic=payload.diagnostic,
        override_publishability=payload.override_publishability,
        publication_mode=cast(PublicationMode, payload.publication_mode),
    )
    return CrossReportAnalysisOrchestratorRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_request=analysis_request,
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        idempotency_db_path=payload.idempotency_db or settings.state_db,
        output_root=payload.output_root or settings.output_dir,
        max_evidence_items=max_evidence_items,
        max_signals=8,
        max_prompt_chars=max_prompt_chars,
        retry_retries=2,
        retry_base_delay_seconds=1.0,
        retry_backoff_step_seconds=1.0,
        retry_jitter_seconds=0.25,
        publish_target_route="wordpress:ml_briefing",
    )


def _signal_analysis_request(
    *,
    request_id: str,
    topic: str,
    category_filters: list[str],
    tag_filters: list[str],
    publisher_filters: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
    max_source_reports: int,
    publication_mode: PublicationMode,
) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=topic,
        auto_theme=False,
        category_filters=category_filters,
        tag_filters=tag_filters,
        publisher_filters=publisher_filters,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        max_source_reports=max_source_reports,
        diagnostic=False,
        override_publishability=True,
        publication_mode=publication_mode,
    )


def _signal_candidate_request(
    payload: SignalCandidateExtractionUiRunPayload,
    settings: Any,
) -> SignalCandidateExtractionRequest:
    max_source_reports = payload.max_source_reports or int(
        getattr(settings, "cross_report_analysis_max_source_reports", 6)
    )
    max_evidence_items = payload.max_evidence_items or int(
        getattr(settings, "cross_report_analysis_max_evidence_items", 48)
    )
    max_signals = payload.max_signals or 8
    material = {
        "topic": payload.topic,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": max_source_reports,
        "max_evidence_items": max_evidence_items,
        "max_signals": max_signals,
    }
    extraction_id = payload.extraction_request_id or _stable_request_id(
        "ui-signal-candidates", material
    )
    analysis_request = _signal_analysis_request(
        request_id=extraction_id,
        topic=payload.topic,
        category_filters=list(payload.category_filters),
        tag_filters=list(payload.tag_filters),
        publisher_filters=list(payload.publisher_filters),
        date_range_start=payload.date_range_start,
        date_range_end=payload.date_range_end,
        max_source_reports=max_source_reports,
        publication_mode="generate_only",
    )
    return SignalCandidateExtractionRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        extraction_request_id=extraction_id,
        analysis_request=analysis_request,
        projected_data_request=CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=settings.reports_db,
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        db_path=payload.signal_store_db
        or settings.signal_store_db
        or settings.reports_db,
        max_evidence_items=max_evidence_items,
        max_signals=max_signals,
        generated_at_utc="",
    )


def _signal_post_request(
    payload: SignalPostUiRunPayload,
    settings: Any,
) -> SignalPostWorkflowRequest:
    max_source_reports = payload.max_source_reports or 3
    max_evidence_items = payload.max_evidence_items or 6
    material = {
        "topic": payload.topic,
        "category_filters": payload.category_filters,
        "tag_filters": payload.tag_filters,
        "publisher_filters": payload.publisher_filters,
        "date_range_start": payload.date_range_start,
        "date_range_end": payload.date_range_end,
        "max_source_reports": max_source_reports,
        "max_evidence_items": max_evidence_items,
        "publication_mode": payload.publication_mode,
    }
    request_id = payload.request_id or _stable_request_id("ui-signal-post", material)
    return SignalPostWorkflowRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id=request_id,
        generation_request=SignalPostGenerationRequest(
            schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
            request_id=request_id,
            topic=payload.topic,
            category_filters=list(payload.category_filters),
            tag_filters=list(payload.tag_filters),
            publisher_filters=list(payload.publisher_filters),
            date_range_start=payload.date_range_start,
            date_range_end=payload.date_range_end,
            max_source_reports=max_source_reports,
            max_evidence_items=max_evidence_items,
            minimum_source_reports=payload.minimum_source_reports or 2,
            minimum_evidence_items=payload.minimum_evidence_items or 2,
            target_route="wordpress:ml_signal",
        ),
        db_path=settings.reports_db,
        output_root=payload.output_root or settings.output_dir,
        cover_style_path=settings.cover_style_path,
        publication_mode=cast(PublicationMode, payload.publication_mode),
        signal_store_db=payload.signal_store_db
        or settings.signal_store_db
        or settings.reports_db,
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
