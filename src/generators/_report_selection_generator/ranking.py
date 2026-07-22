from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from src.contracts.candidates import Candidate
from src.contracts.ingest import IngestSettings
from src.contracts.report_assets import RankRequest
from src.contracts.run_budget import RunBudget
from src.generators.prompt_preparation import (
    model_request_identity_fields,
    prepare_prompt_bundle,
)
from src.generators.report_generation_dependencies import ReportSelectionDependencies
from src.generators.report_generation_shared import logger
from src.utils.candidate_features import candidate_features, candidate_features_payload
from src.utils.coercion import coerce_float, coerce_int
from src.utils.costing import estimate_cost_usd, estimate_text_tokens
from src.utils.logging import log_event
from src.utils.url_utils import text_has_url_or_domain_marker


@dataclass(frozen=True)
class _RankBatchResult:
    ranked: list[Any]
    usage: dict[str, Optional[int]]


_RANK_FEATURE_KEYS_BY_KIND: dict[str, tuple[str, ...]] = {
    "chart": (
        "area_frac",
        "aspect",
        "text_ratio",
        "text_chars",
        "ocr_density",
        "visual_entropy",
        "chart_confidence",
    ),
    "table": (
        "area_frac",
        "rows",
        "cols",
        "numeric_ratio",
        "avg_words_per_cell",
        "text_chars",
        "ocr_density",
        "table_confidence",
    ),
}

_RANK_FLOAT_PRECISION = 3
_RANK_TITLE_LIMIT = 220
_RANK_TABLE_PREVIEW_LIMIT = 240


def _ranking_run_budget(settings: IngestSettings, ctx) -> RunBudget:
    """Use the report's isolated authority scope for every ranking call."""

    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=str(getattr(ctx, "publisher_id", "") or ""),
        usage_db_path=settings.usage_db_path,
        max_spend_usd=getattr(settings, "run_budget_max_spend_usd", None),
        max_tokens=getattr(settings, "run_budget_max_tokens", None),
        max_calls=getattr(settings, "run_budget_max_calls", None),
        max_retries=getattr(settings, "run_budget_max_retries", None),
        max_runtime_seconds=getattr(settings, "run_budget_max_runtime_seconds", None),
        max_pdfs=getattr(settings, "run_budget_max_pdfs", None),
        limit_decision=getattr(settings, "run_budget_limit_decision", "stop"),
        enabled_effect_kinds=getattr(settings, "run_budget_enabled_effect_kinds", ()),
    )


def _candidate_meta(candidate: Candidate, key: str, default: float = 0.0) -> float:
    features = candidate_features(candidate)
    value = getattr(features, key, default)
    return coerce_float(value, default)


def _candidate_quality_signals(candidate: Candidate) -> dict[str, float]:
    features = candidate_features(candidate)
    return {
        "ocr_density": round(coerce_float(features.ocr_density, 0.0), 3),
        "visual_entropy": round(coerce_float(features.visual_entropy, 0.0), 3),
        "chart_confidence": round(coerce_float(features.chart_confidence, 0.0), 3),
        "table_confidence": round(coerce_float(features.table_confidence, 0.0), 3),
    }


def _rank_feature_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(float(value), _RANK_FLOAT_PRECISION)
    return value


def _compact_rank_features(candidate: Candidate) -> dict[str, Any]:
    features = candidate_features(candidate)
    compact: dict[str, Any] = {}
    for key in _RANK_FEATURE_KEYS_BY_KIND.get(
        candidate.kind, _RANK_FEATURE_KEYS_BY_KIND["chart"]
    ):
        value = _rank_feature_value(getattr(features, key, 0))
        if isinstance(value, str):
            if value.strip():
                compact[key] = value.strip()
            continue
        if isinstance(value, bool):
            compact[key] = value
            continue
        if isinstance(value, (int, float)) and value == 0:
            continue
        compact[key] = value
    return compact


def _legacy_rank_row(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "type": candidate.kind,
        "page": candidate.page,
        "features": candidate_features_payload(candidate),
        "quality_signals": _candidate_quality_signals(candidate),
        "title_or_caption": (candidate.caption or "")[:300],
        "table_preview": candidate.preview_text[:400]
        if candidate.kind == "table"
        else "",
    }


def _compact_rank_row(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "type": candidate.kind,
        "page": candidate.page,
        "features": _compact_rank_features(candidate),
        "quality_signals": _candidate_quality_signals(candidate),
        "title_or_caption": (candidate.caption or "")[:_RANK_TITLE_LIMIT],
        "table_preview": (candidate.preview_text or "")[:_RANK_TABLE_PREVIEW_LIMIT]
        if candidate.kind == "table"
        else "",
    }


