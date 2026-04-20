from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from src.contracts.candidate_extraction import CandidateExtractOutcome, CandidateExtractRequest
from src.contracts.files import WriteBytesRequest
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.report_assets import CropRequest, ExtractCandidatesRequest
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services import file_service, pdf_service
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment
from src.utils.validation import validate_candidate

logger = logging.getLogger("market_lense.candidate_extraction_generator")


def _candidate_payload(candidates, crop_map: Dict[str, str]) -> List[dict]:
    payload = []
    for cand in candidates:
        payload.append({
            "schema_version": cand.schema_version,
            "id": cand.id,
            "kind": cand.kind,
            "type": cand.kind,
            "page": cand.page,
            "bbox": list(cand.bbox),
            "preview_text": cand.preview_text,
            "caption": cand.caption or "",
            "thumb_path": cand.thumb_path or "",
            "crop_path": crop_map.get(cand.id, ""),
            "meta": cand.meta or {},
        })
    return payload


def _candidates_path(output_dir: str, report_name: str, subdir: str) -> str:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    safe_subdir = safe_path_segment(subdir or "candidates", fallback="candidates")
    base = Path(output_dir) / safe_report_name / safe_subdir
    return str(base / "candidates.json")


def generate_candidate_pack(request: CandidateExtractRequest, ctx: RunContext) -> CandidateExtractOutcome:
    logger.info(log_event(
        ctx,
        role="generator",
        event="candidate_extract_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "report_name": request.report_name,
            "pdf_path": request.pdf_path,
            "output_dir": request.output_dir,
            "save_crops": request.save_crops,
            "subdir": request.subdir,
        },
    ))

    pdf_context = None
    try:
        pdf_ctx_resp = pdf_service.build_pdf_context(
            PdfContextBuildRequest(schema_version="1.0", path=request.pdf_path),
            ctx,
        )
        pdf_context = pdf_ctx_resp.context
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="candidate_pdf_context_failed",
            module=logger.name,
            fields={"pdf_path": request.pdf_path, "error": str(exc)},
        ))
        pdf_context = None

    try:
        candidates_resp = pdf_service.collect_candidates(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=request.pdf_path,
                out_dir=request.output_dir,
                report_name=request.report_name,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        for cand in candidates_resp.candidates:
            validate_candidate(cand)

        chart_count = sum(1 for c in candidates_resp.candidates if c.kind == "chart")
        table_count = sum(1 for c in candidates_resp.candidates if c.kind == "table")
        logger.info(log_event(
            ctx,
            role="generator",
            event="candidate_extract_collected",
            module=logger.name,
            fields={
                "candidate_count": len(candidates_resp.candidates),
                "chart_count": chart_count,
                "table_count": table_count,
            },
        ))

        crop_paths: List[str] = []
        crop_map: Dict[str, str] = {}
        if request.save_crops and candidates_resp.candidates:
            items = [
                CropItem(
                    id=c.id,
                    type=c.kind,
                    score=0.0,
                    page=c.page,
                    bbox=c.bbox,
                )
                for c in candidates_resp.candidates
            ]
            crop_resp = pdf_service.crop_regions(
                CropRequest(
                    schema_version="1.0",
                    pdf_path=request.pdf_path,
                    out_dir=request.output_dir,
                    report_name=request.report_name,
                    subdir=request.subdir,
                    items=items,
                    pdf_context=pdf_context,
                ),
                ctx,
            )
            crop_paths = crop_resp.paths
            crop_map = {item.id: path for item, path in zip(items, crop_paths)}
            logger.info(log_event(
                ctx,
                role="generator",
                event="candidate_extract_crops_complete",
                module=logger.name,
                fields={"crop_count": len(crop_paths)},
            ))

        payload = {
            "schema_version": "1.0",
            "report_id": request.report_id,
            "report_name": request.report_name,
            "pdf_path": request.pdf_path,
            "candidate_count": len(candidates_resp.candidates),
            "chart_count": chart_count,
            "table_count": table_count,
            "candidates": _candidate_payload(candidates_resp.candidates, crop_map),
        }
        output_path = _candidates_path(request.output_dir, request.report_name, request.subdir)
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=output_path,
                content=json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8"),
                make_parents=True,
            ),
            ctx,
        )
        logger.info(log_event(
            ctx,
            role="generator",
            event="candidate_extract_saved",
            module=logger.name,
            fields={"candidates_path": output_path},
        ))

        return CandidateExtractOutcome(
            schema_version="1.0",
            report_id=request.report_id,
            report_name=request.report_name,
            pdf_path=request.pdf_path,
            candidates_path=output_path,
            candidate_count=len(candidates_resp.candidates),
            chart_count=chart_count,
            table_count=table_count,
            crop_count=len(crop_paths),
            crop_paths=crop_paths,
            error=None,
        )
    finally:
        if pdf_context is not None:
            pdf_context.close()
