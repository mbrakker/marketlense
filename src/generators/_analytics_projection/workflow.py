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
from src.contracts.report_generation import VerifiedAuthorityContext
from src.contracts.semantic_ids import PublisherId, ReportId
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
from src.utils.verified_facts import (
    build_verified_authority_context,
    verified_facts_mode,
    verified_source_identity_matches_runtime,
)

logger = logging.getLogger("market_lense.analytics_projection_generator")


def _validation_allows_source(validation_status: str, validation_severity: str) -> bool:
    return str(validation_status or "").strip().casefold() == "pass" and str(
        validation_severity or ""
    ).strip().casefold() not in {"error", "fail"}


def _verified_projection_authority(
    analysis: Any,
) -> VerifiedAuthorityContext | None:
    """Return only a context revalidated from the retained canonical snapshot."""

    artifacts = (
        analysis.artifacts_payload
        if isinstance(analysis.artifacts_payload, dict)
        else {}
    )
    authority = analysis.verified_authority_context
    if authority is None:
        if verified_facts_mode(artifacts, ""):
            raise AppError(
                code="analytics_projection_verified_authority_missing",
                message=(
                    "Verified analytics projection has no trusted authority context"
                ),
                retryable=False,
                severity="error",
            )
        return None
    try:
        canonical = build_verified_authority_context(
            artifacts, expected_source_identity=authority.source_identity
        )
    except AppError as exc:
        raise AppError(
            code="analytics_projection_verified_authority_invalid",
            message=(
                "Verified analytics projection authority could not be revalidated"
            ),
            cause=exc,
            retryable=False,
            severity="error",
        ) from exc
    runtime_identity = str(
        getattr(getattr(analysis.runtime, "ctx", None), "source_identity_id", "") or ""
    ).strip()
    if not verified_source_identity_matches_runtime(
        runtime_identity, canonical.source_identity
    ):
        raise AppError(
            code="analytics_projection_verified_authority_invalid",
            message=(
                "Verified analytics projection source identity does not match runtime"
            ),
            retryable=False,
            severity="error",
        )
    if canonical != authority:
        raise AppError(
            code="analytics_projection_verified_authority_invalid",
            message="Verified analytics projection retained authority is stale",
            retryable=False,
            severity="error",
        )
    if analysis.authoritative_evidence_packs != canonical.evidence_packs:
        raise AppError(
            code="analytics_projection_verified_authority_invalid",
            message="Verified analytics projection evidence packs are not canonical",
            retryable=False,
            severity="error",
        )
    return canonical


def _verified_metric_spine(authority: VerifiedAuthorityContext) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    findings_by_fact_id = {
        str(row.get("verified_fact_id")): row
        for row in authority.evidence_packs.get("findings", {}).get("findings", [])
        if isinstance(row, dict) and row.get("verified_fact_id")
    }
    for fact_id, fact in authority.verified_facts.items():
        metric = fact.get("metric") if isinstance(fact, dict) else None
        if not isinstance(metric, dict):
            continue
        label = _clean_text(metric.get("label") or metric.get("metric"))
        value = _clean_text(metric.get("value"))
        if not label or not value:
            continue
        evidence_id = f"verified-fact:{fact_id}"
        rows.append(
            {
                "metric_id": str(fact_id),
                "label": label,
                "value": value,
                "unit": _clean_text(metric.get("unit")),
                "evidence_id": evidence_id,
                "pages": list(fact.get("supporting_physical_pages") or []),
                "verified_fact_id": str(fact_id),
                "source_identity": str(fact.get("source_identity") or ""),
                "source_pdf_sha256": str(fact.get("source_pdf_sha256") or ""),
                "verified_fact_digest": authority.verified_fact_digest,
                "metric_context": metric,
                "evidence_spans": findings_by_fact_id.get(str(fact_id), {}).get(
                    "evidence_spans", []
                ),
            }
        )
    return rows


def build_projection(
    request: AnalyticsProjectionBuildRequest,
) -> AnalyticsProjectionBatch:
    analysis = request.analysis
    authority = _verified_projection_authority(analysis)
    verified_mode = authority is not None
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
    publisher = _clean_text(analysis.runtime.publisher_name) or _clean_text(
        payload.publisher
    )
    canonical_publisher_id = _clean_text(analysis.runtime.ctx.publisher_id)
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
        publisher_id=(
            PublisherId(canonical_publisher_id)
            if canonical_publisher_id
            else _publisher_id(publisher)
        ),
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
        authority_mode="verified" if verified_mode else "normal",
        source_validation_eligible=_validation_allows_source(
            validation_status, validation_severity
        ),
        verified_source_identity=authority.source_identity if authority else "",
        verified_source_pdf_sha256=authority.source_pdf_sha256 if authority else "",
        verified_fact_digest=authority.verified_fact_digest if authority else "",
    )
    sections = _build_sections(
        report_id=report_id,
        doc_map=doc_map,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    findings = _build_findings(
        report_id=report_id,
        findings_pack=(
            authority.evidence_packs.get("findings", {})
            if authority
            else analysis.evidence_packs.get("findings", {})
        ),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
        authority=(
            {
                "source_identity": authority.source_identity,
                "source_pdf_sha256": authority.source_pdf_sha256,
                "verified_fact_digest": authority.verified_fact_digest,
            }
            if authority
            else None
        ),
    )
    metrics = _build_metrics(
        report_id=report_id,
        metric_spine=(
            _verified_metric_spine(authority)
            if authority
            else artifacts.get("metric_spine", [])
        ),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    quotes = _build_quotes(
        report_id=report_id,
        artifacts=artifacts,
        quote_candidates=(
            {} if authority else analysis.evidence_packs.get("quote_candidates", {})
        ),
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
    )
    claims = _build_claims(
        report_id=report_id,
        artifacts=artifacts,
        generated_at_utc=generated_at_utc,
        analysis_run_id=analysis_run_id,
        verified_evidence_ids=None,
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
        verified_mode=verified_mode,
        verified_evidence_ids=(
            {
                str(
                    row.get("evidence_id")
                    or f"verified-fact:{row.get('verified_fact_id')}"
                )
                for row in authority.evidence_packs.get("findings", {}).get(
                    "findings", []
                )
                if isinstance(row, dict) and row.get("verified_fact_id")
            }
            if authority
            else None
        ),
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
