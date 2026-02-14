from __future__ import annotations

import hashlib
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.contracts.candidates import Candidate
from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextExtractResponse, PdfTextSampleRequest
from src.contracts.report_store import ReportMetadataGetRequest, ReportMetadataUpsertRequest
from src.contracts.report_models import CropItem, Figure, Quote, ReportPayload
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_contents import PdfContentsDetectionRequest, PdfContentsDetectionResponse
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.services.pdf_service import extract_pdf_text, sample_pdf_text
from src.utils.slugify import slugify
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.files import FileStatRequest, ReadTextRequest, WriteBytesRequest
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefineCandidate,
    CropRefinePageRenderRequest,
    CropRefineRequest,
    CropRequest,
    ExtractCandidatesRequest,
    FigureExtractRequest,
    PreviewRequest,
    RankRequest,
    RenderRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.categories import CategoryAssignment, CategoryMappingLoadRequest, UncategorizedTagsUpdateRequest
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.generators.categorize_generator import categorize_taxonomy
from src.generators.normalize_generator import normalize_report
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.artifact_generator import generate_artifacts
from src.generators.cover_image_generator import generate_cover_images
from src.generators.taxonomy_generator import extract_taxonomy
from src.generators.validation_generator import validate_report as run_validation
from src.services.pdf_service import (
    apply_crop_refine_bbox as apply_crop_refine_bbox_service,
    build_pdf_context,
    collect_candidates as collect_candidates_service,
    crop_regions as crop_regions_service,
    detect_contents_page as detect_contents_page_service,
    extract_best_figure as extract_best_figure_service,
    extract_pdf_info,
    render_page_for_crop_refine as render_page_for_crop_refine_service,
    render_preview as render_preview_service,
)
from src.services.rank_service import rank_candidates as rank_candidates_service, refine_candidate_crops as refine_candidate_crops_service
from src.services.render_service import render_report as render_report_service
from src.services.prompt_service import load_prompt_set, render_prompt
from src.services.file_service import file_stat, read_text, write_bytes
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
    update_uncategorized_tags,
)
from src.services.report_store_service import (
    get_metadata as get_report_metadata,
    upsert_metadata as upsert_report_metadata,
)
from src.services import vector_store_service, state_service, report_analysis_store_service
from src.contracts.state import StateGetRequest, StateRecordRequest
from src.contracts.validation import ValidationIssue, ValidationReport, ValidationRequest
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreCreateRequest,
    VectorStoreMetadata,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUploadFileRequest,
    VectorStoreWaitRequest,
)
from src.utils.logging import child_context, log_event
from src.utils.validation import validate_candidate
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.cache_utils import sha256_json

logger = logging.getLogger("market_lense.report_generator")


@dataclass(frozen=True)
class _VectorStoreIndexingState:
    vector_store_id: Optional[str]
    openai_file_id: Optional[str]
    vector_store_status: Optional[str]
    indexed_at_utc: Optional[str]
    last_error: Optional[str]


@dataclass(frozen=True)
class _TaxonomyCategoryState:
    taxonomy: list[str]
    region: str
    time_period: str
    category_assignment: CategoryAssignment