def _candidate_prefilter_reject_reason(candidate: Candidate) -> str:
    area = _candidate_meta(candidate, "area_frac", 0.0)
    if area <= 0.0:
        return "missing_area"
    if candidate.kind == "table":
        features = candidate_features(candidate)
        rows = coerce_int(features.rows, 0)
        cols = coerce_int(features.cols, 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        avg_words_per_cell = coerce_float(features.avg_words_per_cell, 0.0)
        table_confidence = coerce_float(features.table_confidence, 0.0)
        preview_normalized = " ".join(
            str(candidate.preview_text or "").replace("|", " ").lower().split()
        )
        if rows < 2 or cols < 2:
            return "table_low_structure"
        if rows < 3 and numeric_ratio < 0.08:
            return "table_low_data"
        if area < 0.025 and numeric_ratio < 0.12:
            return "table_too_small"
        if (
            preview_normalized.startswith("figure ")
            and numeric_ratio <= 0.05
            and avg_words_per_cell >= 6.0
        ):
            return "table_figure_text_block"
        if (
            preview_normalized.startswith("box ")
            and numeric_ratio <= 0.05
            and avg_words_per_cell >= 6.0
        ):
            return "table_box_text_block"
        if (
            text_has_url_or_domain_marker(
                preview_normalized,
                domains={"doi.org"},
            )
            and rows >= 8
            and numeric_ratio <= 0.12
        ):
            return "table_reference_text_block"
        if (
            area >= 0.18
            and rows >= 8
            and cols <= 5
            and numeric_ratio <= 0.03
            and avg_words_per_cell >= 8.0
        ):
            return "table_large_text_block"
        if 0.0 < table_confidence < 0.32 and numeric_ratio < 0.12 and rows < 5:
            return "table_low_confidence"
        return ""
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    text_chars = _candidate_meta(candidate, "text_chars", 0.0)
    visual_entropy = _candidate_meta(candidate, "visual_entropy", 0.0)
    chart_confidence = _candidate_meta(candidate, "chart_confidence", 0.0)
    if area < 0.035:
        return "chart_too_small"
    if text_ratio > 0.9 and area < 0.12:
        return "chart_text_fragment"
    if not (candidate.caption or "").strip() and area < 0.05 and text_ratio < 0.02:
        return "chart_decorative"
    if 0.0 < chart_confidence < 0.24 and area < 0.11:
        return "chart_low_confidence"
    if 0.0 < visual_entropy < 0.04 and text_chars < 30:
        return "chart_low_visual_entropy"
    return ""


def _candidate_prefilter_priority(candidate: Candidate) -> float:
    area = _candidate_meta(candidate, "area_frac", 0.0)
    if candidate.kind == "table":
        features = candidate_features(candidate)
        rows = coerce_int(features.rows, 0)
        cols = coerce_int(features.cols, 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        table_confidence = coerce_float(features.table_confidence, 0.0)
        ocr_density = coerce_float(features.ocr_density, 0.0)
        return (
            area * 100.0
            + rows * 2.5
            + cols * 1.5
            + numeric_ratio * 50.0
            + table_confidence * 22.0
            + min(ocr_density, 35.0) * 0.18
        )
    caption_bonus = 12.0 if (candidate.caption or "").strip() else 0.0
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    chart_confidence = _candidate_meta(candidate, "chart_confidence", 0.0)
    visual_entropy = _candidate_meta(candidate, "visual_entropy", 0.0)
    return (
        area * 100.0
        + caption_bonus
        + max(0.0, (0.6 - text_ratio) * 20.0)
        + chart_confidence * 26.0
        + visual_entropy * 8.0
    )


def _candidate_is_obvious_reject(candidate: Candidate) -> tuple[bool, str]:
    reason = _candidate_prefilter_reject_reason(candidate)
    if reason:
        return True, reason
    if candidate.kind == "table":
        features = candidate_features(candidate)
        rows = coerce_int(features.rows, 0)
        cols = coerce_int(features.cols, 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        if rows < 3 and cols < 3 and numeric_ratio < 0.1:
            return True, "table_ambiguous_low_data"
        return False, ""
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    text_chars = _candidate_meta(candidate, "text_chars", 0.0)
    if text_ratio > 0.88 and text_chars < 70:
        return True, "chart_text_heavy_fragment"
    return False, ""


def _candidate_is_obvious_pass(candidate: Candidate) -> bool:
    if candidate.kind == "table":
        features = candidate_features(candidate)
        rows = coerce_int(features.rows, 0)
        cols = coerce_int(features.cols, 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        area = _candidate_meta(candidate, "area_frac", 0.0)
        return rows >= 4 and cols >= 3 and numeric_ratio >= 0.15 and area >= 0.05
    area = _candidate_meta(candidate, "area_frac", 0.0)
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    has_caption = bool((candidate.caption or "").strip())
    return area >= 0.12 and text_ratio <= 0.65 and has_caption


def _rank_threshold_pass(row: Any, settings: IngestSettings) -> tuple[bool, str]:
    if not bool(getattr(row, "keep", True)):
        return False, str(getattr(row, "reject_reason", "") or "model_reject")
    score = coerce_int(getattr(row, "score", 0), 0)
    quality = coerce_int(getattr(row, "quality_score", score), score)
    insight = coerce_int(getattr(row, "insight_score", score), score)
    data_score = coerce_int(getattr(row, "data_score", score), score)
    if score < int(settings.rank_min_overall_score):
        return False, "overall_below_threshold"
    if quality < int(settings.rank_min_quality_score):
        return False, "quality_below_threshold"
    if insight < int(settings.rank_min_insight_score):
        return False, "insight_below_threshold"
    if data_score < int(settings.rank_min_data_score):
        return False, "data_below_threshold"
    return True, ""


def _split_candidates_by_kind(
    candidates: list[Candidate],
) -> tuple[list[Candidate], list[Candidate]]:
    tables = [candidate for candidate in candidates if candidate.kind == "table"]
    charts = [candidate for candidate in candidates if candidate.kind == "chart"]
    return tables, charts


def _truncate_prefiltered_candidates(
    candidates: list[Candidate],
    max_candidates: int,
) -> tuple[list[Candidate], dict[str, int]]:
    if max_candidates <= 0 or len(candidates) <= max_candidates:
        return list(candidates), {
            "table": sum(1 for candidate in candidates if candidate.kind == "table"),
            "chart": sum(1 for candidate in candidates if candidate.kind == "chart"),
        }
    table_candidates, chart_candidates = _split_candidates_by_kind(candidates)
    by_kind = {
        "table": sorted(
            table_candidates,
            key=_candidate_prefilter_priority,
            reverse=True,
        ),
        "chart": sorted(
            chart_candidates,
            key=_candidate_prefilter_priority,
            reverse=True,
        ),
    }
    selected_by_kind: dict[str, list[Candidate]] = {"table": [], "chart": []}
    next_index_by_kind = {"table": 0, "chart": 0}
    active_kinds = [kind for kind, rows in by_kind.items() if rows]
    if not active_kinds:
        return [], {"table": 0, "chart": 0}
    base_slots = max_candidates // len(active_kinds)
    for kind in active_kinds:
        take = min(len(by_kind[kind]), base_slots)
        selected_by_kind[kind] = by_kind[kind][:take]
        next_index_by_kind[kind] = take
    remaining_slots = max_candidates - sum(
        len(selected_rows) for selected_rows in selected_by_kind.values()
    )
    while remaining_slots > 0:
        best_kind = ""
        best_priority = float("-inf")
        for kind in active_kinds:
            next_index = next_index_by_kind[kind]
            rows = by_kind[kind]
            if next_index >= len(rows):
                continue
            priority = _candidate_prefilter_priority(rows[next_index])
            if priority > best_priority:
                best_priority = priority
                best_kind = kind
        if not best_kind:
            break
        next_index = next_index_by_kind[best_kind]
        selected_by_kind[best_kind].append(by_kind[best_kind][next_index])
        next_index_by_kind[best_kind] = next_index + 1
        remaining_slots -= 1
    selected = selected_by_kind["table"] + selected_by_kind["chart"]
    selected.sort(key=_candidate_prefilter_priority, reverse=True)
    return selected, {
        "table": len(selected_by_kind["table"]),
        "chart": len(selected_by_kind["chart"]),
    }


def _rank_candidates_batch(
    *,
    candidates: list[Candidate],
    kind: str,
    settings: IngestSettings,
    ctx,
    dependencies: ReportSelectionDependencies,
) -> _RankBatchResult:
    if not candidates:
        return _RankBatchResult(
            ranked=[],
            usage={
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            },
        )
    rank_model = settings.rank_model or settings.openai_model
    legacy_json = json.dumps(
        [_legacy_rank_row(candidate) for candidate in candidates],
        ensure_ascii=True,
    )
    rows = [_compact_rank_row(candidate) for candidate in candidates]
    candidates_json = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    legacy_input_tokens = estimate_text_tokens(legacy_json)
    compact_input_tokens = estimate_text_tokens(candidates_json)
    legacy_input_cost = estimate_cost_usd(
        rank_model,
        legacy_input_tokens,
        0,
        0,
        settings.model_pricing or {},
    )
    compact_input_cost = estimate_cost_usd(
        rank_model,
        compact_input_tokens,
        0,
        0,
        settings.model_pricing or {},
    )
    prompt_bundle = prepare_prompt_bundle(
        namespace="rank_candidates",
        settings=settings,
        ctx=ctx,
        prompt_client=dependencies,
        system_variables={},
        user_variables={"candidates_json": candidates_json},
        reload_if_changed=True,
        default_model=rank_model,
        temperature=settings.rank_temperature,
        seed=settings.rank_seed,
        timeout_seconds=settings.rank_timeout_seconds,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="prompt_selected",
            module=logger.name,
            fields={
                "namespace": "rank_candidates",
                "candidate_kind": kind,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="rank_payload_profile",
            module=logger.name,
            fields={
                "candidate_kind": kind,
                "candidate_count": len(candidates),
                "legacy_payload_chars": len(legacy_json),
                "compact_payload_chars": len(candidates_json),
                "payload_chars_saved": len(legacy_json) - len(candidates_json),
                "legacy_input_tokens_est": legacy_input_tokens,
                "compact_input_tokens_est": compact_input_tokens,
                "input_tokens_saved_est": legacy_input_tokens - compact_input_tokens,
                "legacy_input_cost_usd_est": legacy_input_cost,
                "compact_input_cost_usd_est": compact_input_cost,
                "input_cost_saved_usd_est": round(
                    legacy_input_cost - compact_input_cost, 6
                ),
                "title_char_limit": _RANK_TITLE_LIMIT,
                "table_preview_char_limit": _RANK_TABLE_PREVIEW_LIMIT,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="prompt_rendered",
            module=logger.name,
            fields={
                "candidate_kind": kind,
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
                "system_prompt_chars": len(prompt_bundle.system_prompt),
                "user_prompt_chars": len(prompt_bundle.user_prompt),
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="rank_request_config",
            module=logger.name,
            fields={
                "candidate_kind": kind,
                "model": prompt_bundle.resolved_model,
                "temperature": prompt_bundle.effective_temperature,
                "seed": prompt_bundle.effective_seed,
                "candidate_count": len(candidates),
            },
        )
    )
    ranked_resp = dependencies.rank_candidates(
        RankRequest(
            schema_version="1.0",
            system_prompt=prompt_bundle.system_prompt,
            user_prompt=prompt_bundle.user_prompt,
            prompt_system_sha256=prompt_bundle.prompt_set.system.sha256,
            prompt_user_sha256=prompt_bundle.prompt_set.user.sha256,
            model=prompt_bundle.resolved_model,
            temperature=prompt_bundle.effective_temperature,
            api_key=settings.openai_api_key,
            seed=prompt_bundle.effective_seed,
            candidate_count=len(candidates),
            max_output_tokens=prompt_bundle.effective_max_output_tokens,
            timeout_seconds=prompt_bundle.effective_timeout_seconds,
            cost_ledger_path=settings.cost_ledger_path,
            cost_daily_path=settings.cost_daily_path,
            model_pricing=settings.model_pricing,
            response_cache_enabled=True,
            response_cache_dir=settings.cache_dir,
            run_budget=_ranking_run_budget(settings, ctx),
            **model_request_identity_fields(prompt_bundle),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="rank_raw_response",
            module=logger.name,
            fields={
                "candidate_kind": kind,
                "request_id": ranked_resp.request_id or "",
                "response_chars": len(ranked_resp.raw_content or ""),
            },
        )
    )
    return _RankBatchResult(
        ranked=ranked_resp.results,
        usage={
            "prompt_tokens": ranked_resp.prompt_tokens,
            "completion_tokens": ranked_resp.completion_tokens,
            "total_tokens": ranked_resp.total_tokens,
        },
    )


def _merge_rank_usage(
    usage_rows: list[dict[str, Optional[int]]],
) -> dict[str, Optional[int]]:
    totals: dict[str, Optional[int]] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    has_any = False
    for row in usage_rows:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = row.get(key)
            if value is None:
                continue
            totals[key] = int(totals[key] or 0) + int(value)
            has_any = True
    if not has_any:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    return totals
