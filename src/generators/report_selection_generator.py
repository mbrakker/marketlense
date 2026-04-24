from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.contracts.candidates import Candidate
from src.contracts.ingest import IngestSettings
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefineCandidate,
    CropRefinePageRenderRequest,
    CropRefineRequest,
    CropItem,
    CropRequest,
    ExtractCandidatesRequest,
    FigureExtractRequest,
    FigureExtractResponse,
    RankRequest,
)
from src.contracts.report_generation import (
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import ReportFigureAsset, ReportPayload
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import logger, read_cache_json
from src.utils.cache_utils import sha256_json
from src.utils.candidate_features import candidate_features, candidate_features_payload
from src.utils.coercion import coerce_float, coerce_int
from src.utils.logging import child_context, log_event
from src.utils.model_resolver import resolve_model
from src.utils.validation import validate_candidate


@dataclass(frozen=True)
class _RankBatchResult:
    ranked: list[Any]
    usage: dict[str, Optional[int]]


def _candidate_meta(candidate: Candidate, key: str, default: float = 0.0) -> float:
    features = candidate_features(candidate)
    value = getattr(features, key, default)
    return coerce_float(value, default)


def _candidate_quality_signals(candidate: Candidate) -> dict[str, float]:
    features = candidate_features(candidate)
    return {
        "ocr_density": coerce_float(features.ocr_density, 0.0),
        "visual_entropy": coerce_float(features.visual_entropy, 0.0),
        "chart_confidence": coerce_float(features.chart_confidence, 0.0),
        "table_confidence": coerce_float(features.table_confidence, 0.0),
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
            ("http" in preview_normalized or "doi.org" in preview_normalized)
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
        if (
            0.0 < table_confidence < 0.32
            and numeric_ratio < 0.12
            and rows < 5
        ):
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
    else:
        area = _candidate_meta(candidate, "area_frac", 0.0)
        text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
        if area < 0.045 and text_ratio > 0.75:
            return True, "chart_small_texty"
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
    dependencies: ReportGeneratorDependencies,
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
    rows = [
        {
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
        for candidate in candidates
    ]
    candidates_json = json.dumps(rows, ensure_ascii=True)
    prompt_bundle = prepare_prompt_bundle(
        namespace="rank_candidates",
        settings=settings,
        ctx=ctx,
        prompt_client=dependencies,
        system_variables={},
        user_variables={"candidates_json": candidates_json},
        reload_if_changed=True,
        default_model=rank_model,
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
            event="prompt_rendered",
            module=logger.name,
            fields={
                "candidate_kind": kind,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
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
                "temperature": settings.rank_temperature,
                "seed": settings.rank_seed,
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
            temperature=settings.rank_temperature,
            api_key=settings.openai_api_key,
            seed=settings.rank_seed,
            candidate_count=len(candidates),
            timeout_seconds=settings.rank_timeout_seconds,
            cost_ledger_path=settings.cost_ledger_path,
            cost_daily_path=settings.cost_daily_path,
            model_pricing=settings.model_pricing,
            response_cache_enabled=True,
            response_cache_dir=settings.cache_dir,
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
                "content": ranked_resp.raw_content,
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


def _bbox_tuple(values: Any) -> tuple[float, float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"Expected bbox with 4 coordinates, received: {values!r}")
    return (
        float(values[0]),
        float(values[1]),
        float(values[2]),
        float(values[3]),
    )


def _crop_refine_parallel_workers(settings: IngestSettings, selected_max: int) -> int:
    configured = coerce_int(getattr(settings, "report_worker_limit", 1), 1)
    if configured < 1:
        configured = 1
    return max(1, min(configured, max(1, selected_max), 3))


def _crop_refine_profile_key(
    md5: str,
    *,
    model: str,
    temperature: float,
    seed: Optional[int],
    mode: str,
    prompt_system_sha256: str,
    prompt_user_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "model": model,
            "temperature": temperature,
            "seed": seed,
            "mode": mode,
            "prompt_system_sha256": prompt_system_sha256,
            "prompt_user_sha256": prompt_user_sha256,
        }
    )


def _crop_refine_entry_key(
    md5: str,
    candidate: Candidate,
    *,
    model: str,
    temperature: float,
    seed: Optional[int],
    mode: str,
    prompt_system_sha256: str,
    prompt_user_sha256: str,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "candidate_id": candidate.id,
            "page": candidate.page,
            "bbox": list(candidate.bbox),
            "features": candidate_features_payload(candidate),
            "quality_signals": _candidate_quality_signals(candidate),
            "caption": candidate.caption or "",
            "preview_text": candidate.preview_text or "",
            "model": model,
            "temperature": temperature,
            "seed": seed,
            "mode": mode,
            "prompt_system_sha256": prompt_system_sha256,
            "prompt_user_sha256": prompt_user_sha256,
        }
    )


def _crop_refine_cache_path(
    settings: IngestSettings,
    file_id: str,
    report_name: str,
    ctx,
    dependencies: ReportGeneratorDependencies,
) -> str:
    return dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=file_id,
            pack_name="crop_refine",
            report_slug=report_name,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:crop_refine_cache_path"),
    ).output_path


def _load_crop_refine_cache(
    settings: IngestSettings,
    *,
    file_id: str,
    report_name: str,
    profile_key: str,
    ctx,
    dependencies: ReportGeneratorDependencies,
) -> dict[str, dict]:
    crop_cache_path = _crop_refine_cache_path(
        settings,
        file_id,
        report_name,
        ctx,
        dependencies,
    )
    payload = read_cache_json(Path(crop_cache_path), ctx, dependencies)
    if not isinstance(payload, dict):
        return {}
    profile_value = payload.get("_cache")
    profile = profile_value if isinstance(profile_value, dict) else {}
    if str(profile.get("key") or "") != profile_key:
        return {}
    rows_value = payload.get("results")
    rows = rows_value if isinstance(rows_value, list) else []
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_key = str(row.get("entry_key") or "").strip()
        if entry_key:
            out[entry_key] = row
    return out


def _write_crop_refine_cache(
    settings: IngestSettings,
    *,
    file_id: str,
    report_name: str,
    profile: dict,
    entries: dict[str, dict],
    ctx,
    dependencies: ReportGeneratorDependencies,
) -> None:
    rows = []
    for entry_key, payload in entries.items():
        if not isinstance(payload, dict):
            continue
        rows.append({"entry_key": entry_key, **payload})
    rows.sort(key=lambda item: str(item.get("entry_key") or ""))
    dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=file_id,
            pack_name="crop_refine",
            payload={
                "schema_version": "1.0",
                "_cache": profile,
                "results": rows,
            },
            report_slug=report_name,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:crop_refine_cache_write"),
    )


def select_refined_candidate_items(
    *,
    ranked_rows: list[Any],
    ranked_candidates: list[Candidate],
    settings: IngestSettings,
    local_pdf_path: str,
    report_name: str,
    file_id: str,
    md5: Optional[str],
    ctx,
    pdf_context: Any,
    fallback_model: str,
    selected_kind_max: int,
    dependencies: ReportGeneratorDependencies,
) -> tuple[list[CropItem], list[Candidate]]:
    id2cand = {candidate.id: candidate for candidate in ranked_candidates}
    thresholded: list[tuple[Any, Candidate]] = []
    threshold_reasons: dict[str, int] = {}
    for row in sorted(ranked_rows, key=lambda item: item.score, reverse=True):
        candidate = id2cand.get(row.id)
        if not candidate:
            continue
        passed, reason = _rank_threshold_pass(row, settings)
        if not passed:
            threshold_reasons[reason] = int(threshold_reasons.get(reason, 0)) + 1
            continue
        thresholded.append((row, candidate))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="rank_threshold_gate_complete",
            module=logger.name,
            fields={
                "ranked_count": len(ranked_rows),
                "thresholded_count": len(thresholded),
                "rejected_count": sum(threshold_reasons.values()),
                "reasons": threshold_reasons,
            },
        )
    )
    if not thresholded:
        return [], []

    crop_refine_mode = (
        str(getattr(settings, "crop_refine_mode", "adaptive") or "adaptive")
        .strip()
        .lower()
    )
    if crop_refine_mode not in {"adaptive", "always", "off"}:
        crop_refine_mode = "adaptive"
    crop_refine_enabled = (
        bool(getattr(settings, "crop_refine_enabled", True))
        and crop_refine_mode != "off"
    )
    selected_max = max(1, int(selected_kind_max)) * 2
    selected_per_kind = max(1, int(selected_kind_max))

    crop_refine_prompt_set = None
    crop_refine_system_render = None
    crop_refine_profile: dict[str, Any] = {}
    crop_refine_cache_rows: dict[str, dict] = {}
    resolved_crop_refine_model = fallback_model
    if crop_refine_enabled:
        crop_refine_prompt_set = dependencies.load_prompt_set(
            PromptLoadRequest(
                schema_version="1.0",
                namespace="rank_candidates/crop_refine",
                reload_if_changed=True,
            ),
            ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="prompt_selected",
                module=logger.name,
                fields={
                    "namespace": "rank_candidates/crop_refine",
                    "system_path": crop_refine_prompt_set.system.path,
                    "system_sha256": crop_refine_prompt_set.system.sha256,
                    "user_path": crop_refine_prompt_set.user.path,
                    "user_sha256": crop_refine_prompt_set.user.sha256,
                },
            )
        )
        crop_refine_system_render = dependencies.render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=crop_refine_prompt_set.system,
                variables={},
            ),
            ctx,
        )
        resolved_crop_refine_model = resolve_model(
            "rank_candidates/crop_refine",
            getattr(settings, "openai_models", {}),
            fallback_model,
        )
        if md5:
            profile_key = _crop_refine_profile_key(
                md5,
                model=resolved_crop_refine_model,
                temperature=float(getattr(settings, "crop_refine_temperature", 0.0)),
                seed=settings.rank_seed,
                mode=crop_refine_mode,
                prompt_system_sha256=crop_refine_prompt_set.system.sha256,
                prompt_user_sha256=crop_refine_prompt_set.user.sha256,
            )
            crop_refine_profile = {
                "schema_version": "1.0",
                "key": profile_key,
                "md5": md5,
                "model": resolved_crop_refine_model,
                "temperature": float(getattr(settings, "crop_refine_temperature", 0.0)),
                "seed": settings.rank_seed,
                "mode": crop_refine_mode,
                "prompt_system_sha256": crop_refine_prompt_set.system.sha256,
                "prompt_user_sha256": crop_refine_prompt_set.user.sha256,
            }
            crop_refine_cache_rows = _load_crop_refine_cache(
                settings,
                file_id=file_id,
                report_name=report_name,
                profile_key=profile_key,
                ctx=ctx,
                dependencies=dependencies,
            )

    plan_rows: list[dict[str, Any]] = []
    llm_pending_by_page: dict[int, list[int]] = {}
    llm_pages: set[int] = set()
    for idx, (_, candidate) in enumerate(thresholded):
        reject_now, reject_reason = _candidate_is_obvious_reject(candidate)
        obvious_pass = False
        use_llm = False
        if not reject_now:
            if crop_refine_enabled and crop_refine_mode == "always":
                use_llm = True
            elif crop_refine_enabled and crop_refine_mode == "adaptive":
                obvious_pass = _candidate_is_obvious_pass(candidate)
                use_llm = not obvious_pass
        entry_key = ""
        cached_row = None
        if use_llm and crop_refine_prompt_set and crop_refine_system_render and md5:
            entry_key = _crop_refine_entry_key(
                md5,
                candidate,
                model=resolved_crop_refine_model,
                temperature=float(getattr(settings, "crop_refine_temperature", 0.0)),
                seed=settings.rank_seed,
                mode=crop_refine_mode,
                prompt_system_sha256=crop_refine_prompt_set.system.sha256,
                prompt_user_sha256=crop_refine_prompt_set.user.sha256,
            )
            cached_row = crop_refine_cache_rows.get(entry_key) if entry_key else None
        if use_llm and cached_row is None:
            llm_pending_by_page.setdefault(candidate.page, []).append(idx)
            llm_pages.add(candidate.page)
        plan_rows.append(
            {
                "reject_now": reject_now,
                "reject_reason": reject_reason,
                "obvious_pass": obvious_pass,
                "use_llm": use_llm,
                "entry_key": entry_key,
                "cached_row": cached_row,
            }
        )

    page_render_cache: dict[int, Any] = {}

    def _render_refine_page(page_number: int) -> Any:
        return dependencies.render_page_for_crop_refine(
            CropRefinePageRenderRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                page=page_number,
                dpi=int(getattr(settings, "crop_refine_page_dpi", 110)),
                pdf_context=pdf_context,
            ),
            ctx,
        )

    if llm_pages:
        page_numbers = sorted(llm_pages)
        refine_workers = _crop_refine_parallel_workers(settings, selected_max)
        page_worker_limit = max(1, min(refine_workers, len(page_numbers)))
        can_parallel_page_render = page_worker_limit > 1 and not bool(
            pdf_context and getattr(pdf_context, "fitz_doc", None)
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_page_prerender_start",
                module=logger.name,
                fields={
                    "page_count": len(page_numbers),
                    "workers": page_worker_limit,
                    "parallel": can_parallel_page_render,
                },
            )
        )
        if can_parallel_page_render:
            with ThreadPoolExecutor(max_workers=page_worker_limit) as executor:
                futures = {
                    executor.submit(_render_refine_page, page): page
                    for page in page_numbers
                }
                for future in as_completed(futures):
                    page = futures[future]
                    page_render_cache[page] = future.result()
        else:
            for page in page_numbers:
                page_render_cache[page] = _render_refine_page(page)
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_page_prerender_complete",
                module=logger.name,
                fields={
                    "page_count": len(page_render_cache),
                    "workers": page_worker_limit,
                    "parallel": can_parallel_page_render,
                },
            )
        )

    def _run_crop_refine_llm_page(
        page_number: int, plan_indices: list[int]
    ) -> dict[int, dict[str, Any]]:
        if crop_refine_prompt_set is None or crop_refine_system_render is None:
            raise RuntimeError("crop_refine prompt set was not initialized")
        page_render = page_render_cache.get(page_number) or _render_refine_page(
            page_number
        )

        def _candidate_prompt_payload(
            candidate: Candidate,
            *,
            bbox: tuple[float, float, float, float],
            include_proposed_bbox: bool,
        ) -> dict[str, Any]:
            payload_item = {
                "id": candidate.id,
                "type": candidate.kind,
                "page": candidate.page,
                "bbox": [float(value) for value in bbox],
                "caption": (candidate.caption or "")[:400],
                "preview_text": (candidate.preview_text or "")[:600],
                "features": candidate_features_payload(candidate),
                "quality_signals": _candidate_quality_signals(candidate),
            }
            if include_proposed_bbox:
                payload_item["proposed_bbox"] = [float(value) for value in bbox]
            return payload_item

        def _invoke_phase(
            phase: str,
            phase_candidates: list[CropRefineCandidate],
            phase_payload: list[dict[str, Any]],
        ) -> Any:
            crop_refine_user_render = dependencies.render_prompt(
                PromptRenderRequest(
                    schema_version="1.0",
                    template=crop_refine_prompt_set.user,
                    variables={
                        "page_width": page_render.page_width,
                        "page_height": page_render.page_height,
                        "phase": phase,
                        "candidates_json": json.dumps(phase_payload, ensure_ascii=True),
                    },
                ),
                ctx,
            )
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_llm_request",
                    module=logger.name,
                    fields={
                        "page": page_number,
                        "phase": phase,
                        "candidate_ids": [
                            candidate.id for candidate in phase_candidates
                        ],
                        "candidate_count": len(phase_candidates),
                    },
                )
            )
            crop_refine_resp = dependencies.refine_candidate_crops(
                CropRefineRequest(
                    schema_version="1.0",
                    system_prompt=crop_refine_system_render.text,
                    user_prompt=crop_refine_user_render.text,
                    prompt_system_sha256=crop_refine_prompt_set.system.sha256,
                    prompt_user_sha256=crop_refine_prompt_set.user.sha256,
                    model=resolved_crop_refine_model,
                    temperature=float(
                        getattr(settings, "crop_refine_temperature", 0.0)
                    ),
                    api_key=settings.openai_api_key,
                    page_image_path=str(
                        Path(settings.output_dir) / page_render.image_path
                    ),
                    page=page_number,
                    page_width=page_render.page_width,
                    page_height=page_render.page_height,
                    candidates=phase_candidates,
                    seed=settings.rank_seed,
                    timeout_seconds=float(
                        getattr(
                            settings,
                            "crop_refine_timeout_seconds",
                            settings.rank_timeout_seconds,
                        )
                    ),
                    cost_ledger_path=settings.cost_ledger_path,
                    cost_daily_path=settings.cost_daily_path,
                    model_pricing=settings.model_pricing,
                    response_cache_enabled=True,
                    response_cache_dir=settings.cache_dir,
                ),
                ctx,
            )
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_llm_response_raw",
                    module=logger.name,
                    fields={
                        "page": page_number,
                        "phase": phase,
                        "candidate_ids": [
                            candidate.id for candidate in phase_candidates
                        ],
                        "candidate_count": len(phase_candidates),
                        "content": crop_refine_resp.raw_content,
                    },
                )
            )
            return crop_refine_resp

        phase_candidates: list[CropRefineCandidate] = []
        phase_payload: list[dict[str, Any]] = []
        for plan_index in plan_indices:
            _, candidate = thresholded[plan_index]
            initial_bbox = _bbox_tuple(candidate.bbox)
            phase_candidates.append(
                CropRefineCandidate(
                    schema_version="1.0",
                    id=candidate.id,
                    type=candidate.kind,
                    page=candidate.page,
                    bbox=initial_bbox,
                    caption=candidate.caption or "",
                    preview_text=candidate.preview_text or "",
                    meta=candidate.meta or {},
                    features=candidate_features(candidate),
                )
            )
            phase_payload.append(
                _candidate_prompt_payload(
                    candidate,
                    bbox=initial_bbox,
                    include_proposed_bbox=False,
                )
            )

        coarse_resp = _invoke_phase("coarse", phase_candidates, phase_payload)

        expected_coarse_ids = {candidate.id for candidate in phase_candidates}
        returned_coarse_ids = {result_item.id for result_item in coarse_resp.results}
        missing_coarse_ids = expected_coarse_ids - returned_coarse_ids
        if missing_coarse_ids:
            logger.warning(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_batch_missing_decisions_recover",
                    module=logger.name,
                    fields={
                        "page": page_number,
                        "phase": "coarse",
                        "missing_candidate_ids": sorted(missing_coarse_ids),
                        "missing_count": len(missing_coarse_ids),
                    },
                )
            )
            for missing_id in sorted(missing_coarse_ids):
                recovery_index = next(
                    (
                        index
                        for index, candidate in enumerate(phase_candidates)
                        if candidate.id == missing_id
                    ),
                    None,
                )
                if recovery_index is None:
                    continue
                recovery_resp = _invoke_phase(
                    "coarse",
                    [phase_candidates[recovery_index]],
                    [phase_payload[recovery_index]],
                )
                coarse_resp.results.extend(recovery_resp.results)
        coarse_results = {
            result_item.id: result_item for result_item in coarse_resp.results
        }
        page_results: dict[int, dict[str, Any]] = {}
        finalize_candidates: list[CropRefineCandidate] = []
        finalize_payload: list[dict[str, Any]] = []
        finalize_plan_indices: list[int] = []

        for plan_index in plan_indices:
            _, candidate = thresholded[plan_index]
            coarse_decision = coarse_results.get(candidate.id)
            if coarse_decision is None:
                page_results[plan_index] = {
                    "is_valid_candidate": False,
                    "reason": "missing_decision:coarse",
                    "refined_bbox": [float(value) for value in candidate.bbox],
                }
                continue
            coarse_bbox = _bbox_tuple(coarse_decision.refined_bbox)
            coarse_valid = bool(coarse_decision.is_valid_candidate)
            coarse_reason = coarse_decision.reason or (
                "valid" if coarse_valid else "rejected"
            )
            if not coarse_valid:
                page_results[plan_index] = {
                    "is_valid_candidate": False,
                    "reason": coarse_reason,
                    "refined_bbox": [float(value) for value in coarse_bbox],
                }
                continue
            finalize_plan_indices.append(plan_index)
            finalize_candidates.append(
                CropRefineCandidate(
                    schema_version="1.0",
                    id=candidate.id,
                    type=candidate.kind,
                    page=candidate.page,
                    bbox=coarse_bbox,
                    caption=candidate.caption or "",
                    preview_text=candidate.preview_text or "",
                    meta=candidate.meta or {},
                    features=candidate_features(candidate),
                )
            )
            finalize_payload.append(
                _candidate_prompt_payload(
                    candidate,
                    bbox=coarse_bbox,
                    include_proposed_bbox=True,
                )
            )

        if not finalize_candidates:
            return page_results

        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_second_pass_start",
                module=logger.name,
                fields={
                    "page": page_number,
                    "candidate_ids": [
                        candidate.id for candidate in finalize_candidates
                    ],
                    "candidate_count": len(finalize_candidates),
                },
            )
        )
        finalize_resp = _invoke_phase("finalize", finalize_candidates, finalize_payload)
        expected_finalize_ids = {candidate.id for candidate in finalize_candidates}
        returned_finalize_ids = {
            result_item.id for result_item in finalize_resp.results
        }
        missing_finalize_ids = expected_finalize_ids - returned_finalize_ids
        if missing_finalize_ids:
            logger.warning(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_batch_missing_decisions_recover",
                    module=logger.name,
                    fields={
                        "page": page_number,
                        "phase": "finalize",
                        "missing_candidate_ids": sorted(missing_finalize_ids),
                        "missing_count": len(missing_finalize_ids),
                    },
                )
            )
            for missing_id in sorted(missing_finalize_ids):
                recovery_index = next(
                    (
                        index
                        for index, candidate in enumerate(finalize_candidates)
                        if candidate.id == missing_id
                    ),
                    None,
                )
                if recovery_index is None:
                    continue
                recovery_resp = _invoke_phase(
                    "finalize",
                    [finalize_candidates[recovery_index]],
                    [finalize_payload[recovery_index]],
                )
                finalize_resp.results.extend(recovery_resp.results)
        finalize_results = {
            result_item.id: result_item for result_item in finalize_resp.results
        }
        for plan_index, finalize_candidate in zip(
            finalize_plan_indices, finalize_candidates
        ):
            finalize_decision = finalize_results.get(finalize_candidate.id)
            if finalize_decision is None:
                page_results[plan_index] = {
                    "is_valid_candidate": False,
                    "reason": "missing_decision:finalize",
                    "refined_bbox": [float(value) for value in finalize_candidate.bbox],
                }
                continue
            final_bbox = _bbox_tuple(finalize_decision.refined_bbox)
            final_valid = bool(finalize_decision.is_valid_candidate)
            final_reason = finalize_decision.reason or (
                "valid" if final_valid else "rejected"
            )
            page_results[plan_index] = {
                "is_valid_candidate": final_valid,
                "reason": final_reason,
                "refined_bbox": [float(value) for value in final_bbox],
            }
        return page_results

    refine_workers = _crop_refine_parallel_workers(settings, selected_max)
    llm_executor: Optional[ThreadPoolExecutor] = None
    llm_inflight: dict[int, Any] = {}
    llm_cursor = 0
    llm_pending_pages = sorted(llm_pending_by_page)

    def _submit_llm_jobs() -> None:
        nonlocal llm_cursor
        if llm_executor is None:
            return
        while (
            llm_cursor < len(llm_pending_pages) and len(llm_inflight) < refine_workers
        ):
            page_number = llm_pending_pages[llm_cursor]
            if page_number not in llm_inflight:
                llm_inflight[page_number] = llm_executor.submit(
                    _run_crop_refine_llm_page,
                    page_number,
                    list(llm_pending_by_page.get(page_number, [])),
                )
            llm_cursor += 1

    if llm_pending_pages and refine_workers > 1:
        llm_executor = ThreadPoolExecutor(max_workers=refine_workers)
        _submit_llm_jobs()

    accepted_items: list[CropItem] = []
    accepted_candidates: list[Candidate] = []
    accepted_by_kind: dict[str, int] = {"table": 0, "chart": 0}
    for idx, (row, candidate) in enumerate(thresholded):
        if len(accepted_items) >= selected_max:
            break
        if accepted_by_kind.get(candidate.kind, 0) >= selected_per_kind:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_skipped_kind_limit",
                    module=logger.name,
                    fields={
                        "candidate_id": candidate.id,
                        "candidate_type": candidate.kind,
                        "selected_per_kind": selected_per_kind,
                    },
                )
            )
            continue
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_start",
                module=logger.name,
                fields={
                    "candidate_id": candidate.id,
                    "candidate_type": candidate.kind,
                    "page": candidate.page,
                    "score": row.score,
                },
            )
        )
        plan = plan_rows[idx]
        if bool(plan["reject_now"]):
            reject_reason = str(plan["reject_reason"] or "deterministic_reject")
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_skipped_deterministic_reject",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "reason": reject_reason},
                )
            )
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_candidate_rejected",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "reason": reject_reason},
                )
            )
            continue
        if (
            crop_refine_enabled
            and crop_refine_mode == "adaptive"
            and bool(plan["obvious_pass"])
        ):
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_skipped_deterministic_pass",
                    module=logger.name,
                    fields={"candidate_id": candidate.id},
                )
            )
        refined_bbox = _bbox_tuple(candidate.bbox)
        llm_valid = True
        llm_reason = "deterministic_pass"
        use_llm = (
            bool(plan["use_llm"])
            and crop_refine_prompt_set is not None
            and crop_refine_system_render is not None
        )
        if use_llm:
            cached_row = plan.get("cached_row")
            if isinstance(cached_row, dict):
                llm_valid = bool(cached_row.get("is_valid_candidate"))
                llm_reason = str(cached_row.get("reason") or "cache")
                cached_bbox = cached_row.get("refined_bbox")
                if isinstance(cached_bbox, (list, tuple)) and len(cached_bbox) == 4:
                    refined_bbox = _bbox_tuple(cached_bbox)
            else:
                page_number = candidate.page
                llm_result = plan.get("llm_result")
                if not isinstance(llm_result, dict):
                    pending_plan_indices = list(
                        llm_pending_by_page.get(page_number, [idx])
                    )
                    if llm_executor is not None:
                        future = llm_inflight.pop(
                            page_number, None
                        ) or llm_executor.submit(
                            _run_crop_refine_llm_page,
                            page_number,
                            pending_plan_indices,
                        )
                        page_results = future.result()
                        _submit_llm_jobs()
                    else:
                        page_results = _run_crop_refine_llm_page(
                            page_number,
                            pending_plan_indices,
                        )
                    for result_index, page_result in page_results.items():
                        plan_rows[result_index]["llm_result"] = page_result
                    llm_result = plan.get("llm_result")
                if not isinstance(llm_result, dict):
                    llm_result = {
                        "is_valid_candidate": False,
                        "reason": "missing_decision:page_batch",
                        "refined_bbox": [float(value) for value in candidate.bbox],
                    }
                llm_valid = bool(llm_result.get("is_valid_candidate"))
                llm_reason = str(
                    llm_result.get("reason") or ("valid" if llm_valid else "rejected")
                )
                result_bbox = llm_result.get("refined_bbox")
                if isinstance(result_bbox, (list, tuple)) and len(result_bbox) == 4:
                    refined_bbox = _bbox_tuple(result_bbox)
                entry_key = str(plan.get("entry_key") or "")
                if entry_key:
                    crop_refine_cache_rows[entry_key] = {
                        "candidate_id": candidate.id,
                        "is_valid_candidate": llm_valid,
                        "refined_bbox": [float(value) for value in refined_bbox],
                        "reason": llm_reason,
                        "page": candidate.page,
                    }
            if not llm_valid:
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="crop_refine_candidate_rejected",
                        module=logger.name,
                        fields={"candidate_id": candidate.id, "reason": llm_reason},
                    )
                )
                continue
        bbox_resp = dependencies.apply_crop_refine_bbox(
            CropRefineBBoxApplyRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                page=candidate.page,
                bbox=refined_bbox,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        refined_bbox = bbox_resp.bbox
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_bbox_applied",
                module=logger.name,
                fields={"candidate_id": candidate.id, "bbox": list(refined_bbox)},
            )
        )
        width = max(0.0, refined_bbox[2] - refined_bbox[0])
        height = max(0.0, refined_bbox[3] - refined_bbox[1])
        page_render = page_render_cache.get(candidate.page)
        page_area = (
            (page_render.page_width * page_render.page_height) if page_render else 0.0
        )
        area_frac = (
            ((width * height) / page_area)
            if page_area > 0
            else _candidate_meta(candidate, "area_frac", 0.0)
        )
        aspect = (width / height) if height > 0 else 0.0
        if width < 12 or height < 12:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_candidate_rejected",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "reason": "bbox_too_small"},
                )
            )
            continue
        if area_frac < 0.01:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_candidate_rejected",
                    module=logger.name,
                    fields={
                        "candidate_id": candidate.id,
                        "reason": "bbox_area_too_small",
                    },
                )
            )
            continue
        if aspect < 0.12 or aspect > 8.0:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_candidate_rejected",
                    module=logger.name,
                    fields={
                        "candidate_id": candidate.id,
                        "reason": "bbox_aspect_out_of_range",
                    },
                )
            )
            continue
        accepted_items.append(
            CropItem(
                id=candidate.id,
                type=candidate.kind,
                score=float(row.score),
                page=candidate.page,
                bbox=refined_bbox,
            )
        )
        accepted_candidates.append(candidate)
        accepted_by_kind[candidate.kind] = (
            int(accepted_by_kind.get(candidate.kind, 0)) + 1
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_accepted",
                module=logger.name,
                fields={
                    "candidate_id": candidate.id,
                    "accepted_count": len(accepted_items),
                },
            )
        )
    if llm_executor is not None:
        for future in llm_inflight.values():
            future.cancel()
        try:
            llm_executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            llm_executor.shutdown(wait=False)
    if crop_refine_profile and md5:
        _write_crop_refine_cache(
            settings,
            file_id=file_id,
            report_name=report_name,
            profile=crop_refine_profile,
            entries=crop_refine_cache_rows,
            ctx=ctx,
            dependencies=dependencies,
        )
    return accepted_items[:selected_max], accepted_candidates[:selected_max]


