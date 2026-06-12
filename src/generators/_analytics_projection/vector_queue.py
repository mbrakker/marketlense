from __future__ import annotations

from typing import Any

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    AnalyticsReportRow,
    ContentClass,
    ReportClaimProjection,
    ReportFigureProjection,
    ReportFindingProjection,
    ReportMetricProjection,
    ReportQuoteProjection,
    ReportSectionProjection,
    VectorProjectionQueueRow,
)
from src.contracts.semantic_ids import EntityUid, ReportId
from src.generators._analytics_projection.common import _clean_text, _hash_payload, _uid
from src.generators._analytics_projection.text_payloads import (
    _claim_text,
    _figure_text,
    _finding_text,
    _metric_text,
    _quote_text,
    _report_summary_text,
    _section_text,
)

def _queue_metadata(
    *,
    report: AnalyticsReportRow,
    entity_type: str,
    pages: list[int],
    source_pack: str,
    source_ref: str,
    category_ids: list[str],
    taxonomy: list[str],
    validation_status: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "entity_type": entity_type,
        "report_id": str(report.report_id),
        "publisher_id": str(report.publisher_id) if report.publisher_id else "",
        "title": report.title,
        "publisher": report.publisher,
        "region": report.region,
        "time_period": report.time_period,
        "category_ids": list(category_ids),
        "taxonomy": list(taxonomy),
        "pages": list(pages),
        "source_pack": source_pack,
        "source_ref": source_ref,
        "validation_status": validation_status,
    }

def _queue_row(
    *,
    entity_uid: EntityUid,
    entity_type: str,
    report_id: ReportId,
    text_payload: str,
    metadata: dict[str, Any],
    content_class: ContentClass,
    generated_at_utc: str,
) -> VectorProjectionQueueRow:
    content_hash = _hash_payload(
        {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "entity_type": entity_type,
            "text_payload": text_payload,
            "metadata": metadata,
            "content_class": content_class,
        }
    )
    return VectorProjectionQueueRow(
        schema_version=PROJECTION_SCHEMA_VERSION,
        entity_uid=entity_uid,
        entity_type=entity_type,
        report_id=report_id,
        text_payload=text_payload,
        content_hash=content_hash,
        metadata=metadata,
        content_class=content_class,
        embedding_status="pending",
        embedding_version="",
        created_at_utc=generated_at_utc,
        updated_at_utc=generated_at_utc,
    )

def _build_vector_queue(
    *,
    report: AnalyticsReportRow,
    sections: list[ReportSectionProjection],
    findings: list[ReportFindingProjection],
    metrics: list[ReportMetricProjection],
    quotes: list[ReportQuoteProjection],
    claims: list[ReportClaimProjection],
    figures: list[ReportFigureProjection],
    artifacts: dict[str, Any],
    category_ids: list[str],
    taxonomy: list[str],
    generated_at_utc: str,
) -> list[VectorProjectionQueueRow]:
    rows: list[VectorProjectionQueueRow] = []
    report_id = report.report_id
    raw_summary = artifacts.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    report_summary = _report_summary_text(
        title=report.title,
        publisher=report.publisher,
        tldr=_clean_text(summary.get("tldr") or getattr(report, "tldr", "")),
        executive_summary=_clean_text(summary.get("executive_summary")),
        category_ids=category_ids,
        taxonomy=taxonomy,
    )
    if report_summary:
        metadata = _queue_metadata(
            report=report,
            entity_type="report_summary",
            pages=[],
            source_pack="artifacts",
            source_ref="summary",
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=_uid(report_id, "report_summary", "report", report_summary),
                entity_type="report_summary",
                report_id=report_id,
                text_payload=report_summary,
                metadata=metadata,
                content_class="derived_evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for section in sections:
        metadata = _queue_metadata(
            report=report,
            entity_type="section",
            pages=section.pages,
            source_pack=section.lineage.source_pack,
            source_ref=section.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=section.section_uid,
                entity_type="section",
                report_id=report_id,
                text_payload=_section_text(section),
                metadata=metadata,
                content_class="evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for finding in findings:
        metadata = _queue_metadata(
            report=report,
            entity_type="finding",
            pages=finding.pages,
            source_pack=finding.lineage.source_pack,
            source_ref=finding.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=finding.finding_uid,
                entity_type="finding",
                report_id=report_id,
                text_payload=_finding_text(finding),
                metadata=metadata,
                content_class="evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for claim in claims:
        metadata = _queue_metadata(
            report=report,
            entity_type="claim",
            pages=claim.pages,
            source_pack=claim.lineage.source_pack,
            source_ref=claim.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=claim.claim_uid,
                entity_type="claim",
                report_id=report_id,
                text_payload=_claim_text(claim),
                metadata=metadata,
                content_class="derived_evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for metric in metrics:
        metadata = _queue_metadata(
            report=report,
            entity_type="metric",
            pages=metric.pages,
            source_pack=metric.lineage.source_pack,
            source_ref=metric.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=metric.metric_uid,
                entity_type="metric",
                report_id=report_id,
                text_payload=_metric_text(metric),
                metadata=metadata,
                content_class="evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for quote in quotes:
        metadata = _queue_metadata(
            report=report,
            entity_type="quote",
            pages=[quote.page] if quote.page is not None else [],
            source_pack=quote.lineage.source_pack,
            source_ref=quote.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=quote.quote_uid,
                entity_type="quote",
                report_id=report_id,
                text_payload=_quote_text(quote),
                metadata=metadata,
                content_class="evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    for figure in figures:
        metadata = _queue_metadata(
            report=report,
            entity_type="figure_caption",
            pages=[figure.page + 1] if figure.page >= 0 else [],
            source_pack=figure.lineage.source_pack,
            source_ref=figure.lineage.source_ref,
            category_ids=category_ids,
            taxonomy=taxonomy,
            validation_status=report.validation_status,
        )
        rows.append(
            _queue_row(
                entity_uid=figure.figure_uid,
                entity_type="figure_caption",
                report_id=report_id,
                text_payload=_figure_text(figure),
                metadata=metadata,
                content_class="derived_evidence",
                generated_at_utc=generated_at_utc,
            )
        )
    return rows
