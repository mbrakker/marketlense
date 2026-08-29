from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_cards import (
    DIRECTIONS,
    DOMAIN_LAYERS,
    EVIDENCE_DENSITIES,
    EVIDENCE_SHAPES,
    GEOGRAPHY_SCOPES,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.generators._artifact_generator.family_policy import (
    apply_artifact_family_policy,
)
from src.generators._artifact_generator.toc import (
    TOC_STRUCTURE_VERSION,
    TOPIC_BRIEF_MAPPING_VERSION,
    audit_topic_brief_mappings,
    build_legacy_topic_briefs,
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
from src.generators.artifact_normalization import (
    bind_artifact_evidence_spans,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_toc_entries,
)
from src.services import file_service
from src.services.prompt_service import build_llm_execution_identity
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.analysis_family import family_is_abstained
from src.utils.cache_utils import sha256_json
from src.utils.coercion import string_value as _s
from src.utils.errors import AppError
from src.utils.json_utils import dump_json_text
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
    resolve_routing_policy,
    routing_policies_from_config,
)

logger = logging.getLogger("market_lense.artifact_generator")
EVIDENCE_QUALITY_BY_SUPPORT_TYPE = {
    "direct_evidence_span": "direct_evidence_span",
    "direct_metric": "direct_metric",
    "direct_quote": "direct_quote",
    "chart_readout": "chart_readout",
    "explicit_recommendation": "explicit_recommendation",
    "explicit_risk": "explicit_risk",
    "canonical_evidence_id": "source_backed",
}


def _dump_json(value: Any) -> str:
    return dump_json_text(value)


def assemble_artifacts_payload(
    *,
    report_id: str,
    report_name: Optional[str],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    toc_bundle: Dict[str, Any],
    summary: Dict[str, Any],
    cover_semantics: Dict[str, str],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
    family_status: Dict[str, Dict[str, Any]],
    ctx: RunContext,
    category_ids: Optional[List[str]] = None,
    cache_meta: Optional[Dict[str, Any]] = None,
    validate_references: bool = True,
) -> Dict[str, Any]:
    del report_name
    toc_entries = normalize_artifact_toc_entries(toc_bundle.get("toc_entries"))
    toc_topics = [
        _s(entry.get("display_title")).strip()
        for entry in toc_entries
        if _s(entry.get("display_title")).strip()
    ]
    topic_briefs = build_legacy_topic_briefs(toc_entries=toc_entries)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_topic_briefs_built",
            module=logger.name,
            fields={
                "topic_count": len(toc_topics),
                "toc_entry_count": len(toc_entries),
                "brief_count": len(topic_briefs),
                "briefs_with_summary": len(
                    [item for item in topic_briefs if _s(item.get("summary")).strip()]
                ),
                "briefs_with_key_points": len(
                    [
                        item
                        for item in topic_briefs
                        if isinstance(item.get("key_points"), list)
                        and len(item.get("key_points") or []) > 0
                    ]
                ),
            },
        )
    )
    evidence_id_stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
    if evidence_id_stats.get("normalized_count", 0) > 0:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_ids_normalized",
                module=logger.name,
                fields=evidence_id_stats,
            )
        )
    evidence_span_stats = bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )
    if (
        evidence_span_stats.get("bound_count", 0) > 0
        or evidence_span_stats.get("unbound_count", 0) > 0
    ):
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_spans_bound",
                module=logger.name,
                fields=evidence_span_stats,
            )
        )
    metric_spine = _merge_metric_spines(
        derive_metric_spine(evidence_packs),
        derive_metric_spine_from_insights(insights_final),
    )
    topics_covered = build_topics_covered(
        toc_entries=toc_entries,
        evidence_packs=evidence_packs,
        summary=summary,
        insights_final=insights_final,
    )
    key_figures = build_key_figures(
        metric_spine=metric_spine,
        evidence_packs=evidence_packs,
        summary=summary,
        insights_final=insights_final,
    )
    chart_insight_cards = build_chart_insight_cards(
        key_figures=key_figures,
        evidence_packs=evidence_packs,
        insights_final=insights_final,
    )
    artifacts_payload: Dict[str, Any] = {
        "schema_version": "3.0",
        "categories": list(
            dict.fromkeys(
                _s(category_id).strip()
                for category_id in (category_ids or [])
                if _s(category_id).strip()
            )
        ),
        "toc_entries": toc_entries,
        "toc_topics": toc_topics,
        "toc_topics_expanded": topic_briefs,
        "metric_spine": metric_spine,
        "topics_covered": topics_covered,
        "key_figures": key_figures,
        "chart_insight_cards": chart_insight_cards,
        "summary": summary,
        "cover_semantics": _validate_cover_semantics(cover_semantics, ctx=ctx),
        "insights_candidates": insights_candidates,
        "insights_final": insights_final,
        "quotes_final": quotes_final,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": source_status,
        "family_status": family_status,
    }
    artifacts_payload["executive_advisory"] = build_executive_advisory_artifacts(
        summary=summary,
        insights_final=insights_final,
        quotes_final=quotes_final,
        metric_spine=metric_spine,
        evidence_packs=evidence_packs,
    )
    artifacts_payload["claim_ledgers"] = build_universal_claim_ledger(
        report_id=report_id,
        summary=summary,
        insights_final=insights_final,
        quotes_final=quotes_final,
        metric_spine=metric_spine,
        executive_advisory=artifacts_payload["executive_advisory"],
    )
    if cache_meta:
        artifacts_payload["_cache"] = dict(cache_meta)
    _log_topic_brief_mapping_audit(
        topic_briefs=topic_briefs,
        doc_map=doc_map,
        ctx=ctx,
    )
    try:
        _validate_artifact_semantic_fields(artifacts_payload, ctx)
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=artifacts_payload,
                schema_name="artifacts",
            ),
            ctx,
        )
        if validate_references:
            validate_evidence_references(artifacts_payload, evidence_packs, ctx)
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_schema_validation_failed",
                module=logger.name,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        raise
    return artifacts_payload