def _candidate_crop_path_map(
    candidates: list[Candidate],
    candidate_paths: list[str],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for candidate, path in zip(candidates, candidate_paths):
        candidate_id = str(candidate.id or "").strip()
        normalized_path = str(path or "").strip()
        if candidate_id and normalized_path:
            mapping[candidate_id] = normalized_path
    return mapping


def _candidate_extraction_output_path(
    settings: IngestSettings,
    report_name: str,
) -> Path:
    return Path(settings.output_dir) / str(report_name or "").strip() / "candidates" / "candidates.json"


def _load_candidate_crop_path_map(
    *,
    settings: IngestSettings,
    report_name: str,
    ctx,
    dependencies: ReportGeneratorDependencies,
) -> dict[str, str]:
    candidates_path = _candidate_extraction_output_path(settings, report_name)
    payload = read_cache_json(candidates_path, ctx, dependencies)
    if not isinstance(payload, dict):
        return {}
    rows_value = payload.get("candidates")
    rows = rows_value if isinstance(rows_value, list) else []
    path_map: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("id") or "").strip()
        crop_path = str(row.get("crop_path") or "").strip()
        if candidate_id and crop_path:
            path_map[candidate_id] = crop_path
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="candidate_crop_paths_loaded",
            module=logger.name,
            fields={
                "path": str(candidates_path),
                "candidate_row_count": len(rows),
                "crop_path_count": len(path_map),
            },
        )
    )
    return path_map


