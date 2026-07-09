"""Crop-region artifact coordination for PDF candidates.

This module owns crop-region ordering, cache fingerprints, filenames, and
artifact writes while delegating geometry and image operations to siblings.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Optional

import pymupdf as fitz
from PIL import Image

from src.contracts.report_assets import CropRequest, CropResponse
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.services._pdf._crop.geometry import (
    _legacy_chart_border_trim,
    _tighten_chart_crop_rect,
    _tighten_crop_rect_for_strict_mode,
    _tighten_table_crop_rect,
)
from src.services._pdf._crop.image_ops import (
    PDF_CROP_EXCEPTIONS,
    _content_aware_trim,
    _render_clip_image,
    _stack_crop_images,
    _trim_uniform_border,
    verify_crop_image,
)
from src.services._pdf._crop.table_continuation import (
    _build_table_continuation_augments,
)
from src.services._pdf.fingerprint_cache import (
    CROP_REGION_ARTIFACT_VERSION,
    PdfArtifactFingerprintDescriptor,
    build_page_content_fingerprint,
    resolve_artifact_cache,
    write_artifact_sidecar,
)
from src.services._pdf.page_artifacts import create_page_artifact_cache
from src.services._pdf.shared import crop_logger
from src.utils.logging import log_event
from src.utils.path_utils import bounded_artifact_filename, safe_path_segment
from src.utils.slugify import slugify

CROP_FILENAME_ID_MAX_LEN = 96
CROP_FILENAME_MAX_LEN = 96


@dataclass(frozen=True)
class _ResolvedCropRegion:
    index: int
    item: CropItem
    rect: fitz.Rect
    filename: str


def _crop_output_filename(report_name: str, item: CropItem, idx: int) -> str:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    item_slug = slugify(str(item.id or ""))
    if not item_slug:
        item_slug = f"item-{idx}"
    if len(item_slug) > CROP_FILENAME_ID_MAX_LEN:
        item_slug = item_slug[:CROP_FILENAME_ID_MAX_LEN]
    return bounded_artifact_filename(
        f"{safe_report_name}-{item_slug}",
        compact_stem=item_slug,
        extension=".png",
        max_length=CROP_FILENAME_MAX_LEN,
    )


def crop_regions(request: CropRequest, ctx: RunContext) -> CropResponse:
    artifact_cache = (
        getattr(request.pdf_context, "page_artifact_cache", None)
        if request.pdf_context is not None
        else None
    ) or create_page_artifact_cache()
    crop_logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_regions_start",
            module=crop_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "count": len(request.items),
                "subdir": request.subdir,
                "mode": request.mode,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
    paths = _crop_regions(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        request.subdir,
        request.items,
        pad=request.pad,
        mode=request.mode,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
        artifact_cache=artifact_cache,
        ctx=ctx,
    )
    crop_logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_regions_complete",
            module=crop_logger.name,
            fields={
                "count": len(paths),
                "page_artifact_cache": artifact_cache.stats(),
            },
        )
    )
    return CropResponse(schema_version="1.0", paths=paths)


def _crop_regions(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    subdir: str,
    items: Iterable[CropItem],
    pad: int = 8,
    mode: str = "legacy",
    doc: Optional[fitz.Document] = None,
    artifact_cache=None,
    ctx: RunContext | None = None,
) -> List[str]:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    safe_subdir = safe_path_segment(subdir or "slices", fallback="slices")
    output_dir = Path(out_dir) / safe_report_name / safe_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    items_list = list(items)
    page_fingerprint_cache: dict[int, str] = {}
    local_doc = doc or fitz.open(pdf_path)
    try:
        regions: list[_ResolvedCropRegion] = []
        for idx, it in enumerate(items_list):
            pno = it.page
            x0, y0, x1, y1 = it.bbox
            page = local_doc[pno]
            rect = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
            effective_mode = _effective_crop_mode(mode, it.type)
            if effective_mode == "chart_strict" or it.type == "chart":
                rect = _tighten_chart_crop_rect(page, rect)
            elif effective_mode == "table_strict" or it.type == "table":
                rect = _tighten_table_crop_rect(page, rect)
            if effective_mode in {
                "table_strict",
                "chart_strict",
                "figure_strict",
                "publication_strict",
            }:
                rect = _tighten_crop_rect_for_strict_mode(
                    page,
                    rect,
                    mode=effective_mode,
                )
            if rect.is_empty:
                continue
            regions.append(
                _ResolvedCropRegion(
                    index=idx,
                    item=it,
                    rect=rect,
                    filename=_crop_output_filename(safe_report_name, it, idx),
                )
            )

        augments = _build_table_continuation_augments(
            local_doc,
            regions,
            artifact_cache=artifact_cache,
        )

        for region in regions:
            it = region.item
            page = local_doc[it.page]
            rel = Path(safe_report_name) / safe_subdir / region.filename
            output_path = output_dir / region.filename
            content_fingerprint_payload = {
                "page": build_page_content_fingerprint(
                    page,
                    per_page_cache=page_fingerprint_cache,
                )
            }
            augment = augments.get(region.index)
            if augment is not None and augment.prepend_page is not None:
                content_fingerprint_payload["prepend_page"] = (
                    build_page_content_fingerprint(
                        local_doc[augment.prepend_page],
                        per_page_cache=page_fingerprint_cache,
                    )
                )
            if augment is not None and augment.append_page is not None:
                content_fingerprint_payload["append_page"] = (
                    build_page_content_fingerprint(
                        local_doc[augment.append_page],
                        per_page_cache=page_fingerprint_cache,
                    )
                )
            descriptor = PdfArtifactFingerprintDescriptor(
                artifact_kind="crop_region",
                source_pdf_path=pdf_path,
                output_rel_path=rel.as_posix(),
                page=int(it.page),
                artifact_identity=json.dumps(
                    {
                        "item_id": str(it.id or ""),
                        "item_type": str(it.type or ""),
                        "page": int(it.page),
                        "bbox": [round(float(value), 3) for value in it.bbox],
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_fingerprint=hashlib.sha256(
                    json.dumps(
                        content_fingerprint_payload,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                settings_payload={
                    "mode": str(mode or ""),
                    "effective_mode": _effective_crop_mode(mode, it.type),
                    "pad": int(pad),
                    "subdir": safe_subdir,
                    "resolved_rect": [
                        round(float(region.rect.x0), 3),
                        round(float(region.rect.y0), 3),
                        round(float(region.rect.x1), 3),
                        round(float(region.rect.y1), 3),
                    ],
                    "prepend_page": (
                        int(augment.prepend_page)
                        if augment is not None and augment.prepend_page is not None
                        else None
                    ),
                    "append_page": (
                        int(augment.append_page)
                        if augment is not None and augment.append_page is not None
                        else None
                    ),
                    "prepend_rect": (
                        [
                            round(float(augment.prepend_rect.x0), 3),
                            round(float(augment.prepend_rect.y0), 3),
                            round(float(augment.prepend_rect.x1), 3),
                            round(float(augment.prepend_rect.y1), 3),
                        ]
                        if augment is not None and augment.prepend_rect is not None
                        else None
                    ),
                    "append_rect": (
                        [
                            round(float(augment.append_rect.x0), 3),
                            round(float(augment.append_rect.y0), 3),
                            round(float(augment.append_rect.x1), 3),
                            round(float(augment.append_rect.y1), 3),
                        ]
                        if augment is not None and augment.append_rect is not None
                        else None
                    ),
                },
                artifact_version=CROP_REGION_ARTIFACT_VERSION,
            )
            cache_status = resolve_artifact_cache(descriptor, output_path)
            if cache_status.hit:
                if ctx is not None:
                    crop_logger.info(
                        log_event(
                            ctx,
                            role="service",
                            event="crop_region_cache_hit",
                            module=crop_logger.name,
                            fields={
                                "cache_key": cache_status.cache_key,
                                "source_artifact": cache_status.output_rel_path,
                                "validity_reason": cache_status.reason,
                                "page": int(it.page),
                                "item_id": str(it.id or ""),
                            },
                        )
                    )
                paths.append(rel.as_posix())
                continue
            pix = page.get_pixmap(
                matrix=fitz.Matrix(2, 2), clip=region.rect, alpha=False
            )
            img: Optional[Image.Image] = None
            effective_mode = _effective_crop_mode(mode, it.type)
            trim_amounts = (0, 0, 0, 0)
            repair_actions: list[str] = []
            if effective_mode == "figure_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(
                        img,
                        allow_top=True,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            elif effective_mode == "table_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if mode == "publication_strict":
                        img, trim_amounts = _content_aware_trim(
                            img,
                            crop_type="table",
                            allow_top=False,
                            allow_bottom=True,
                            allow_left=True,
                            allow_right=True,
                        )
                    else:
                        img = _trim_uniform_border(
                            img,
                            allow_top=False,
                            allow_bottom=True,
                            allow_left=True,
                            allow_right=True,
                        )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            elif effective_mode == "chart_strict" or it.type == "chart":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if effective_mode == "chart_strict":
                        if mode == "publication_strict":
                            img, trim_amounts = _content_aware_trim(
                                img,
                                crop_type="chart",
                                allow_top=True,
                                allow_bottom=True,
                                allow_left=True,
                                allow_right=True,
                            )
                        else:
                            img = _trim_uniform_border(
                                img,
                                allow_top=True,
                                allow_bottom=True,
                                allow_left=True,
                                allow_right=True,
                            )
                    else:
                        img = _legacy_chart_border_trim(
                            page,
                            region.rect,
                            img,
                            artifact_cache=artifact_cache,
                        )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            elif mode == "publication_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img, trim_amounts = _content_aware_trim(
                        img,
                        crop_type="figure",
                        allow_top=True,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            if it.type == "table" and augment is not None:
                try:
                    base_img = img or Image.frombytes(
                        "RGB", (pix.width, pix.height), pix.samples
                    )
                    stack: list[Image.Image] = []
                    if (
                        augment.prepend_page is not None
                        and augment.prepend_rect is not None
                    ):
                        stack.append(
                            _render_clip_image(
                                local_doc[augment.prepend_page], augment.prepend_rect
                            )
                        )
                    stack.append(base_img)
                    if (
                        augment.append_page is not None
                        and augment.append_rect is not None
                    ):
                        stack.append(
                            _render_clip_image(
                                local_doc[augment.append_page], augment.append_rect
                            )
                        )
                    img = _stack_crop_images(stack)
                except PDF_CROP_EXCEPTIONS:
                    img = img or Image.frombytes(
                        "RGB", (pix.width, pix.height), pix.samples
                    )

            qa_result = None
            if mode == "publication_strict":
                if img is None:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                qa_result = verify_crop_image(img, crop_type=_qa_crop_type(it.type))
                for repair_index in range(2):
                    if qa_result.get("accepted"):
                        break
                    defects = set(qa_result.get("defect_labels") or [])
                    repairable = {
                        "neighbor_contamination",
                        "edge_clipped_content",
                    }
                    if not defects.intersection(repairable):
                        break
                    repaired, repaired_trim = _content_aware_trim(
                        img,
                        crop_type=_qa_crop_type(it.type),
                        allow_top=True,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                    repaired_qa = verify_crop_image(
                        repaired, crop_type=_qa_crop_type(it.type)
                    )
                    if float(repaired_qa.get("total_score") or 0.0) <= float(
                        qa_result.get("total_score") or 0.0
                    ):
                        break
                    img = repaired
                    qa_result = repaired_qa
                    trim_amounts = tuple(
                        int(trim_amounts[index]) + int(repaired_trim[index])
                        for index in range(4)
                    )
                    repair_actions.append(f"content_aware_trim:{repair_index + 1}")
                _write_crop_diagnostics(
                    output_path=output_path,
                    mode=mode,
                    effective_mode=effective_mode,
                    item=it,
                    region=region,
                    trim_amounts=trim_amounts,
                    qa_result=qa_result,
                    repair_actions=repair_actions,
                )
                if not qa_result.get("accepted"):
                    if ctx is not None:
                        crop_logger.info(
                            log_event(
                                ctx,
                                role="service",
                                event="crop_region_publication_rejected",
                                module=crop_logger.name,
                                fields={
                                    "source_artifact": rel.as_posix(),
                                    "page": int(it.page),
                                    "item_id": str(it.id or ""),
                                    "defect_labels": qa_result.get("defect_labels"),
                                    "total_score": qa_result.get("total_score"),
                                },
                            )
                        )
                    continue

            if img is not None:
                img.save(output_path.as_posix())
            else:
                pix.save(output_path.as_posix())
            write_artifact_sidecar(descriptor, output_path)
            if ctx is not None:
                crop_logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="crop_region_cache_store",
                        module=crop_logger.name,
                        fields={
                            "cache_key": cache_status.cache_key,
                            "source_artifact": rel.as_posix(),
                            "validity_reason": cache_status.reason,
                            "page": int(it.page),
                            "item_id": str(it.id or ""),
                        },
                    )
                )
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths


def _effective_crop_mode(mode: str, item_type: str) -> str:
    if mode != "publication_strict":
        return mode
    if item_type == "table":
        return "table_strict"
    if item_type == "chart":
        return "chart_strict"
    return "publication_strict"


def _qa_crop_type(item_type: str) -> str:
    if item_type == "table":
        return "table"
    if item_type == "chart":
        return "chart"
    return "figure"


def _write_crop_diagnostics(
    *,
    output_path: Path,
    mode: str,
    effective_mode: str,
    item: CropItem,
    region: _ResolvedCropRegion,
    trim_amounts: tuple[int, int, int, int],
    qa_result: dict[str, object],
    repair_actions: list[str],
) -> None:
    diagnostics = {
        "schema_version": "1.0",
        "candidate_id": str(item.id or ""),
        "candidate_type": str(item.type or ""),
        "page": int(item.page),
        "mode": mode,
        "effective_mode": effective_mode,
        "original_bbox": [round(float(value), 3) for value in item.bbox],
        "final_bbox": [
            round(float(region.rect.x0), 3),
            round(float(region.rect.y0), 3),
            round(float(region.rect.x1), 3),
            round(float(region.rect.y1), 3),
        ],
        "render_scale": 2,
        "trims": {
            "top": int(trim_amounts[0]),
            "bottom": int(trim_amounts[1]),
            "left": int(trim_amounts[2]),
            "right": int(trim_amounts[3]),
        },
        "qa": qa_result,
        "repair_actions": repair_actions,
        "accepted": bool(qa_result.get("accepted")),
        "rejection_reason": ",".join(
            str(label) for label in qa_result.get("defect_labels") or []
        ),
    }
    output_path.with_suffix(output_path.suffix + ".qa.json").write_text(
        json.dumps(diagnostics, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "CROP_FILENAME_ID_MAX_LEN",
    "CROP_FILENAME_MAX_LEN",
    "_ResolvedCropRegion",
    "_crop_output_filename",
    "crop_regions",
    "_crop_regions",
    "_effective_crop_mode",
    "_write_crop_diagnostics",
]
