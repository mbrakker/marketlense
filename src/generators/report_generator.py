from __future__ import annotations

import logging
from typing import Optional

from src.contracts.openai import OpenAIAnalyzeRequest
from src.contracts.report_models import CropItem
from src.services.openai_service import analyze_pdf as openai_analyze
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
from src.contracts.normalize import NormalizeRequest
from src.services.normalize_service import normalize_report as normalize_report_service
from src.services.crop_service import crop_regions as crop_regions_service
from src.services.extract_service import collect_candidates as collect_candidates_service
from src.services.figure_service import extract_best_figure as extract_best_figure_service
from src.services.preview_service import render_preview as render_preview_service
from src.services.rank_service import rank_candidates as rank_candidates_service
from src.services.render_service import render_report as render_report_service
from src.utils.logging import log_event
from src.utils.validation import validate_candidate, validate_report_payload

logger = logging.getLogger("market_lense.report_generator")


def generate_report(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
) -> IngestOutcome:
    log_event(
        logger,
        ctx,
        role="generator",
        event="report_generate_start",
        fields={"file_id": file.file_id, "name": file.name},
    )

    openai_resp = openai_analyze(
        OpenAIAnalyzeRequest(
            schema_version="1.0",
            pdf_path=local_pdf_path,
            model=settings.openai_model,
            temperature=settings.temperature,
            api_key=settings.openai_api_key,
        ),
        ctx,
    )
    raw = openai_resp.payload
    normalize_resp = normalize_report_service(
        NormalizeRequest(schema_version="1.0", payload=raw),
        ctx,
    )
    data = normalize_resp.payload
    validate_report_payload(data)
    report_name = slugify(file.name)

    fig_resp = extract_best_figure_service(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=local_pdf_path,
            out_dir=settings.output_dir,
            report_name=report_name,
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
        ),
        ctx,
    )
    ranked = []
    sliced_paths = []
    if cands_resp.candidates:
        for cand in cands_resp.candidates:
            validate_candidate(cand)
        try:
            ranked_resp = rank_candidates_service(
                RankRequest(
                    schema_version="1.0",
                    candidates=cands_resp.candidates,
                    model=settings.openai_model,
                    api_key=settings.openai_api_key,
                    debug_dir=None,
                ),
                ctx,
            )
            ranked = ranked_resp.results
        except Exception:
            logger.exception("Ranking failed for %s; continuing without ranks", file.file_id)
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
            ),
            ctx,
        )
        sliced_paths = crop_resp.paths

    if sliced_paths:
        data._figure_gallery = sliced_paths
        data._figure_top = sliced_paths[0]

    preview_resp = render_preview_service(
        PreviewRequest(
            schema_version="1.0",
            pdf_path=local_pdf_path,
            out_dir=settings.output_dir,
            report_name=report_name,
        ),
        ctx,
    )

    data_dict = data.to_dict()
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

    log_event(
        logger,
        ctx,
        role="generator",
        event="report_generate_complete",
        fields={"file_id": file.file_id, "html_path": out_html},
    )

    return IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5=md5,
        html_path=out_html,
        status="processed",
    )