def _empty_figure_response() -> FigureExtractResponse:
    return FigureExtractResponse(
        schema_version="1.0",
        image_path=None,
        caption=None,
        page=-1,
    )


def _select_fallback_candidates(
    *,
    ranked_rows: list[Any],
    prefiltered_candidates: list[Candidate],
    selected_kind_max: int,
    settings: Optional[IngestSettings] = None,
) -> tuple[list[Candidate], dict[str, Any]]:
    selected_max = max(1, int(selected_kind_max)) * 2
    selected_per_kind = max(1, int(selected_kind_max))
    prefiltered_by_id = {
        str(candidate.id or "").strip(): candidate
        for candidate in prefiltered_candidates
    }
    ordered_candidates: list[tuple[str, Candidate]] = []
    seen_ids: set[str] = set()
    blocked_ids: set[str] = set()
    rejected_reasons: dict[str, int] = {}
    for row in sorted(
        ranked_rows,
        key=lambda item: coerce_float(getattr(item, "score", 0.0), 0.0),
        reverse=True,
    ):
        candidate_id = str(getattr(row, "id", "") or "").strip()
        candidate = prefiltered_by_id.get(candidate_id)
        if candidate is None or candidate_id in seen_ids:
            continue
        if settings is not None:
            passed, reason = _rank_threshold_pass(row, settings)
            if not passed:
                blocked_ids.add(candidate_id)
                rejected_reasons[reason] = int(rejected_reasons.get(reason, 0)) + 1
                continue
        seen_ids.add(candidate_id)
        ordered_candidates.append(("ranked", candidate))
    for candidate in prefiltered_candidates:
        candidate_id = str(candidate.id or "").strip()
        if candidate_id in blocked_ids:
            continue
        if candidate_id and candidate_id not in seen_ids:
            seen_ids.add(candidate_id)
            ordered_candidates.append(("prefilter", candidate))
    fallback_candidates: list[Candidate] = []
    selected_by_kind: dict[str, int] = {"table": 0, "chart": 0}
    selected_by_source: dict[str, int] = {"ranked": 0, "prefilter": 0}
    skipped_kind_limit = 0
    for source, candidate in ordered_candidates:
        if len(fallback_candidates) >= selected_max:
            break
        reject_now, reject_reason = _candidate_is_obvious_reject(candidate)
        if reject_now:
            rejected_reasons[reject_reason] = (
                int(rejected_reasons.get(reject_reason, 0)) + 1
            )
            continue
        candidate_kind = str(candidate.kind or "").strip()
        if selected_by_kind.get(candidate_kind, 0) >= selected_per_kind:
            skipped_kind_limit += 1
            continue
        fallback_candidates.append(candidate)
        selected_by_kind[candidate_kind] = (
            int(selected_by_kind.get(candidate_kind, 0)) + 1
        )
        selected_by_source[source] = int(selected_by_source.get(source, 0)) + 1
    stats = {
        "ordered_candidate_count": len(ordered_candidates),
        "selected_count": len(fallback_candidates),
        "selected_by_kind": selected_by_kind,
        "selected_by_source": {
            key: value for key, value in selected_by_source.items() if value
        },
        "skipped_kind_limit": skipped_kind_limit,
        "rejected_reasons": rejected_reasons,
    }
    return fallback_candidates, stats


