from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class Candidate:
    schema_version: str = field(metadata={"doc": "Candidate schema version."})
    id: str = field(metadata={"doc": "Candidate identifier."})
    kind: str = field(metadata={"doc": "Candidate type: chart|table."})
    page: int = field(metadata={"doc": "Page number (0-based)."})
    bbox: Tuple[float, float, float, float] = field(metadata={"doc": "Bounding box coordinates."})
    preview_text: str = field(metadata={"doc": "Preview text/caption snippet."})
    caption: Optional[str] = field(default=None, metadata={"doc": "Detected caption text, if any."})
    thumb_path: Optional[str] = field(default=None, metadata={"doc": "Relative thumbnail path, if any."})
    meta: Optional[Dict[str, Any]] = field(default=None, metadata={"doc": "Additional metadata."})
