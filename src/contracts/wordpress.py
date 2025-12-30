from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WordPressAuthSettings:
    schema_version: str
    site_url: str
    username: Optional[str]
    app_password: Optional[str]
    bearer_token: Optional[str]
    post_status: str


@dataclass(frozen=True)
class WordPressMediaUploadRequest:
    schema_version: str
    base_url: str
    auth_header: str
    filename: str
    mime_type: str
    data: bytes
    alt_text: Optional[str] = None


@dataclass(frozen=True)
class WordPressMediaUploadResponse:
    schema_version: str
    media_id: int
    source_url: str


@dataclass(frozen=True)
class WordPressPostCreateRequest:
    schema_version: str
    base_url: str
    auth_header: str
    title: str
    content_html: str
    status: str
    slug: Optional[str] = None
    featured_media: Optional[int] = None


@dataclass(frozen=True)
class WordPressPostCreateResponse:
    schema_version: str
    post_id: int
    link: str
    status: str
