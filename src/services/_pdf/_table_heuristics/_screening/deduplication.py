from __future__ import annotations

import math
from typing import Dict, List, Literal, Tuple

from ..models import _TableCandidate
from ..policy import TABLE_DEDUP_IOU

def _table_sort_key(cand: _TableCandidate) -> Tuple[float, float]:
    return (cand.bbox[1], cand.bbox[0])


def _table_quality(cand: _TableCandidate) -> Tuple[int, int, int, int]:
    method_bonus = 100 if cand.method == "ranked" else 0
    return (
        method_bonus,
        cand.row_count * cand.col_count,
        cand.non_empty_cells,
        cand.text_len,
    )


def _table_iou(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _table_containment_ratio(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    smaller = min(area_a, area_b)
    if smaller <= 0.0:
        return 0.0
    return inter / smaller


def _prefer_inner_lattice_table(
    smaller: _TableCandidate, larger: _TableCandidate
) -> bool:
    if smaller.method != "lattice" or larger.method != "stream":
        return False
    sx0, sy0, sx1, sy1 = smaller.bbox
    lx0, ly0, lx1, ly1 = larger.bbox
    smaller_width = max(1.0, sx1 - sx0)
    smaller_height = max(1.0, sy1 - sy0)
    larger_width = max(1.0, lx1 - lx0)
    larger_height = max(1.0, ly1 - ly0)
    width_ratio = smaller_width / larger_width
    height_ratio = smaller_height / larger_height
    return width_ratio >= 0.7 and height_ratio >= 0.75


class _TableDedupeSpatialIndex:
    _BIN_HEIGHT = 96.0

    def __init__(self) -> None:
        self._bins: Dict[int, List[int]] = {}
        self._candidate_bins: Dict[int, Tuple[int, ...]] = {}
        self._candidates: Dict[int, _TableCandidate] = {}

    def add(self, index: int, candidate: _TableCandidate) -> None:
        previous_bins = self._candidate_bins.get(index, ())
        for bucket in previous_bins:
            values = self._bins.get(bucket)
            if values is None:
                continue
            self._bins[bucket] = [value for value in values if value != index]

        buckets = tuple(self._buckets(candidate.bbox))
        for bucket in buckets:
            self._bins.setdefault(bucket, []).append(index)
        self._candidate_bins[index] = buckets
        self._candidates[index] = candidate

    def lookup(self, candidate: _TableCandidate) -> List[int]:
        matches: Dict[int, None] = {}
        for bucket in self._buckets(candidate.bbox):
            for index in self._bins.get(bucket, []):
                existing = self._candidates.get(index)
                if existing is None:
                    continue
                if self._intersects(candidate.bbox, existing.bbox):
                    matches[index] = None
        return sorted(matches)

    def _buckets(self, bbox: Tuple[float, float, float, float]) -> range:
        y0 = min(float(bbox[1]), float(bbox[3]))
        y1 = max(float(bbox[1]), float(bbox[3]))
        start = math.floor(y0 / self._BIN_HEIGHT)
        end = math.floor(max(y0, y1 - 0.000001) / self._BIN_HEIGHT)
        return range(start, end + 1)

    @staticmethod
    def _intersects(
        a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
    ) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0)


def _table_area(candidate: _TableCandidate) -> float:
    return max(
        0.0,
        (candidate.bbox[2] - candidate.bbox[0])
        * (candidate.bbox[3] - candidate.bbox[1]),
    )


def _preferred_duplicate_table(
    candidate: _TableCandidate,
    existing: _TableCandidate,
    *,
    containment: float,
    contained_table_preference: Literal["quality", "larger"],
) -> _TableCandidate:
    if containment >= 0.98:
        area_candidate = _table_area(candidate)
        area_existing = _table_area(existing)
        smaller, larger = (
            (candidate, existing) if area_candidate <= area_existing else (existing, candidate)
        )
        if contained_table_preference == "larger":
            preferred = (
                smaller if _prefer_inner_lattice_table(smaller, larger) else larger
            )
            if _table_quality(candidate) <= _table_quality(existing):
                return existing
            return preferred
        if _prefer_inner_lattice_table(smaller, larger):
            return smaller
        if _table_quality(candidate) <= _table_quality(existing):
            return existing
        return candidate
    if _table_quality(candidate) <= _table_quality(existing):
        return existing
    return candidate


def _dedupe_table_candidates(
    candidates: List[_TableCandidate],
    *,
    contained_table_preference: Literal["quality", "larger"] = "quality",
) -> List[_TableCandidate]:
    kept: List[_TableCandidate] = []
    index = _TableDedupeSpatialIndex()
    for cand in candidates:
        replaced = False
        for idx in index.lookup(cand):
            existing = kept[idx]
            iou = _table_iou(cand.bbox, existing.bbox)
            containment = _table_containment_ratio(cand.bbox, existing.bbox)
            ranked_overlap = containment >= 0.8 and (
                "ranked" in (cand.method, existing.method)
            )
            if iou >= TABLE_DEDUP_IOU or containment >= 0.98 or ranked_overlap:
                preferred = _preferred_duplicate_table(
                    cand,
                    existing,
                    containment=containment,
                    contained_table_preference=contained_table_preference,
                )
                kept[idx] = preferred
                index.add(idx, preferred)
                replaced = True
                break
        if not replaced:
            index.add(len(kept), cand)
            kept.append(cand)
    return kept
