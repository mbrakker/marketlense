from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class Candidate:
    schema_version: str
    id: str
    kind: str
    page: int
    bbox: Tuple[float, float, float, float]
    preview_text: str
    caption: Optional[str] = None
    thumb_path: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
