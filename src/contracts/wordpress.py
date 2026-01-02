from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class WordPressAuthSettings:
    schema_version: str = field(metadata={"doc": "WordPress auth settings schema version."})
    site_url: str = field(metadata={"doc": "WordPress site base URL."})
    username: Optional[str] = field(metadata={"doc": "WordPress username, if using app password."})
    app_password: Optional[str] = field(metadata={"doc": "WordPress application password (secret)."})
    bearer_token: Optional[str] = field(metadata={"doc": "WordPress bearer token (secret)."})
    post_status: str = field(metadata={"doc": "Default WordPress post status."})


@dataclass(frozen=True)
class WordPressMediaUploadRequest:
    schema_version: str = field(metadata={"doc": "Media upload request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    filename: str = field(metadata={"doc": "Filename to upload."})
    mime_type: str = field(metadata={"doc": "Content MIME type."})
    data: bytes = field(metadata={"doc": "Binary content to upload."})
    alt_text: Optional[str] = field(default=None, metadata={"doc": "Optional alt text."})


@dataclass(frozen=True)
class WordPressMediaUploadResponse:
    schema_version: str = field(metadata={"doc": "Media upload response schema version."})
    media_id: int = field(metadata={"doc": "WordPress media ID."})
    source_url: str = field(metadata={"doc": "WordPress media URL."})


@dataclass(frozen=True)
class WordPressPostCreateRequest:
    schema_version: str = field(metadata={"doc": "Post create request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    title: str = field(metadata={"doc": "Post title."})
    content_html: str = field(metadata={"doc": "Rendered HTML content."})
    status: str = field(metadata={"doc": "Post status."})
    slug: Optional[str] = field(default=None, metadata={"doc": "Optional post slug."})
    featured_media: Optional[int] = field(default=None, metadata={"doc": "Optional featured media ID."})
    categories: Optional[List[int]] = field(default=None, metadata={"doc": "Optional WordPress category IDs."})


@dataclass(frozen=True)
class WordPressPostCreateResponse:
    schema_version: str = field(metadata={"doc": "Post create response schema version."})
    post_id: int = field(metadata={"doc": "WordPress post ID."})
    link: str = field(metadata={"doc": "WordPress post URL."})
    status: str = field(metadata={"doc": "WordPress post status."})


@dataclass(frozen=True)
class WordPressPostLookupRequest:
    schema_version: str = field(metadata={"doc": "Post lookup request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    file_id: str = field(metadata={"doc": "Drive file ID to search for."})
    per_page: int = field(default=5, metadata={"doc": "Max posts to inspect."})


@dataclass(frozen=True)
class WordPressPostLookupResponse:
    schema_version: str = field(metadata={"doc": "Post lookup response schema version."})
    found: bool = field(metadata={"doc": "True if a matching post was found."})
    post_id: Optional[int] = field(default=None, metadata={"doc": "Matching post ID, if found."})
    link: Optional[str] = field(default=None, metadata={"doc": "Matching post URL, if found."})


@dataclass(frozen=True)
class WordPressCategoryTerm:
    schema_version: str = field(metadata={"doc": "Category term schema version."})
    slug: str = field(metadata={"doc": "Category slug."})
    name: str = field(metadata={"doc": "Category display name."})


@dataclass(frozen=True)
class WordPressCategoryEnsureRequest:
    schema_version: str = field(metadata={"doc": "Category ensure request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    categories: List[WordPressCategoryTerm] = field(metadata={"doc": "Category terms to ensure exist."})


@dataclass(frozen=True)
class WordPressCategoryEnsureResponse:
    schema_version: str = field(metadata={"doc": "Category ensure response schema version."})
    slug_to_id: Dict[str, int] = field(metadata={"doc": "Mapping of category slug to WordPress term ID."})


@dataclass(frozen=True)
class WordPressPostUpdateRequest:
    schema_version: str = field(metadata={"doc": "Post update request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    post_id: int = field(metadata={"doc": "WordPress post ID."})
    categories: List[int] = field(metadata={"doc": "Category IDs to assign to the post."})


@dataclass(frozen=True)
class WordPressPostUpdateResponse:
    schema_version: str = field(metadata={"doc": "Post update response schema version."})
    post_id: int = field(metadata={"doc": "Updated WordPress post ID."})
    link: Optional[str] = field(default=None, metadata={"doc": "Updated WordPress post URL, if returned."})
