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
class PdfIntegrityCheckRequest:
    schema_version: str = field(
        metadata={"doc": "PDF integrity-check request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})


@dataclass(frozen=True)
class PdfIntegrityCheckResponse:
    schema_version: str = field(
        metadata={"doc": "PDF integrity-check response schema version."}
    )
    path: str = field(metadata={"doc": "Validated local PDF path."})
    size_bytes: int = field(metadata={"doc": "Observed byte size."})
    sha256: str = field(metadata={"doc": "Observed SHA-256 digest."})
    md5: str = field(
        metadata={"doc": "Observed MD5 digest for source-version matching."}
    )
    validator_version: str = field(
        metadata={"doc": "Deterministic integrity-validator version."}
    )
    has_pdf_header: bool = field(metadata={"doc": "Whether bytes start with %PDF-."})
    has_eof: bool = field(metadata={"doc": "Whether the EOF marker is present."})
    parser_opened: bool = field(
        metadata={"doc": "Whether the parser opened the structural document."}
    )
    page_count: int = field(
        metadata={"doc": "Page count when structural parsing succeeded."}
    )
    failure_code: str = field(
        metadata={"doc": "Stable deterministic failure code; empty when valid."}
    )
    retryable: bool = field(
        metadata={
            "doc": "Whether a validation failure is transient rather than structural."
        }
    )
    validated_at_utc: str = field(metadata={"doc": "Validation observation timestamp."})


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