def _derive_title(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    cleaned = base.strip()
    return cleaned or name


def _select_sample_pages(file_id: str, md5: Optional[str], page_count: int, sample_count: int) -> list[int]:
    if page_count <= 0 or sample_count <= 0:
        return []
    count = min(sample_count, page_count)
    seed_input = f"{file_id}:{md5 or ''}:{page_count}"
    seed = int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    return sorted(rng.sample(range(page_count), count))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _candidate_meta(candidate: Candidate, key: str, default: float = 0.0) -> float:
    meta = candidate.meta if isinstance(candidate.meta, dict) else {}
    return _to_float(meta.get(key), default)


def _candidate_prefilter_reject_reason(candidate: Candidate) -> str:
    area = _candidate_meta(candidate, "area_frac", 0.0)
    if area <= 0.0:
        return "missing_area"
    if candidate.kind == "table":
        rows = _to_int((candidate.meta or {}).get("rows"), 0)
        cols = _to_int((candidate.meta or {}).get("cols"), 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        if rows < 2 or cols < 2:
            return "table_low_structure"
        if rows < 3 and numeric_ratio < 0.08:
            return "table_low_data"
        if area < 0.025 and numeric_ratio < 0.12:
            return "table_too_small"
        return ""
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    if area < 0.035:
        return "chart_too_small"
    if text_ratio > 0.9 and area < 0.12:
        return "chart_text_fragment"
    if not (candidate.caption or "").strip() and area < 0.05 and text_ratio < 0.02:
        return "chart_decorative"
    return ""


def _candidate_prefilter_priority(candidate: Candidate) -> float:
    area = _candidate_meta(candidate, "area_frac", 0.0)
    if candidate.kind == "table":
        rows = _to_int((candidate.meta or {}).get("rows"), 0)
        cols = _to_int((candidate.meta or {}).get("cols"), 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        return area * 100.0 + rows * 2.5 + cols * 1.5 + numeric_ratio * 50.0
    caption_bonus = 12.0 if (candidate.caption or "").strip() else 0.0
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    return area * 100.0 + caption_bonus + max(0.0, (0.6 - text_ratio) * 20.0)


def _candidate_is_obvious_reject(candidate: Candidate) -> tuple[bool, str]:
    reason = _candidate_prefilter_reject_reason(candidate)
    if reason:
        return True, reason
    if candidate.kind == "table":
        rows = _to_int((candidate.meta or {}).get("rows"), 0)
        cols = _to_int((candidate.meta or {}).get("cols"), 0)
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
        rows = _to_int((candidate.meta or {}).get("rows"), 0)
        cols = _to_int((candidate.meta or {}).get("cols"), 0)
        numeric_ratio = _candidate_meta(candidate, "numeric_ratio", 0.0)
        area = _candidate_meta(candidate, "area_frac", 0.0)
        return rows >= 4 and cols >= 3 and numeric_ratio >= 0.15 and area >= 0.05
    area = _candidate_meta(candidate, "area_frac", 0.0)
    text_ratio = _candidate_meta(candidate, "text_ratio", 0.0)
    has_caption = bool((candidate.caption or "").strip())
    return area >= 0.12 and text_ratio <= 0.65 and has_caption


def _rank_threshold_pass(row, settings: IngestSettings) -> tuple[bool, str]:
    if not bool(getattr(row, "keep", True)):
        return False, str(getattr(row, "reject_reason", "") or "model_reject")
    score = _to_int(getattr(row, "score", 0), 0)
    quality = _to_int(getattr(row, "quality_score", score), score)
    insight = _to_int(getattr(row, "insight_score", score), score)
    data_score = _to_int(getattr(row, "data_score", score), score)
    if score < int(settings.rank_min_overall_score):
        return False, "overall_below_threshold"
    if quality < int(settings.rank_min_quality_score):
        return False, "quality_below_threshold"
    if insight < int(settings.rank_min_insight_score):
        return False, "insight_below_threshold"
    if data_score < int(settings.rank_min_data_score):
        return False, "data_below_threshold"
    return True, ""


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
    return sha256_json({
        "schema_version": "1.0",
        "md5": md5,
        "model": model,
        "temperature": temperature,
        "seed": seed,
        "mode": mode,
        "prompt_system_sha256": prompt_system_sha256,
        "prompt_user_sha256": prompt_user_sha256,
    })


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
    return sha256_json({
        "schema_version": "1.0",
        "md5": md5,
        "candidate_id": candidate.id,
        "page": candidate.page,
        "bbox": list(candidate.bbox),
        "meta": candidate.meta or {},
        "caption": candidate.caption or "",
        "preview_text": candidate.preview_text or "",
        "model": model,
        "temperature": temperature,
        "seed": seed,
        "mode": mode,
        "prompt_system_sha256": prompt_system_sha256,
        "prompt_user_sha256": prompt_user_sha256,
    })


def _crop_refine_cache_path(settings: IngestSettings, file_id: str, report_name: str, ctx: RunContext) -> str:
    return report_analysis_store_service.pack_path(
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
    ctx: RunContext,
) -> dict[str, dict]:
    cache_path = _crop_refine_cache_path(settings, file_id, report_name, ctx)
    payload = _read_cache_json(Path(cache_path), ctx)
    if not isinstance(payload, dict):
        return {}
    profile = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else {}
    if str(profile.get("key") or "") != profile_key:
        return {}
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_key = str(row.get("entry_key") or "").strip()
        if not entry_key:
            continue
        out[entry_key] = row
    return out


def _write_crop_refine_cache(
    settings: IngestSettings,
    *,
    file_id: str,
    report_name: str,
    profile: dict,
    entries: dict[str, dict],
    ctx: RunContext,
) -> None:
    rows = []
    for entry_key, payload in entries.items():
        if not isinstance(payload, dict):
            continue
        rows.append({"entry_key": entry_key, **payload})
    rows.sort(key=lambda item: str(item.get("entry_key") or ""))
    report_analysis_store_service.store_pack(
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
            mirror_legacy=settings.mirror_legacy_packs,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:crop_refine_cache_write"),
    )


def _select_refined_candidate_items(
    *,
    ranked_rows: list[Any],
    ranked_candidates: list[Candidate],
    settings: IngestSettings,
    local_pdf_path: str,
    report_name: str,
    file_id: str,
    md5: Optional[str],
    ctx: RunContext,
    pdf_context: Any,
    fallback_model: str,
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
    logger.info(log_event(
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
    ))
    if not thresholded:
        return [], []

    crop_refine_mode = str(getattr(settings, "crop_refine_mode", "adaptive") or "adaptive").strip().lower()
    if crop_refine_mode not in {"adaptive", "always", "off"}:
        crop_refine_mode = "adaptive"
    crop_refine_enabled = bool(getattr(settings, "crop_refine_enabled", True)) and crop_refine_mode != "off"
    selected_max = max(1, int(getattr(settings, "rank_selected_max", 5)))

    crop_refine_prompt_set = None
    crop_refine_system_render = None
    crop_refine_profile: dict[str, Any] = {}
    crop_refine_cache_rows: dict[str, dict] = {}
    if crop_refine_enabled:
        crop_refine_prompt_set = load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace="rank_candidates/crop_refine", reload_if_changed=True),
            ctx,
        )
        logger.info(log_event(
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
        ))
        crop_refine_system_render = render_prompt(
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
            )
    else:
        resolved_crop_refine_model = fallback_model

    page_render_cache: dict[int, Any] = {}
    accepted_items: list[CropItem] = []
    accepted_candidates: list[Candidate] = []
    for row, candidate in thresholded:
        if len(accepted_items) >= selected_max:
            break
        logger.info(log_event(
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
        ))
        reject_now, reject_reason = _candidate_is_obvious_reject(candidate)
        if reject_now:
            logger.info(log_event(
                ctx,
                role="generator",
                event="crop_refine_skipped_deterministic_reject",
                module=logger.name,
                fields={"candidate_id": candidate.id, "reason": reject_reason},
            ))
            logger.info(log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_rejected",
                module=logger.name,
                fields={"candidate_id": candidate.id, "reason": reject_reason},
            ))
            continue
        use_llm = False
        if crop_refine_enabled and crop_refine_mode == "always":
            use_llm = True
        elif crop_refine_enabled and crop_refine_mode == "adaptive":
            if _candidate_is_obvious_pass(candidate):
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_skipped_deterministic_pass",
                    module=logger.name,
                    fields={"candidate_id": candidate.id},
                ))
            else:
                use_llm = True
        refined_bbox = tuple(float(v) for v in candidate.bbox)
        llm_valid = True
        llm_reason = "deterministic_pass"
        if use_llm and crop_refine_prompt_set and crop_refine_system_render:
            if md5:
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
            else:
                entry_key = ""
            cached_row = crop_refine_cache_rows.get(entry_key) if entry_key else None
            if cached_row:
                llm_valid = bool(cached_row.get("is_valid_candidate"))
                llm_reason = str(cached_row.get("reason") or "cache")
                refined_bbox = tuple(cached_row.get("refined_bbox") or list(candidate.bbox))
            else:
                page_render = page_render_cache.get(candidate.page)
                if page_render is None:
                    page_render = render_page_for_crop_refine_service(
                        CropRefinePageRenderRequest(
                            schema_version="1.0",
                            pdf_path=local_pdf_path,
                            out_dir=settings.output_dir,
                            report_name=report_name,
                            page=candidate.page,
                            dpi=int(getattr(settings, "crop_refine_page_dpi", 110)),
                            pdf_context=pdf_context,
                        ),
                        ctx,
                    )
                    page_render_cache[candidate.page] = page_render
                llm_candidate_payload = [{
                    "id": candidate.id,
                    "type": candidate.kind,
                    "page": candidate.page,
                    "bbox": [float(value) for value in candidate.bbox],
                    "caption": (candidate.caption or "")[:400],
                    "preview_text": (candidate.preview_text or "")[:600],
                    "meta": candidate.meta or {},
                }]
                crop_refine_user_render = render_prompt(
                    PromptRenderRequest(
                        schema_version="1.0",
                        template=crop_refine_prompt_set.user,
                        variables={
                            "page_width": page_render.page_width,
                            "page_height": page_render.page_height,
                            "candidates_json": json.dumps(llm_candidate_payload, ensure_ascii=True),
                        },
                    ),
                    ctx,
                )
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_llm_request",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "page": candidate.page},
                ))
                crop_refine_resp = refine_candidate_crops_service(
                    CropRefineRequest(
                        schema_version="1.0",
                        system_prompt=crop_refine_system_render.text,
                        user_prompt=crop_refine_user_render.text,
                        prompt_system_sha256=crop_refine_prompt_set.system.sha256,
                        prompt_user_sha256=crop_refine_prompt_set.user.sha256,
                        model=resolved_crop_refine_model,
                        temperature=float(getattr(settings, "crop_refine_temperature", 0.0)),
                        api_key=settings.openai_api_key,
                        page_image_path=str(Path(settings.output_dir) / page_render.image_path),
                        page=candidate.page,
                        page_width=page_render.page_width,
                        page_height=page_render.page_height,
                        candidates=[
                            CropRefineCandidate(
                                schema_version="1.0",
                                id=candidate.id,
                                type=candidate.kind,
                                page=candidate.page,
                                bbox=candidate.bbox,
                                caption=candidate.caption or "",
                                preview_text=candidate.preview_text or "",
                                meta=candidate.meta or {},
                            ),
                        ],
                        seed=settings.rank_seed,
                        timeout_seconds=float(getattr(settings, "crop_refine_timeout_seconds", settings.rank_timeout_seconds)),
                        cost_ledger_path=settings.cost_ledger_path,
                        cost_daily_path=settings.cost_daily_path,
                        model_pricing=settings.model_pricing,
                    ),
                    ctx,
                )
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_llm_response_raw",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "content": crop_refine_resp.raw_content},
                ))
                decision = None
                for result_item in crop_refine_resp.results:
                    if result_item.id == candidate.id:
                        decision = result_item
                        break
                if decision is None:
                    llm_valid = False
                    llm_reason = "missing_decision"
                    refined_bbox = tuple(float(value) for value in candidate.bbox)
                else:
                    llm_valid = bool(decision.is_valid_candidate)
                    llm_reason = decision.reason or ("valid" if llm_valid else "rejected")
                    refined_bbox = tuple(float(value) for value in decision.refined_bbox)
                if entry_key:
                    crop_refine_cache_rows[entry_key] = {
                        "candidate_id": candidate.id,
                        "is_valid_candidate": llm_valid,
                        "refined_bbox": [float(v) for v in refined_bbox],
                        "reason": llm_reason,
                        "page": candidate.page,
                    }
            if not llm_valid:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="crop_refine_candidate_rejected",
                    module=logger.name,
                    fields={"candidate_id": candidate.id, "reason": llm_reason},
                ))
                continue
        bbox_resp = apply_crop_refine_bbox_service(
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
        logger.info(log_event(
            ctx,
            role="generator",
            event="crop_refine_bbox_applied",
            module=logger.name,
            fields={"candidate_id": candidate.id, "bbox": list(refined_bbox)},
        ))
        width = max(0.0, refined_bbox[2] - refined_bbox[0])
        height = max(0.0, refined_bbox[3] - refined_bbox[1])
        page_render = page_render_cache.get(candidate.page)
        page_area = (page_render.page_width * page_render.page_height) if page_render else 0.0
        area_frac = ((width * height) / page_area) if page_area > 0 else _candidate_meta(candidate, "area_frac", 0.0)
        aspect = (width / height) if height > 0 else 0.0
        if width < 12 or height < 12:
            logger.info(log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_rejected",
                module=logger.name,
                fields={"candidate_id": candidate.id, "reason": "bbox_too_small"},
            ))
            continue
        if area_frac < 0.01:
            logger.info(log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_rejected",
                module=logger.name,
                fields={"candidate_id": candidate.id, "reason": "bbox_area_too_small"},
            ))
            continue
        if aspect < 0.12 or aspect > 8.0:
            logger.info(log_event(
                ctx,
                role="generator",
                event="crop_refine_candidate_rejected",
                module=logger.name,
                fields={"candidate_id": candidate.id, "reason": "bbox_aspect_out_of_range"},
            ))
            continue
        accepted_items.append(CropItem(
            id=candidate.id,
            type=candidate.kind,
            score=float(row.score),
            page=candidate.page,
            bbox=refined_bbox,
        ))
        accepted_candidates.append(candidate)
        logger.info(log_event(
            ctx,
            role="generator",
            event="crop_refine_candidate_accepted",
            module=logger.name,
            fields={"candidate_id": candidate.id, "accepted_count": len(accepted_items)},
        ))
    if crop_refine_profile and md5:
        _write_crop_refine_cache(
            settings,
            file_id=file_id,
            report_name=report_name,
            profile=crop_refine_profile,
            entries=crop_refine_cache_rows,
            ctx=ctx,
        )
    return accepted_items[:selected_max], accepted_candidates[:selected_max]

