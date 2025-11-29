from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

@dataclass
class Candidate:
    id: str                 # "chart-<page>-<idx>" | "table-<page>-<idx>"
    kind: str               # "chart" | "table"
    page: int               # 0-based
    bbox: tuple[float,float,float,float]  # x0,y0,x1,y1 (PDF points)
    preview_text: str
    caption: Optional[str] = None
    thumb_path: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_public(self) -> Dict[str, Any]:
        return asdict(self)
