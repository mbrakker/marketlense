"""Lightweight cached page artifacts for PDF candidate extraction.

This module keeps repeated text-dictionary parsing out of hot extraction loops
without changing the public `pdf_service` boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable

import pymupdf as fitz


@dataclass(frozen=True)
class PdfPageArtifacts:
    text_dict: dict[str, Any]
    text_blocks: list[tuple[float, float, float, float, str]]
    image_block_rects: tuple[fitz.Rect, ...]
    text_block_count: int
    text_char_count: int
    full_page_scan_without_text: bool


@dataclass
class PdfPageArtifactCache:
    artifacts_by_page: dict[int, PdfPageArtifacts] = field(default_factory=dict)
    text_block_pairs_by_page: dict[int, list[tuple[fitz.Rect, str]]] = field(
        default_factory=dict
    )
    crop_refine_rects_by_page: dict[int, list[fitz.Rect]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)

    def stats(self) -> dict[str, int]:
        return {
            "hits": int(self.hits),
            "misses": int(self.misses),
            "artifact_entries": len(self.artifacts_by_page),
            "text_block_pair_entries": len(self.text_block_pairs_by_page),
            "crop_refine_rect_entries": len(self.crop_refine_rects_by_page),
        }


def create_page_artifact_cache() -> PdfPageArtifactCache:
    return PdfPageArtifactCache()


def is_full_page_scan_without_text(page: fitz.Page, *, page_text: str = "") -> bool:
    normalized_text = str(page_text or "").strip()
    if not normalized_text:
        try:
            normalized_text = str(page.get_text("text") or "").strip()
        except Exception:
            return False
    if normalized_text:
        return False
    try:
        images = page.get_images(full=True) or []
    except Exception:
        return False
    if len(images) != 1:
        return False
    try:
        rects = page.get_image_rects(images[0][0]) or []
    except Exception:
        return False
    if len(rects) != 1:
        return False
    page_area = max(1.0, float(page.rect.get_area()))
    return (rects[0].get_area() / page_area) >= 0.85


def build_page_artifacts(page: fitz.Page) -> PdfPageArtifacts:
    try:
        text_dict = page.get_text("dict")
    except Exception:
        text_dict = {}

    text_blocks: list[tuple[float, float, float, float, str]] = []
    image_block_rects: list[fitz.Rect] = []
    text_block_count = 0
    text_char_count = 0

    for raw_block in text_dict.get("blocks") or []:
        bbox = raw_block.get("bbox") or []
        if len(bbox) != 4:
            continue
        try:
            rect = fitz.Rect(*map(float, bbox))
        except Exception:
            continue
        block_type = raw_block.get("type")
        if block_type == 1:
            image_block_rects.append(rect)
            continue
        if block_type != 0:
            continue
        line_texts: list[str] = []
        for line in raw_block.get("lines") or []:
            span_texts: list[str] = []
            for span in line.get("spans") or []:
                text = str(span.get("text") or "").strip()
                if text:
                    span_texts.append(text)
            if span_texts:
                line_texts.append(" ".join(span_texts).strip())
        if not line_texts:
            continue
        block_text = "\n".join(line for line in line_texts if line).strip()
        if not block_text:
            continue
        text_blocks.append((rect.x0, rect.y0, rect.x1, rect.y1, block_text))
        text_block_count += 1
        text_char_count += sum(len(line) for line in line_texts)

    page_area = max(1.0, float(page.rect.get_area()))
    full_page_scan_without_text = (
        text_block_count == 0
        and len(image_block_rects) == 1
        and (image_block_rects[0].get_area() / page_area) >= 0.85
    )

    return PdfPageArtifacts(
        text_dict=text_dict,
        text_blocks=text_blocks,
        image_block_rects=tuple(image_block_rects),
        text_block_count=text_block_count,
        text_char_count=text_char_count,
        full_page_scan_without_text=full_page_scan_without_text,
    )


def get_page_artifacts(
    page: fitz.Page,
    *,
    cache: PdfPageArtifactCache | None = None,
) -> PdfPageArtifacts:
    if cache is None:
        return build_page_artifacts(page)
    page_number = int(getattr(page, "number", 0) or 0)
    with cache.lock:
        cached = cache.artifacts_by_page.get(page_number)
        if cached is not None:
            cache.hits += 1
            return cached
        cache.misses += 1
    artifacts = build_page_artifacts(page)
    with cache.lock:
        existing = cache.artifacts_by_page.get(page_number)
        if existing is not None:
            cache.hits += 1
            return existing
        cache.artifacts_by_page[page_number] = artifacts
    return artifacts


def get_page_text_block_pairs(
    page: fitz.Page,
    *,
    cache: PdfPageArtifactCache | None = None,
) -> list[tuple[fitz.Rect, str]]:
    if cache is None:
        artifacts = build_page_artifacts(page)
        return [
            (fitz.Rect(x0, y0, x1, y1), text)
            for x0, y0, x1, y1, text in artifacts.text_blocks
            if text
        ]
    page_number = int(getattr(page, "number", 0) or 0)
    with cache.lock:
        cached = cache.text_block_pairs_by_page.get(page_number)
        if cached is not None:
            cache.hits += 1
            return list(cached)
        cache.misses += 1
    artifacts = get_page_artifacts(page, cache=cache)
    pairs = [
        (fitz.Rect(x0, y0, x1, y1), text)
        for x0, y0, x1, y1, text in artifacts.text_blocks
        if text
    ]
    with cache.lock:
        existing = cache.text_block_pairs_by_page.get(page_number)
        if existing is not None:
            cache.hits += 1
            return list(existing)
        cache.text_block_pairs_by_page[page_number] = pairs
    return list(pairs)


def get_crop_refine_text_block_rects(
    page: fitz.Page,
    *,
    cache: PdfPageArtifactCache | None = None,
    is_page_number_text: Callable[[str], bool] | None = None,
) -> list[fitz.Rect]:
    if cache is None:
        pairs = get_page_text_block_pairs(page, cache=None)
        return [
            fitz.Rect(block)
            for block, text in pairs
            if str(text or "").strip()
            and not (
                callable(is_page_number_text) and is_page_number_text(str(text or "").strip())
            )
        ]
    page_number = int(getattr(page, "number", 0) or 0)
    with cache.lock:
        cached = cache.crop_refine_rects_by_page.get(page_number)
        if cached is not None:
            cache.hits += 1
            return [fitz.Rect(rect) for rect in cached]
        cache.misses += 1
    pairs = get_page_text_block_pairs(page, cache=cache)
    rects = [
        fitz.Rect(block)
        for block, text in pairs
        if str(text or "").strip()
        and not (
            callable(is_page_number_text) and is_page_number_text(str(text or "").strip())
        )
    ]
    with cache.lock:
        existing = cache.crop_refine_rects_by_page.get(page_number)
        if existing is not None:
            cache.hits += 1
            return [fitz.Rect(rect) for rect in existing]
        cache.crop_refine_rects_by_page[page_number] = rects
    return [fitz.Rect(rect) for rect in rects]
