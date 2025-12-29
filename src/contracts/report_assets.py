from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.contracts.candidates import Candidate
from src.contracts.report_models import CropItem, RankedCandidate


@dataclass(frozen=True)
class ExtractCandidatesRequest:
    schema_version: str
    pdf_path: str
    out_dir: str
    report_name: str


@dataclass(frozen=True)
class ExtractCandidatesResponse:
    schema_version: str
    candidates: List[Candidate]


@dataclass(frozen=True)
class FigureExtractRequest:
    schema_version: str
    pdf_path: str
    out_dir: str
    report_name: str


@dataclass(frozen=True)
class FigureExtractResponse:
    schema_version: str
    image_path: Optional[str]
    caption: Optional[str]


@dataclass(frozen=True)
class PreviewRequest:
    schema_version: str
    pdf_path: str
    out_dir: str
    report_name: str
    dpi: int = 144


@dataclass(frozen=True)
class PreviewResponse:
    schema_version: str
    image_path: Optional[str]


@dataclass(frozen=True)
class CropRequest:
    schema_version: str
    pdf_path: str
    out_dir: str
    report_name: str
    items: List[CropItem]
    pad: int = 8


@dataclass(frozen=True)
class CropResponse:
    schema_version: str
    paths: List[str]


@dataclass(frozen=True)
class RankRequest:
    schema_version: str
    candidates: List[Candidate]
    model: str
    api_key: str
    debug_dir: Optional[str] = None


@dataclass(frozen=True)
class RankResponse:
    schema_version: str
    results: List[RankedCandidate]


@dataclass(frozen=True)
class RenderRequest:
    schema_version: str
    data: Dict[str, Any]
    doc_name: str
    file_id: str
    out_dir: str
    preview_png: Optional[str] = None


@dataclass(frozen=True)
class RenderResponse:
    schema_version: str
    html_path: str
