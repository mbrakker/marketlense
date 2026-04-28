from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.pdf_context import PdfContext


@dataclass(frozen=True)
class PdfEofCheckRequest:
    schema_version: str = field(
        metadata={"doc": "PDF EOF check request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})


@dataclass(frozen=True)
class PdfEofCheckResponse:
    schema_version: str = field(
        metadata={"doc": "PDF EOF check response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    has_eof: bool = field(metadata={"doc": "True if EOF marker was detected."})


@dataclass(frozen=True)
class PdfInfoRequest:
    schema_version: str = field(metadata={"doc": "PDF info request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    pdf_context: Optional[PdfContext] = field(
        default=None, metadata={"doc": "Optional pre-opened PDF context for reuse."}
    )


@dataclass(frozen=True)
class PdfInfoResponse:
    schema_version: str = field(metadata={"doc": "PDF info response schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    page_count: int = field(metadata={"doc": "Total number of pages in the PDF."})
    metadata: dict[str, str] = field(
        default_factory=dict, metadata={"doc": "Flattened PDF document metadata."}
    )
