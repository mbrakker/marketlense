# app/models.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


@dataclass
class Quote:
    """Quote dataclass for report payload."""
    text: str
    author: str = "Unknown"


@dataclass
class Figure:
    """Figure dataclass for report payload."""
    title: str
    evidence: str


@dataclass
class ReportPayload:
    """Report payload dataclass containing all analysis results from OpenAI."""
    tldr: str
    insights: List[str]  # exactly 5 strings
    quote: Quote
    figure: Figure
    commentary: str
    source: str
    _openai_file_id: str = ""
    _figure_image: str = ""
    _figure_gallery: List[str] = field(default_factory=list)
    _figure_top: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for Jinja2 template rendering."""
        result = asdict(self)
        # Convert nested dataclasses to dicts
        result["quote"] = asdict(self.quote)
        result["figure"] = asdict(self.figure)
        return result


@dataclass
class RankedCandidate:
    """Ranked candidate from LLM ranking."""
    id: str
    type: str  # "chart" | "table"
    score: int  # 0-100


@dataclass
class CropItem:
    """Item to crop from PDF."""
    id: str
    type: str  # "chart" | "table"
    score: float
    page: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1

