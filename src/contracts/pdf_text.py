from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PdfTextExtractRequest:
    schema_version: str = field(metadata={"doc": "PDF text extract request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    max_pages: int = field(metadata={"doc": "Maximum number of pages to extract."})
    max_chars: int = field(metadata={"doc": "Maximum number of characters to return."})


@dataclass(frozen=True)
class PdfTextExtractResponse:
    schema_version: str = field(metadata={"doc": "PDF text extract response schema version."})
    text: str = field(metadata={"doc": "Extracted text content."})
    pages_extracted: int = field(metadata={"doc": "Number of pages extracted."})
    char_count: int = field(metadata={"doc": "Number of characters returned."})