def _pack_paths(
    output_dir: str,
    report_id: str,
    report_name: str,
    pack_names: list[str],
    ctx: RunContext,
) -> dict[str, str]:
    return {
        name: report_analysis_store_service.pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=output_dir,
                report_id=report_id,
                pack_name=name,
                report_slug=report_name,
            ),
            child_context(ctx, task_id=f"{ctx.task_id}:analysis_pack_path:{name}"),
        ).output_path
        for name in pack_names
    }


def _report_slug(file: DriveFile) -> str:
    return slugify(file.name or file.file_id)


def _cache_dir(settings: IngestSettings, md5: str) -> Path:
    return Path(settings.cache_dir) / "pdf_cache" / md5


def _read_cache_json(path: Path, ctx: RunContext) -> Optional[dict]:
    try:
        resp = read_text(ReadTextRequest(schema_version="1.0", path=str(path)), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(log_event(
            ctx,
            role="generator",
            event="cache_read_failed",
            module=logger.name,
            fields={"path": str(path), "error": exc.message},
        ))
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache_json(path: Path, payload: dict, ctx: RunContext) -> None:
    data = json.dumps(payload, ensure_ascii=True)
    write_bytes(
        WriteBytesRequest(schema_version="1.0", path=str(path), content=data.encode("utf-8")),
        ctx,
    )


def _pdf_info_cache_key(md5: str) -> str:
    return sha256_json({"schema_version": "1.0", "md5": md5})


def _contents_cache_key(md5: str, settings: IngestSettings) -> str:
    return sha256_json({
        "schema_version": "1.0",
        "md5": md5,
        "max_pages": settings.contents_max_pages,
        "min_headings": settings.contents_min_headings,
        "keywords": settings.contents_keywords,
    })


def _text_cache_key(md5: str, settings: IngestSettings) -> str:
    return sha256_json({
        "schema_version": "1.0",
        "md5": md5,
        "max_pages": settings.pdf_text_max_pages,
        "max_chars": settings.pdf_text_max_chars,
    })


def _cache_path(cache_root: Path, prefix: str, cache_key: str) -> Path:
    return cache_root / f"{prefix}_{cache_key}.json"


def _template_sha256(path: Path, ctx: RunContext) -> Optional[str]:
    try:
        resp = read_text(ReadTextRequest(schema_version="1.0", path=str(path)), ctx)
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="template_hash_failed",
            module=logger.name,
            fields={"path": str(path), "error": exc.message},
        ))
        return None
    return hashlib.sha256(resp.content.encode("utf-8")).hexdigest()


def _html_cache_key(md5: str, template_sha256: str, data_sha256: str, preview_png: str, doc_name: str) -> str:
    return sha256_json({
        "schema_version": "1.0",
        "md5": md5,
        "template_sha256": template_sha256,
        "data_sha256": data_sha256,
        "preview_png": preview_png,
        "doc_name": doc_name,
    })


def _base_payload(title: str, contents_page_number: int, contents_heading: str, contents_image: str) -> ReportPayload:
    return ReportPayload(
        tldr="Not available from text",
        title=title,
        insights=["", "", "", "", ""],
        quote=Quote(text="", author="Unknown"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
        publisher="",
        taxonomy=[],
        categories=[],
        region="",
        time_period="",
        contents_page_number=contents_page_number,
        contents_heading=contents_heading,
        _contents_image=contents_image,
    )


def _merge_artifacts_into_payload(payload: ReportPayload, artifacts: dict) -> ReportPayload:
    if not isinstance(artifacts, dict):
        return payload
    summary = artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
    tldr = summary.get("tldr") if isinstance(summary, dict) else None
    exec_summary = summary.get("executive_summary") if isinstance(summary, dict) else None
    if tldr:
        payload.tldr = str(tldr)
    if exec_summary:
        payload.commentary = str(exec_summary)
    insights_final = artifacts.get("insights_final") if isinstance(artifacts.get("insights_final"), list) else []
    if insights_final:
        normalized = []
        for item in insights_final[:5]:
            if isinstance(item, dict):
                normalized.append(str(item.get("text") or ""))
            else:
                normalized.append(str(item))
        while len(normalized) < 5:
            normalized.append("")
        payload.insights = normalized
    quotes_final = artifacts.get("quotes_final") if isinstance(artifacts.get("quotes_final"), list) else []
    if quotes_final:
        first_quote = quotes_final[0] if quotes_final else {}
        if isinstance(first_quote, dict):
            payload.quote = Quote(text=str(first_quote.get("text") or ""), author=str(first_quote.get("speaker") or first_quote.get("author") or "Unknown"))
    return payload


def _resolve_publisher(payload: ReportPayload, pdf_metadata: dict[str, str]) -> str:
    # Publisher is now sourced exclusively from the DocMap evidence pack.
    # Ignore payload-provided values and PDF metadata to avoid inconsistent sources.
    return ""


def _record_state_progress(
    *,
    settings: IngestSettings,
    file_id: str,
    md5: Optional[str],
    ctx: RunContext,
    stage: str,
    vector_store_id: Optional[str] = None,
    vector_store_status: Optional[str] = None,
    indexed_at_utc: Optional[str] = None,
    openai_file_id: Optional[str] = None,
    last_error: Optional[str] = None,
) -> None:
    if not md5:
        return
    try:
        state_service.record(
            StateRecordRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
                md5=md5,
                openai_file_id=openai_file_id or "",
                vector_store_id=vector_store_id,
                vector_store_status=vector_store_status,
                indexed_at_utc=indexed_at_utc,
                last_error=last_error,
            ),
            ctx,
        )
        logger.info(log_event(
            ctx,
            role="generator",
            event="state_progress_recorded",
            module=logger.name,
            fields={
                "file_id": file_id,
                "stage": stage,
                "vector_store_id": vector_store_id or "",
                "vector_store_status": vector_store_status or "",
                "indexed_at_utc": indexed_at_utc or "",
            },
        ))
    except Exception as exc:  # pragma: no cover - best-effort state tracking
        logger.info(log_event(
            ctx,
            role="generator",
            event="state_progress_failed",
            module=logger.name,
            fields={"file_id": file_id, "stage": stage, "error": str(exc)},
        ))


def _is_vector_store_ready(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in {"completed", "ready", "indexed"}


def _start_vector_store_indexing(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    ctx: RunContext,
) -> _VectorStoreIndexingState:
    vector_store_id = None
    openai_file_id = None
    vector_store_status = None
    indexed_at_utc = None
    last_error = None

    logger.info(log_event(
        ctx,
        role="generator",
        event="vector_store_prepare_start",
        module=logger.name,
        fields={"file_id": file.file_id, "analysis_mode": settings.analysis_mode},
    ))
    existing = None
    try:
        existing = state_service.get(
            StateGetRequest(schema_version="1.0", state_db=settings.state_db, file_id=file.file_id),
            ctx,
        )
    except Exception:
        existing = None
    if existing and settings.vector_store_keep and existing.vector_store_id:
        vector_store_id = existing.vector_store_id
        openai_file_id = existing.openai_file_id
        logger.info(log_event(
            ctx,
            role="generator",
            event="vector_store_reuse",
            module=logger.name,
            fields={"file_id": file.file_id, "vector_store_id": vector_store_id},
        ))
        status_resp = vector_store_service.get_vector_store_status(
            VectorStoreStatusRequest(schema_version="1.0", vector_store_id=vector_store_id),
            ctx=ctx,
        )
        vector_store_status = status_resp.status
        indexed_at_utc = status_resp.indexed_at_utc
        last_error = status_resp.last_error
    if not vector_store_id:
        vs_resp = vector_store_service.create_vector_store(
            VectorStoreCreateRequest(
                schema_version="1.0",
                name=file.file_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=file.file_id,
                    report_name=file.name or file.file_id,
                    taxonomy=[],
                    categories=[],
                    region="",
                    time_period="",
                ),
            ),
            ctx,
        )
        vector_store_id = vs_resp.vector_store_id
        logger.info(log_event(
            ctx,
            role="generator",
            event="vector_store_created",
            module=logger.name,
            fields={"file_id": file.file_id, "vector_store_id": vector_store_id},
        ))
        upload_resp = vector_store_service.upload_file(
            VectorStoreUploadFileRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                file_path=local_pdf_path,
            ),
            ctx,
        )
        openai_file_id = upload_resp.openai_file_id
        vector_store_service.attach_file(
            VectorStoreAttachFileRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                openai_file_id=upload_resp.openai_file_id,
            ),
            ctx,
        )
        vector_store_status = "indexing"

    logger.info(log_event(
        ctx,
        role="generator",
        event="vector_store_indexing_started" if not _is_vector_store_ready(vector_store_status) else "vector_store_already_indexed",
        module=logger.name,
        fields={
            "file_id": file.file_id,
            "vector_store_id": vector_store_id,
            "status": vector_store_status or "",
            "indexed_at_utc": indexed_at_utc or "",
        },
    ))
    return _VectorStoreIndexingState(
        vector_store_id=vector_store_id,
        openai_file_id=openai_file_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        last_error=last_error,
    )


