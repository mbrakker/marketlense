from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    ReportCategoryProjection,
    ReportClaimProjection,
    ReportFigureProjection,
    ReportFindingProjection,
    ReportMetricProjection,
    ReportQuoteProjection,
    ReportSectionProjection,
    ReportTagProjection,
)
from src.contracts.semantic_ids import ReportId
from src.generators._analytics_projection.common import (
    _clean_int_list,
    _clean_string_list,
    _clean_text,
    _lineage,
    _source_pack_model,
    _uid,
)
from src.utils.errors import AppError

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
    metric_spine: Any,
    generated_at_utc: str,
    analysis_run_id: str,
) -> list[ReportMetricProjection]:
    metrics: list[Any] = metric_spine if isinstance(metric_spine, list) else []
    rows: list[ReportMetricProjection] = []
    for index, raw in enumerate(metrics):
        if not isinstance(raw, dict):
            continue
        metric_id = _clean_text(raw.get("metric_id"))
        metric = _clean_text(raw.get("label") or raw.get("metric"))
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
                    source_pack="artifacts.metric_spine",
                    source_ref=f"metric_spine[{index}]",
                    generated_at_utc=generated_at_utc,
                    analysis_run_id=analysis_run_id,
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
        page = (
            int(page_raw)
            if isinstance(page_raw, int) and not isinstance(page_raw, bool)
            else None
        )
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
                    model=_source_pack_model(
                        artifacts if source_pack == "artifacts" else quote_candidates
                    ),
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
                evidence_sections=_clean_string_list(
                    raw.get("evidence_sections") or []
                ),
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
