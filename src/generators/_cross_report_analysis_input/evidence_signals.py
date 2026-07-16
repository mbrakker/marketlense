"""Evidence assembly, signal scoring, and agreement grouping.

This module owns deterministic evidence/raw-metric selection, prompt input
sizing, lightweight signal scoring, and evidence agreement grouping for the
cross-report synthesis prompt.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import replace
from typing import Any

from src.contracts.analytics_projection import ClaimEmbeddingRecord
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceAgreementType,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportRawMetricReference,
    CrossReportSemanticPreselectionSummary,
    CrossReportSelectedSourceReport,
    CrossReportSignalScore,
    CrossReportSignalScoreResult,
    CrossReportSourceSelectionResult,
    CrossReportThemeSelectionResult,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .shared import (
    _DEFAULT_SIGNAL_SCORE_WEIGHTS,
    _RAW_METRIC_POLICY,
    _slug,
    _source_recency_scores,
    _topic_terms,
)

logger = logging.getLogger("market_lense.cross_report_analysis_input_generator")

__all__ = (
    "_ordered_selected_report_ids",
    "_evidence_sort_key",
    "_raw_metric_sort_key",
    "_prompt_input_chars",
    "_semantic_preselection_summary",
    "_signal_score_weights",
    "_signal_label",
    "_signal_candidates",
    "_source_taxonomy_tokens",
    "_evidence_matches_signal",
    "_contradiction_score",
    "_support_score",
    "_weighted_signal_total",
    "score_cross_report_signals",
    "_directional_markers",
    "_agreement_type_and_reasons",
    "group_cross_report_evidence_agreement",
    "assemble_cross_report_analysis_inputs",
)


def _ordered_selected_report_ids(
    source_selection: CrossReportSourceSelectionResult,
) -> list[str]:
    return [source.report_id for source in source_selection.selected_sources]


def _evidence_sort_key(
    evidence,
    selected_order: dict[str, int],
) -> tuple[int, int, str]:
    class_priority = {"claim": 0, "finding": 1, "quote": 2, "metric": 3}
    return (
        selected_order.get(evidence.report_id, 9999),
        class_priority.get(str(evidence.content_class), 99),
        evidence.evidence_id,
    )


def _raw_metric_sort_key(
    metric,
    selected_order: dict[str, int],
) -> tuple[int, str]:
    return (selected_order.get(metric.report_id, 9999), metric.metric_id)


def _prompt_input_chars(
    evidence,
    raw_metrics,
) -> int:
    evidence_chars = sum(
        len(item.evidence_id)
        + len(item.report_id)
        + len(item.publisher)
        + len(item.title)
        + len(item.source_table)
        + len(item.entity_uid)
        + len(str(item.content_class))
        + len(item.text)
        + len(json.dumps(item.source_metadata, sort_keys=True, default=str))
        for item in evidence
    )
    metric_chars = sum(
        len(item.metric_id)
        + len(item.report_id)
        + len(item.publisher)
        + len(item.label)
        + len(item.raw_value)
        + len(item.unit)
        + len(item.context)
        + len(item.evidence_id)
        + len(json.dumps(item.source_metadata, sort_keys=True, default=str))
        for item in raw_metrics
    )
    return evidence_chars + metric_chars


def _fresh_content_hash(
    evidence: CrossReportEvidenceReference,
    content_hashes: dict[str, dict[str, str]],
) -> str:
    report_hashes = content_hashes.get(evidence.report_id) or {}
    for key in (evidence.entity_uid, evidence.evidence_id):
        value = str(report_hashes.get(key) or "").strip()
        if value:
            return value
    return ""


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dimensions = len(vectors[0])
    if dimensions <= 0 or any(len(vector) != dimensions for vector in vectors):
        return []
    return [
        sum(vector[index] for vector in vectors) / len(vectors)
        for index in range(dimensions)
    ]


def _embedding_by_entity(
    claim_embeddings: list[ClaimEmbeddingRecord] | None,
) -> dict[str, ClaimEmbeddingRecord]:
    records: dict[str, ClaimEmbeddingRecord] = {}
    for record in claim_embeddings or []:
        if record.status != "embedded" or not record.vector:
            continue
        records.setdefault(str(record.entity_uid), record)
    return records


def _semantic_preselection_summary(
    *,
    mode: str,
    candidate_claim_count: int,
    embedding_count: int,
    fresh_embedding_count: int,
    stale_embedding_count: int,
    selected_claims: list[CrossReportEvidenceReference],
    selected_embedding_uids: list[str],
    fallback_reason: str = "",
    prompt_input_chars_before: int = 0,
    prompt_input_chars_after: int = 0,
) -> CrossReportSemanticPreselectionSummary:
    return CrossReportSemanticPreselectionSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        mode=mode,
        candidate_claim_count=candidate_claim_count,
        embedding_count=embedding_count,
        fresh_embedding_count=fresh_embedding_count,
        stale_embedding_count=stale_embedding_count,
        selected_claim_count=len(selected_claims),
        selected_embedding_uids=selected_embedding_uids,
        fallback_reason=fallback_reason,
        prompt_input_chars_before=prompt_input_chars_before,
        prompt_input_chars_after=prompt_input_chars_after,
    )


def _semantic_preselected_evidence(
    *,
    candidate_evidence: list[CrossReportEvidenceReference],
    claim_embeddings: list[ClaimEmbeddingRecord] | None,
    content_hashes: dict[str, dict[str, str]],
    selected_order: dict[str, int],
    max_evidence_items: int,
) -> tuple[
    list[CrossReportEvidenceReference],
    CrossReportSemanticPreselectionSummary | None,
    Counter[str],
]:
    if claim_embeddings is None:
        return candidate_evidence, None, Counter()

    dropped: Counter[str] = Counter()
    claim_evidence = [
        item for item in candidate_evidence if str(item.content_class) == "claim"
    ]
    embeddings_by_entity = _embedding_by_entity(claim_embeddings)
    fresh_records: dict[str, ClaimEmbeddingRecord] = {}
    stale_count = 0
    for item in claim_evidence:
        record = embeddings_by_entity.get(item.entity_uid)
        if record is None:
            continue
        expected_hash = _fresh_content_hash(item, content_hashes)
        if not expected_hash or record.content_hash != expected_hash:
            stale_count += 1
            continue
        fresh_records[item.entity_uid] = record

    if not fresh_records:
        summary = _semantic_preselection_summary(
            mode="deterministic_fallback",
            candidate_claim_count=len(claim_evidence),
            embedding_count=len(claim_embeddings),
            fresh_embedding_count=0,
            stale_embedding_count=stale_count,
            selected_claims=[],
            selected_embedding_uids=[],
            fallback_reason="no_fresh_claim_embeddings",
        )
        return candidate_evidence, summary, dropped

    focus_vector = _centroid(
        [record.vector or [] for record in fresh_records.values() if record.vector]
    )
    if not focus_vector:
        summary = _semantic_preselection_summary(
            mode="deterministic_fallback",
            candidate_claim_count=len(claim_evidence),
            embedding_count=len(claim_embeddings),
            fresh_embedding_count=len(fresh_records),
            stale_embedding_count=stale_count,
            selected_claims=[],
            selected_embedding_uids=[],
            fallback_reason="embedding_dimensions_invalid",
        )
        return candidate_evidence, summary, dropped

    semantic_ranked = sorted(
        [
            (
                item,
                fresh_records[item.entity_uid],
                _cosine_similarity(
                    fresh_records[item.entity_uid].vector or [], focus_vector
                ),
            )
            for item in claim_evidence
            if item.entity_uid in fresh_records
        ],
        key=lambda scored: (
            -scored[2],
            selected_order.get(scored[0].report_id, 9999),
            scored[0].evidence_id,
        ),
    )
    selected_claim_limit = max(1, min(max_evidence_items, len(semantic_ranked)))
    selected_claims = [
        item for item, _record, _score in semantic_ranked[:selected_claim_limit]
    ]
    selected_entity_uids = {item.entity_uid for item in selected_claims}
    selected_embedding_by_entity = {
        item.entity_uid: record
        for item, record, _score in semantic_ranked[:selected_claim_limit]
    }
    preselected = [
        item
        for item in candidate_evidence
        if str(item.content_class) != "claim" or item.entity_uid in selected_entity_uids
    ]
    dropped_count = len(claim_evidence) - len(selected_claims)
    if dropped_count > 0:
        dropped["semantic_claim_preselection"] = dropped_count
    selected_embedding_uids = [
        str(selected_embedding_by_entity[item.entity_uid].embedding_uid)
        for item in preselected
        if str(item.content_class) == "claim"
        and item.entity_uid in selected_embedding_by_entity
    ]
    summary = _semantic_preselection_summary(
        mode="claim_embedding_similarity",
        candidate_claim_count=len(claim_evidence),
        embedding_count=len(claim_embeddings),
        fresh_embedding_count=len(fresh_records),
        stale_embedding_count=stale_count,
        selected_claims=selected_claims,
        selected_embedding_uids=selected_embedding_uids,
    )
    return preselected, summary, dropped


def _signal_score_weights(raw_weights: dict[str, float] | None) -> dict[str, float]:
    weights = dict(_DEFAULT_SIGNAL_SCORE_WEIGHTS)
    if raw_weights:
        for key, value in raw_weights.items():
            if key not in weights:
                raise AppError(
                    code="cross_report_signal_weight_invalid",
                    message=f"Unknown cross-report signal score weight: {key}",
                    retryable=False,
                    severity="error",
                    context={"weight": key},
                )
            parsed = float(value)
            if parsed < 0:
                raise AppError(
                    code="cross_report_signal_weight_invalid",
                    message=f"Cross-report signal score weight must be non-negative: {key}",
                    retryable=False,
                    severity="error",
                    context={"weight": key, "value": parsed},
                )
            weights[key] = parsed
    return dict(sorted(weights.items()))


def _signal_label(value: str) -> str:
    cleaned = str(value).strip()
    if cleaned.upper() == cleaned and len(cleaned) <= 5:
        return cleaned
    if len(cleaned) <= 3:
        return cleaned.upper()
    return " ".join(token.capitalize() for token in re.split(r"\s+", cleaned))


def _signal_candidates(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    theme_selection: CrossReportThemeSelectionResult,
) -> list[str]:
    selected_theme = theme_selection.selected_theme
    values: list[str] = [
        *selected_theme.matched_tags,
        *selected_theme.matched_categories,
        *request.tag_filters,
        *request.category_filters,
    ]
    for source in evidence_inputs.selected_sources:
        values.extend(source.tags)
        values.extend(source.category_labels)
    seen: set[str] = set()
    candidates: list[str] = []
    for value in values:
        normalized = str(value).strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(_signal_label(str(value)))
    if candidates:
        return candidates
    return [_signal_label(term) for term in _topic_terms(request.topic)]


def _source_taxonomy_tokens(source: CrossReportSelectedSourceReport) -> set[str]:
    return {
        value.strip().casefold()
        for value in [*source.tags, *source.category_labels]
        if value.strip()
    }


def _evidence_matches_signal(
    evidence,
    signal_label: str,
    source: CrossReportSelectedSourceReport | None,
) -> bool:
    normalized_label = signal_label.strip().casefold()
    text = evidence.text.casefold()
    text_tokens = _topic_terms(evidence.text)
    label_tokens = _topic_terms(signal_label)
    if normalized_label in text_tokens:
        return True
    if label_tokens:
        pattern = (
            r"(?<![A-Za-z0-9])"
            + r"\W+".join(re.escape(token) for token in label_tokens)
            + r"(?![A-Za-z0-9])"
        )
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    if source is None:
        return False
    return normalized_label in _source_taxonomy_tokens(source)


def _contradiction_score(evidence) -> float:
    positive_markers = {
        "adoption",
        "accelerate",
        "growth",
        "higher",
        "increase",
        "increasing",
        "rise",
        "strong",
    }
    uncertainty_markers = {
        "decline",
        "decrease",
        "down",
        "fall",
        "risk",
        "slower",
        "uneven",
        "weak",
    }
    tokens = {
        token.casefold()
        for item in evidence
        for token in re.findall(r"[A-Za-z0-9]+", item.text)
    }
    return (
        1.0
        if tokens.intersection(positive_markers)
        and tokens.intersection(uncertainty_markers)
        else 0.0
    )


def _support_score(evidence) -> float:
    classes = {str(item.content_class) for item in evidence}
    if {"finding", "quote"}.intersection(classes):
        return 1.0
    if "claim" in classes:
        return 0.5
    return 0.0


def _weighted_signal_total(
    component_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    return round(
        sum(component_scores[key] * weights[key] for key in sorted(weights)),
        6,
    )


def score_cross_report_signals(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    theme_selection: CrossReportThemeSelectionResult,
    ctx: RunContext,
    *,
    score_weights: dict[str, float] | None = None,
    max_signals: int = 8,
) -> CrossReportSignalScoreResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(theme_selection)
    if max_signals < 1:
        raise AppError(
            code="cross_report_signal_limit_invalid",
            message="max_signals must be at least 1",
            retryable=False,
            severity="error",
            context={"max_signals": max_signals},
        )

    weights = _signal_score_weights(score_weights)
    selected_theme = theme_selection.selected_theme
    source_by_report_id = {
        source.report_id: source for source in evidence_inputs.selected_sources
    }
    recency_scores = _source_recency_scores(evidence_inputs.selected_sources)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_signal_scoring_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": selected_theme.theme_id,
                "evidence_count": len(evidence_inputs.evidence),
                "raw_metric_count": len(evidence_inputs.raw_metrics),
                "score_weights": weights,
                "raw_metric_policy": _RAW_METRIC_POLICY,
            },
        )
    )

    dropped: Counter[str] = Counter()
    signal_scores: list[CrossReportSignalScore] = []
    signal_slug_counts: Counter[str] = Counter()
    taxonomy_focus = {
        value.strip().casefold()
        for value in [
            *selected_theme.matched_tags,
            *selected_theme.matched_categories,
            *request.tag_filters,
            *request.category_filters,
        ]
        if value.strip()
    }
    for label in _signal_candidates(request, evidence_inputs, theme_selection):
        matched_evidence = [
            item
            for item in evidence_inputs.evidence
            if _evidence_matches_signal(
                item,
                label,
                source_by_report_id.get(item.report_id),
            )
        ]
        if not matched_evidence:
            dropped["no_matching_evidence"] += 1
            continue
        supporting_sources = {
            item.report_id
            for item in matched_evidence
            if item.report_id in source_by_report_id
        }
        supporting_publishers = {
            source_by_report_id[report_id].publisher.strip().casefold()
            for report_id in supporting_sources
        }
        normalized_label = label.strip().casefold()
        component_scores = {
            "contradiction": _contradiction_score(matched_evidence),
            "diversity": min(len(supporting_publishers) / 2.0, 1.0),
            "recency": max(
                (
                    recency_scores.get(report_id, 0.0)
                    for report_id in supporting_sources
                ),
                default=0.0,
            ),
            "recurrence": min(len(matched_evidence) / 3.0, 1.0),
            "support": _support_score(matched_evidence),
            "taxonomy_fit": 1.0 if normalized_label in taxonomy_focus else 0.0,
        }
        reasons = [
            f"evidence_recurrence:{len(matched_evidence)}",
            f"source_publishers:{len(supporting_publishers)}",
            f"taxonomy_fit:{component_scores['taxonomy_fit']}",
            f"support:{component_scores['support']}",
            "raw_metric_magnitude_ignored",
        ]
        if component_scores["contradiction"] > 0:
            reasons.append("contradiction_presence")
        signal_slug = _slug(label)
        signal_slug_counts[signal_slug] += 1
        signal_id = (
            f"signal-{signal_slug}"
            if signal_slug_counts[signal_slug] == 1
            else f"signal-{signal_slug}-{signal_slug_counts[signal_slug]}"
        )
        signal_scores.append(
            CrossReportSignalScore(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                signal_id=signal_id,
                label=label,
                evidence_ids=[item.evidence_id for item in matched_evidence],
                component_scores=dict(sorted(component_scores.items())),
                total_score=_weighted_signal_total(component_scores, weights),
                reasons=reasons,
            )
        )

    signal_scores.sort(
        key=lambda score: (-score.total_score, score.signal_id),
    )
    selected_scores = signal_scores[:max_signals]
    dropped_count = max(len(signal_scores) - len(selected_scores), 0)
    if dropped_count:
        dropped["max_signals_reached"] = dropped_count
    result = CrossReportSignalScoreResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        signal_scores=selected_scores,
        selected_signal_ids=[score.signal_id for score in selected_scores],
        score_weights=weights,
        raw_metric_policy=_RAW_METRIC_POLICY,
        dropped_signal_counts=dict(sorted(dropped.items())),
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_signal_scoring_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": selected_theme.theme_id,
                "selected_signal_ids": result.selected_signal_ids,
                "signal_components": [
                    {
                        "signal_id": score.signal_id,
                        "component_scores": score.component_scores,
                        "total_score": score.total_score,
                        "reasons": score.reasons,
                    }
                    for score in result.signal_scores
                ],
                "dropped_signal_counts": result.dropped_signal_counts,
                "raw_metric_policy": result.raw_metric_policy,
            },
        )
    )
    return result


def _directional_markers(evidence) -> tuple[set[str], set[str]]:
    positive_markers = {
        "accelerating",
        "growth",
        "increase",
        "increasing",
        "rising",
        "strong",
    }
    negative_markers = {
        "decline",
        "declining",
        "decrease",
        "decreasing",
        "falling",
        "slower",
        "weak",
    }
    positive_evidence: set[str] = set()
    negative_evidence: set[str] = set()
    for item in evidence:
        tokens = {token.casefold() for token in re.findall(r"[A-Za-z0-9]+", item.text)}
        if tokens.intersection(positive_markers):
            positive_evidence.add(item.evidence_id)
        if tokens.intersection(negative_markers):
            negative_evidence.add(item.evidence_id)
    return positive_evidence, negative_evidence


def _agreement_type_and_reasons(
    evidence: list[CrossReportEvidenceReference],
    *,
    publisher_count: int,
    report_count: int,
) -> tuple[CrossReportEvidenceAgreementType, list[str]]:
    if publisher_count < 2 or report_count < 2:
        return "thin_coverage", ["single_report_coverage"]
    positive_evidence, negative_evidence = _directional_markers(evidence)
    positive_only = positive_evidence - negative_evidence
    negative_only = negative_evidence - positive_evidence
    if positive_only and negative_only:
        return "divergent", ["opposed_directional_language"]
    return "convergent", ["multi_publisher_alignment"]


def group_cross_report_evidence_agreement(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    signal_result: CrossReportSignalScoreResult,
    ctx: RunContext,
) -> CrossReportEvidenceAgreementResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(signal_result)
    evidence_by_id = {item.evidence_id: item for item in evidence_inputs.evidence}
    source_by_report_id = {
        source.report_id: source for source in evidence_inputs.selected_sources
    }
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_agreement_grouping_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": signal_result.selected_theme.theme_id,
                "signal_count": len(signal_result.signal_scores),
                "evidence_count": len(evidence_inputs.evidence),
            },
        )
    )

    groups: list[CrossReportEvidenceAgreementGroup] = []
    prompt_inputs: list[dict[str, Any]] = []
    for signal in signal_result.signal_scores:
        group_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in signal.evidence_ids
            if evidence_id in evidence_by_id
        ]
        if not group_evidence:
            continue
        source_report_ids = sorted({item.report_id for item in group_evidence})
        publishers = {
            source_by_report_id[report_id].publisher.strip().casefold()
            for report_id in source_report_ids
            if report_id in source_by_report_id
        }
        agreement_type, uncertainty_reasons = _agreement_type_and_reasons(
            group_evidence,
            publisher_count=len(publishers),
            report_count=len(source_report_ids),
        )
        group = CrossReportEvidenceAgreementGroup(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            group_id=f"group-{signal.signal_id}",
            label=signal.label,
            agreement_type=agreement_type,
            signal_ids=[signal.signal_id],
            evidence_ids=[item.evidence_id for item in group_evidence],
            source_report_ids=source_report_ids,
            publisher_count=len(publishers),
            uncertainty_reasons=uncertainty_reasons,
            prompt_input_label=f"{agreement_type}: {signal.label}",
        )
        groups.append(group)
        prompt_inputs.append(
            {
                "group_id": group.group_id,
                "label": group.label,
                "agreement_type": group.agreement_type,
                "evidence_ids": group.evidence_ids,
                "source_report_ids": group.source_report_ids,
                "uncertainty_reasons": group.uncertainty_reasons,
                "prompt_input_label": group.prompt_input_label,
            }
        )

    agreement_counts: dict[str, int] = dict(
        sorted(Counter(group.agreement_type for group in groups).items())
    )
    result = CrossReportEvidenceAgreementResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=signal_result.selected_theme,
        evidence_groups=groups,
        prompt_uncertainty_inputs=prompt_inputs,
        agreement_counts=agreement_counts,
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_agreement_grouping_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": signal_result.selected_theme.theme_id,
                "agreement_counts": result.agreement_counts,
                "groups": [
                    {
                        "group_id": group.group_id,
                        "agreement_type": group.agreement_type,
                        "evidence_ids": group.evidence_ids,
                        "uncertainty_reasons": group.uncertainty_reasons,
                    }
                    for group in result.evidence_groups
                ],
            },
        )
    )
    return result


def assemble_cross_report_analysis_inputs(
    request: CrossReportAnalysisRequest,
    source_selection: CrossReportSourceSelectionResult,
    projected_data: CrossReportProjectedDataReadResponse,
    ctx: RunContext,
    *,
    max_evidence_items: int = 48,
    claim_embeddings: list[ClaimEmbeddingRecord] | None = None,
) -> CrossReportEvidenceInputResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(source_selection)
    validate_cross_report_contract(projected_data)
    if max_evidence_items < 1:
        raise AppError(
            code="cross_report_evidence_limit_invalid",
            message="max_evidence_items must be at least 1",
            retryable=False,
            severity="error",
            context={"max_evidence_items": max_evidence_items},
        )
    selected_report_ids = _ordered_selected_report_ids(source_selection)
    selected_set = set(selected_report_ids)
    selected_order = {
        report_id: index for index, report_id in enumerate(selected_report_ids)
    }
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_input_assembly_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_report_ids": selected_report_ids,
                "projected_evidence_count": len(projected_data.evidence),
                "projected_raw_metric_count": len(projected_data.raw_metrics),
                "max_evidence_items": max_evidence_items,
            },
        )
    )
    dropped: Counter[str] = Counter()
    seen_evidence_keys: set[tuple[str, str]] = set()
    candidate_evidence: list[CrossReportEvidenceReference] = []
    for item in sorted(
        projected_data.evidence,
        key=lambda evidence: _evidence_sort_key(evidence, selected_order),
    ):
        if item.report_id not in selected_set:
            dropped["unselected_report"] += 1
            continue
        evidence_key = (item.report_id, item.evidence_id)
        if evidence_key in seen_evidence_keys:
            dropped["duplicate_evidence_id_same_report"] += 1
            continue
        seen_evidence_keys.add(evidence_key)
        candidate_evidence.append(item)

    prompt_chars_before_preselection = _prompt_input_chars(candidate_evidence, [])
    candidate_evidence, semantic_preselection, semantic_dropped = (
        _semantic_preselected_evidence(
            candidate_evidence=candidate_evidence,
            claim_embeddings=claim_embeddings,
            content_hashes=projected_data.content_hashes,
            selected_order=selected_order,
            max_evidence_items=max_evidence_items,
        )
    )
    dropped.update(semantic_dropped)

    bounded_evidence: list[CrossReportEvidenceReference] = []
    for item in candidate_evidence:
        if len(bounded_evidence) >= max_evidence_items:
            dropped["max_evidence_items_reached"] += 1
            continue
        bounded_evidence.append(item)

    raw_metrics: list[CrossReportRawMetricReference] = []
    for metric in sorted(
        projected_data.raw_metrics,
        key=lambda metric: _raw_metric_sort_key(metric, selected_order),
    ):
        if metric.report_id not in selected_set:
            dropped["unselected_raw_metric_report"] += 1
            continue
        raw_metrics.append(metric)

    prompt_input_chars = _prompt_input_chars(bounded_evidence, raw_metrics)
    if semantic_preselection is not None:
        semantic_preselection = replace(
            semantic_preselection,
            prompt_input_chars_before=prompt_chars_before_preselection,
            prompt_input_chars_after=prompt_input_chars,
        )
    evidence_by_report: dict[str, list[str]] = {
        report_id: [] for report_id in selected_report_ids
    }
    for item in bounded_evidence:
        evidence_by_report.setdefault(item.report_id, []).append(item.evidence_id)
    evidence_by_report = {
        report_id: evidence_ids
        for report_id, evidence_ids in evidence_by_report.items()
        if evidence_ids
    }
    result = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=source_selection.selected_sources,
        evidence=bounded_evidence,
        raw_metrics=raw_metrics,
        evidence_by_report_id=evidence_by_report,
        dropped_evidence_counts=dict(sorted(dropped.items())),
        prompt_input_chars=prompt_input_chars,
        semantic_preselection=semantic_preselection,
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_input_assembly_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_report_ids": selected_report_ids,
                "evidence_count": len(result.evidence),
                "raw_metric_count": len(result.raw_metrics),
                "prompt_input_chars": result.prompt_input_chars,
                "dropped_evidence_counts": result.dropped_evidence_counts,
                "semantic_preselection_present": result.semantic_preselection
                is not None,
                "semantic_preselection_selected_count": (
                    result.semantic_preselection.selected_claim_count
                )
                if result.semantic_preselection is not None
                else 0,
            },
        )
    )
    return result
