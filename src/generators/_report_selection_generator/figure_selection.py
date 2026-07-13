from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from src.contracts.candidates import Candidate
from src.contracts.crop_qa_escalation import (
    CropQaEscalationPolicy,
    CropQaEscalationRequest,
)
from src.contracts.ingest import IngestSettings
from src.contracts.report_assets import (
    CropItem,
    CropRequest,
    ExtractCandidatesRequest,
    FigureExtractRequest,
    FigureExtractResponse,
)
from src.contracts.report_generation import (
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import ReportFigureAsset, ReportPayload
from src.generators.report_generation_dependencies import ReportSelectionDependencies
from src.generators.report_generation_shared import logger, read_cache_json
from src.utils.coercion import coerce_float
from src.utils.logging import log_event
from src.utils.validation import validate_candidate

from .crop_refine import select_refined_candidate_items
from .ranking import (
    _candidate_is_obvious_reject,
    _candidate_prefilter_priority,
    _candidate_prefilter_reject_reason,
    _merge_rank_usage,
    _rank_candidates_batch,
    _rank_threshold_pass,
    _split_candidates_by_kind,
    _truncate_prefiltered_candidates,
)


def _rank_candidate_batches(
    *,
    table_candidates: list[Candidate],
    chart_candidates: list[Candidate],
    runtime: ReportRuntimeState,
    dependencies: ReportSelectionDependencies,
) -> tuple[list[Any], dict[str, Optional[int]]]:
    batches = [
        ("table", table_candidates),
        ("chart", chart_candidates),
    ]
    active_batches = [(kind, batch) for kind, batch in batches if batch]
    if not active_batches:
        return [], {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    usage_rows: list[dict[str, Optional[int]]] = []
    ranked_by_kind: dict[str, list[Any]] = {"table": [], "chart": []}
    max_workers = min(2, max(1, int(getattr(runtime, "report_worker_limit", 1) or 1)))
    if len(active_batches) <= 1 or not runtime.parallel_within_file or max_workers <= 1:
        for kind, batch in active_batches:
            batch_result = _rank_candidates_batch(
                candidates=batch,
                kind=kind,
                settings=runtime.settings,
                ctx=runtime.ctx,
                dependencies=dependencies,
            )
            ranked_by_kind[kind] = list(batch_result.ranked)
            usage_rows.append(batch_result.usage)
        return ranked_by_kind["table"] + ranked_by_kind["chart"], _merge_rank_usage(
            usage_rows
        )

    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="candidate_rank_parallel_start",
            module=logger.name,
            fields={
                "max_workers": max_workers,
                "table_candidates": len(table_candidates),
                "chart_candidates": len(chart_candidates),
            },
        )
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _rank_candidates_batch,
                candidates=batch,
                kind=kind,
                settings=runtime.settings,
                ctx=runtime.ctx,
                dependencies=dependencies,
            ): kind
            for kind, batch in active_batches
        }
        for future, kind in futures.items():
            batch_result = future.result()
            ranked_by_kind[kind] = list(batch_result.ranked)
            usage_rows.append(batch_result.usage)
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="candidate_rank_parallel_complete",
            module=logger.name,
            fields={
                "max_workers": max_workers,
                "ranked_table_count": len(ranked_by_kind["table"]),
                "ranked_chart_count": len(ranked_by_kind["chart"]),
            },
        )
    )
    return ranked_by_kind["table"] + ranked_by_kind["chart"], _merge_rank_usage(
        usage_rows
    )