def build_universal_claim_ledger(
    *,
    report_id: str,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    metric_spine: List[Dict[str, Any]],
    executive_advisory: Dict[str, Any],
) -> List[Dict[str, Any]]:
    ledger: List[Dict[str, Any]] = []

    def _evidence_ids(*values: Any) -> List[str]:
        ids: List[str] = []
        for value in values:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    ids.append(text)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        ids.append(item.strip())
                    elif isinstance(item, dict):
                        evidence_id = _s(item.get("evidence_id")).strip()
                        if evidence_id:
                            ids.append(evidence_id)
        return sorted(dict.fromkeys(ids))

    def _append(
        *,
        artifact_section: str,
        local_id: str,
        claim_text: str,
        evidence_ids: List[str],
        spans: Any = None,
        support_type: str = "",
        confidence: str = "source_backed",
        risk: str = "low",
        evidence_quality_grade: str = "",
    ) -> None:
        text = " ".join(_s(claim_text).split())
        if not text or not evidence_ids:
            return
        span_count = len(spans) if isinstance(spans, list) else 0
        resolved_support = support_type or (
            "direct_evidence_span" if span_count else "canonical_evidence_id"
        )
        ledger.append(
            {
                "schema_version": "1.0",
                "canonical_claim_id": f"{report_id}:{artifact_section}:{local_id}",
                "claim_text": text,
                "artifact_section": artifact_section,
                "evidence_ids": evidence_ids,
                "support_type": resolved_support,
                "evidence_quality_grade": (
                    _s(evidence_quality_grade).strip()
                    or EVIDENCE_QUALITY_BY_SUPPORT_TYPE.get(
                        resolved_support, "source_backed"
                    )
                ),
                "confidence": confidence,
                "risk": risk,
                "evidence_span_count": span_count,
            }
        )

    for index, claim in enumerate(summary.get("claim_evidence_map") or [], start=1):
        if not isinstance(claim, dict):
            continue
        spans = claim.get("evidence_spans")
        _append(
            artifact_section="summary.claim_evidence_map",
            local_id=str(index),
            claim_text=_s(claim.get("claim")),
            evidence_ids=_evidence_ids(claim.get("evidence_id"), spans),
            spans=spans,
        )
    for item in insights_final:
        if not isinstance(item, dict):
            continue
        spans = item.get("evidence_spans")
        _append(
            artifact_section="insights_final",
            local_id=_s(item.get("id")).strip() or str(len(ledger) + 1),
            claim_text=_s(item.get("text")),
            evidence_ids=_evidence_ids(item.get("evidence_id"), spans),
            spans=spans,
        )
    for item in metric_spine:
        if not isinstance(item, dict):
            continue
        label = _s(item.get("label")).strip()
        value = _s(item.get("value")).strip()
        unit = _s(item.get("unit")).strip()
        claim_text = " ".join(part for part in (label, value, unit) if part)
        _append(
            artifact_section="metric_spine",
            local_id=_s(item.get("metric_id")).strip() or str(len(ledger) + 1),
            claim_text=claim_text,
            evidence_ids=_evidence_ids(item.get("evidence_id")),
            support_type="direct_metric",
            confidence=_s(item.get("confidence")).strip() or "source_backed",
            risk="medium" if item.get("missing_context_notes") else "low",
        )
    advisory = executive_advisory if isinstance(executive_advisory, dict) else {}
    recommendations = advisory.get("recommendations")
    if isinstance(recommendations, dict):
        for index, item in enumerate(recommendations.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            _append(
                artifact_section="executive_advisory.recommendations",
                local_id=_s(item.get("id")).strip() or str(index),
                claim_text=_s(item.get("recommendation") or item.get("text")),
                evidence_ids=_evidence_ids(item.get("evidence_id")),
                support_type="explicit_recommendation",
                risk="medium",
            )
    risks = advisory.get("risks")
    if isinstance(risks, dict):
        for index, item in enumerate(risks.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            _append(
                artifact_section="executive_advisory.risks",
                local_id=_s(item.get("id")).strip() or str(index),
                claim_text=_s(item.get("risk") or item.get("text")),
                evidence_ids=_evidence_ids(item.get("evidence_id")),
                support_type="explicit_risk",
                risk="medium",
            )
    for index, quote in enumerate(quotes_final, start=1):
        if not isinstance(quote, dict):
            continue
        spans = quote.get("evidence_spans")
        _append(
            artifact_section="quotes_final",
            local_id=_s(quote.get("id")).strip() or str(index),
            claim_text=_s(quote.get("text")),
            evidence_ids=_evidence_ids(quote.get("evidence_id"), spans),
            spans=spans,
            support_type="direct_quote",
        )
    return ledger


def derive_metric_spine(evidence_packs: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_metrics: list[Any] = []
    key_metrics = (
        evidence_packs.get("key_metrics") if isinstance(evidence_packs, dict) else {}
    )
    if isinstance(key_metrics, dict):
        raw_metrics = key_metrics.get("metrics") or key_metrics.get("key_metrics") or []
    if not isinstance(raw_metrics, list):
        return []
    spine: List[Dict[str, Any]] = []
    for raw in raw_metrics:
        if not isinstance(raw, dict):
            continue
        value = _s(raw.get("value") or raw.get("raw_value")).strip()
        unit = _s(raw.get("unit")).strip()
        evidence_id = _s(raw.get("evidence_id")).strip()
        label = _s(raw.get("label") or raw.get("metric")).strip()
        if not value or not unit or not evidence_id or not label:
            continue
        missing_context_notes = [
            field_name
            for field_name in ("timeframe", "segment", "geography")
            if not _s(raw.get(field_name)).strip()
        ]
        spine.append(
            {
                "schema_version": "1.0",
                "metric_id": _s(raw.get("metric_id") or evidence_id).strip(),
                "label": label,
                "value": value,
                "unit": unit,
                "timeframe": _s(raw.get("timeframe")).strip(),
                "segment": _s(raw.get("segment")).strip(),
                "geography": _s(raw.get("geography")).strip(),
                "comparator": _s(raw.get("comparator")).strip(),
                "baseline": _s(raw.get("baseline")).strip(),
                "delta": _s(raw.get("delta")).strip(),
                "sample_size": _s(raw.get("sample_size")).strip(),
                "confidence": (_s(raw.get("confidence")).strip() or "source_backed"),
                "missing_context_notes": missing_context_notes,
                "evidence_id": evidence_id,
            }
        )
    return sorted(
        spine,
        key=lambda item: (
            len(item["missing_context_notes"]),
            item["metric_id"],
            item["label"],
        ),
    )[:6]


def derive_metric_spine_from_insights(
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    spine: List[Dict[str, Any]] = []
    for index, insight in enumerate(insights_final, start=1):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric")
        if not isinstance(metric, dict):
            continue
        value = _s(metric.get("value") or metric.get("raw_value")).strip()
        unit = _s(metric.get("unit")).strip()
        evidence_id = _s(
            insight.get("evidence_id") or metric.get("evidence_id")
        ).strip()
        label = _s(metric.get("label") or metric.get("metric")).strip()
        if not label:
            label = _metric_label_from_insight_text(_s(insight.get("text")).strip())
        if not value or not unit or not evidence_id or not label:
            continue
        missing_context_notes = [
            field_name
            for field_name in ("timeframe", "segment", "geography")
            if not _s(metric.get(field_name)).strip()
        ]
        spine.append(
            {
                "schema_version": "1.0",
                "metric_id": _s(insight.get("id") or metric.get("metric_id")).strip()
                or f"insight_metric_{index}",
                "label": label,
                "value": value,
                "unit": unit,
                "timeframe": _s(metric.get("timeframe")).strip(),
                "segment": _s(metric.get("segment")).strip(),
                "geography": _s(metric.get("geography")).strip(),
                "comparator": _s(metric.get("comparator")).strip(),
                "baseline": _s(metric.get("baseline")).strip(),
                "delta": _s(metric.get("delta") or metric.get("trend")).strip(),
                "sample_size": _s(metric.get("sample_size")).strip(),
                "confidence": _s(metric.get("confidence")).strip() or "source_backed",
                "missing_context_notes": missing_context_notes,
                "evidence_id": evidence_id,
            }
        )
    return sorted(
        spine,
        key=lambda item: (
            len(item["missing_context_notes"]),
            item["metric_id"],
            item["label"],
        ),
    )[:6]


def _merge_metric_spines(
    primary: List[Dict[str, Any]],
    secondary: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*primary, *secondary]:
        evidence_id = _s(item.get("evidence_id")).strip()
        label = _s(item.get("label")).strip().lower()
        value = _s(item.get("value")).strip().lower()
        unit = _s(item.get("unit")).strip().lower()
        key = "|".join([evidence_id, label, value, unit])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return sorted(
        merged,
        key=lambda item: (
            len(item.get("missing_context_notes") or []),
            _s(item.get("metric_id")).strip(),
            _s(item.get("label")).strip(),
        ),
    )[:6]


def _metric_label_from_insight_text(text: str) -> str:
    token = _s(text).strip()
    if not token:
        return ""
    if ":" in token:
        token = token.split(":", 1)[0]
    if "." in token:
        token = token.split(".", 1)[0]
    return token.strip()[:120]


def build_topics_covered(
    *,
    toc_entries: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    summary: Dict[str, Any] | None = None,
    insights_final: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    evidence_by_page = _evidence_ids_by_page(evidence_packs)
    for page, evidence_ids in _artifact_evidence_ids_by_page(
        summary=summary or {},
        insights_final=insights_final or [],
    ).items():
        current = evidence_by_page.setdefault(page, [])
        for evidence_id in evidence_ids:
            if evidence_id not in current:
                current.append(evidence_id)
    topics: List[Dict[str, Any]] = []
    for index, entry in enumerate(toc_entries, start=1):
        if not isinstance(entry, dict):
            continue
        topic = _s(entry.get("display_title") or entry.get("section_title")).strip()
        if not topic:
            continue
        pages = _int_list(entry.get("pages"))
        evidence_ids = sorted(
            {
                evidence_id
                for page in pages
                for evidence_id in evidence_by_page.get(page, [])
            }
        )
        subtopics = [
            _s(item).strip()
            for item in (entry.get("key_points") or [])
            if _s(item).strip()
        ][:5]
        why_it_matters = _s(entry.get("summary")).strip()
        if not why_it_matters and subtopics:
            why_it_matters = subtopics[0]
        if not why_it_matters:
            why_it_matters = f"{topic} is covered in the source structure."
        topics.append(
            {
                "schema_version": "1.0",
                "topic_id": _s(entry.get("section_id")).strip() or f"topic-{index}",
                "topic": topic,
                "subtopics": subtopics,
                "why_it_matters": why_it_matters,
                "evidence_ids": evidence_ids,
                "pages": pages,
                "status": "source_backed" if evidence_ids else "toc_only",
            }
        )
    return topics


def _artifact_evidence_ids_by_page(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> Dict[int, List[str]]:
    ids_by_page: Dict[int, List[str]] = {}

    def register(evidence_id: str, pages: List[int]) -> None:
        if not evidence_id:
            return
        for page in pages:
            ids_by_page.setdefault(page, [])
            if evidence_id not in ids_by_page[page]:
                ids_by_page[page].append(evidence_id)

    for claim in summary.get("claim_evidence_map") or []:
        if not isinstance(claim, dict):
            continue
        register(_s(claim.get("evidence_id")).strip(), _int_list(claim.get("pages")))
        for span in claim.get("evidence_spans") or []:
            if isinstance(span, dict):
                register(
                    _s(span.get("evidence_id")).strip(), _int_list([span.get("page")])
                )
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        register(
            _s(insight.get("evidence_id")).strip(), _int_list(insight.get("pages"))
        )
        for span in insight.get("evidence_spans") or []:
            if isinstance(span, dict):
                register(
                    _s(span.get("evidence_id")).strip(), _int_list([span.get("page")])
                )
    return ids_by_page


def build_key_figures(
    *,
    metric_spine: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    summary: Dict[str, Any] | None = None,
    insights_final: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    evidence_pages = _evidence_pages(evidence_packs)
    artifact_pages = _artifact_pages_by_evidence_id(
        summary=summary or {},
        insights_final=insights_final or [],
    )
    figures: List[Dict[str, Any]] = []
    for metric in metric_spine:
        evidence_id = _s(metric.get("evidence_id")).strip()
        label = _s(metric.get("label")).strip()
        value = _s(metric.get("value")).strip()
        unit = _s(metric.get("unit")).strip()
        if not label or not value or not unit or not evidence_id:
            continue
        page_values = evidence_pages.get(evidence_id, []) or artifact_pages.get(
            evidence_id, []
        )
        missing = [
            _s(item).strip()
            for item in (metric.get("missing_context_notes") or [])
            if _s(item).strip()
        ]
        figure = f"{value} {unit}".strip()
        figures.append(
            {
                "schema_version": "1.0",
                "figure_id": _s(metric.get("metric_id")).strip() or evidence_id,
                "figure": figure,
                "label": label,
                "unit": unit,
                "segment": _s(metric.get("segment")).strip(),
                "geography": _s(metric.get("geography")).strip(),
                "timeframe": _s(metric.get("timeframe")).strip(),
                "source_page": page_values[0] if page_values else None,
                "why_it_matters": _key_figure_why_it_matters(metric),
                "caveat": ("Missing context: " + ", ".join(missing) if missing else ""),
                "evidence_id": evidence_id,
                "related_chart_candidate": _related_chart_candidate_id(
                    evidence_packs=evidence_packs,
                    evidence_id=evidence_id,
                ),
            }
        )
    return figures


def _artifact_pages_by_evidence_id(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> Dict[str, List[int]]:
    pages_by_id: Dict[str, List[int]] = {}
    for page, evidence_ids in _artifact_evidence_ids_by_page(
        summary=summary,
        insights_final=insights_final,
    ).items():
        for evidence_id in evidence_ids:
            pages_by_id.setdefault(evidence_id, [])
            if page not in pages_by_id[evidence_id]:
                pages_by_id[evidence_id].append(page)
    return pages_by_id


def build_chart_insight_cards(
    *,
    key_figures: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    chart_candidates = _chart_candidates(evidence_packs)
    insights_by_evidence = {
        _s(item.get("evidence_id")).strip(): {
            "insight_id": _s(item.get("id") or item.get("insight_id")).strip(),
            "text": _s(item.get("text")).strip(),
        }
        for item in insights_final
        if isinstance(item, dict) and _s(item.get("evidence_id")).strip()
    }
    cards: List[Dict[str, Any]] = []
    for index, figure in enumerate(key_figures, start=1):
        evidence_id = _s(figure.get("evidence_id")).strip()
        chart = _chart_candidate_for_evidence(chart_candidates, evidence_id)
        confidence = _s((chart or {}).get("confidence")).strip() or "medium"
        candidate_id = _s(
            (chart or {}).get("candidate_id")
            or (chart or {}).get("chart_id")
            or (chart or {}).get("id")
        ).strip()
        insight = insights_by_evidence.get(evidence_id, {})
        caption = _s((chart or {}).get("caption") or figure.get("label")).strip()
        metric_mentions = _metric_mentions_for_figure(figure)
        weak_reason = ""
        if not chart:
            weak_reason = "No chart candidate was linked to the metric evidence."
        elif not candidate_id:
            weak_reason = "The linked chart has no retained accepted candidate ID."
        elif not bool((chart or {}).get("crop_qa_accepted")):
            weak_reason = "The linked candidate is not retained as crop-QA accepted."
        elif not _s(
            (chart or {}).get("source_page") or figure.get("source_page")
        ).strip():
            weak_reason = "The accepted candidate has no retained source-page linkage."
        elif (
            not _s(insight.get("insight_id")).strip()
            or not _s(insight.get("text")).strip()
        ):
            weak_reason = "No retained insight is linked to the chart evidence."
        elif confidence.lower() in {"low", "weak"}:
            weak_reason = "Chart candidate confidence is below source-backed threshold."
        public_takeaway = _chart_takeaway(figure, insights_by_evidence)
        cards.append(
            {
                "schema_version": "1.0",
                "card_id": candidate_id or f"chart-card-{index}",
                "status": "generated" if not weak_reason else "weak_evidence",
                "candidate_id": candidate_id,
                "crop_qa_accepted": bool((chart or {}).get("crop_qa_accepted")),
                "caption": caption,
                "takeaway": public_takeaway,
                "public_takeaway": public_takeaway,
                "business_implication": _business_implication(
                    figure, insights_by_evidence
                ),
                "metric_mentions": metric_mentions,
                "evidence_confidence": confidence,
                "evidence_id": evidence_id,
                "source_page": (chart or {}).get("source_page")
                or figure.get("source_page"),
                "insight_id": _s(insight.get("insight_id")).strip(),
                "avoid_reason_if_weak": weak_reason,
            }
        )
    return cards


def _int_list(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    numbers: List[int] = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in numbers:
            numbers.append(number)
    return numbers


def _evidence_items(evidence_packs: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not isinstance(evidence_packs, dict):
        return items
    for pack_name, pack in evidence_packs.items():
        if not isinstance(pack, dict):
            continue
        for key in ("findings", "quotes", "metrics", "key_metrics", "items"):
            raw_items = pack.get(key)
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if isinstance(item, dict):
                    copied = dict(item)
                    copied.setdefault("source_pack", pack_name)
                    items.append(copied)
    return items


def _evidence_pages(evidence_packs: Dict[str, Any]) -> Dict[str, List[int]]:
    pages_by_id: Dict[str, List[int]] = {}
    for item in _evidence_items(evidence_packs):
        evidence_id = _s(
            item.get("evidence_id") or item.get("id") or item.get("metric_id")
        ).strip()
        if not evidence_id:
            continue
        pages = _int_list(item.get("pages"))
        page = item.get("page")
        if page is not None:
            pages = _int_list([*pages, page])
        pages_by_id[evidence_id] = pages
    return pages_by_id


def _evidence_ids_by_page(evidence_packs: Dict[str, Any]) -> Dict[int, List[str]]:
    ids_by_page: Dict[int, List[str]] = {}
    for evidence_id, pages in _evidence_pages(evidence_packs).items():
        for page in pages:
            ids_by_page.setdefault(page, [])
            if evidence_id not in ids_by_page[page]:
                ids_by_page[page].append(evidence_id)
    return ids_by_page


def _key_figure_why_it_matters(metric: Dict[str, Any]) -> str:
    label = _s(metric.get("label")).strip()
    segment = _s(metric.get("segment")).strip()
    geography = _s(metric.get("geography")).strip()
    timeframe = _s(metric.get("timeframe")).strip()
    parts = [label]
    context = ", ".join([item for item in (segment, geography, timeframe) if item])
    if context:
        parts.append(context)
    delta = _s(metric.get("delta")).strip()
    if delta:
        parts.append(f"change: {delta}")
    return "; ".join(parts)


def _chart_candidates(evidence_packs: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not isinstance(evidence_packs, dict):
        return candidates
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        for key in ("chart_candidates", "charts", "figures", "visual_candidates"):
            raw_items = pack.get(key)
            if not isinstance(raw_items, list):
                continue
            candidates.extend([item for item in raw_items if isinstance(item, dict)])
    return candidates


def _related_chart_candidate_id(
    *, evidence_packs: Dict[str, Any], evidence_id: str
) -> str:
    chart = _chart_candidate_for_evidence(
        _chart_candidates(evidence_packs), evidence_id
    )
    if not chart:
        return ""
    return _s(chart.get("chart_id") or chart.get("id")).strip()


def _chart_candidate_for_evidence(
    chart_candidates: List[Dict[str, Any]], evidence_id: str
) -> Dict[str, Any]:
    for chart in chart_candidates:
        candidate_evidence_id = _s(
            chart.get("evidence_id") or chart.get("source_evidence_id")
        ).strip()
        if candidate_evidence_id == evidence_id:
            return chart
        evidence_ids = [
            _s(item).strip()
            for item in (chart.get("evidence_ids") or [])
            if _s(item).strip()
        ]
        if evidence_id in evidence_ids:
            return chart
    return {}


def _metric_mentions_for_figure(figure: Dict[str, Any]) -> List[str]:
    mentions = [
        _s(figure.get("figure")).strip(),
        _s(figure.get("label")).strip(),
        _s(figure.get("segment")).strip(),
        _s(figure.get("geography")).strip(),
        _s(figure.get("timeframe")).strip(),
    ]
    return [item for item in mentions if item]


def _chart_takeaway(
    figure: Dict[str, Any], insights_by_evidence: Dict[str, Dict[str, str]]
) -> str:
    evidence_id = _s(figure.get("evidence_id")).strip()
    insight = insights_by_evidence.get(evidence_id, {})
    if _s(insight.get("text")).strip():
        return _s(insight.get("text")).strip()
    return f"{_s(figure.get('label')).strip()} is reported at {_s(figure.get('figure')).strip()}."


def _business_implication(
    figure: Dict[str, Any], insights_by_evidence: Dict[str, Dict[str, str]]
) -> str:
    evidence_id = _s(figure.get("evidence_id")).strip()
    insight = insights_by_evidence.get(evidence_id, {})
    if _s(insight.get("text")).strip():
        return _s(insight.get("text")).strip()
    context = _s(figure.get("why_it_matters")).strip()
    return context or _s(figure.get("label")).strip()


def build_executive_advisory_artifacts(
    *,
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    metric_spine: List[Dict[str, Any]],
    evidence_packs: Dict[str, Any],
) -> Dict[str, Any]:
    recommendations_pack = evidence_packs.get("recommendations", {})
    risks_pack = evidence_packs.get("risk_register", {})
    recommendations = (
        recommendations_pack.get("recommendations")
        if isinstance(recommendations_pack, dict)
        else []
    )
    risks = risks_pack.get("risks") if isinstance(risks_pack, dict) else []
    if not isinstance(recommendations, list):
        recommendations = []
    if not isinstance(risks, list):
        risks = []
    supported_insights = [
        item
        for item in insights_final
        if isinstance(item, dict)
        and (_s(item.get("evidence_id")).strip() or item.get("evidence_spans"))
    ]
    return {
        "schema_version": "1.0",
        "decision_brief": {
            "schema_version": "1.0",
            "status": "generated"
            if supported_insights or metric_spine
            else "not_found",
            "strategic_context": _s(summary.get("executive_summary")).strip(),
            "decision_implications": [
                _s(item.get("text")).strip()
                for item in supported_insights[:3]
                if _s(item.get("text")).strip()
            ],
            "priority_moves": [
                _s(item.get("recommendation") or item.get("text")).strip()
                for item in recommendations[:3]
                if isinstance(item, dict)
                and _s(item.get("recommendation") or item.get("text")).strip()
            ],
            "watchouts": [
                _s(item.get("risk") or item.get("text")).strip()
                for item in risks[:3]
                if isinstance(item, dict)
                and _s(item.get("risk") or item.get("text")).strip()
            ],
            "evidence_links": sorted(
                {
                    _s(item.get("evidence_id")).strip()
                    for item in [*supported_insights, *quotes_final]
                    if isinstance(item, dict) and _s(item.get("evidence_id")).strip()
                }
            ),
            "confidence_note": (
                "Metric spine available"
                if metric_spine
                else "Evidence-linked insights available"
            ),
        },
        "recommendations": {
            "schema_version": "1.0",
            "status": "generated" if recommendations else "recommendations_not_found",
            "items": recommendations,
        },
        "risks": {
            "schema_version": "1.0",
            "status": "generated" if risks else "risks_not_found",
            "items": risks,
        },
        "coverage_diagnostics": {
            "schema_version": "1.0",
            "metric_spine_count": len(metric_spine),
            "evidence_linked_insight_count": len(supported_insights),
            "quote_count": len(quotes_final),
        },
        "audience_variants": {
            "schema_version": "1.0",
            "status": "not_requested",
            "items": [],
        },
        "category_relevance": {
            "schema_version": "1.0",
            "status": "not_found",
            "items": [],
        },
    }


def _log_topic_brief_mapping_audit(
    *,
    topic_briefs: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    ctx: RunContext,
) -> None:
    diagnostics = audit_topic_brief_mappings(
        topic_briefs=topic_briefs,
        doc_map=doc_map,
    )
    status_counts: Dict[str, int] = {}
    for diagnostic in diagnostics:
        status = _s(diagnostic.get("status")).strip() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    issue_count = sum(
        count for status, count in status_counts.items() if status != "ok"
    )
    unmapped_count = sum(
        status_counts.get(status, 0)
        for status in ("identity_mismatch", "unknown_section")
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_topic_brief_mapping_audit",
            module=logger.name,
            fields={
                "mapping_version": TOPIC_BRIEF_MAPPING_VERSION,
                "brief_count": len(topic_briefs),
                "diagnostic_count": len(diagnostics),
                "mapped_count": status_counts.get("ok", 0),
                "unmapped_count": unmapped_count,
                "issue_count": issue_count,
                "status_counts": status_counts,
                "diagnostics": diagnostics,
            },
        )
    )


def store_artifacts_payload(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    payload: Dict[str, Any],
    ctx: RunContext,
    pack_name: str = "artifacts",
) -> str:
    output_path = _store_pack(
        analysis_store=analysis_store,
        output_dir=output_dir,
        report_id=report_id,
        pack_name=pack_name,
        payload=payload,
        ctx=ctx,
        report_slug=report_name,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_payload_stored",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack_name": pack_name,
                "path": output_path,
            },
        )
    )
    return output_path


def _has_evidence_content(
    doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]
) -> bool:
    if isinstance(doc_map, dict):
        sections = doc_map.get("sections")
        if isinstance(sections, list) and len(sections) > 0:
            return True
    if not isinstance(evidence_packs, dict):
        return False
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        if (
            pack.get("findings")
            or pack.get("quote_candidates")
            or pack.get("methods")
            or pack.get("scope")
            or pack.get("limitations")
            or pack.get("key_metrics")
            or pack.get("risk_register")
            or pack.get("recommendations")
            or pack.get("contradictions")
        ):
            return True
    return False


def _artifact_cache_meta(
    *,
    md5: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    availability: Dict[str, Any],
    expert_domain: str,
    category_ids: List[str],
    retrieval_mode: str,
    settings: AppSettings,
    prompt_client,
    ctx: RunContext,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/artifacts/summary",
        "report_vs/artifacts/cover_semantics",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/quotes",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
    ]
    for namespace in namespaces:
        prompt_set = prompt_client.load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx
        )
        routing_decision = resolve_routing_policy(
            namespace,
            routing_policies_from_config(
                getattr(settings, "llm_routing", {}),
                model_overrides=getattr(settings, "openai_models", {}),
            ),
            default_model=settings.openai_model,
        )
        execution_policy = resolve_execution_policy(
            namespace,
            execution_policies_from_config(
                getattr(settings, "llm_execution_policies", {}),
                model_overrides=getattr(settings, "openai_models", {}),
                legacy_routing=getattr(settings, "llm_routing", {}),
                default_model=settings.openai_model,
                default_temperature=settings.temperature,
                default_seed=settings.openai_seed,
                default_timeout_seconds=settings.openai_timeout_seconds,
            ),
            default_model=settings.openai_model,
            default_temperature=settings.temperature,
            default_seed=settings.openai_seed,
            default_timeout_seconds=settings.openai_timeout_seconds,
        )
        policy = execution_policy.policy
        seed = (
            None
            if policy.seed_policy == "disabled"
            else policy.seed
            if policy.seed_policy == "fixed"
            else settings.openai_seed
        )
        execution_identity = build_llm_execution_identity(
            prompt_content_hash=prompt_set.prompt_content_hash,
            provider=policy.provider,
            model=policy.model,
            temperature=policy.temperature,
            seed=seed,
            max_output_tokens=policy.max_output_tokens,
            timeout_seconds=policy.timeout_seconds,
            retrieval_mode=retrieval_mode,
            routing_policy={
                "policy_source": routing_decision.policy_source,
                "tier": routing_decision.tier,
                "quality_threshold": routing_decision.quality_threshold,
                "same_provider_fallback": routing_decision.same_provider_fallback,
                "max_input_tokens": routing_decision.max_input_tokens,
                "compaction_enabled": routing_decision.compaction_enabled,
                "execution_policy_hash": execution_policy.policy_hash,
                "execution_policy_source": execution_policy.policy_source,
            },
            compaction_policy={
                "enabled": routing_decision.compaction_enabled,
                "max_input_tokens": routing_decision.max_input_tokens or None,
                "strategy": "anchor_preserving_head_tail",
            },
            output_contract_schema_version="artifact_json:1.0",
            validator_version="artifacts_schema:3.0",
        )
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "prompt_content_hash": prompt_set.prompt_content_hash,
            "dependency_manifest": (
                asdict(prompt_set.dependency_manifest)
                if prompt_set.dependency_manifest is not None
                else {}
            ),
            "execution_identity": execution_identity.execution_identity,
            "execution_identity_manifest": asdict(execution_identity),
            "model": policy.model,
            "execution_policy_hash": execution_policy.policy_hash,
            "execution_policy_source": execution_policy.policy_source,
        }
    inputs_hash = sha256_json(
        {
            "doc_map": doc_map,
            "evidence_packs": evidence_packs,
            "availability": availability,
            "expert_domain": expert_domain,
            "category_ids": category_ids,
        }
    )
    return {
        "schema_version": "2.0",
        "topic_brief_mapping_version": TOPIC_BRIEF_MAPPING_VERSION,
        "toc_structure_version": TOC_STRUCTURE_VERSION,
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "retrieval_mode": retrieval_mode,
    }


def _load_cached_artifacts(
    *,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    cache_key: str,
    expected_cache_meta: Optional[Dict[str, Any]] = None,
    ctx: RunContext,
    analysis_store,
) -> Optional[Dict[str, Any]]:
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_read_failed",
                module=logger.name,
                fields={"report_id": report_id, "error": exc.message},
            )
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            analysis_store=analysis_store,
            output_dir=output_dir,
            report_id=report_id,
            pack_name="artifacts",
            ctx=ctx,
            report_slug=report_name,
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        cache_meta_matcher=lambda cached_meta: _artifact_cache_meta_matches(
            cached_meta=cached_meta,
            expected_cache_meta=expected_cache_meta or {},
            cache_key=cache_key,
        ),
        adapt_payload=lambda payload, path: _adapt_cached_artifacts_payload(
            payload=payload,
            path=path,
            report_id=report_id,
            ctx=ctx,
        ),
    )
    return result.value if result.status == "hit" else None


def _artifact_cache_meta_matches(
    *,
    cached_meta: dict[str, Any],
    expected_cache_meta: dict[str, Any],
    cache_key: str,
) -> tuple[bool, str]:
    if cached_meta.get("key") == cache_key:
        return True, ""
    cached_prompts = cached_meta.get("prompts")
    expected_prompts = expected_cache_meta.get("prompts")
    if not isinstance(cached_prompts, dict):
        return False, "legacy_identity_read"
    if not isinstance(expected_prompts, dict):
        return False, "key_mismatch"
    for namespace, expected in expected_prompts.items():
        cached = cached_prompts.get(namespace)
        if not isinstance(expected, dict) or not isinstance(cached, dict):
            return False, "execution_identity_mismatch"
        if cached.get("execution_identity") != expected.get("execution_identity"):
            return False, "execution_identity_mismatch"
        if cached.get("prompt_content_hash") != expected.get("prompt_content_hash"):
            return False, "prompt_content_identity_mismatch"
    return False, "key_mismatch"


def _adapt_cached_artifacts_payload(
    *,
    payload: Dict[str, Any],
    path: str,
    report_id: str,
    ctx: RunContext,
) -> CachedPackAdaptResult[Dict[str, Any]]:
    payload = _attach_cached_artifact_family_status(payload)
    try:
        payload = _adapt_cached_artifact_schema(payload)
        _validate_cover_semantics(payload.get("cover_semantics"), ctx=ctx)
        raw_summary = payload.get("summary")
        _validate_card_tldrs(
            raw_summary if isinstance(raw_summary, dict) else {},
            summary_abstained=family_is_abstained(payload, "summary"),
            ctx=ctx,
        )
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=payload,
                schema_name="artifacts",
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_invalid",
                module=logger.name,
                fields={
                    "report_id": report_id,
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
        value=payload,
    )


def _adapt_cached_artifact_schema(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = _s(payload.get("schema_version")).strip()
    if version == "3.0":
        return _ensure_cached_derived_artifact_fields(dict(payload))
    if version not in {"1.0", "2.0"}:
        raise AppError(
            code="artifact_schema_migration_required",
            message="Cached artifact schema version is unsupported",
            retryable=False,
            context={"schema_version": version},
        )
    adapted = dict(payload)
    if version == "1.0":
        raw_summary = adapted.get("summary")
        summary = dict(raw_summary) if isinstance(raw_summary, dict) else {}
        if family_is_abstained(adapted, "summary"):
            summary.setdefault("card_tldr_compact", "")
        else:
            standard = _validate_complete_tldr(
                summary.get("tldr"),
                limit=18,
                code="card_tldr_compact_invalid",
                field_name="summary.tldr",
            )
            summary["card_tldr_compact"] = standard
        adapted["summary"] = summary
    if not isinstance(adapted.get("cover_semantics"), dict):
        raise AppError(
            code="cover_fingerprint_invalid",
            message="Cached artifacts do not contain grounded cover semantics",
            retryable=False,
            context={"schema_version": version},
        )
    adapted["schema_version"] = "3.0"
    return _ensure_cached_derived_artifact_fields(adapted)


def _ensure_cached_derived_artifact_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("topics_covered", [])
    payload.setdefault("key_figures", [])
    payload.setdefault("chart_insight_cards", [])
    return payload


def _validate_cover_semantics(
    value: Any,
    *,
    ctx: RunContext,
) -> Dict[str, str]:
    if not isinstance(value, dict):
        raise AppError(
            code="cover_fingerprint_invalid",
            message="cover_semantics must be an object",
            retryable=False,
            context={"field": "cover_semantics"},
        )
    allowed_values = {
        "evidence_shape": EVIDENCE_SHAPES,
        "direction": DIRECTIONS,
        "geography_scope": GEOGRAPHY_SCOPES,
        "evidence_density": EVIDENCE_DENSITIES,
        "domain_layer": DOMAIN_LAYERS,
    }
    normalized: Dict[str, str] = {}
    for field_name, allowed in allowed_values.items():
        field_value = _normalize_cover_semantic_enum(value.get(field_name))
        if field_value not in allowed:
            raise AppError(
                code="cover_fingerprint_invalid",
                message=f"cover_semantics.{field_name} is not approved",
                retryable=False,
                context={"field": field_name, "value": field_value},
            )
        normalized[field_name] = field_value
    selection_reason = " ".join(_s(value.get("selection_reason")).split())
    if not selection_reason:
        raise AppError(
            code="cover_fingerprint_invalid",
            message="cover_semantics.selection_reason must be populated",
            retryable=False,
            context={"field": "selection_reason"},
        )
    normalized["selection_reason"] = selection_reason
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_cover_semantics_validated",
            module=logger.name,
            fields={key: normalized[key] for key in allowed_values},
        )
    )
    return normalized


def _normalize_cover_semantic_enum(value: Any) -> str:
    """Normalize provider formatting without broadening the semantic contract."""
    return re.sub(r"[\s-]+", "_", _s(value).strip().casefold())


def _attach_cached_artifact_family_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_summary = payload.get("summary")
    raw_insights_candidates = payload.get("insights_candidates")
    raw_insights_final = payload.get("insights_final")
    raw_quotes_final = payload.get("quotes_final")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    insights_candidates: List[Dict[str, Any]] = normalize_artifact_insights(
        raw_insights_candidates, prefix="candidate"
    )
    insights_final: List[Dict[str, Any]] = normalize_artifact_insights(
        raw_insights_final, prefix="insight"
    )
    quotes_final: List[Dict[str, Any]] = (
        [item for item in raw_quotes_final if isinstance(item, dict)]
        if isinstance(raw_quotes_final, list)
        else []
    )
    (
        summary,
        insights_candidates,
        insights_final,
        quotes_final,
        expert_comment,
        linkedin_post,
        family_status,
    ) = apply_artifact_family_policy(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=_s(payload.get("expert_comment")),
        linkedin_post=_s(payload.get("linkedin_post")),
    )
    enriched = dict(payload)
    enriched["summary"] = summary
    enriched["insights_candidates"] = insights_candidates
    enriched["insights_final"] = insights_final
    enriched["quotes_final"] = quotes_final
    enriched["expert_comment"] = expert_comment
    enriched["linkedin_post"] = linkedin_post
    enriched["family_status"] = family_status
    return enriched


def _resolve_pack_path(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: Dict[str, Any],
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _validate_artifact_semantic_fields(
    artifacts_payload: Dict[str, Any],
    ctx: RunContext,
) -> None:
    missing_fields: List[str] = []
    sentinel_values = {"not available from text"}
    raw_summary = artifacts_payload.get("summary")
    raw_insights_final = artifacts_payload.get("insights_final")
    raw_quotes_final = artifacts_payload.get("quotes_final")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    insights_final: List[Dict[str, Any]] = (
        [item for item in raw_insights_final if isinstance(item, dict)]
        if isinstance(raw_insights_final, list)
        else []
    )
    quotes_final: List[Dict[str, Any]] = (
        [item for item in raw_quotes_final if isinstance(item, dict)]
        if isinstance(raw_quotes_final, list)
        else []
    )

    def _missing_text(value: Any) -> bool:
        text = _s(value).strip()
        return not text or text.lower() in sentinel_values

    summary_abstained = family_is_abstained(artifacts_payload, "summary")
    insights_abstained = family_is_abstained(artifacts_payload, "insights_bundle")
    quotes_abstained = family_is_abstained(artifacts_payload, "quotes")
    expert_abstained = family_is_abstained(artifacts_payload, "expert_comment")
    linkedin_abstained = family_is_abstained(artifacts_payload, "linkedin_post")

    _validate_card_tldrs(
        summary,
        summary_abstained=summary_abstained,
        ctx=ctx,
    )
    if not summary_abstained and _missing_text(summary.get("executive_summary")):
        missing_fields.append("summary.executive_summary")
    if not summary_abstained:
        for index, claim in enumerate(summary.get("claim_evidence_map") or []):
            if not isinstance(claim, dict) or _missing_text(claim.get("claim")):
                continue
            if not (
                isinstance(claim.get("evidence_spans"), list)
                and (claim.get("evidence_spans") or [])
            ):
                missing_fields.append(
                    f"summary.claim_evidence_map[{index}].evidence_spans"
                )
    if not insights_abstained and len(insights_final) < 2:
        missing_fields.append("insights_final")
    for index, insight in enumerate(insights_final):
        if insights_abstained:
            break
        if not isinstance(insight, dict) or _missing_text(insight.get("text")):
            missing_fields.append(f"insights_final[{index}].text")
    if not quotes_abstained and not quotes_final:
        missing_fields.append("quotes_final")
    elif not quotes_abstained and (
        not isinstance(quotes_final[0], dict)
        or _missing_text(quotes_final[0].get("text"))
    ):
        missing_fields.append("quotes_final[0].text")
    if not expert_abstained and _missing_text(artifacts_payload.get("expert_comment")):
        missing_fields.append("expert_comment")
    if not linkedin_abstained and _missing_text(artifacts_payload.get("linkedin_post")):
        missing_fields.append("linkedin_post")

    if not missing_fields:
        return

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_contract_incomplete",
            module=logger.name,
            fields={
                "missing_fields": missing_fields,
                "summary_abstained": summary_abstained,
                "insights_abstained": insights_abstained,
                "quotes_abstained": quotes_abstained,
                "expert_comment_abstained": expert_abstained,
                "linkedin_post_abstained": linkedin_abstained,
            },
        )
    )
    raise AppError(
        code="artifact_contract_incomplete",
        message="Artifact payload is missing required semantic fields",
        retryable=False,
        context={"missing_fields": missing_fields},
    )


def _word_count(value: str) -> int:
    return len(value.split())


def _validate_card_tldrs(
    summary: Dict[str, Any],
    *,
    summary_abstained: bool,
    ctx: RunContext,
) -> None:
    if summary_abstained:
        return
    standard_tldr = _validate_complete_tldr(
        summary.get("tldr"),
        limit=45,
        code="card_tldr_standard_invalid",
        field_name="summary.tldr",
    )
    compact_tldr = _validate_complete_tldr(
        summary.get("card_tldr_compact"),
        limit=18,
        code="card_tldr_compact_invalid",
        field_name="summary.card_tldr_compact",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_card_tldrs_validated",
            module=logger.name,
            fields={
                "standard_word_count": _word_count(standard_tldr),
                "compact_word_count": _word_count(compact_tldr),
            },
        )
    )


def _validate_complete_tldr(
    value: Any,
    *,
    limit: int,
    code: str,
    field_name: str,
) -> str:
    text = " ".join(_s(value).split())
    count = _word_count(text)
    if (
        count < 1
        or count > limit
        or text.endswith(("...", "\u2026"))
        or text[-1] not in ".?!"
    ):
        raise AppError(
            code=code,
            message=f"{field_name} must be a complete sentence of 1 to {limit} words",
            retryable=False,
            context={"field": field_name, "word_count": count},
        )
    return text
