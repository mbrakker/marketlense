from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.pdf_context import PdfContext


@dataclass(frozen=True)
class PdfTextExtractRequest:
    schema_version: str = field(metadata={"doc": "PDF text extract request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    max_pages: int = field(metadata={"doc": "Maximum number of pages to extract."})
    max_chars: int = field(metadata={"doc": "Maximum number of characters to return."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class PdfTextExtractResponse:
    schema_version: str = field(metadata={"doc": "PDF text extract response schema version."})
    text: str = field(metadata={"doc": "Extracted text content."})
    pages_extracted: int = field(metadata={"doc": "Number of pages extracted."})
    char_count: int = field(metadata={"doc": "Number of characters returned."})
    text_density: float = field(default=0.0, metadata={"doc": "Characters per page across the sampled pages."})


@dataclass(frozen=True)
class PdfTextSample:
    page_index: int = field(metadata={"doc": "Zero-based page index sampled."})
    page_number: int = field(metadata={"doc": "One-based page number sampled."})
    char_count: int = field(metadata={"doc": "Number of extracted characters for the page."})
    has_text: bool = field(metadata={"doc": "Whether the sampled page contains extractable text."})


@dataclass(frozen=True)
class PdfTextSampleRequest:
    schema_version: str = field(metadata={"doc": "PDF text sample request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    page_indices: List[int] = field(metadata={"doc": "Zero-based page indices to sample."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class PdfTextSampleResponse:
    schema_version: str = field(metadata={"doc": "PDF text sample response schema version."})
    samples: List[PdfTextSample] = field(metadata={"doc": "Extracted text samples for requested pages."})
    any_text: bool = field(metadata={"doc": "True when any sampled page contains extractable text."})
