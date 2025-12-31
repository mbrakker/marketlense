from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PdfEofCheckRequest:
    schema_version: str = field(metadata={"doc": "PDF EOF check request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})


@dataclass(frozen=True)
class PdfEofCheckResponse:
    schema_version: str = field(metadata={"doc": "PDF EOF check response schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    has_eof: bool = field(metadata={"doc": "True if EOF marker was detected."})
