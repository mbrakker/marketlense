"""Small deterministic helpers for six-coefficient 2D affine transforms."""

from __future__ import annotations

import math
from typing import Sequence

AffineTransform = tuple[float, float, float, float, float, float]
BoundingBox = tuple[float, float, float, float]


def transform_bbox(bbox: Sequence[float], transform: Sequence[float]) -> BoundingBox:
    """Map all four bbox corners and return their axis-aligned enclosing box."""
    if len(bbox) != 4 or len(transform) != 6:
        raise ValueError("bbox and affine transform must contain four and six values")
    values = tuple(float(value) for value in (*bbox, *transform))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("bbox and affine transform values must be finite")
    x0, y0, x1, y1, a, b, c, d, e, f = values
    if x0 >= x1 or y0 >= y1:
        raise ValueError("bbox must be ordered and non-degenerate")
    points = (
        (a * x + c * y + e, b * x + d * y + f)
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    )
    transformed = tuple(points)
    xs = tuple(point[0] for point in transformed)
    ys = tuple(point[1] for point in transformed)
    result = (min(xs), min(ys), max(xs), max(ys))
    if (
        not all(math.isfinite(value) for value in result)
        or result[0] >= result[2]
        or result[1] >= result[3]
    ):
        raise ValueError("affine transform produced invalid bbox geometry")
    return result
