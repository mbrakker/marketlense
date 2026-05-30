from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
)
from src.contracts.semantic_ids import ReportId
from src.generators.report_generation_dependencies import ReportSelectionDependencies
from src.generators.report_generation_shared import logger, read_cache_json
from src.utils.cache_utils import sha256_json
from src.utils.candidate_features import candidate_features, candidate_features_payload
from src.utils.coercion import coerce_int
from src.utils.logging import child_context, log_event
from src.utils.model_resolver import resolve_model

from .ranking import (
    _candidate_is_obvious_pass,
    _candidate_is_obvious_reject,
    _candidate_meta,
    _candidate_quality_signals,
    _rank_threshold_pass,
)


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
    dependencies: ReportSelectionDependencies,
) -> str:
    return dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=settings.output_dir,
            report_id=ReportId(file_id),
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
    dependencies: ReportSelectionDependencies,
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
    dependencies: ReportSelectionDependencies,
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
            report_id=ReportId(file_id),
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
    dependencies: ReportSelectionDependencies,
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
            coarse_index_by_candidate_id = {
                candidate.id: index for index, candidate in enumerate(phase_candidates)
            }
            for missing_id in sorted(missing_coarse_ids):
                recovery_index = coarse_index_by_candidate_id.get(missing_id)
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
            finalize_index_by_candidate_id = {
                candidate.id: index
                for index, candidate in enumerate(finalize_candidates)
            }
            for missing_id in sorted(missing_finalize_ids):
                recovery_index = finalize_index_by_candidate_id.get(missing_id)
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
