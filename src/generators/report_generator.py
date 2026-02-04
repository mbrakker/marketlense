from __future__ import annotations

import hashlib
import json
import logging
import random
from copy import deepcopy
from pathlib import Path
from typing import Optional

from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextSampleRequest
from src.contracts.report_store import ReportMetadataGetRequest, ReportMetadataUpsertRequest
from src.contracts.report_models import CropItem, Figure, Quote, ReportPayload
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_contents import PdfContentsDetectionRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.services.pdf_service import extract_pdf_text, sample_pdf_text
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
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.artifact_generator import generate_artifacts
from src.generators.cover_image_generator import generate_cover_images
from src.generators.taxonomy_generator import extract_taxonomy
from src.generators.validation_generator import validate_report as run_validation
from src.services.crop_service import crop_regions as crop_regions_service
from src.services.candidate_extraction_service import collect_candidates as collect_candidates_service
from src.services.figure_service import extract_best_figure as extract_best_figure_service
from src.services.preview_service import render_preview as render_preview_service
from src.services.rank_service import rank_candidates as rank_candidates_service
from src.services.render_service import render_report as render_report_service
from src.services.prompt_service import load_prompt_set, render_prompt
from src.services.pdf_service import detect_contents_page as detect_contents_page_service
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
    update_uncategorized_tags,
)
from src.services.report_store_service import (
    get_metadata as get_report_metadata,
    upsert_metadata as upsert_report_metadata,
)
from src.services.pdf_service import build_pdf_context, extract_pdf_info
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

logger = logging.getLogger("market_lense.report_generator")


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

def _pack_paths(output_dir: str, report_id: str, report_name: str, pack_names: list[str]) -> dict[str, str]:
    return {
        name: str(report_analysis_store_service.pack_path(
            output_dir,
            report_id,
            name,
            report_slug=report_name,
        ))
        for name in pack_names
    }


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


def _ensure_vector_store(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    ctx: RunContext,
):
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
        if vector_store_status != "completed":
            status_resp = vector_store_service.wait_until_indexed(
                VectorStoreWaitRequest(
                    schema_version="1.0",
                    vector_store_id=vector_store_id,
                    timeout_s=int(settings.openai_timeout_seconds),
                    poll_interval_s=5,
                ),
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
        status_resp = vector_store_service.wait_until_indexed(
            VectorStoreWaitRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                timeout_s=int(settings.openai_timeout_seconds),
                poll_interval_s=5,
            ),
            ctx=ctx,
        )
        vector_store_status = status_resp.status
        indexed_at_utc = status_resp.indexed_at_utc
        last_error = status_resp.last_error

    logger.info(log_event(
        ctx,
        role="generator",
        event="vector_store_ready",
        module=logger.name,
        fields={
            "file_id": file.file_id,
            "vector_store_id": vector_store_id,
            "status": vector_store_status,
            "indexed_at_utc": indexed_at_utc or "",
        },
    ))
    return vector_store_id, openai_file_id, vector_store_status, indexed_at_utc, last_error


