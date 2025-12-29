from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PdfEofCheckRequest:
    schema_version: str
    path: str


@dataclass(frozen=True)
class PdfEofCheckResponse:
    schema_version: str
    path: str
    has_eof: bool