def _candidate_crop_path_map(
    candidates: list[Candidate],
    candidate_paths: list[str],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for candidate, path in zip(candidates, candidate_paths, strict=False):
        candidate_id = str(candidate.id or "").strip()
        normalized_path = str(path or "").strip()
        if candidate_id and normalized_path:
            mapping[candidate_id] = normalized_path
    return mapping


def _outcome_value(outcome: object, field_name: str, default: Any = "") -> Any:
    if isinstance(outcome, dict):
        return outcome.get(field_name, default)
    return getattr(outcome, field_name, default)


def _crop_outcomes_by_candidate_id(crop_response: object) -> dict[str, object]:
    raw_outcomes = getattr(crop_response, "outcomes", [])
    if not isinstance(raw_outcomes, list):
        return {}
    outcomes: dict[str, object] = {}
    for outcome in raw_outcomes:
        candidate_id = str(_outcome_value(outcome, "candidate_id", "") or "").strip()
        if candidate_id:
            outcomes[candidate_id] = outcome
    return outcomes


def _accepted_crop_path_by_id(
    *,
    crop_response: object,
    items: list[CropItem],
) -> dict[str, str]:
    outcomes = _crop_outcomes_by_candidate_id(crop_response)
    if outcomes:
        return {
            candidate_id: str(_outcome_value(outcome, "path", "") or "").strip()
            for candidate_id, outcome in outcomes.items()
            if bool(_outcome_value(outcome, "accepted", False))
            and str(_outcome_value(outcome, "path", "") or "").strip()
        }
    return {
        item.id: str(path or "").strip()
        for item, path in zip(
            items, getattr(crop_response, "paths", []), strict=False
        )
        if str(path or "").strip()
    }


def _crop_metadata_by_id(crop_response: object) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for candidate_id, outcome in _crop_outcomes_by_candidate_id(crop_response).items():
        defects = _outcome_value(outcome, "defects", [])
        if not isinstance(defects, list):
            defects = []
        metadata[candidate_id] = {
            "crop_qa_score": float(_outcome_value(outcome, "score", 0.0) or 0.0),
            "crop_qa_defects": [str(item) for item in defects],
            "crop_qa_accepted": bool(_outcome_value(outcome, "accepted", False)),
            "crop_qa_sidecar_path": str(
                _outcome_value(outcome, "qa_sidecar_path", "") or ""
            ),
            "crop_quality_profile": str(
                _outcome_value(outcome, "quality_profile", "") or ""
            ),
            "crop_rejection_reason": str(
                _outcome_value(outcome, "rejection_reason", "") or ""
            ),
        }
    return metadata


def _apply_crop_qa_escalation(
    *,
    paths: list[str],
    candidates: list[Candidate],
    crop_metadata_by_id: dict[str, dict[str, Any]],
    runtime: ReportRuntimeState,
    dependencies: ReportSelectionDependencies,
    llm_client: Any | None,
) -> tuple[list[str], list[Candidate]]:
    if not runtime.settings.crop_qa_escalation_enabled or not paths or not candidates:
        return paths, candidates
    crops: list[dict[str, Any]] = []
    paired: list[tuple[str, Candidate]] = []
    for path, candidate in zip(paths, candidates, strict=False):
        candidate_id = str(candidate.id or "").strip()
        metadata = crop_metadata_by_id.get(candidate_id, {})
        if not candidate_id or not bool(metadata.get("crop_qa_accepted")):
            continue
        crops.append(
            {
                "candidate_id": candidate_id,
                "image_path": str(path or "").strip(),
                "qa_sidecar_path": str(
                    metadata.get("crop_qa_sidecar_path") or ""
                ).strip(),
                "quality_profile": str(
                    metadata.get("crop_quality_profile") or ""
                ).strip(),
                "score": metadata.get("crop_qa_score"),
                "defects": list(metadata.get("crop_qa_defects") or []),
            }
        )
        paired.append((str(path or "").strip(), candidate))
    if not crops:
        return paths, candidates
    response = dependencies.crop_qa_escalation(
        CropQaEscalationRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            crops=crops,
            policy=CropQaEscalationPolicy(
                schema_version="1.0",
                enabled=True,
                low_confidence_min_score=(
                    runtime.settings.crop_qa_escalation_min_score
                ),
                low_confidence_max_score=(
                    runtime.settings.crop_qa_escalation_max_score
                ),
                max_escalations=runtime.settings.crop_qa_escalation_max_calls,
                max_repairs=runtime.settings.crop_qa_escalation_max_repairs,
                model=runtime.settings.rank_model or runtime.settings.openai_model,
                temperature=runtime.settings.rank_temperature,
                seed=runtime.settings.rank_seed,
                timeout_seconds=runtime.settings.rank_timeout_seconds,
                api_key=runtime.settings.openai_api_key,
                cost_ledger_path=runtime.settings.cost_ledger_path,
                cost_daily_path=runtime.settings.cost_daily_path,
                model_pricing=runtime.settings.model_pricing,
            ),
        ),
        runtime.ctx,
        llm_client=llm_client,
    )
    accepted_ids = {
        decision.candidate_id
        for decision in response.decisions
        if decision.decision in {"not_escalated", "accept"}
    }
    selected = [
        (path, candidate)
        for path, candidate in paired
        if str(candidate.id or "").strip() in accepted_ids
    ]
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="figure_crop_qa_escalation_applied",
            module=logger.name,
            fields={
                "evaluated_count": len(crops),
                "model_call_count": response.model_call_count,
                "repair_count": response.repair_count,
                "reject_count": response.reject_count,
                "selected_count": len(selected),
                "rejected_candidate_ids": sorted(
                    decision.candidate_id
                    for decision in response.decisions
                    if decision.decision in {"repair", "reject"}
                ),
            },
        )
    )
    return [path for path, _ in selected], [candidate for _, candidate in selected]