def _select_fallback_candidate_crop_paths(
    *,
    ranked_rows: list[Any],
    prefiltered_candidates: list[Candidate],
    candidate_path_by_id: dict[str, str],
    selected_kind_max: int,
    settings: Optional[IngestSettings] = None,
) -> tuple[list[str], list[Candidate], dict[str, Any]]:
    ordered_fallback_candidates, stats = _select_fallback_candidates(
        ranked_rows=ranked_rows,
        prefiltered_candidates=prefiltered_candidates,
        selected_kind_max=selected_kind_max,
        settings=settings,
    )
    fallback_paths: list[str] = []
    fallback_candidates: list[Candidate] = []
    skipped_missing_crop = 0
    for candidate in ordered_fallback_candidates:
        candidate_id = str(candidate.id or "").strip()
        crop_path = str(candidate_path_by_id.get(candidate_id) or "").strip()
        if not crop_path:
            skipped_missing_crop += 1
            continue
        fallback_paths.append(crop_path)
        fallback_candidates.append(candidate)
    stats = {
        **stats,
        "candidate_crop_count": len(candidate_path_by_id),
        "selected_count": len(fallback_paths),
        "skipped_missing_crop": skipped_missing_crop,
    }
    return fallback_paths, fallback_candidates, stats


def _apply_figure_candidate_metadata(
    data: ReportPayload,
    candidate: Optional[Candidate],
) -> None:
    if candidate is None:
        return
    caption = (candidate.caption or "").strip()
    preview = (candidate.preview_text or "").strip()
    derived_title = caption or (preview[:140] if preview else "")
    if derived_title:
        data.figure.title = derived_title
    if caption or preview:
        data.figure.evidence = caption or preview


