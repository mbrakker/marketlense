from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    schema_version: str
    path: str
    text: str
    sha256: str