def _candidate_extraction_output_path(
    settings: IngestSettings,
    report_name: str,
) -> Path:
    return (
        Path(settings.output_dir)
        / str(report_name or "").strip()
        / "candidates"
        / "candidates.json"
    )


def _load_candidate_crop_path_map(
    *,
    settings: IngestSettings,
    report_name: str,
    ctx,
    dependencies: ReportSelectionDependencies,
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
    crop_metadata: Optional[dict[str, Any]] = None,
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
        crop_qa_score=float((crop_metadata or {}).get("crop_qa_score") or 0.0),
        crop_qa_defects=list((crop_metadata or {}).get("crop_qa_defects") or []),
        crop_qa_accepted=bool((crop_metadata or {}).get("crop_qa_accepted") or False),
        crop_qa_sidecar_path=str(
            (crop_metadata or {}).get("crop_qa_sidecar_path") or ""
        ),
        crop_quality_profile=str(
            (crop_metadata or {}).get("crop_quality_profile") or ""
        ),
        crop_rejection_reason=str(
            (crop_metadata or {}).get("crop_rejection_reason") or ""
        ),
    )


def _build_figure_assets(
    *,
    gallery_paths: list[str],
    figure_candidates: list[Candidate],
    primary_figure_path: str,
    primary_caption: str,
    fig_resp: Any,
    crop_metadata_by_id: Optional[dict[str, dict[str, Any]]] = None,
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
                crop_metadata=(crop_metadata_by_id or {}).get(
                    str(getattr(candidate, "id", "") or "").strip()
                )
                if candidate is not None
                else None,
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
    dependencies: ReportSelectionDependencies,
    *,
    crop_qa_llm_client: Any | None = None,
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
                page_gate_enabled=runtime.settings.candidate_page_gate_enabled,
                page_gate_min_score=runtime.settings.candidate_page_gate_min_score,
                page_gate_min_recall_pages=(
                    runtime.settings.candidate_page_gate_min_recall_pages
                ),
                page_gate_min_recall_page_fraction=(
                    runtime.settings.candidate_page_gate_min_recall_page_fraction
                ),
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
    figure_crop_metadata_by_id: dict[str, dict[str, Any]] = {}
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
            try:
                ranked, rank_usage = _rank_candidate_batches(
                    table_candidates=table_candidates,
                    chart_candidates=chart_candidates,
                    runtime=runtime,
                    dependencies=dependencies,
                )
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
            crop_response = dependencies.crop_regions(
                CropRequest(
                    schema_version="1.0",
                    pdf_path=runtime.local_pdf_path,
                    out_dir=runtime.settings.output_dir,
                    report_name=runtime.report_name,
                    items=selected_items,
                    mode="publication_strict",
                    dpi=int(runtime.settings.final_crop_dpi),
                    pdf_context=source.pdf_context,
                ),
                runtime.ctx,
            )
            selected_path_by_id = _accepted_crop_path_by_id(
                crop_response=crop_response,
                items=selected_items,
            )
            figure_crop_metadata_by_id.update(_crop_metadata_by_id(crop_response))
            sliced_paths = [
                str(selected_path_by_id.get(item.id) or "").strip()
                for item in selected_items
                if str(selected_path_by_id.get(item.id) or "").strip()
            ]
            selected_candidate_by_id = {
                str(candidate.id or "").strip(): candidate
                for candidate in selected_candidates
            }
            figure_candidates = [
                selected_candidate_by_id[item.id]
                for item in selected_items
                if str(selected_path_by_id.get(item.id) or "").strip()
                and item.id in selected_candidate_by_id
            ]
        else:
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
                                mode="publication_strict",
                                pdf_context=source.pdf_context,
                            ),
                            runtime.ctx,
                        )
                        fallback_path_by_id.update(
                            _accepted_crop_path_by_id(
                                crop_response=fallback_crop_resp,
                                items=fallback_items,
                            )
                        )
                        figure_crop_metadata_by_id.update(
                            _crop_metadata_by_id(fallback_crop_resp)
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
                                )
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
        sliced_paths, figure_candidates = _apply_crop_qa_escalation(
            paths=sliced_paths,
            candidates=figure_candidates,
            crop_metadata_by_id=figure_crop_metadata_by_id,
            runtime=runtime,
            dependencies=dependencies,
            llm_client=crop_qa_llm_client,
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
        crop_metadata_by_id=figure_crop_metadata_by_id,
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
