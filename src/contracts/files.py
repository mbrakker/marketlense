from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ReadTextRequest:
    schema_version: str
    path: str


@dataclass(frozen=True)
class ReadTextResponse:
    schema_version: str
    path: str
    content: str


@dataclass(frozen=True)
class ReadBytesRequest:
    schema_version: str
    path: str


@dataclass(frozen=True)
class ReadBytesResponse:
    schema_version: str
    path: str
    content: bytes


@dataclass(frozen=True)
class ListHtmlRequest:
    schema_version: str
    root_dir: str


@dataclass(frozen=True)
class ListHtmlResponse:
    schema_version: str
    root_dir: str
    html_paths: List[str]
