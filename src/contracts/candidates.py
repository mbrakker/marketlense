from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class CandidateFeatures:
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Candidate feature schema version."},
    )
    area_frac: float = field(
        default=0.0,
        metadata={"doc": "Candidate area as a fraction of page area."},
    )
    aspect: float = field(
        default=0.0,
        metadata={"doc": "Candidate width divided by height."},
    )
    text_lines: int = field(
        default=0,
        metadata={"doc": "Text line count inside the candidate bbox."},
    )
    text_chars: int = field(
        default=0,
        metadata={"doc": "Text character count inside the candidate bbox."},
    )
    text_ratio: float = field(
        default=0.0,
        metadata={"doc": "Candidate text characters as a fraction of page text."},
    )
    rows: int = field(
        default=0,
        metadata={"doc": "Detected table row count, or 0 when not applicable."},
    )
    cols: int = field(
        default=0,
        metadata={"doc": "Detected table column count, or 0 when not applicable."},
    )
    numeric_ratio: float = field(
        default=0.0,
        metadata={
            "doc": "Fraction of detected table cells or lines with numeric content."
        },
    )
    avg_words_per_cell: float = field(
        default=0.0,
        metadata={"doc": "Average words per table cell, or 0 when not applicable."},
    )
    method: str = field(
        default="",
        metadata={"doc": "Extraction method that produced the candidate."},
    )


@dataclass(frozen=True)
class Candidate:
    schema_version: str = field(metadata={"doc": "Candidate schema version."})
    id: str = field(metadata={"doc": "Candidate identifier."})
    kind: str = field(metadata={"doc": "Candidate type: chart|table."})
    page: int = field(metadata={"doc": "Page number (0-based)."})
    bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Bounding box coordinates."}
    )
    preview_text: str = field(metadata={"doc": "Preview text/caption snippet."})
    caption: Optional[str] = field(
        default=None, metadata={"doc": "Detected caption text, if any."}
    )
    thumb_path: Optional[str] = field(
        default=None, metadata={"doc": "Relative thumbnail path, if any."}
    )
    meta: Optional[Dict[str, Any]] = field(
        default=None, metadata={"doc": "Additional metadata."}
    )
    features: Optional[CandidateFeatures] = field(
        default=None,
        metadata={"doc": "Typed feature contract used by ranking and crop decisions."},
    )
