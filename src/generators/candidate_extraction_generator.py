from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from src.contracts.candidate_extraction import (
    CandidateExtractOutcome,
    CandidateExtractRequest,
)
from src.contracts.files import WriteBytesRequest
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.report_assets import CropRequest, ExtractCandidatesRequest
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services import file_service, pdf_service
from src.utils.candidate_features import candidate_features_payload
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment
from src.utils.validation import validate_candidate

logger = logging.getLogger("market_lense.candidate_extraction_generator")


def _outcome_value(outcome: object, field_name: str, default: Any = "") -> Any:
    if isinstance(outcome, dict):
        return outcome.get(field_name, default)
    return getattr(outcome, field_name, default)


def _outcomes_by_candidate_id(outcomes: object) -> Dict[str, object]:
    if not isinstance(outcomes, list):
        return {}
    mapped: Dict[str, object] = {}
    for outcome in outcomes:
        candidate_id = str(_outcome_value(outcome, "candidate_id", "") or "").strip()
        if candidate_id:
            mapped[candidate_id] = outcome
    return mapped


def _candidate_payload(
    candidates, crop_map: Dict[str, str], crop_outcomes: Dict[str, object]
) -> List[dict]:
    payload = []
    for cand in candidates:
        outcome = crop_outcomes.get(str(cand.id or "").strip())
        defects = _outcome_value(outcome, "defects", []) if outcome is not None else []
        if not isinstance(defects, list):
            defects = []
        payload.append(
            {
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
                "crop_qa_accepted": bool(
                    _outcome_value(outcome, "accepted", False)
                )
                if outcome is not None
                else False,
                "crop_qa_score": float(_outcome_value(outcome, "score", 0.0) or 0.0)
                if outcome is not None
                else 0.0,
                "crop_qa_defects": [str(item) for item in defects],
                "crop_qa_sidecar_path": str(
                    _outcome_value(outcome, "qa_sidecar_path", "") or ""
                )
                if outcome is not None
                else "",
                "crop_quality_profile": str(
                    _outcome_value(outcome, "quality_profile", "") or ""
                )
                if outcome is not None
                else "",
                "crop_rejection_reason": str(
                    _outcome_value(outcome, "rejection_reason", "") or ""
                )
                if outcome is not None
                else "",
                "meta": cand.meta or {},
                "features": candidate_features_payload(cand),
            }
        )
    return payload


def _candidates_path(output_dir: str, report_name: str, subdir: str) -> str:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    safe_subdir = safe_path_segment(subdir or "candidates", fallback="candidates")
    base = Path(output_dir) / safe_report_name / safe_subdir
    return str(base / "candidates.json")


def generate_candidate_pack(
    request: CandidateExtractRequest, ctx: RunContext
) -> CandidateExtractOutcome:
    logger.info(
        log_event(
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
        )
    )

    pdf_context = None
    try:
        pdf_ctx_resp = pdf_service.build_pdf_context(
            PdfContextBuildRequest(schema_version="1.0", path=request.pdf_path),
            ctx,
        )
        pdf_context = pdf_ctx_resp.context
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="candidate_pdf_context_failed",
                module=logger.name,
                fields={"pdf_path": request.pdf_path, "error": str(exc)},
            )
        )
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
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="candidate_extract_collected",
                module=logger.name,
                fields={
                    "candidate_count": len(candidates_resp.candidates),
                    "chart_count": chart_count,
                    "table_count": table_count,
                    "triage_failure_count": candidates_resp.stats.triage_failure_count,
                    "degraded_page_count": len(candidates_resp.stats.degraded_pages),
                },
            )
        )

        crop_paths: List[str] = []
        crop_map: Dict[str, str] = {}
        crop_outcomes: Dict[str, object] = {}
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
                    mode="publication_strict",
                    pdf_context=pdf_context,
                ),
                ctx,
            )
            crop_paths = crop_resp.paths
            crop_outcomes = _outcomes_by_candidate_id(
                getattr(crop_resp, "outcomes", [])
            )
            if crop_outcomes:
                crop_map = {
                    candidate_id: str(_outcome_value(outcome, "path", "") or "")
                    for candidate_id, outcome in crop_outcomes.items()
                    if bool(_outcome_value(outcome, "accepted", False))
                    and str(_outcome_value(outcome, "path", "") or "").strip()
                }
            else:
                crop_map = {
                    item.id: path for item, path in zip(items, crop_paths, strict=False)
                }
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="candidate_extract_crops_complete",
                    module=logger.name,
                    fields={"crop_count": len(crop_paths)},
                )
            )

        payload = {
            "schema_version": "1.0",
            "report_id": request.report_id,
            "report_name": request.report_name,
            "pdf_path": request.pdf_path,
            "candidate_count": len(candidates_resp.candidates),
            "chart_count": chart_count,
            "table_count": table_count,
            "degraded_pages": [
                {
                    "page": item.page,
                    "stage": item.stage,
                    "reason_code": item.reason_code,
                    "policy": item.policy,
                    "message": item.message,
                }
                for item in candidates_resp.stats.degraded_pages
            ],
            "candidates": _candidate_payload(
                candidates_resp.candidates, crop_map, crop_outcomes
            ),
        }
        output_path = _candidates_path(
            request.output_dir, request.report_name, request.subdir
        )
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=output_path,
                content=json.dumps(payload, ensure_ascii=True, indent=2).encode(
                    "utf-8"
                ),
                make_parents=True,
            ),
            ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="candidate_extract_saved",
                module=logger.name,
                fields={"candidates_path": output_path},
            )
        )

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
