from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PdfContext:
    schema_version: str = field(metadata={"doc": "PDF context schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF used to open handles."})
    fitz_doc: Optional[Any] = field(default=None, metadata={"doc": "Pre-opened PyMuPDF document handle, if available."})
    pypdf_reader: Optional[Any] = field(default=None, metadata={"doc": "Pre-opened pypdf PdfReader handle, if available."})
    page_artifact_cache: Optional[Any] = field(
        default=None,
        metadata={
            "doc": "Optional internal per-page artifact cache reused across PDF candidate and crop passes."
        },
    )

    def close(self) -> None:
        """Close any managed PDF handles. Failures are swallowed to keep cleanup best-effort."""
        try:
            if self.fitz_doc is not None:
                close_fn = getattr(self.fitz_doc, "close", None)
                if callable(close_fn):
                    close_fn()
        except Exception:
            pass
        try:
            if self.pypdf_reader is not None:
                stream = getattr(self.pypdf_reader, "stream", None)
                if stream is not None:
                    close_fn = getattr(stream, "close", None)
                    if callable(close_fn):
                        close_fn()
        except Exception:
            pass


@dataclass(frozen=True)
class PdfContextBuildRequest:
    schema_version: str = field(metadata={"doc": "PDF context build request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    load_fitz: bool = field(default=True, metadata={"doc": "Whether to pre-open a PyMuPDF document handle."})
    load_pypdf: bool = field(default=True, metadata={"doc": "Whether to pre-open a pypdf reader handle."})


@dataclass(frozen=True)
class PdfContextBuildResponse:
    schema_version: str = field(metadata={"doc": "PDF context build response schema version."})
    context: PdfContext = field(metadata={"doc": "Prepared PDF context with any available handles."})
    fitz_error: Optional[str] = field(default=None, metadata={"doc": "Error message if PyMuPDF failed to open, if any."})
    pypdf_error: Optional[str] = field(default=None, metadata={"doc": "Error message if pypdf failed to open, if any."})
