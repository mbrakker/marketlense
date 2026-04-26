from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from typing import Any, Iterable, Optional

from src.contracts.analytics_projection import (
    AnalyticsProjectionBatch,
    AnalyticsProjectionBuildRequest,
    AnalyticsReportRow,
    ContentClass,
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
    ProjectionLineage,
    ReportCategoryProjection,
    ReportClaimProjection,
    ReportFigureProjection,
    ReportFindingProjection,
    ReportMetricProjection,
    ReportQuoteProjection,
    ReportSectionProjection,
    ReportTagProjection,
    VectorProjectionQueueRow,
)
from src.contracts.semantic_ids import EntityUid, PublisherId, ReportId
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.analytics_projection_generator")

_SAFE_TOKEN_RX = re.compile(r"[^A-Za-z0-9._:-]+")


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_string_list(values: Iterable[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        item = _clean_text(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _clean_int_list(values: Iterable[Any]) -> list[int]:
    cleaned: list[int] = []
    for value in values or []:
        if isinstance(value, bool):
            continue
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def _hash_payload(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _safe_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RX.sub("-", str(value or "").strip()).strip("-")
    return cleaned[:96] if cleaned else ""


def _uid(
    report_id: ReportId, entity_type: str, local_id: str, payload: Any
) -> EntityUid:
    token = _safe_token(local_id)
    if not token:
        token = _hash_payload(payload)[:16]
    return EntityUid(f"{report_id}:{entity_type}:{token}")


def _publisher_id(publisher: str) -> Optional[PublisherId]:
    token = _safe_token(publisher.lower())
    if not token:
        return None
    return PublisherId(f"publisher:{token}")


def _lineage(
    *,
    source_pack: str,
    source_ref: str,
    generated_at_utc: str,
    analysis_run_id: str,
    model: str = "",
) -> ProjectionLineage:
    return ProjectionLineage(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_version=PROJECTION_VERSION,
        source_pack=source_pack,
        source_ref=source_ref,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
        model=model,
    )


def _unwrap_doc_map(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = payload.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    return candidate


def _source_pack_model(payload: dict[str, Any]) -> str:
    raw_cache = payload.get("_cache")
    cache: dict[str, Any] = raw_cache if isinstance(raw_cache, dict) else {}
    return _clean_text(payload.get("model") or cache.get("model"))


def _report_summary_text(
    *,
    title: str,
    publisher: str,
    tldr: str,
    executive_summary: str,
    category_ids: list[str],
    taxonomy: list[str],
) -> str:
    parts = [
        f"Title: {title}",
        f"Publisher: {publisher}" if publisher else "",
        f"TLDR: {tldr}" if tldr else "",
        f"Executive summary: {executive_summary}" if executive_summary else "",
        f"Categories: {', '.join(category_ids)}" if category_ids else "",
        f"Taxonomy: {', '.join(taxonomy)}" if taxonomy else "",
    ]
    return "\n".join(part for part in parts if part)


def _section_text(section: ReportSectionProjection) -> str:
    parts = [
        f"Title: {section.title}",
        f"Summary: {section.summary}" if section.summary else "",
    ]
    if section.key_points:
        parts.append("Key points: " + "; ".join(section.key_points))
    return "\n".join(part for part in parts if part)


def _finding_text(finding: ReportFindingProjection) -> str:
    parts = [f"Finding: {finding.text}"]
    if finding.evidence:
        parts.append(f"Evidence: {finding.evidence}")
    if finding.confidence:
        parts.append(f"Confidence: {finding.confidence}")
    return "\n".join(parts)


def _metric_text(metric: ReportMetricProjection) -> str:
    value_parts = [metric.value]
    if metric.unit:
        value_parts.append(metric.unit)
    parts = [
        f"Metric: {metric.metric}",
        "Value: " + " ".join(value_parts).strip(),
    ]
    if metric.evidence_id:
        parts.append(f"Evidence ID: {metric.evidence_id}")
    return "\n".join(parts)


def _quote_text(quote: ReportQuoteProjection) -> str:
    parts = [f"Quote: {quote.text}"]
    if quote.speaker:
        parts.append(f"Speaker: {quote.speaker}")
    if quote.citation:
        parts.append(f"Citation: {quote.citation}")
    return "\n".join(parts)


def _claim_text(claim: ReportClaimProjection) -> str:
    parts = [f"Claim: {claim.claim}"]
    if claim.evidence:
        parts.append(f"Evidence: {claim.evidence}")
    return "\n".join(parts)


def _figure_text(figure: ReportFigureProjection) -> str:
    caption = (
        figure.display_caption
        or figure.generated_caption
        or figure.detected_caption
        or figure.image_path
    )
    parts = [f"Figure caption: {caption}"]
    if figure.kind:
        parts.append(f"Figure kind: {figure.kind}")
    return "\n".join(parts)


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


def _build_sections(
    *,
    report_id: ReportId,
    doc_map: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportSectionProjection]:
    raw_sections = doc_map.get("sections")
    sections: list[Any] = raw_sections if isinstance(raw_sections, list) else []
    rows: list[ReportSectionProjection] = []
    for index, raw in enumerate(sections):
        if not isinstance(raw, dict):
            continue
        section_id = _clean_text(raw.get("id"))
        title = _clean_text(raw.get("title"))
        summary = _clean_text(raw.get("summary"))
        if not section_id or not title:
            raise AppError(
                code="analytics_projection_section_contract_invalid",
                message="DocMap section projection requires id and title",
                retryable=False,
                severity="error",
                context={"report_id": report_id, "index": index},
            )
        row = ReportSectionProjection(
            schema_version=PROJECTION_SCHEMA_VERSION,
            section_uid=_uid(report_id, "section", section_id, raw),
            report_id=report_id,
            section_id=section_id,
            title=title,
            summary=summary,
            key_points=_clean_string_list(raw.get("key_points") or []),
            pages=_clean_int_list(raw.get("pages") or []),
            order_index=index,
            lineage=_lineage(
                source_pack="doc_map",
                source_ref=f"sections[{index}]",
                generated_at_utc=generated_at_utc,
                analysis_run_id=analysis_run_id,
                model=_source_pack_model(doc_map),
            ),
        )
        rows.append(row)
    return rows


def _build_findings(
    *,
    report_id: ReportId,
    findings_pack: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportFindingProjection]:
    raw_findings = findings_pack.get("findings")
    findings: list[Any] = raw_findings if isinstance(raw_findings, list) else []
    rows: list[ReportFindingProjection] = []
    for index, raw in enumerate(findings):
        if not isinstance(raw, dict):
            continue
        finding_id = _clean_text(raw.get("id"))
        text = _clean_text(raw.get("text"))
        if not finding_id or not text:
            raise AppError(
                code="analytics_projection_finding_contract_invalid",
                message="Finding projection requires id and text",
                retryable=False,
                severity="error",
                context={"report_id": report_id, "index": index},
            )
        rows.append(
            ReportFindingProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                finding_uid=_uid(report_id, "finding", finding_id, raw),
                report_id=report_id,
                finding_id=finding_id,
                text=text,
                evidence=_clean_text(raw.get("evidence")),
                confidence=_clean_text(raw.get("confidence")),
                pages=_clean_int_list(raw.get("pages") or []),
                lineage=_lineage(
                    source_pack="findings",
                    source_ref=f"findings[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(findings_pack),
                ),
            )
        )
    return rows


def _build_metrics(
    *,
    report_id: ReportId,
    metrics_pack: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportMetricProjection]:
    raw_metrics = metrics_pack.get("key_metrics")
    metrics: list[Any] = raw_metrics if isinstance(raw_metrics, list) else []
    rows: list[ReportMetricProjection] = []
    for index, raw in enumerate(metrics):
        if not isinstance(raw, dict):
            continue
        metric_id = _clean_text(raw.get("id"))
        metric = _clean_text(raw.get("metric"))
        value = _clean_text(raw.get("value"))
        if not metric_id or not metric or not value:
            raise AppError(
                code="analytics_projection_metric_contract_invalid",
                message="Metric projection requires id, metric, and value",
                retryable=False,
                severity="error",
                context={"report_id": report_id, "index": index},
            )
        rows.append(
            ReportMetricProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                metric_uid=_uid(report_id, "metric", metric_id, raw),
                report_id=report_id,
                metric_id=metric_id,
                metric=metric,
                value=value,
                unit=_clean_text(raw.get("unit")),
                evidence_id=_clean_text(raw.get("evidence_id")),
                pages=_clean_int_list(raw.get("pages") or []),
                lineage=_lineage(
                    source_pack="key_metrics",
                    source_ref=f"key_metrics[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(metrics_pack),
                ),
            )
        )
    return rows


def _build_quotes(
    *,
    report_id: ReportId,
    artifacts: dict[str, Any],
    quote_candidates: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportQuoteProjection]:
    source_pack = "artifacts"
    raw_quotes = artifacts.get("quotes_final")
    if not isinstance(raw_quotes, list) or not raw_quotes:
        source_pack = "quote_candidates"
        raw_quotes = quote_candidates.get("quote_candidates")
    quotes = raw_quotes if isinstance(raw_quotes, list) else []
    rows: list[ReportQuoteProjection] = []
    for index, raw in enumerate(quotes):
        if not isinstance(raw, dict):
            continue
        text = _clean_text(raw.get("text"))
        if not text:
            raise AppError(
                code="analytics_projection_quote_contract_invalid",
                message="Quote projection requires text",
                retryable=False,
                severity="error",
                context={"report_id": report_id, "index": index},
            )
        quote_id = _clean_text(
            raw.get("id") or raw.get("evidence_id") or f"quote-{index + 1}"
        )
        page_raw = raw.get("page")
        page = int(page_raw) if isinstance(page_raw, int) and not isinstance(page_raw, bool) else None
        rows.append(
            ReportQuoteProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                quote_uid=_uid(report_id, "quote", quote_id, raw),
                report_id=report_id,
                quote_id=quote_id,
                text=text,
                speaker=_clean_text(raw.get("speaker") or raw.get("source")),
                citation=_clean_text(raw.get("citation")),
                page=page,
                evidence_id=_clean_text(raw.get("evidence_id")),
                lineage=_lineage(
                    source_pack=source_pack,
                    source_ref=f"{source_pack}[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(artifacts if source_pack == "artifacts" else quote_candidates),
                ),
            )
        )
    return rows


def _build_claims(
    *,
    report_id: ReportId,
    artifacts: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportClaimProjection]:
    raw_summary = artifacts.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    raw_claims = summary.get("claim_evidence_map")
    claims: list[Any] = raw_claims if isinstance(raw_claims, list) else []
    rows: list[ReportClaimProjection] = []
    for index, raw in enumerate(claims):
        if not isinstance(raw, dict):
            continue
        claim = _clean_text(raw.get("claim"))
        evidence = _clean_text(raw.get("evidence"))
        if not claim:
            raise AppError(
                code="analytics_projection_claim_contract_invalid",
                message="Claim projection requires claim text",
                retryable=False,
                severity="error",
                context={"report_id": report_id, "index": index},
            )
        rows.append(
            ReportClaimProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                claim_uid=_uid(report_id, "claim", "", {"index": index, **raw}),
                report_id=report_id,
                claim=claim,
                evidence_id=_clean_text(raw.get("evidence_id")),
                evidence=evidence,
                pages=_clean_int_list(raw.get("pages") or []),
                lineage=_lineage(
                    source_pack="artifacts",
                    source_ref=f"summary.claim_evidence_map[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(artifacts),
                ),
            )
        )
    return rows


def _build_tags(
    *,
    report_id: ReportId,
    taxonomy_pack: dict[str, Any],
    payload_taxonomy: list[str],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportTagProjection]:
    rows: list[ReportTagProjection] = []
    specs = [
        ("taxonomy", taxonomy_pack.get("taxonomy") or payload_taxonomy),
        ("primary", taxonomy_pack.get("primary_tags") or []),
        ("secondary", taxonomy_pack.get("secondary_tags") or []),
    ]
    for tag_type, values in specs:
        for index, tag in enumerate(_clean_string_list(values)):
            rows.append(
                ReportTagProjection(
                    schema_version=PROJECTION_SCHEMA_VERSION,
                    tag_uid=_uid(report_id, "tag", f"{tag_type}:{tag.lower()}", tag),
                    report_id=report_id,
                    tag=tag,
                    tag_type=tag_type,
                    lineage=_lineage(
                        source_pack="taxonomy",
                        source_ref=f"{tag_type}[{index}]",
                        generated_at_utc=generated_at_utc,
                        analysis_run_id=analysis_run_id,
                        model=_source_pack_model(taxonomy_pack),
                    ),
                )
            )
    return rows


def _build_categories(
    *,
    report_id: ReportId,
    category_pack: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportCategoryProjection]:
    selected_ids = _clean_string_list(category_pack.get("selected_category_ids") or [])
    raw_fits = category_pack.get("category_fits")
    fits: list[Any] = raw_fits if isinstance(raw_fits, list) else []
    rows: list[ReportCategoryProjection] = []
    seen: set[str] = set()
    for index, raw in enumerate(fits):
        if not isinstance(raw, dict):
            continue
        category_id = _clean_text(raw.get("category_id"))
        if not category_id:
            continue
        seen.add(category_id)
        rows.append(
            ReportCategoryProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                category_uid=_uid(report_id, "category", category_id, raw),
                report_id=report_id,
                category_id=category_id,
                label=_clean_text(raw.get("label")),
                fit_score=float(raw.get("fit_score") or 0.0),
                decision=_clean_text(raw.get("decision")),
                selected=category_id in selected_ids,
                evidence_sections=_clean_string_list(raw.get("evidence_sections") or []),
                lineage=_lineage(
                    source_pack="context_category_fit",
                    source_ref=f"category_fits[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(category_pack),
                ),
            )
        )
    for index, category_id in enumerate(selected_ids):
        if category_id in seen:
            continue
        rows.append(
            ReportCategoryProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                category_uid=_uid(report_id, "category", category_id, category_id),
                report_id=report_id,
                category_id=category_id,
                label="",
                fit_score=0.0,
                decision="selected",
                selected=True,
                evidence_sections=[],
                lineage=_lineage(
                    source_pack="context_category_fit",
                    source_ref=f"selected_category_ids[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=_source_pack_model(category_pack),
                ),
            )
        )
    return rows


