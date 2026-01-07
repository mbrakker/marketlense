from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.pdf_context import PdfContext


@dataclass(frozen=True)
class PdfContentsDetectionRequest:
    schema_version: str = field(metadata={"doc": "Contents detection request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    max_pages: int = field(default=8, metadata={"doc": "Max pages to scan from the start of the PDF."})
    min_headings: int = field(default=3, metadata={"doc": "Minimum heading-like entries required to confirm a contents/index page."})
    keywords: List[str] = field(
        default_factory=lambda: ["table of contents", "contents", "index"],
        metadata={"doc": "Case-insensitive keywords that indicate an index/contents page."},
    )
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class PdfContentsDetectionResponse:
    schema_version: str = field(metadata={"doc": "Contents detection response schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    has_contents: bool = field(metadata={"doc": "True when a contents/index page is detected."})
    page_index: int = field(metadata={"doc": "Zero-based page index for the detected contents page; -1 when not found."})
    page_number: int = field(metadata={"doc": "One-based page number for the detected contents page; 0 when not found."})
    heading: str = field(default="", metadata={"doc": "Matched heading keyword for the contents page, if any."})
    confidence: float = field(default=0.0, metadata={"doc": "Heuristic confidence score between 0 and 1."})
