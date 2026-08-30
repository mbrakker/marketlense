from __future__ import annotations

import logging
from typing import Any

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
    AnalyticsProjectionBatch,
    AnalyticsProjectionBuildRequest,
    AnalyticsReportRow,
)
from src.contracts.semantic_ids import ReportId
from src.generators._analytics_projection.builders import (
    _build_categories,
    _build_claims,
    _build_figures,
    _build_findings,
    _build_metrics,
    _build_quotes,
    _build_sections,
    _build_tags,
)
from src.generators._analytics_projection.common import (
    _clean_string_list,
    _clean_text,
    _publisher_id,
    _unwrap_doc_map,
)
from src.generators._analytics_projection.vector_queue import _build_vector_queue
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.analytics_projection_generator")

def build_projection(
    request: AnalyticsProjectionBuildRequest,
) -> AnalyticsProjectionBatch:
    analysis = request.analysis
    report_id = ReportId(str(analysis.runtime.file.file_id))
    payload = analysis.normalized_payload
    title = _clean_text(payload.title or analysis.runtime.report_title)
    if not title:
        raise AppError(
            code="analytics_projection_report_title_missing",
            message="Projected report title is required",
            retryable=False,
            severity="error",
            context={"report_id": report_id},
        )
    publisher = _clean_text(payload.publisher)
    validation_status = (
        analysis.validation_report.status if analysis.validation_report else ""
    )
    validation_severity = (
        analysis.validation_report.severity if analysis.validation_report else ""
    )
    taxonomy_pack: dict[str, Any] = (
        analysis.evidence_packs.get("taxonomy", {})
        if isinstance(analysis.evidence_packs.get("taxonomy", {}), dict)
        else {}
    )
    category_pack: dict[str, Any] = (
        analysis.evidence_packs.get("context_category_fit", {})
        if isinstance(analysis.evidence_packs.get("context_category_fit", {}), dict)
        else {}
    )
    artifacts: dict[str, Any] = (
        analysis.artifacts_payload
        if isinstance(analysis.artifacts_payload, dict)
        else {}
    )
    doc_map = _unwrap_doc_map(
        analysis.evidence_packs.get("doc_map", {})
        if isinstance(analysis.evidence_packs.get("doc_map", {}), dict)
        else {}
    )
    generated_at_utc = request.generated_at_utc
    analysis_run_id = str(analysis.runtime.ctx.run_id)
    report = AnalyticsReportRow(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        report_id=report_id,
        title=title,
        publisher=publisher,
        publisher_id=_publisher_id(publisher),
        source_md5=analysis.runtime.md5,
        ingest_run_id=str(analysis.runtime.ctx.run_id),
        analysis_run_id=analysis_run_id,
        region=_clean_text(payload.region),
        time_period=_clean_text(payload.time_period),
        validation_status=validation_status,
        validation_severity=validation_severity,
        text_density=float(getattr(payload, "_text_density", 0.0) or 0.0),
        text_not_available=bool(getattr(payload, "_text_not_available", False)),
        projection_generated_at_utc=generated_at_utc,
        source_url=_clean_text(payload.source),
    )
    sections = _build_sections(
        report_id=report_id,
        doc_map=doc_map,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    findings = _build_findings(
        report_id=report_id,
        findings_pack=analysis.evidence_packs.get("findings", {}),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    metrics = _build_metrics(
        report_id=report_id,
        metric_spine=artifacts.get("metric_spine", []),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    quotes = _build_quotes(
        report_id=report_id,
        artifacts=artifacts,
        quote_candidates=analysis.evidence_packs.get("quote_candidates", {}),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    claims = _build_claims(
        report_id=report_id,
        artifacts=artifacts,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    payload_taxonomy = _clean_string_list(payload.taxonomy)
    tags = _build_tags(
        report_id=report_id,
        taxonomy_pack=taxonomy_pack,
        payload_taxonomy=payload_taxonomy,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    payload_categories = _clean_string_list(payload.categories)
    categories = _build_categories(
        report_id=report_id,
        category_pack=category_pack,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    figures = _build_figures(
        report_id=report_id,
        figure_assets=list(getattr(payload, "_figure_assets", []) or []),
        figure_pack=analysis.evidence_packs.get("figure_captions", {}),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    vector_queue = _build_vector_queue(
        report=report,
        sections=sections,
        findings=findings,
        metrics=metrics,
        quotes=quotes,
        claims=claims,
        figures=figures,
        artifacts=artifacts,
        category_ids=payload_categories,
        taxonomy=payload_taxonomy,
        generated_at_utc=generated_at_utc,
    )
    batch = AnalyticsProjectionBatch(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        report=report,
        sections=sections,
        findings=findings,
        metrics=metrics,
        quotes=quotes,
        claims=claims,
        tags=tags,
        categories=categories,
        figures=figures,
        vector_queue=vector_queue,
    )
    logger.info(
        log_event(
            analysis.runtime.ctx,
            role="generator",
            event="analytics_projection_built",
            module=logger.name,
            fields={
                "report_id": report_id,
                "section_count": len(sections),
                "finding_count": len(findings),
                "metric_count": len(metrics),
                "quote_count": len(quotes),
                "claim_count": len(claims),
                "tag_count": len(tags),
                "category_count": len(categories),
                "figure_count": len(figures),
                "vector_queue_count": len(vector_queue),
            },
        )
    )
    return batch