def _build_figures(
    *,
    report_id: ReportId,
    figure_assets: list[Any],
    figure_pack: dict[str, Any],
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportFigureProjection]:
    rows: list[ReportFigureProjection] = []
    model = _source_pack_model(figure_pack)
    for index, asset in enumerate(figure_assets):
        raw = asdict(asset) if hasattr(asset, "__dataclass_fields__") else dict(asset)
        candidate_id = _clean_text(raw.get("candidate_id") or f"figure-{index + 1}")
        image_path = _clean_text(raw.get("image_path"))
        caption = _clean_text(
            raw.get("display_caption")
            or raw.get("generated_caption")
            or raw.get("detected_caption")
        )
        if not image_path and not caption:
            continue
        rows.append(
            ReportFigureProjection(
                schema_version=PROJECTION_SCHEMA_VERSION,
                figure_uid=_uid(report_id, "figure", candidate_id, raw),
                report_id=report_id,
                candidate_id=candidate_id,
                image_path=image_path,
                kind=_clean_text(raw.get("kind")),
                page=int(raw.get("page") or -1),
                is_primary=bool(raw.get("is_primary")),
                detected_caption=_clean_text(raw.get("detected_caption")),
                generated_caption=_clean_text(raw.get("generated_caption")),
                display_caption=_clean_text(raw.get("display_caption")),
                caption_source=_clean_text(raw.get("caption_source")),
                lineage=_lineage(
                    source_pack="figure_captions" if figure_pack else "report_payload",
                    source_ref=f"_figure_assets[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
                    model=model,
                ),
            )
        )
    return rows


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
        analysis.artifacts_payload if isinstance(analysis.artifacts_payload, dict) else {}
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
        metrics_pack=analysis.evidence_packs.get("key_metrics", {}),
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
