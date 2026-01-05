from __future__ import annotations

import json
import logging
from typing import Optional

from src.contracts.openai import OpenAIAnalyzeRequest
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.report_models import CropItem
from src.contracts.pdf_context import PdfContextBuildRequest
from src.services.openai_service import analyze_report as openai_analyze
from src.services.pdf_text_service import extract_pdf_text
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.slugify import slugify
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.report_assets import (
    CropRequest,
    ExtractCandidatesRequest,
    FigureExtractRequest,
    PreviewRequest,
    RankRequest,
    RenderRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.categories import CategoryMappingLoadRequest, UncategorizedTagsUpdateRequest
from src.contracts.pdf_utils import PdfInfoRequest
from src.generators.categorize_generator import categorize_taxonomy
from src.generators.normalize_generator import normalize_report
from src.services.crop_service import crop_regions as crop_regions_service
from src.services.extract_service import collect_candidates as collect_candidates_service
from src.services.figure_service import extract_best_figure as extract_best_figure_service
from src.services.preview_service import render_preview as render_preview_service
from src.services.rank_service import rank_candidates as rank_candidates_service
from src.services.render_service import render_report as render_report_service
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
    update_uncategorized_tags,
)
from src.services.report_store_service import upsert_metadata as upsert_report_metadata
from src.services.pdf_context_service import build_pdf_context
from src.services.pdf_utils_service import extract_pdf_info
from src.utils.logging import log_event
from src.utils.validation import validate_candidate, validate_report_payload

logger = logging.getLogger("market_lense.report_generator")


