from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Tuple


@dataclass
class Quote:
    text: str
    author: str = "Unknown"
    schema_version: str = "1.0"


@dataclass
class Figure:
    title: str
    evidence: str
    schema_version: str = "1.0"


@dataclass
class ReportPayload:
    tldr: str
    insights: List[str]
    quote: Quote
    figure: Figure
    commentary: str
    source: str
    _openai_file_id: str = ""
    _figure_image: str = ""
    _figure_gallery: List[str] = field(default_factory=list)
    _figure_top: str = ""
    schema_version: str = "1.0"

    def to_dict(self) -> dict:
        result = asdict(self)
        result["quote"] = asdict(self.quote)
        result["figure"] = asdict(self.figure)
        return result


@dataclass
class RankedCandidate:
    id: str
    type: str
    score: int
    schema_version: str = "1.0"


@dataclass
class CropItem:
    id: str
    type: str
    score: float
    page: int
    bbox: Tuple[float, float, float, float]
    schema_version: str = "1.0"
