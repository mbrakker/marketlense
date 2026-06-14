"""Shared deterministic metrics for PDF candidate families."""

from __future__ import annotations

import math


def bounded_quality(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def candidate_ocr_density(text_chars: int, area_frac: float) -> float:
    if text_chars <= 0 or area_frac <= 0.0:
        return 0.0
    return round(float(text_chars) / max(1.0, float(area_frac) * 100.0), 2)