def _derive_title(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    cleaned = base.strip()
    return cleaned or name


def generate_report(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
) -> IngestOutcome:
    pdf_context = None
    logger.info(log_event(
        ctx,
        role="generator",
        event="report_generate_start",
        module=logger.name,
        fields={"file_id": file.file_id, "name": file.name},
    ))

    info_resp = extract_pdf_info(
        PdfInfoRequest(schema_version="1.0", path=local_pdf_path),
        ctx,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="pdf_info_loaded",
        module=logger.name,
        fields={"file_id": file.file_id, "page_count": info_resp.page_count, "metadata_keys": list(info_resp.metadata.keys())},
    ))

    try:
        pdf_ctx_resp = build_pdf_context(
            PdfContextBuildRequest(schema_version="1.0", path=local_pdf_path),
            ctx,
        )
        pdf_context = pdf_ctx_resp.context
        if pdf_ctx_resp.fitz_error or pdf_ctx_resp.pypdf_error:
            logger.info(log_event(
                ctx,
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

    try:
        text_resp = extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=local_pdf_path,
                max_pages=settings.pdf_text_max_pages,
                max_chars=settings.pdf_text_max_chars,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        prompt_set = load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace="report_generation", reload_if_changed=True),
            ctx,
        )
        logger.info(log_event(
            ctx,
            role="generator",
            event="prompt_selected",
            module=logger.name,
            fields={
                "namespace": "report_generation",
                "system_path": prompt_set.system.path,
                "system_sha256": prompt_set.system.sha256,
                "user_path": prompt_set.user.path,
                "user_sha256": prompt_set.user.sha256,
            },
        ))
        system_render = render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.system,
                variables={},
            ),
            ctx,
        )
        user_render = render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.user,
                variables={"extracted": text_resp.text},
            ),
            ctx,
        )
        logger.info(log_event(
            ctx,
            role="generator",
            event="prompt_rendered",
            module=logger.name,
            fields={
                "system_prompt": system_render.text,
                "user_prompt": user_render.text,
            },
        ))
        logger.info(log_event(
            ctx,
            role="generator",
            event="openai_request_config",
            module=logger.name,
            fields={
                "model": settings.openai_model,
                "temperature": settings.temperature,
                "seed": settings.openai_seed,
            },
        ))
        openai_resp = openai_analyze(
            OpenAIAnalyzeRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                prompt_system_sha256=prompt_set.system.sha256,
                prompt_user_sha256=prompt_set.user.sha256,
                model=settings.openai_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
            ),
            ctx,
        )
        report_usage = {
            "prompt_tokens": openai_resp.prompt_tokens,
            "completion_tokens": openai_resp.completion_tokens,
            "total_tokens": openai_resp.total_tokens,
        }
        logger.info(log_event(
            ctx,
            role="generator",
            event="openai_raw_response",
            module=logger.name,
            fields={"request_id": openai_resp.request_id or "", "content": openai_resp.raw_content},
        ))
        raw = openai_resp.payload
        data = normalize_report(raw, ctx)
        report_title = data.title.strip() or _derive_title(file.name)
        data.title = report_title
        validate_report_payload(data)
        logger.info(log_event(
            ctx,
            role="generator",
            event="report_payload_validated",
            module=logger.name,
            fields={"file_id": file.file_id},
        ))
    
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(schema_version="1.0", path=settings.category_mapping_path, reload_if_changed=True),
            ctx,
        )
        category_assignment = categorize_taxonomy(data.taxonomy, mappings_resp, ctx)
        data.categories = category_assignment.categories
        if category_assignment.unmapped_tags or mappings_resp.mappings.uncategorized:
            update_uncategorized_tags(
                UncategorizedTagsUpdateRequest(
                    schema_version="1.0",
                    path=settings.category_mapping_path,
                    report_title=report_title,
                    tags=category_assignment.unmapped_tags,
                ),
                ctx,
            )
        report_name = slugify(file.name)
    
        fig_resp = extract_best_figure_service(
            FigureExtractRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        if fig_resp.image_path:
            data._figure_image = fig_resp.image_path
            if fig_resp.caption and not (data.figure.evidence or "").strip():
                data.figure.evidence = fig_resp.caption
    
        cands_resp = collect_candidates_service(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        ranked = []
        rank_usage = None
        sliced_paths = []
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
            rank_model = settings.rank_model or settings.openai_model
            rows = [{
                "id": c.id,
                "type": c.kind,
                "page": c.page,
                "meta": c.meta or {},
                "title_or_caption": (c.caption or "")[:300],
                "table_preview": c.preview_text[:400] if c.kind == "table" else "",
            } for c in cands_resp.candidates]
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
                    "model": rank_model,
                    "temperature": settings.rank_temperature,
                    "seed": settings.rank_seed,
                },
            ))
            rank_usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
            try:
                ranked_resp = rank_candidates_service(
                    RankRequest(
                        schema_version="1.0",
                        system_prompt=rank_system_render.text,
                        user_prompt=rank_user_render.text,
                        prompt_system_sha256=rank_prompt_set.system.sha256,
                        prompt_user_sha256=rank_prompt_set.user.sha256,
                        model=rank_model,
                        temperature=settings.rank_temperature,
                        api_key=settings.openai_api_key,
                        seed=settings.rank_seed,
                        candidate_count=len(cands_resp.candidates),
                        timeout_seconds=settings.rank_timeout_seconds,
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
    
            id2cand = {c.id: c for c in cands_resp.candidates}
            top_items = []
            for row in sorted(ranked, key=lambda r: r.score, reverse=True)[:3]:
                c = id2cand.get(row.id)
                if not c:
                    continue
                top_items.append(CropItem(
                    id=c.id,
                    type=c.kind,
                    score=float(row.score),
                    page=c.page,
                    bbox=c.bbox,
                ))
    
            crop_resp = crop_regions_service(
                CropRequest(
                    schema_version="1.0",
                    pdf_path=local_pdf_path,
                    out_dir=settings.output_dir,
                    report_name=report_name,
                    items=top_items,
                    pdf_context=pdf_context,
                ),
                ctx,
            )
            sliced_paths = crop_resp.paths
            if top_items:
                top_cand = id2cand.get(top_items[0].id)
                if top_cand:
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
    
        preview_resp = render_preview_service(
            PreviewRequest(
                schema_version="1.0",
                pdf_path=local_pdf_path,
                out_dir=settings.output_dir,
                report_name=report_name,
                pdf_context=pdf_context,
            ),
            ctx,
        )
    
        data_dict = data.to_dict()
        data_dict["categories_display"] = category_assignment.category_labels
        logger.info(log_event(
            ctx,
            role="generator",
            event="report_payload_ready",
            module=logger.name,
            fields={"payload": data_dict},
        ))
        render_resp = render_report_service(
            RenderRequest(
                schema_version="1.0",
                data=data_dict,
                doc_name=file.name,
                file_id=file.file_id,
                out_dir=settings.output_dir,
                preview_png=preview_resp.image_path,
            ),
            ctx,
        )
        out_html = render_resp.html_path
    
        upsert_report_metadata(
            ReportMetadataUpsertRequest(
                schema_version="1.0",
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
            ),
            ctx,
        )
    
        logger.info(log_event(
            ctx,
            role="generator",
            event="token_usage_summary",
            module=logger.name,
            fields={
                "report_generation": report_usage,
                "rank_candidates": rank_usage if cands_resp.candidates else None,
            },
        ))
        logger.info(log_event(
            ctx,
            role="generator",
            event="report_generate_complete",
            module=logger.name,
            fields={"file_id": file.file_id, "html_path": out_html},
        ))
    
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name,
            md5=md5,
            html_path=out_html,
            status="processed",
        )
    finally:
        if pdf_context is not None:
            pdf_context.close()
