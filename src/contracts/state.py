from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StateCheckRequest:
    schema_version: str
    file_id: str
    md5: str


@dataclass(frozen=True)
class StateRecordRequest:
    schema_version: str
    file_id: str
    md5: str
    openai_file_id: Optional[str]


@dataclass(frozen=True)
class StateGetRequest:
    schema_version: str
    file_id: str


@dataclass(frozen=True)
class StateGetResponse:
    schema_version: str
    file_id: str
    md5: str
    processed_at: int
    openai_file_id: Optional[str]


@dataclass(frozen=True)
class StatePublishCheckRequest:
    schema_version: str
    file_id: str


@dataclass(frozen=True)
class StatePublishRecordRequest:
    schema_version: str
    file_id: str
    md5: str
    wp_post_id: int
    wp_post_url: str


@dataclass(frozen=True)
class StatePublishGetResponse:
    schema_version: str
    file_id: str
    md5: str
    published_at: int
    wp_post_id: int
    wp_post_url: str