def _await_vector_store_indexing(
    state: _VectorStoreIndexingState,
    settings: IngestSettings,
    ctx: RunContext,
) -> _VectorStoreIndexingState:
    vector_store_id = state.vector_store_id
    if not vector_store_id:
        raise AppError(
            code="vector_store_missing",
            message="vector_store_id is required before awaiting indexing",
            retryable=False,
        )
    if _is_vector_store_ready(state.vector_store_status):
        logger.info(log_event(
            ctx,
            role="generator",
            event="vector_store_wait_skipped",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "status": state.vector_store_status or "",
                "indexed_at_utc": state.indexed_at_utc or "",
            },
        ))
        logger.info(log_event(
            ctx,
            role="generator",
            event="vector_store_ready",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "status": state.vector_store_status,
                "indexed_at_utc": state.indexed_at_utc or "",
            },
        ))
        return state

    logger.info(log_event(
        ctx,
        role="generator",
        event="vector_store_wait_start",
        module=logger.name,
        fields={"vector_store_id": vector_store_id, "status": state.vector_store_status or ""},
    ))
    status_resp = vector_store_service.wait_until_indexed(
        VectorStoreWaitRequest(
            schema_version="1.0",
            vector_store_id=vector_store_id,
            timeout_s=int(settings.openai_timeout_seconds),
            poll_interval_s=5,
        ),
        ctx=ctx,
    )
    ready_state = _VectorStoreIndexingState(
        vector_store_id=vector_store_id,
        openai_file_id=state.openai_file_id,
        vector_store_status=status_resp.status,
        indexed_at_utc=status_resp.indexed_at_utc,
        last_error=status_resp.last_error,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="vector_store_ready",
        module=logger.name,
        fields={
            "vector_store_id": ready_state.vector_store_id,
            "status": ready_state.vector_store_status,
            "indexed_at_utc": ready_state.indexed_at_utc or "",
        },
    ))
    return ready_state


def _ensure_vector_store(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    ctx: RunContext,
):
    indexing_state = _start_vector_store_indexing(file, local_pdf_path, settings, ctx)
    ready_state = _await_vector_store_indexing(indexing_state, settings, ctx)
    return (
        ready_state.vector_store_id,
        ready_state.openai_file_id,
        ready_state.vector_store_status,
        ready_state.indexed_at_utc,
        ready_state.last_error,
    )


def _resolve_taxonomy_and_categories(
    *,
    file: DriveFile,
    report_title: str,
    vector_store_id: Optional[str],
    settings: IngestSettings,
    mode_ctx: RunContext,
) -> _TaxonomyCategoryState:
    taxonomy_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:taxonomy")
    taxonomy_resp = extract_taxonomy(
        TaxonomyExtractRequest(
            schema_version="1.0",
            report_id=file.file_id,
            report_title=report_title,
            vector_store_id=vector_store_id or "",
            settings=settings,
        ),
        taxonomy_ctx,
    )
    mappings_resp = load_category_mappings(
        CategoryMappingLoadRequest(schema_version="1.0", path=settings.category_mapping_path, reload_if_changed=True),
        taxonomy_ctx,
    )
    category_assignment = categorize_taxonomy(taxonomy_resp.taxonomy, mappings_resp, taxonomy_ctx)
    if category_assignment.unmapped_tags or mappings_resp.mappings.uncategorized:
        update_uncategorized_tags(
            UncategorizedTagsUpdateRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
                report_title=report_title,
                tags=category_assignment.unmapped_tags,
            ),
            taxonomy_ctx,
        )
    if vector_store_id:
        vector_store_service.update_metadata(
            VectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=file.file_id,
                    report_name=report_title,
                    taxonomy=taxonomy_resp.taxonomy,
                    categories=category_assignment.categories,
                    region=taxonomy_resp.region,
                    time_period=taxonomy_resp.time_period,
                ),
            ),
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:metadata"),
        )
    return _TaxonomyCategoryState(
        taxonomy=taxonomy_resp.taxonomy,
        region=taxonomy_resp.region,
        time_period=taxonomy_resp.time_period,
        category_assignment=category_assignment,
    )


