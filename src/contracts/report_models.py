from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Tuple


@dataclass
class Quote:
    text: str = field(metadata={"doc": "Quoted text."})
    author: str = field(default="Unknown", metadata={"doc": "Quote author."})
    schema_version: str = field(default="1.0", metadata={"doc": "Quote schema version."})


@dataclass
class Figure:
    title: str = field(metadata={"doc": "Figure title."})
    evidence: str = field(metadata={"doc": "Figure evidence/description."})
    schema_version: str = field(default="1.0", metadata={"doc": "Figure schema version."})


@dataclass
class ReportPayload:
    tldr: str = field(metadata={"doc": "TL;DR summary."})
    insights: List[str] = field(metadata={"doc": "List of five insights."})
    quote: Quote = field(metadata={"doc": "Key quote extracted from the report."})
    figure: Figure = field(metadata={"doc": "Figure metadata."})
    commentary: str = field(metadata={"doc": "Commentary paragraph."})
    source: str = field(metadata={"doc": "Primary source URL, if any."})
    _openai_file_id: str = field(default="", metadata={"doc": "Internal OpenAI file ID, if any."})
    _figure_image: str = field(default="", metadata={"doc": "Relative path to primary figure image."})
    _figure_gallery: List[str] = field(default_factory=list, metadata={"doc": "Relative paths to figure gallery images."})
    _figure_top: str = field(default="", metadata={"doc": "Relative path to top-ranked figure image."})
    schema_version: str = field(default="1.0", metadata={"doc": "Report payload schema version."})

    def to_dict(self) -> dict:
        result = asdict(self)
        result["quote"] = asdict(self.quote)
        result["figure"] = asdict(self.figure)
        return result


@dataclass
class RankedCandidate:
    id: str = field(metadata={"doc": "Candidate identifier."})
    type: str = field(metadata={"doc": "Candidate type: chart|table."})
    score: int = field(metadata={"doc": "Ranking score (0-100)."})
    schema_version: str = field(default="1.0", metadata={"doc": "Ranked candidate schema version."})


@dataclass
class CropItem:
    id: str = field(metadata={"doc": "Candidate identifier."})
    type: str = field(metadata={"doc": "Candidate type: chart|table."})
    score: float = field(metadata={"doc": "Ranking score as float."})
    page: int = field(metadata={"doc": "Page number (0-based)."})
    bbox: Tuple[float, float, float, float] = field(metadata={"doc": "Bounding box coordinates."})
    schema_version: str = field(default="1.0", metadata={"doc": "Crop item schema version."})