def _resolve_figure_section_assets(
    sliced_paths: list[str],
    primary_figure_path: str,
) -> tuple[list[str], str, bool]:
    gallery_paths = [
        str(path or "").strip() for path in sliced_paths if str(path or "").strip()
    ]
    if gallery_paths:
        return gallery_paths, gallery_paths[0], True
    normalized_primary = str(primary_figure_path or "").strip()
    return [], normalized_primary, bool(normalized_primary)


def _legacy_primary_display_caption(
    data: ReportPayload,
    detected_caption: str = "",
) -> str:
    for candidate in (
        str(getattr(data.figure, "title", "") or "").strip(),
        str(getattr(data.figure, "evidence", "") or "").strip(),
        str(detected_caption or "").strip(),
    ):
        if candidate:
            return candidate
    return "Representative figure from the source report."


def _asset_from_candidate(
    *,
    image_path: str,
    candidate: Optional[Candidate],
    is_primary: bool,
    index: int,
    primary_display_caption: str,
) -> ReportFigureAsset:
    detected_caption = str(getattr(candidate, "caption", "") or "").strip()
    preview_text = str(getattr(candidate, "preview_text", "") or "").strip()
    display_caption = (
        primary_display_caption if is_primary else f"Additional figure {index}"
    )
    caption_source = "legacy" if is_primary else "placeholder"
    return ReportFigureAsset(
        image_path=str(image_path or "").strip(),
        page=int(getattr(candidate, "page", -1) if candidate is not None else -1),
        candidate_id=str(getattr(candidate, "id", "") or "").strip(),
        kind=str(getattr(candidate, "kind", "") or "image").strip() or "image",
        is_primary=bool(is_primary),
        detected_caption=detected_caption,
        preview_text=preview_text,
        generated_caption="",
        display_caption=display_caption,
        caption_source=caption_source,
    )