def generate_report(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
) -> IngestOutcome:
    report_worker_limit = getattr(settings, "report_worker_limit", 1)
    try:
        report_worker_limit = int(report_worker_limit)
    except (TypeError, ValueError):
        report_worker_limit = 1
    if report_worker_limit < 1:
        report_worker_limit = 1
    parallel_within_file = report_worker_limit > 1

    pdf_context = None
    analysis_mode = "vector_store"
    analysis_modes = [analysis_mode]
    file_name = file.name or file.file_id
    logger.info(log_event(
        ctx,
        role="generator",
        event="report_generate_start",
        module=logger.name,
        fields={"file_id": file.file_id, "name": file_name, "modes": analysis_modes},
    ))
    report_name = _report_slug(file)
    cache_root = _cache_dir(settings, md5) if md5 else None
    contents_page_number = 0
    contents_image = ""
    contents_heading = ""

    logger.info(log_event(
        ctx,
        role="generator",
        event="report_parallel_config",
        module=logger.name,
        fields={"report_worker_limit": report_worker_limit, "parallel_within_file": parallel_within_file},
    ))

    if not parallel_within_file:
        try:
            ctx_pdf = child_context(ctx, task_id=f"{ctx.task_id}:pdf_context")
            pdf_ctx_resp = build_pdf_context(
                PdfContextBuildRequest(schema_version="1.0", path=local_pdf_path),
                ctx_pdf,
            )
            pdf_context = pdf_ctx_resp.context
            if pdf_ctx_resp.fitz_error or pdf_ctx_resp.pypdf_error:
                logger.info(log_event(
                    ctx_pdf,
                    role="generator",
                    event="pdf_context_partial",
                    module=logger.name,
                    fields={
                        "fitz_ready": pdf_ctx_resp.context.fitz_doc is not None,
                        "pypdf_ready": pdf_ctx_resp.context.pypdf_reader is not None,
                        "fitz_error": pdf_ctx_resp.fitz_error or "",
                        "pypdf_error": pdf_ctx_resp.pypdf_error or "",
                    },
                ))
        except Exception as exc:
            logger.info(log_event(
                ctx,
                role="generator",
                event="pdf_context_unavailable",
                module=logger.name,
                fields={"path": local_pdf_path, "error": str(exc)},
            ))
            pdf_context = None

    pdf_context_for_tasks = pdf_context if not parallel_within_file else None

    def _load_pdf_info_task() -> tuple[PdfInfoResponse, bool]:
        info_ctx = child_context(ctx, task_id=f"{ctx.task_id}:pdf_info")
        info_resp = None
        info_cache_hit = False
        info_cache_key = ""
        info_cache_path = None
        if md5 and cache_root is not None:
            info_cache_key = _pdf_info_cache_key(md5)
            info_cache_path = _cache_path(cache_root, "pdf_info", info_cache_key)
            cached = _read_cache_json(info_cache_path, info_ctx)
            if cached and cached.get("key") == info_cache_key:
                page_count = int(cached.get("page_count") or 0)
                metadata = cached.get("metadata") if isinstance(cached.get("metadata"), dict) else {}
                info_resp = PdfInfoResponse(
                    schema_version="1.0",
                    path=local_pdf_path,
                    page_count=page_count,
                    metadata=metadata,
                )
                info_cache_hit = True
                logger.info(log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_hit",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(info_cache_path)},
                ))
            else:
                logger.info(log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_miss",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(info_cache_path) if info_cache_path else ""},
                ))
        if info_resp is None:
            info_resp = extract_pdf_info(
                PdfInfoRequest(schema_version="1.0", path=local_pdf_path, pdf_context=pdf_context_for_tasks),
                info_ctx,
            )
            if md5 and cache_root is not None and info_cache_path is not None:
                _write_cache_json(
                    info_cache_path,
                    {
                        "schema_version": "1.0",
                        "key": info_cache_key,
                        "page_count": info_resp.page_count,
                        "metadata": info_resp.metadata,
                    },
                    info_ctx,
                )
                logger.info(log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_written",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(info_cache_path)},
                ))
        logger.info(log_event(
            info_ctx,
            role="generator",
            event="pdf_info_loaded",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "page_count": info_resp.page_count,
                "metadata_keys": list(info_resp.metadata.keys()),
                "cache_hit": info_cache_hit,
            },
        ))
        return info_resp, info_cache_hit

    def _load_contents_task() -> tuple[int, str, str, bool]:
        local_contents_page = 0
        local_contents_heading = ""
        local_contents_image = ""
        contents_ctx = child_context(ctx, task_id=f"{ctx.task_id}:contents")
        try:
            contents_resp = None
            contents_cache_hit = False
            contents_cache_key = ""
            contents_cache_path = None
            if md5 and cache_root is not None:
                contents_cache_key = _contents_cache_key(md5, settings)
                contents_cache_path = _cache_path(cache_root, "contents", contents_cache_key)
                cached = _read_cache_json(contents_cache_path, contents_ctx)
                if cached and cached.get("key") == contents_cache_key:
                    contents_resp = PdfContentsDetectionResponse(
                        schema_version="1.0",
                        path=local_pdf_path,
                        has_contents=bool(cached.get("has_contents")),
                        page_index=int(cached.get("page_index") or -1),
                        page_number=int(cached.get("page_number") or 0),
                        heading=str(cached.get("heading") or ""),
                        confidence=float(cached.get("confidence") or 0.0),
                    )
                    contents_cache_hit = True
                    logger.info(log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_hit",
                        module=logger.name,
                        fields={"file_id": file.file_id, "cache_path": str(contents_cache_path)},
                    ))
                else:
                    logger.info(log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_miss",
                        module=logger.name,
                        fields={"file_id": file.file_id, "cache_path": str(contents_cache_path) if contents_cache_path else ""},
                    ))
            if contents_resp is None:
                contents_resp = detect_contents_page_service(
                    PdfContentsDetectionRequest(
                        schema_version="1.0",
                        path=local_pdf_path,
                        max_pages=settings.contents_max_pages,
                        min_headings=settings.contents_min_headings,
                        keywords=settings.contents_keywords,
                        pdf_context=pdf_context_for_tasks,
                    ),
                    contents_ctx,
                )
                if md5 and cache_root is not None and contents_cache_path is not None:
                    _write_cache_json(
                        contents_cache_path,
                        {
                            "schema_version": "1.0",
                            "key": contents_cache_key,
                            "has_contents": contents_resp.has_contents,
                            "page_index": contents_resp.page_index,
                            "page_number": contents_resp.page_number,
                            "heading": contents_resp.heading,
                            "confidence": contents_resp.confidence,
                        },
                        contents_ctx,
                    )
                    logger.info(log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_written",
                        module=logger.name,
                        fields={"file_id": file.file_id, "cache_path": str(contents_cache_path)},
                    ))
            if contents_resp.has_contents:
                local_contents_page = contents_resp.page_number
                local_contents_heading = contents_resp.heading or ""
                if settings.contents_preview_enabled:
                    contents_preview = render_preview_service(
                        PreviewRequest(
                            schema_version="1.1",
                            pdf_path=local_pdf_path,
                            out_dir=settings.output_dir,
                            report_name=report_name,
                            page_number=max(contents_resp.page_index, 0),
                            variant="contents",
                            dpi=settings.contents_preview_dpi,
                            pdf_context=pdf_context_for_tasks,
                        ),
                        ctx,
                    )
                    if contents_preview.image_path:
                        local_contents_image = contents_preview.image_path
                else:
                    logger.info(log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_preview_skipped",
                        module=logger.name,
                        fields={"file_id": file.file_id, "reason": "preview_disabled"},
                    ))
            logger.info(log_event(
                contents_ctx,
                role="generator",
                event="contents_detection_result",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "has_contents": contents_resp.has_contents,
                    "page_number": local_contents_page,
                    "image_path": local_contents_image or "",
                    "cache_hit": contents_cache_hit,
                },
            ))
            return local_contents_page, local_contents_heading, local_contents_image, contents_cache_hit
        except Exception as exc:
            logger.info(log_event(
                ctx,
                role="generator",
                event="contents_detection_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": str(exc)},
            ))
            return local_contents_page, local_contents_heading, local_contents_image, False

    text_ctx = child_context(ctx, task_id=f"{ctx.task_id}:text")

    def _load_text_task() -> tuple[PdfTextExtractResponse, bool]:
        text_resp = None
        text_cache_hit = False
        text_cache_key = ""
        text_cache_path = None
        if md5 and cache_root is not None:
            text_cache_key = _text_cache_key(md5, settings)
            text_cache_path = _cache_path(cache_root, "text", text_cache_key)
            cached = _read_cache_json(text_cache_path, text_ctx)
            if cached and cached.get("key") == text_cache_key:
                text_resp = PdfTextExtractResponse(
                    schema_version="1.0",
                    text=str(cached.get("text") or ""),
                    pages_extracted=int(cached.get("pages_extracted") or 0),
                    char_count=int(cached.get("char_count") or 0),
                    text_density=float(cached.get("text_density") or 0.0),
                )
                text_cache_hit = True
                logger.info(log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_hit",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(text_cache_path)},
                ))
            else:
                logger.info(log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_miss",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(text_cache_path) if text_cache_path else ""},
                ))
        if text_resp is None:
            text_resp = extract_pdf_text(
                PdfTextExtractRequest(
                    schema_version="1.0",
                    path=local_pdf_path,
                    max_pages=settings.pdf_text_max_pages,
                    max_chars=settings.pdf_text_max_chars,
                    pdf_context=pdf_context_for_tasks,
                ),
                text_ctx,
            )
            if md5 and cache_root is not None and text_cache_path is not None:
                _write_cache_json(
                    text_cache_path,
                    {
                        "schema_version": "1.0",
                        "key": text_cache_key,
                        "text": text_resp.text,
                        "pages_extracted": text_resp.pages_extracted,
                        "char_count": text_resp.char_count,
                        "text_density": text_resp.text_density,
                    },
                    text_ctx,
                )
                logger.info(log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_written",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(text_cache_path)},
                ))
        return text_resp, text_cache_hit

    if parallel_within_file:
        with ThreadPoolExecutor(max_workers=report_worker_limit) as executor:
            info_future = executor.submit(_load_pdf_info_task)
            contents_future = executor.submit(_load_contents_task)
            text_future = executor.submit(_load_text_task)
            info_resp, info_cache_hit = info_future.result()
            contents_page_number, contents_heading, contents_image, contents_cache_hit = contents_future.result()
            text_resp, text_cache_hit = text_future.result()
    else:
        info_resp, info_cache_hit = _load_pdf_info_task()
        contents_page_number, contents_heading, contents_image, contents_cache_hit = _load_contents_task()
        text_resp, text_cache_hit = _load_text_task()
    text_status = {
        "schema_version": "1.0",
        "text_density": float(text_resp.text_density or 0.0),
        "density_threshold": float(getattr(settings, "pdf_text_min_density", 0.0)),
        "pages_sampled": text_resp.pages_extracted,
        "char_count": text_resp.char_count,
        "not_available": False,
        "reason": "",
    }
    if text_status["density_threshold"] and text_status["text_density"] < text_status["density_threshold"]:
        text_status["not_available"] = True
        text_status["reason"] = "text_density_below_threshold"
    logger.info(log_event(
        text_ctx,
        role="generator",
        event="text_density_evaluated",
        module=logger.name,
        fields={"density": text_status["text_density"], "threshold": text_status["density_threshold"], "pages": text_status["pages_sampled"], "char_count": text_status["char_count"], "not_available": text_status["not_available"], "cache_hit": text_cache_hit},
    ))
    sample_ctx = child_context(ctx, task_id=f"{ctx.task_id}:text_sample")
    sample_indices = _select_sample_pages(
        file_id=file.file_id,
        md5=md5,
        page_count=info_resp.page_count,
        sample_count=settings.pdf_text_sample_pages,
    )
    text_validation_status = "pass"
    text_validation_reason = ""
    text_validation_pages: list[int] = [idx + 1 for idx in sample_indices]
    if not sample_indices:
        text_validation_status = "fail"
        text_validation_reason = "no_pages_to_sample"
        logger.info(log_event(
            sample_ctx,
            role="generator",
            event="text_extractability_failed",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "reason": text_validation_reason,
                "page_count": info_resp.page_count,
                "sample_pages": text_validation_pages,
            },
        ))
        if pdf_context is not None:
            pdf_context.close()
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file_name,
            md5=md5,
            html_path=None,
            status="error",
            error="pdf_text_unextractable",
            text_validation_status=text_validation_status,
            text_validation_reason=text_validation_reason,
            text_validation_pages=text_validation_pages,
        )
    sample_resp = sample_pdf_text(
        PdfTextSampleRequest(
            schema_version="1.0",
            path=local_pdf_path,
            page_indices=sample_indices,
            pdf_context=pdf_context,
        ),
        sample_ctx,
    )
    sample_chars = {sample.page_number: sample.char_count for sample in sample_resp.samples}
    logger.info(log_event(
        sample_ctx,
        role="generator",
        event="text_extractability_checked",
        module=logger.name,
        fields={
            "file_id": file.file_id,
            "sample_pages": text_validation_pages,
            "any_text": sample_resp.any_text,
            "char_counts": sample_chars,
        },
    ))
    if not sample_resp.any_text:
        text_validation_status = "fail"
        text_validation_reason = "no_text_in_sampled_pages"
        logger.info(log_event(
            sample_ctx,
            role="generator",
            event="text_extractability_failed",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "reason": text_validation_reason,
                "sample_pages": text_validation_pages,
                "char_counts": sample_chars,
            },
        ))
        if pdf_context is not None:
            pdf_context.close()
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file_name,
            md5=md5,
            html_path=None,
            status="error",
            error="pdf_text_unextractable",
            text_validation_status=text_validation_status,
            text_validation_reason=text_validation_reason,
            text_validation_pages=text_validation_pages,
        )
    report_title = _derive_title(file_name)
    data = _base_payload(report_title, contents_page_number, contents_heading, contents_image)
    data._text_density = text_status["text_density"]
    data._text_pages_sampled = text_status["pages_sampled"]
    data._text_char_count = text_status["char_count"]
    data._text_not_available = text_status["not_available"]
    data.publisher = _resolve_publisher(data, info_resp.metadata)
    logger.info(log_event(
        ctx,
        role="generator",
        event="publisher_resolved",
        module=logger.name,
        fields={"file_id": file.file_id, "publisher": data.publisher},
    ))

    mode_ctx = child_context(ctx, task_id=f"{ctx.task_id}:vector_store")
    vector_state = _start_vector_store_indexing(
        file,
        local_pdf_path,
        settings,
        mode_ctx,
    )
    vector_store_id = vector_state.vector_store_id
    openai_file_id = vector_state.openai_file_id
    vector_store_status = vector_state.vector_store_status
    indexed_at_utc = vector_state.indexed_at_utc
    last_error = vector_state.last_error
    if not _is_vector_store_ready(vector_store_status):
        _record_state_progress(
            settings=settings,
            file_id=file.file_id,
            md5=md5,
            ctx=mode_ctx,
            stage="vector_store_indexing",
            vector_store_id=vector_store_id,
            vector_store_status=vector_store_status or "indexing",
            indexed_at_utc=indexed_at_utc,
            openai_file_id=openai_file_id,
            last_error=last_error,
        )

    def _extract_figure_task():
        return extract_best_figure_service(
            FigureExtractRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                pdf_context=pdf_context_for_tasks,
            ),
            ctx,
        )

    def _extract_candidates_task():
        return collect_candidates_service(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                pdf_context=pdf_context_for_tasks,
            ),
            ctx,
        )

    if parallel_within_file:
        with ThreadPoolExecutor(max_workers=report_worker_limit) as executor:
            fig_future = executor.submit(_extract_figure_task)
            cands_future = executor.submit(_extract_candidates_task)
            fig_resp = fig_future.result()
            cands_resp = cands_future.result()
    else:
        fig_resp = _extract_figure_task()
        cands_resp = _extract_candidates_task()
    if fig_resp.image_path:
        data._figure_image = fig_resp.image_path
        if fig_resp.caption and not (data.figure.evidence or "").strip():
            data.figure.evidence = fig_resp.caption

    ranked = []
    rank_usage = None
    sliced_paths = []
    candidate_paths = []
    data._figure_section_enabled = False
    if cands_resp.candidates:
        for cand in cands_resp.candidates:
            validate_candidate(cand)
        logger.info(log_event(
            ctx,
            role="generator",
            event="candidate_validation_complete",
            module=logger.name,
            fields={"count": len(cands_resp.candidates)},
        ))
        prefiltered_candidates: list[Candidate] = []
        prefilter_reasons: dict[str, int] = {}
        for cand in cands_resp.candidates:
            reason = _candidate_prefilter_reject_reason(cand)
            if reason:
                prefilter_reasons[reason] = int(prefilter_reasons.get(reason, 0)) + 1
                continue
            prefiltered_candidates.append(cand)
        prefiltered_candidates = sorted(
            prefiltered_candidates,
            key=lambda candidate: _candidate_prefilter_priority(candidate),
            reverse=True,
        )
        if settings.rank_max_candidates > 0:
            prefiltered_candidates = prefiltered_candidates[: int(settings.rank_max_candidates)]
        logger.info(log_event(
            ctx,
            role="generator",
            event="candidate_prefilter_complete",
            module=logger.name,
            fields={
                "raw_count": len(cands_resp.candidates),
                "kept_count": len(prefiltered_candidates),
                "rejected_count": sum(prefilter_reasons.values()),
                "reasons": prefilter_reasons,
                "rank_max_candidates": settings.rank_max_candidates,
            },
        ))
        all_items = [
            CropItem(
                id=c.id,
                type=c.kind,
                score=0.0,
                page=c.page,
                bbox=c.bbox,
            )
            for c in cands_resp.candidates
        ]
        if all_items:
            logger.info(log_event(
                ctx,
                role="generator",
                event="candidate_crops_start",
                module=logger.name,
                fields={"count": len(all_items), "subdir": "candidates"},
            ))
            try:
                candidate_crop_resp = crop_regions_service(
                    CropRequest(
                        schema_version="1.0",
                        pdf_path=local_pdf_path,
                        out_dir=settings.output_dir,
                        report_name=report_name,
                        subdir="candidates",
                        items=all_items,
                        pdf_context=pdf_context,
                    ),
                    ctx,
                )
                candidate_paths = candidate_crop_resp.paths
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="candidate_crops_complete",
                    module=logger.name,
                    fields={"count": len(candidate_paths), "subdir": "candidates"},
                ))
            except Exception as exc:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="candidate_crops_failed",
                    module=logger.name,
                    fields={"error": str(exc), "subdir": "candidates"},
                ))
        rank_model = settings.rank_model or settings.openai_model
        resolved_rank_model = resolve_model("rank_candidates", getattr(settings, "openai_models", {}), rank_model)
        rank_usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        ranked = []
        if prefiltered_candidates:
            rows = [{
                "id": c.id,
                "type": c.kind,
                "page": c.page,
                "meta": c.meta or {},
                "title_or_caption": (c.caption or "")[:300],
                "table_preview": c.preview_text[:400] if c.kind == "table" else "",
            } for c in prefiltered_candidates]
            candidates_json = json.dumps(rows, ensure_ascii=True)
            rank_prompt_set = load_prompt_set(
                PromptLoadRequest(schema_version="1.0", namespace="rank_candidates", reload_if_changed=True),
                ctx,
            )
            logger.info(log_event(
                ctx,
                role="generator",
                event="prompt_selected",
                module=logger.name,
                fields={
                    "namespace": "rank_candidates",
                    "system_path": rank_prompt_set.system.path,
                    "system_sha256": rank_prompt_set.system.sha256,
                    "user_path": rank_prompt_set.user.path,
                    "user_sha256": rank_prompt_set.user.sha256,
                },
            ))
            rank_system_render = render_prompt(
                PromptRenderRequest(
                    schema_version="1.0",
                    template=rank_prompt_set.system,
                    variables={},
                ),
                ctx,
            )
            rank_user_render = render_prompt(
                PromptRenderRequest(
                    schema_version="1.0",
                    template=rank_prompt_set.user,
                    variables={"candidates_json": candidates_json},
                ),
                ctx,
            )
            logger.info(log_event(
                ctx,
                role="generator",
                event="prompt_rendered",
                module=logger.name,
                fields={
                    "system_prompt": rank_system_render.text,
                    "user_prompt": rank_user_render.text,
                },
            ))
            logger.info(log_event(
                ctx,
                role="generator",
                event="rank_request_config",
                module=logger.name,
                fields={
                    "model": resolved_rank_model,
                    "temperature": settings.rank_temperature,
                    "seed": settings.rank_seed,
                    "candidate_count": len(prefiltered_candidates),
                },
            ))
            try:
                ranked_resp = rank_candidates_service(
                    RankRequest(
                        schema_version="1.0",
                        system_prompt=rank_system_render.text,
                        user_prompt=rank_user_render.text,
                        prompt_system_sha256=rank_prompt_set.system.sha256,
                        prompt_user_sha256=rank_prompt_set.user.sha256,
                        model=resolved_rank_model,
                        temperature=settings.rank_temperature,
                        api_key=settings.openai_api_key,
                        seed=settings.rank_seed,
                        candidate_count=len(prefiltered_candidates),
                        timeout_seconds=settings.rank_timeout_seconds,
                        cost_ledger_path=settings.cost_ledger_path,
                        cost_daily_path=settings.cost_daily_path,
                        model_pricing=settings.model_pricing,
                    ),
                    ctx,
                )
                ranked = ranked_resp.results
                rank_usage = {
                    "prompt_tokens": ranked_resp.prompt_tokens,
                    "completion_tokens": ranked_resp.completion_tokens,
                    "total_tokens": ranked_resp.total_tokens,
                }
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="rank_raw_response",
                    module=logger.name,
                    fields={"request_id": ranked_resp.request_id or "", "content": ranked_resp.raw_content},
                ))
            except Exception as exc:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="rank_failed",
                    module=logger.name,
                    fields={"file_id": file.file_id, "error": str(exc)},
                ))
                ranked = []
        else:
            logger.info(log_event(
                ctx,
                role="generator",
                event="rank_skipped_no_prefilter_candidates",
                module=logger.name,
                fields={"file_id": file.file_id},
            ))

        selected_items, selected_candidates = _select_refined_candidate_items(
            ranked_rows=ranked,
            ranked_candidates=prefiltered_candidates,
            settings=settings,
            local_pdf_path=local_pdf_path,
            report_name=report_name,
            file_id=file.file_id,
            md5=md5,
            ctx=ctx,
            pdf_context=pdf_context,
            fallback_model=resolved_rank_model,
        )
        if selected_items:
            crop_resp = crop_regions_service(
                CropRequest(
                    schema_version="1.0",
                    pdf_path=local_pdf_path,
                    out_dir=settings.output_dir,
                    report_name=report_name,
                    items=selected_items,
                    mode="figure_strict",
                    pdf_context=pdf_context,
                ),
                ctx,
            )
            sliced_paths = crop_resp.paths
        if selected_candidates:
            top_cand = selected_candidates[0]
            caption = (top_cand.caption or "").strip()
            preview = (top_cand.preview_text or "").strip()
            derived_title = caption or (preview[:140] if preview else "")
            if derived_title:
                data.figure.title = derived_title
            if caption or preview:
                data.figure.evidence = caption or preview

    if sliced_paths:
        data._figure_gallery = sliced_paths
        data._figure_top = sliced_paths[0]
        data._figure_section_enabled = True
    else:
        data._figure_gallery = []
        data._figure_top = ""
        data._figure_section_enabled = False
        logger.info(log_event(
            ctx,
            role="generator",
            event="figure_section_disabled_zero_candidates",
            module=logger.name,
            fields={"file_id": file.file_id},
        ))

    preview_ctx = child_context(ctx, task_id=f"{ctx.task_id}:preview")
    preview_resp = render_preview_service(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=local_pdf_path,
            out_dir=settings.output_dir,
            report_name=report_name,
            pdf_context=pdf_context,
        ),
        preview_ctx,
    )

    vector_state = _await_vector_store_indexing(vector_state, settings, mode_ctx)
    vector_store_id = vector_state.vector_store_id
    openai_file_id = vector_state.openai_file_id
    vector_store_status = vector_state.vector_store_status
    indexed_at_utc = vector_state.indexed_at_utc
    last_error = vector_state.last_error
    _record_state_progress(
        settings=settings,
        file_id=file.file_id,
        md5=md5,
        ctx=mode_ctx,
        stage="vector_store_ready",
        vector_store_id=vector_store_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        openai_file_id=openai_file_id,
        last_error=last_error,
    )

    data.contents_page_number = contents_page_number
    data.contents_heading = contents_heading
    data._contents_image = contents_image
    evidence_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:evidence")
    taxonomy_state: _TaxonomyCategoryState
    evidence_error: Optional[Exception] = None
    packs: dict[str, dict] = {}
    if parallel_within_file:
        logger.info(log_event(
            mode_ctx,
            role="generator",
            event="post_vector_store_parallel_start",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "tasks": ["taxonomy_categories", "evidence_packs"],
                "max_workers": min(report_worker_limit, 2),
            },
        ))
        with ThreadPoolExecutor(max_workers=min(report_worker_limit, 2)) as executor:
            taxonomy_future = executor.submit(
                _resolve_taxonomy_and_categories,
                file=file,
                report_title=report_title,
                vector_store_id=vector_store_id,
                settings=settings,
                mode_ctx=mode_ctx,
            )
            evidence_future = executor.submit(
                generate_evidence_packs,
                report_id=file.file_id,
                report_name=report_name,
                vector_store_id=vector_store_id,
                settings=settings,
                ctx=evidence_ctx,
                md5=md5,
            )
            taxonomy_state = taxonomy_future.result()
            try:
                packs = evidence_future.result()
            except Exception as exc:
                evidence_error = exc
        logger.info(log_event(
            mode_ctx,
            role="generator",
            event="post_vector_store_parallel_complete",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "tasks": ["taxonomy_categories", "evidence_packs"],
                "evidence_failed": evidence_error is not None,
            },
        ))
    else:
        taxonomy_state = _resolve_taxonomy_and_categories(
            file=file,
            report_title=report_title,
            vector_store_id=vector_store_id,
            settings=settings,
            mode_ctx=mode_ctx,
        )
    data.taxonomy = taxonomy_state.taxonomy
    data.region = taxonomy_state.region
    data.time_period = taxonomy_state.time_period
    category_assignment = taxonomy_state.category_assignment
    data.categories = category_assignment.categories
    base_payload = normalize_report(data, ctx)

    mode_data = deepcopy(base_payload)
    mode_evidence_packs: dict[str, dict] = {}
    mode_evidence_paths: dict[str, str] = {}
    validation_report: ValidationReport | None = None
    artifacts_payload: dict | None = None
    try:
        if not parallel_within_file:
            packs = generate_evidence_packs(
                report_id=file.file_id,
                report_name=report_name,
                vector_store_id=vector_store_id,
                settings=settings,
                ctx=evidence_ctx,
                md5=md5,
            )
        elif evidence_error is not None:
            raise evidence_error
    except AppError as exc:
        if exc.code == "doc_map_empty":
            doc_map_summary = exc.context if isinstance(exc.context, dict) else None
            logger.info(log_event(
                mode_ctx,
                role="generator",
                event="doc_map_validation_halt",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "code": exc.code,
                    "message": exc.message,
                    "has_content": doc_map_summary.get("has_content") if doc_map_summary else None,
                    "sections_count": doc_map_summary.get("sections_count") if doc_map_summary else None,
                    "title_present": doc_map_summary.get("title_present") if doc_map_summary else None,
                    "doc_id_present": doc_map_summary.get("doc_id_present") if doc_map_summary else None,
                    "summary_present": doc_map_summary.get("summary_present") if doc_map_summary else None,
                    "not_found_reason": doc_map_summary.get("not_found_reason") if doc_map_summary else "",
                },
            ))
            if pdf_context is not None:
                pdf_context.close()
            return IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file_name,
                md5=md5,
                html_path=None,
                status="error",
                error=exc.message or exc.code,
                vector_store_id=vector_store_id,
                vector_store_status=vector_store_status,
                indexed_at_utc=indexed_at_utc,
                openai_file_id=openai_file_id,
                vector_store_last_error=last_error,
                text_validation_status=text_validation_status,
                text_validation_reason=text_validation_reason,
                text_validation_pages=text_validation_pages,
                doc_map_summary=doc_map_summary,
            )
        raise
    mode_evidence_packs = packs
    pack_names = list(packs.keys())
    mode_evidence_paths = _pack_paths(settings.output_dir, file.file_id, report_name, pack_names, mode_ctx)
    mode_data._vector_store_id = vector_store_id or ""
    mode_data._evidence_packs = mode_evidence_paths
    logger.info(log_event(
        mode_ctx,
        role="generator",
        event="evidence_packs_ready",
        module=logger.name,
        fields={"file_id": file.file_id, "vector_store_id": vector_store_id, "pack_count": len(mode_evidence_paths)},
    ))
    _record_state_progress(
        settings=settings,
        file_id=file.file_id,
        md5=md5,
        ctx=mode_ctx,
        stage="evidence_packs",
        vector_store_id=vector_store_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        openai_file_id=openai_file_id,
        last_error=last_error,
    )
    doc_map_pack = packs.get("doc_map", {})
    if isinstance(doc_map_pack, dict):
        doc_map_title = str(doc_map_pack.get("title") or "").strip()
        if doc_map_title:
            data.title = doc_map_title
        doc_map_publisher = str(doc_map_pack.get("publisher") or "").strip()
        if doc_map_publisher and not data.publisher:
            data.publisher = doc_map_publisher
        if doc_map_title or doc_map_publisher:
            logger.info(log_event(
                mode_ctx,
                role="generator",
                event="doc_map_resolved_metadata",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "title": data.title,
                    "publisher": data.publisher,
                    "title_source": "doc_map.title" if doc_map_title else "ingest_payload",
                    "publisher_source": "doc_map.publisher" if doc_map_publisher else "unset",
                },
            ))
    try:
        artifacts_payload = generate_artifacts(
            report_id=file.file_id,
            report_name=report_name,
            doc_map=packs.get("doc_map", {}),
            evidence_packs=packs,
            settings=settings,
            vector_store_id=vector_store_id,
            source_status=text_status,
            ctx=child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:artifacts"),
            md5=md5,
        )
        mode_evidence_paths["artifacts"] = _pack_paths(
            settings.output_dir,
            file.file_id,
            report_name,
            ["artifacts"],
            mode_ctx,
        )["artifacts"]
        _record_state_progress(
            settings=settings,
            file_id=file.file_id,
            md5=md5,
            ctx=mode_ctx,
            stage="artifacts_ready",
            vector_store_id=vector_store_id,
            vector_store_status=vector_store_status,
            indexed_at_utc=indexed_at_utc,
            openai_file_id=openai_file_id,
            last_error=last_error,
        )
    except Exception as exc:
        logger.info(log_event(
            mode_ctx,
            role="generator",
            event="artifacts_generation_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "error": str(exc)},
        ))

    mode_data = _merge_artifacts_into_payload(mode_data, artifacts_payload or {})

    validation_pack_name = "validation"
    try:
        validation_req = ValidationRequest(
            schema_version="1.0",
            report_id=file.file_id,
            report=mode_data,
            artifacts=artifacts_payload or {},
            evidence_packs=mode_evidence_packs,
            vector_store_id=vector_store_id,
        )
        validation_report = run_validation(
            validation_req,
            settings,
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:validation"),
            pack_name=validation_pack_name,
            report_name=report_name,
            md5=md5,
        )
        if validation_report.source_path:
            mode_evidence_paths[validation_pack_name] = validation_report.source_path
        _record_state_progress(
            settings=settings,
            file_id=file.file_id,
            md5=md5,
            ctx=mode_ctx,
            stage="validation_complete",
            vector_store_id=vector_store_id,
            vector_store_status=vector_store_status,
            indexed_at_utc=indexed_at_utc,
            openai_file_id=openai_file_id,
            last_error=last_error,
        )
    except Exception as exc:
        logger.info(log_event(
            mode_ctx,
            role="generator",
            event="validation_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "error": str(exc), "mode": analysis_mode},
        ))
        fallback_issue = ValidationIssue(
            schema_version="1.0",
            message=f"Validation error: {exc}",
            severity="error",
            affected_section="validation",
        )
        fallback_report = ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[fallback_issue],
            severity="error",
        )
        try:
            validation_path = report_analysis_store_service.store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=settings.output_dir,
                    report_id=file.file_id,
                    pack_name=validation_pack_name,
                    payload=fallback_report.to_dict(),
                    report_slug=report_name,
                    mirror_legacy=settings.mirror_legacy_packs,
                ),
                mode_ctx,
            ).output_path
            fallback_report = ValidationReport(
                schema_version=fallback_report.schema_version,
                status=fallback_report.status,
                issues=fallback_report.issues,
                severity=fallback_report.severity,
                source_path=validation_path,
            )
            mode_evidence_paths[validation_pack_name] = validation_path
        except Exception as store_exc:  # pragma: no cover - best-effort fallback
            logger.info(log_event(
                mode_ctx,
                role="generator",
                event="validation_store_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": str(store_exc), "mode": analysis_mode},
            ))
        validation_report = fallback_report

    data_dict = mode_data.to_dict()
    if artifacts_payload:
        data_dict["artifacts"] = artifacts_payload
    if validation_report:
        data_dict["validation_report"] = validation_report.to_dict()
    data_dict["categories_display"] = category_assignment.category_labels
    data_dict["analysis_mode"] = analysis_mode
    logger.info(log_event(
        mode_ctx,
        role="generator",
        event="report_payload_ready",
        module=logger.name,
        fields={"payload": data_dict},
    ))

    snapshot_name = f"analysis_{analysis_mode}"
    snapshot_path = report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=file.file_id,
            pack_name=snapshot_name,
            payload=data_dict,
            report_slug=report_name,
            mirror_legacy=settings.mirror_legacy_packs,
        ),
        mode_ctx,
    ).output_path
    mode_evidence_paths[snapshot_name] = snapshot_path
    primary_result = {
        "data_dict": data_dict,
        "evidence_paths": mode_evidence_paths,
        "validation_report": validation_report,
        "artifacts_payload": artifacts_payload,
        "vector_store_id": vector_store_id,
        "vector_store_status": vector_store_status,
        "indexed_at_utc": indexed_at_utc,
        "openai_file_id": openai_file_id,
        "last_error": last_error,
    }
    vector_info_for_outcome = {
        "vector_store_id": vector_store_id,
        "vector_store_status": vector_store_status,
        "indexed_at_utc": indexed_at_utc,
        "openai_file_id": openai_file_id,
        "last_error": last_error,
    }
    primary_evidence_paths = dict(mode_evidence_paths)

    doc_name = file_name
    out_html = ""
    html_cache_hit = False
    html_cache_key = ""
    html_cache_meta = None
    template_sha = None
    expected_html_path = Path(settings.output_dir) / f"{slugify(doc_name)}.html"
    if md5:
        template_path = Path(__file__).resolve().parents[2] / "templates" / "report.html.j2"
        template_sha = _template_sha256(template_path, ctx)
        if template_sha:
            data_sha = sha256_json(primary_result["data_dict"])
            html_cache_meta = {
                "schema_version": "1.0",
                "md5": md5,
                "template_sha256": template_sha,
                "data_sha256": data_sha,
                "preview_png": preview_resp.image_path or "",
                "doc_name": doc_name,
            }
            html_cache_key = _html_cache_key(
                md5,
                template_sha,
                data_sha,
                preview_resp.image_path or "",
                doc_name,
            )
            html_cache_path = Path(f"{expected_html_path}.cache.json")
            cached = _read_cache_json(html_cache_path, ctx)
            if cached and cached.get("key") == html_cache_key:
                html_stat = file_stat(FileStatRequest(schema_version="1.0", path=str(expected_html_path)), ctx)
                if html_stat.exists:
                    out_html = str(expected_html_path)
                    html_cache_hit = True
                    logger.info(log_event(
                        ctx,
                        role="generator",
                        event="render_html_cache_hit",
                        module=logger.name,
                        fields={"file_id": file.file_id, "html_path": out_html},
                    ))
                else:
                    logger.info(log_event(
                        ctx,
                        role="generator",
                        event="render_html_cache_stale",
                        module=logger.name,
                        fields={"file_id": file.file_id, "html_path": str(expected_html_path)},
                    ))
            else:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="render_html_cache_miss",
                    module=logger.name,
                    fields={"file_id": file.file_id, "cache_path": str(html_cache_path)},
                ))
    if not html_cache_hit:
        render_resp = render_report_service(
            RenderRequest(
                schema_version="1.0",
                data=primary_result["data_dict"],
                doc_name=doc_name,
                file_id=file.file_id,
                out_dir=settings.output_dir,
                preview_png=preview_resp.image_path,
            ),
            ctx,
        )
        out_html = render_resp.html_path
        if md5 and template_sha and html_cache_meta and html_cache_key:
            cache_path = Path(f"{out_html}.cache.json")
            _write_cache_json(
                cache_path,
                {**html_cache_meta, "key": html_cache_key, "html_path": out_html},
                ctx,
            )
            logger.info(log_event(
                ctx,
                role="generator",
                event="render_html_cache_written",
                module=logger.name,
                fields={"file_id": file.file_id, "cache_path": str(cache_path)},
            ))

    upsert_report_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id=file.file_id,
            title=report_title,
            publisher=data.publisher or None,
            taxonomy=data.taxonomy,
            categories=data.categories,
            region=data.region or None,
            time_period=data.time_period or None,
            source_url=data.source,
            html_path=out_html,
            md5=md5,
            page_count=info_resp.page_count,
            pdf_metadata=info_resp.metadata,
            contents_page_number=contents_page_number,
            analysis_mode=analysis_mode,
            vector_store_id=vector_info_for_outcome["vector_store_id"],
            evidence_pack_paths=primary_evidence_paths,
        ),
        ctx,
    )

    cover_meta = get_report_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            file_id=file.file_id,
        ),
        child_context(ctx, task_id=f"{ctx.task_id}:cover_metadata"),
    )
    cover_title = (cover_meta.title if cover_meta else report_title).strip()
    cover_publisher = (cover_meta.publisher or "").strip() if cover_meta else (data.publisher or "")
    cover_time_period = cover_meta.time_period if cover_meta else (data.time_period or None)
    cover_region = cover_meta.region if cover_meta else (data.region or None)

    cover_ctx = child_context(ctx, task_id=f"{ctx.task_id}:cover_image")
    try:
        cover_outcomes = generate_cover_images(
            CoverImageGenerationRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                style_config_path=settings.cover_style_path,
                reports=[
                    CoverImageReport(
                        schema_version="1.0",
                        file_id=file.file_id,
                        title=cover_title,
                        publisher=cover_publisher,
                        categories=list(data.categories),
                        time_period=cover_time_period,
                        region=cover_region,
                    ),
                ],
            ),
            cover_ctx,
        )
        cover_outcome = cover_outcomes[0] if cover_outcomes else None
        logger.info(log_event(
            cover_ctx,
            role="generator",
            event="cover_image_generation_complete",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "status": cover_outcome.status if cover_outcome else "skipped",
                "output_path": cover_outcome.output_path if cover_outcome else "",
                "error": cover_outcome.error if cover_outcome else "",
            },
        ))
    except AppError as exc:
        logger.info(log_event(
            cover_ctx,
            role="generator",
            event="cover_image_generation_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "code": exc.code, "error": exc.message},
        ))

    logger.info(log_event(
        ctx,
        role="generator",
        event="token_usage_summary",
        module=logger.name,
        fields={
            "report_generation": None,
            "rank_candidates": rank_usage if cands_resp.candidates else None,
        },
    ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="report_generate_complete",
        module=logger.name,
        fields={"file_id": file.file_id, "html_path": out_html, "modes": analysis_modes},
    ))

    if pdf_context is not None:
        pdf_context.close()

    return IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file_name,
        md5=md5,
        html_path=out_html,
        status="processed",
        vector_store_id=vector_info_for_outcome["vector_store_id"],
        vector_store_status=vector_info_for_outcome["vector_store_status"],
        indexed_at_utc=vector_info_for_outcome["indexed_at_utc"],
        openai_file_id=vector_info_for_outcome["openai_file_id"],
        evidence_packs=primary_evidence_paths or None,
        vector_store_last_error=vector_info_for_outcome["last_error"],
        text_validation_status=text_validation_status,
        text_validation_reason=text_validation_reason,
        text_validation_pages=text_validation_pages,
    )