def generate_report(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
) -> IngestOutcome:
    pdf_context = None
    analysis_mode = "vector_store"
    analysis_modes = [analysis_mode]
    logger.info(log_event(
        ctx,
        role="generator",
        event="report_generate_start",
        module=logger.name,
        fields={"file_id": file.file_id, "name": file.name, "modes": analysis_modes},
    ))
    report_name = slugify(file.name)
    contents_page_number = 0
    contents_image = ""
    contents_heading = ""

    info_ctx = child_context(ctx, task_id=f"{ctx.task_id}:pdf_info")
    info_resp = extract_pdf_info(
        PdfInfoRequest(schema_version="1.0", path=local_pdf_path),
        info_ctx,
    )
    logger.info(log_event(
        info_ctx,
        role="generator",
        event="pdf_info_loaded",
        module=logger.name,
        fields={"file_id": file.file_id, "page_count": info_resp.page_count, "metadata_keys": list(info_resp.metadata.keys())},
    ))

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

    try:
        contents_resp = detect_contents_page_service(
            PdfContentsDetectionRequest(
                schema_version="1.0",
                path=local_pdf_path,
                max_pages=settings.contents_max_pages,
                min_headings=settings.contents_min_headings,
                keywords=settings.contents_keywords,
                pdf_context=pdf_context,
            ),
            child_context(ctx, task_id=f"{ctx.task_id}:contents"),
        )
        if contents_resp.has_contents:
            contents_page_number = contents_resp.page_number
            contents_heading = contents_resp.heading or ""
            contents_preview = render_preview_service(
                PreviewRequest(
                    schema_version="1.1",
                    pdf_path=local_pdf_path,
                    out_dir=settings.output_dir,
                    report_name=report_name,
                    page_number=max(contents_resp.page_index, 0),
                    variant="contents",
                    dpi=settings.contents_preview_dpi,
                    pdf_context=pdf_context,
                ),
                ctx,
            )
            if contents_preview.image_path:
                contents_image = contents_preview.image_path
        logger.info(log_event(
            ctx,
            role="generator",
            event="contents_detection_result",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "has_contents": contents_resp.has_contents,
                "page_number": contents_page_number,
                "image_path": contents_image or "",
            },
        ))
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="contents_detection_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "error": str(exc)},
        ))

    text_ctx = child_context(ctx, task_id=f"{ctx.task_id}:text")
    text_resp = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=local_pdf_path,
            max_pages=settings.pdf_text_max_pages,
            max_chars=settings.pdf_text_max_chars,
            pdf_context=pdf_context,
        ),
        text_ctx,
    )
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
        fields={"density": text_status["text_density"], "threshold": text_status["density_threshold"], "pages": text_status["pages_sampled"], "char_count": text_status["char_count"], "not_available": text_status["not_available"]},
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
            name=file.name,
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
            name=file.name,
            md5=md5,
            html_path=None,
            status="error",
            error="pdf_text_unextractable",
            text_validation_status=text_validation_status,
            text_validation_reason=text_validation_reason,
            text_validation_pages=text_validation_pages,
        )
    report_title = _derive_title(file.name)
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
    vector_store_id, openai_file_id, vector_store_status, indexed_at_utc, last_error = _ensure_vector_store(
        file,
        local_pdf_path,
        settings,
        mode_ctx,
    )
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
    data.taxonomy = taxonomy_resp.taxonomy
    data.region = taxonomy_resp.region
    data.time_period = taxonomy_resp.time_period

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
    if vector_store_id:
        vector_store_service.update_metadata(
            VectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=file.file_id,
                    report_name=report_title,
                    taxonomy=data.taxonomy,
                    categories=data.categories,
                    region=data.region,
                    time_period=data.time_period,
                ),
            ),
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:metadata"),
        )

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
    candidate_paths = []
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
                "model": resolved_rank_model,
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
                    model=resolved_rank_model,
                    temperature=settings.rank_temperature,
                    api_key=settings.openai_api_key,
                    seed=settings.rank_seed,
                    candidate_count=len(cands_resp.candidates),
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

    data.contents_page_number = contents_page_number
    data.contents_heading = contents_heading
    data._contents_image = contents_image
    base_payload = normalize_report(data, ctx)

    mode_data = deepcopy(base_payload)
    mode_evidence_packs: dict[str, dict] = {}
    mode_evidence_paths: dict[str, str] = {}
    validation_report: ValidationReport | None = None
    artifacts_payload: dict | None = None
    packs = generate_evidence_packs(
        report_id=file.file_id,
        report_name=report_name,
        vector_store_id=vector_store_id,
        settings=settings,
        ctx=child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:evidence"),
    )
    mode_evidence_packs = packs
    pack_names = list(packs.keys())
    mode_evidence_paths = _pack_paths(settings.output_dir, file.file_id, report_name, pack_names)
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
        )
        mode_evidence_paths["artifacts"] = _pack_paths(settings.output_dir, file.file_id, report_name, ["artifacts"])["artifacts"]
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
                settings.output_dir,
                file.file_id,
                validation_pack_name,
                fallback_report.to_dict(),
                mode_ctx,
                report_slug=report_name,
            )
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
        settings.output_dir,
        file.file_id,
        snapshot_name,
        data_dict,
        mode_ctx,
        report_slug=report_name,
    )
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

    render_resp = render_report_service(
        RenderRequest(
            schema_version="1.0",
            data=primary_result["data_dict"],
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
        name=file.name,
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