def _build_figure_assets(
    *,
    gallery_paths: list[str],
    figure_candidates: list[Candidate],
    primary_figure_path: str,
    primary_caption: str,
    fig_resp: Any,
) -> list[ReportFigureAsset]:
    assets: list[ReportFigureAsset] = []
    for index, image_path in enumerate(gallery_paths, start=1):
        candidate = (
            figure_candidates[index - 1] if index - 1 < len(figure_candidates) else None
        )
        normalized_path = str(image_path or "").strip()
        if not normalized_path:
            continue
        assets.append(
            _asset_from_candidate(
                image_path=normalized_path,
                candidate=candidate,
                is_primary=index == 1,
                index=index,
                primary_display_caption=primary_caption,
            )
        )
    if assets:
        return assets
    normalized_primary = str(primary_figure_path or "").strip()
    if not normalized_primary:
        return []
    fallback_caption = str(getattr(fig_resp, "caption", "") or "").strip()
    return [
        ReportFigureAsset(
            image_path=normalized_primary,
            page=int(getattr(fig_resp, "page", -1) or -1),
            candidate_id="",
            kind="image",
            is_primary=True,
            detected_caption=fallback_caption,
            preview_text="",
            generated_caption="",
            display_caption=primary_caption,
            caption_source="legacy",
        )
    ]


def select_report_figures(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    dependencies: ReportGeneratorDependencies,
) -> ReportSelectionState:
    data = source.payload
    fig_resp: FigureExtractResponse = _empty_figure_response()
    figure_extracted = False

    def _extract_figure_task():
        return dependencies.extract_best_figure(
            FigureExtractRequest(
                schema_version="1.0",
                pdf_path=runtime.local_pdf_path,
                out_dir=runtime.settings.output_dir,
                report_name=runtime.report_name,
                pdf_context=source.pdf_context_for_tasks,
            ),
            runtime.ctx,
        )

    def _ensure_figure_extracted() -> FigureExtractResponse:
        nonlocal fig_resp, figure_extracted
        if figure_extracted:
            return fig_resp
        fig_resp = _extract_figure_task()
        figure_extracted = True
        if fig_resp.image_path:
            data._figure_image = fig_resp.image_path
            if fig_resp.caption and not (data.figure.evidence or "").strip():
                data.figure.evidence = fig_resp.caption
        return fig_resp

    def _extract_candidates_task():
        exclude_page_indices: list[int] = []
        if source.contents_page_number > 0:
            exclude_page_indices = [int(source.contents_page_number) - 1]
        return dependencies.collect_candidates(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=runtime.local_pdf_path,
                out_dir=runtime.settings.output_dir,
                report_name=runtime.report_name,
                pdf_context=source.pdf_context_for_tasks,
                parallel_workers=runtime.report_worker_limit,
                exclude_page_indices=exclude_page_indices,
            ),
            runtime.ctx,
        )

    cands_resp = _extract_candidates_task()

    ranked: list[Any] = []
    rank_usage: dict[str, Optional[int]] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    sliced_paths: list[str] = []
    figure_candidates: list[Candidate] = []
    data._figure_section_enabled = False
    if cands_resp.candidates:
        for candidate in cands_resp.candidates:
            validate_candidate(candidate)
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="candidate_validation_complete",
                module=logger.name,
                fields={"count": len(cands_resp.candidates)},
            )
        )
        prefiltered_candidates: list[Candidate] = []
        prefilter_reasons: dict[str, int] = {}
        for candidate in cands_resp.candidates:
            reason = _candidate_prefilter_reject_reason(candidate)
            if reason:
                prefilter_reasons[reason] = int(prefilter_reasons.get(reason, 0)) + 1
                continue
            prefiltered_candidates.append(candidate)
        prefiltered_candidates = sorted(
            prefiltered_candidates,
            key=_candidate_prefilter_priority,
            reverse=True,
        )
        prefilter_kind_counts = {
            "table": sum(
                1 for candidate in prefiltered_candidates if candidate.kind == "table"
            ),
            "chart": sum(
                1 for candidate in prefiltered_candidates if candidate.kind == "chart"
            ),
        }
        truncated_kind_counts = dict(prefilter_kind_counts)
        if runtime.settings.rank_max_candidates > 0:
            prefiltered_candidates, truncated_kind_counts = (
                _truncate_prefiltered_candidates(
                    prefiltered_candidates,
                    int(runtime.settings.rank_max_candidates),
                )
            )
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="candidate_prefilter_complete",
                module=logger.name,
                fields={
                    "raw_count": len(cands_resp.candidates),
                    "kept_count": len(prefiltered_candidates),
                    "rejected_count": sum(prefilter_reasons.values()),
                    "reasons": prefilter_reasons,
                    "prefilter_kind_counts": prefilter_kind_counts,
                    "truncated_kind_counts": truncated_kind_counts,
                    "rank_max_candidates": runtime.settings.rank_max_candidates,
                },
            )
        )
        if prefiltered_candidates:
            table_candidates, chart_candidates = _split_candidates_by_kind(
                prefiltered_candidates
            )
            per_kind_limit = max(1, int(runtime.settings.rank_selected_max))
            logger.info(
                log_event(
                    runtime.ctx,
                    role="generator",
                    event="candidate_rank_split",
                    module=logger.name,
                    fields={
                        "table_candidates": len(table_candidates),
                        "chart_candidates": len(chart_candidates),
                        "per_kind_limit": per_kind_limit,
                    },
                )
            )
            usage_rows: list[dict[str, Optional[int]]] = []
            try:
                for kind, batch in (
                    ("table", table_candidates),
                    ("chart", chart_candidates),
                ):
                    batch_result = _rank_candidates_batch(
                        candidates=batch,
                        kind=kind,
                        settings=runtime.settings,
                        ctx=runtime.ctx,
                        dependencies=dependencies,
                    )
                    ranked.extend(batch_result.ranked)
                    usage_rows.append(batch_result.usage)
                rank_usage = _merge_rank_usage(usage_rows)
            except Exception as exc:
                logger.info(
                    log_event(
                        runtime.ctx,
                        role="generator",
                        event="rank_failed",
                        module=logger.name,
                        fields={"file_id": runtime.file.file_id, "error": str(exc)},
                    )
                )
                ranked = []
        else:
            logger.info(
                log_event(
                    runtime.ctx,
                    role="generator",
                    event="rank_skipped_no_prefilter_candidates",
                    module=logger.name,
                    fields={"file_id": runtime.file.file_id},
                )
            )

        selected_items, selected_candidates = select_refined_candidate_items(
            ranked_rows=ranked,
            ranked_candidates=prefiltered_candidates,
            settings=runtime.settings,
            local_pdf_path=runtime.local_pdf_path,
            report_name=runtime.report_name,
            file_id=runtime.file.file_id,
            md5=runtime.md5,
            ctx=runtime.ctx,
            pdf_context=source.pdf_context,
            fallback_model=(
                runtime.settings.rank_model or runtime.settings.openai_model
            ),
            selected_kind_max=max(1, int(runtime.settings.rank_selected_max)),
            dependencies=dependencies,
        )
        if selected_items:
            table_items = [item for item in selected_items if item.type == "table"]
            chart_items = [item for item in selected_items if item.type == "chart"]
            selected_path_by_id: dict[str, str] = {}
            if table_items:
                table_paths = dependencies.crop_regions(
                    CropRequest(
                        schema_version="1.0",
                        pdf_path=runtime.local_pdf_path,
                        out_dir=runtime.settings.output_dir,
                        report_name=runtime.report_name,
                        items=table_items,
                        mode="table_strict",
                        pdf_context=source.pdf_context,
                    ),
                    runtime.ctx,
                ).paths
                selected_path_by_id.update(
                    {
                        item.id: str(path or "").strip()
                        for item, path in zip(table_items, table_paths)
                        if str(path or "").strip()
                    }
                )
            if chart_items:
                chart_paths = dependencies.crop_regions(
                    CropRequest(
                        schema_version="1.0",
                        pdf_path=runtime.local_pdf_path,
                        out_dir=runtime.settings.output_dir,
                        report_name=runtime.report_name,
                        items=chart_items,
                        mode="chart_strict",
                        pdf_context=source.pdf_context,
                    ),
                    runtime.ctx,
                ).paths
                selected_path_by_id.update(
                    {
                        item.id: str(path or "").strip()
                        for item, path in zip(chart_items, chart_paths)
                        if str(path or "").strip()
                    }
                )
            sliced_paths = [
                str(selected_path_by_id.get(item.id) or "").strip()
                for item in selected_items
                if str(selected_path_by_id.get(item.id) or "").strip()
            ]
        figure_candidates = selected_candidates
        if not sliced_paths:
            fallback_candidates, fallback_stats = _select_fallback_candidates(
                ranked_rows=ranked,
                prefiltered_candidates=prefiltered_candidates,
                selected_kind_max=max(1, int(runtime.settings.rank_selected_max)),
                settings=runtime.settings,
            )
            if fallback_candidates:
                candidate_path_by_id = _load_candidate_crop_path_map(
                    settings=runtime.settings,
                    report_name=runtime.report_name,
                    ctx=runtime.ctx,
                    dependencies=dependencies,
                )
                fallback_path_by_id: dict[str, str] = {}
                reuse_stats: dict[str, Any] = {}
                if candidate_path_by_id:
                    reused_paths, reused_candidates, reuse_stats = (
                        _select_fallback_candidate_crop_paths(
                            ranked_rows=ranked,
                            prefiltered_candidates=prefiltered_candidates,
                            candidate_path_by_id=candidate_path_by_id,
                            selected_kind_max=max(
                                1, int(runtime.settings.rank_selected_max)
                            ),
                            settings=runtime.settings,
                        )
                    )
                    fallback_path_by_id.update(
                        _candidate_crop_path_map(reused_candidates, reused_paths)
                    )
                    if fallback_path_by_id:
                        logger.info(
                            log_event(
                                runtime.ctx,
                                role="generator",
                                event="candidate_crops_reused",
                                module=logger.name,
                                fields={
                                    "file_id": runtime.file.file_id,
                                    **reuse_stats,
                                },
                            )
                        )
                missing_fallback_candidates = [
                    candidate
                    for candidate in fallback_candidates
                    if str(candidate.id or "").strip() not in fallback_path_by_id
                ]
                newly_cropped_count = 0
                if missing_fallback_candidates:
                    fallback_items = [
                        CropItem(
                            id=candidate.id,
                            type=candidate.kind,
                            score=0.0,
                            page=candidate.page,
                            bbox=candidate.bbox,
                        )
                        for candidate in missing_fallback_candidates
                    ]
                    logger.info(
                        log_event(
                            runtime.ctx,
                            role="generator",
                            event="candidate_crops_start",
                            module=logger.name,
                            fields={
                                "count": len(fallback_items),
                                "subdir": "candidates",
                                "reuse_count": len(fallback_path_by_id),
                            },
                        )
                    )
                    try:
                        fallback_crop_resp = dependencies.crop_regions(
                            CropRequest(
                                schema_version="1.0",
                                pdf_path=runtime.local_pdf_path,
                                out_dir=runtime.settings.output_dir,
                                report_name=runtime.report_name,
                                subdir="candidates",
                                items=fallback_items,
                                mode="legacy",
                                pdf_context=source.pdf_context,
                            ),
                            runtime.ctx,
                        )
                        fallback_path_by_id.update(
                            _candidate_crop_path_map(
                                missing_fallback_candidates,
                                fallback_crop_resp.paths,
                            )
                        )
                        newly_cropped_count = sum(
                            1
                            for candidate in missing_fallback_candidates
                            if str(candidate.id or "").strip() in fallback_path_by_id
                        )
                        if newly_cropped_count:
                            logger.info(
                                log_event(
                                    runtime.ctx,
                                    role="generator",
                                    event="candidate_crops_complete",
                                    module=logger.name,
                                    fields={
                                        "count": newly_cropped_count,
                                        "subdir": "candidates",
                                        "reuse_count": len(fallback_path_by_id)
                                        - newly_cropped_count,
                                    },
                                ),
                            )
                    except Exception as exc:
                        logger.info(
                            log_event(
                                runtime.ctx,
                                role="generator",
                                event="candidate_crops_failed",
                                module=logger.name,
                                fields={"error": str(exc), "subdir": "candidates"},
                            )
                        )
                fallback_paths: list[str] = []
                fallback_candidates_with_paths: list[Candidate] = []
                for candidate in fallback_candidates:
                    normalized_path = str(
                        fallback_path_by_id.get(str(candidate.id or "").strip()) or ""
                    ).strip()
                    if not normalized_path:
                        continue
                    fallback_paths.append(normalized_path)
                    fallback_candidates_with_paths.append(candidate)
                if fallback_paths:
                    sliced_paths = fallback_paths
                    figure_candidates = fallback_candidates_with_paths
                    logger.info(
                        log_event(
                            runtime.ctx,
                            role="generator",
                            event="figure_section_fallback_candidate_crops_enabled",
                            module=logger.name,
                            fields={
                                "file_id": runtime.file.file_id,
                                "ranked_count": len(ranked),
                                "prefiltered_count": len(prefiltered_candidates),
                                "candidate_crop_count": len(candidate_path_by_id),
                                "selected_count": len(fallback_paths),
                                "reused_crop_count": len(fallback_path_by_id)
                                - newly_cropped_count,
                                "new_crop_count": newly_cropped_count,
                                "skipped_missing_crop": max(
                                    0,
                                    len(fallback_candidates) - len(fallback_paths),
                                ),
                                "ordered_candidate_count": int(
                                    fallback_stats.get("ordered_candidate_count", 0)
                                ),
                                "selected_by_kind": fallback_stats.get(
                                    "selected_by_kind", {}
                                ),
                                "selected_by_source": fallback_stats.get(
                                    "selected_by_source", {}
                                ),
                                "rejected_reasons": fallback_stats.get(
                                    "rejected_reasons", {}
                                ),
                                "skipped_kind_limit": int(
                                    fallback_stats.get("skipped_kind_limit", 0)
                                ),
                            },
                        )
                    )
        if figure_candidates:
            _apply_figure_candidate_metadata(data, figure_candidates[0])
        if not sliced_paths:
            _ensure_figure_extracted()
    else:
        _ensure_figure_extracted()

    primary_figure_path = str(data._figure_top or data._figure_image or "").strip()
    figure_gallery, figure_top, figure_section_enabled = _resolve_figure_section_assets(
        sliced_paths,
        primary_figure_path,
    )
    data._figure_gallery = figure_gallery
    data._figure_top = figure_top
    data._figure_assets = _build_figure_assets(
        gallery_paths=figure_gallery,
        figure_candidates=figure_candidates,
        primary_figure_path=figure_top,
        primary_caption=_legacy_primary_display_caption(
            data,
            detected_caption=str(getattr(fig_resp, "caption", "") or "").strip(),
        ),
        fig_resp=fig_resp,
    )
    data._figure_section_enabled = figure_section_enabled
    if data._figure_section_enabled and not figure_gallery and figure_top:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="figure_section_enabled_primary_only",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "primary_figure": figure_top},
            )
        )
    if not data._figure_section_enabled:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="figure_section_disabled_zero_candidates",
                module=logger.name,
                fields={"file_id": runtime.file.file_id},
            )
        )

    return ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=data,
        rank_usage=rank_usage,
        candidate_count=len(cands_resp.candidates),
    )
