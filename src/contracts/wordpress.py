from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class WordPressAuthSettings:
    schema_version: str = field(
        metadata={"doc": "WordPress auth settings schema version."}
    )
    site_url: str = field(metadata={"doc": "WordPress site base URL."})
    username: Optional[str] = field(
        metadata={"doc": "WordPress username, if using app password."}
    )
    app_password: Optional[str] = field(
        metadata={"doc": "WordPress application password (secret)."}
    )
    bearer_token: Optional[str] = field(
        metadata={"doc": "WordPress bearer token (secret)."}
    )
    post_status: str = field(metadata={"doc": "Default WordPress post status."})
    post_type: str = field(
        default="ml_report",
        metadata={
            "doc": "REST post type endpoint slug (for example: posts, ml_report)."
        },
    )
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for WordPress REST calls."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used for WordPress HTTPS verification."
        },
    )


@dataclass(frozen=True)
class WordPressPublisherProfileSeed:
    schema_version: str = field(
        metadata={"doc": "Publisher profile seed schema version."}
    )
    notion_page_id: str = field(
        metadata={"doc": "Source Notion publisher page identifier."}
    )
    notion_page_url: str = field(metadata={"doc": "Source Notion publisher page URL."})
    name: str = field(metadata={"doc": "Publisher display name."})
    slug: str = field(
        metadata={"doc": "Canonical WordPress term slug for the publisher."}
    )
    homepage: str = field(
        metadata={"doc": "Normalized publisher homepage URL, if available."}
    )
    self_presentation: str = field(
        metadata={"doc": "Publisher self-description copied from Notion."}
    )
    insights_url: str = field(
        metadata={
            "doc": "One or more normalized publisher insights URLs separated by newlines."
        }
    )
    icon_source: str = field(
        metadata={
            "doc": "Publisher icon source string from Notion (URL, data URI, or emoji)."
        }
    )


@dataclass(frozen=True)
class WordPressMediaUploadRequest:
    schema_version: str = field(
        metadata={"doc": "Media upload request schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    filename: str = field(metadata={"doc": "Filename to upload."})
    mime_type: str = field(metadata={"doc": "Content MIME type."})
    data: bytes = field(metadata={"doc": "Binary content to upload."})
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )
    alt_text: Optional[str] = field(
        default=None, metadata={"doc": "Optional alt text."}
    )


@dataclass(frozen=True)
class WordPressMediaUploadResponse:
    schema_version: str = field(
        metadata={"doc": "Media upload response schema version."}
    )
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
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )
    slug: Optional[str] = field(default=None, metadata={"doc": "Optional post slug."})
    featured_media: Optional[int] = field(
        default=None, metadata={"doc": "Optional featured media ID."}
    )
    categories: Optional[List[int]] = field(
        default=None, metadata={"doc": "Optional WordPress category IDs."}
    )
    tags: Optional[List[int]] = field(
        default=None, metadata={"doc": "Optional WordPress tag IDs."}
    )
    taxonomy_terms: Optional[Dict[str, List[int]]] = field(
        default=None,
        metadata={
            "doc": "Optional mapping of taxonomy REST base to WordPress term IDs."
        },
    )
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )


@dataclass(frozen=True)
class WordPressPostCreateResponse:
    schema_version: str = field(
        metadata={"doc": "Post create response schema version."}
    )
    post_id: int = field(metadata={"doc": "WordPress post ID."})
    link: str = field(metadata={"doc": "WordPress post URL."})
    status: str = field(metadata={"doc": "WordPress post status."})


@dataclass(frozen=True)
class WordPressPostLookupRequest:
    schema_version: str = field(metadata={"doc": "Post lookup request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    file_id: str = field(metadata={"doc": "Drive file ID to search for."})
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )
    per_page: int = field(default=5, metadata={"doc": "Max posts to inspect."})
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )


@dataclass(frozen=True)
class WordPressPostLookupResponse:
    schema_version: str = field(
        metadata={"doc": "Post lookup response schema version."}
    )
    found: bool = field(metadata={"doc": "True if a matching post was found."})
    post_id: Optional[int] = field(
        default=None, metadata={"doc": "Matching post ID, if found."}
    )
    link: Optional[str] = field(
        default=None, metadata={"doc": "Matching post URL, if found."}
    )


@dataclass(frozen=True)
class WordPressTaxonomyTerm:
    schema_version: str = field(
        metadata={"doc": "WordPress taxonomy term schema version."}
    )
    slug: str = field(metadata={"doc": "WordPress taxonomy term slug."})
    name: str = field(metadata={"doc": "WordPress taxonomy term display name."})


@dataclass(frozen=True)
class WordPressTaxonomyEnsureRequest:
    schema_version: str = field(
        metadata={"doc": "WordPress taxonomy ensure request schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    taxonomy_rest_base: str = field(
        metadata={"doc": "Taxonomy REST base endpoint slug to target."}
    )
    terms: List[WordPressTaxonomyTerm] = field(
        metadata={"doc": "Taxonomy terms to ensure exist."}
    )
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )


@dataclass(frozen=True)
class WordPressTaxonomyEnsureResponse:
    schema_version: str = field(
        metadata={"doc": "WordPress taxonomy ensure response schema version."}
    )
    slug_to_id: Dict[str, int] = field(
        metadata={"doc": "Mapping of taxonomy term slug to WordPress term ID."}
    )


@dataclass(frozen=True)
class WordPressTagEnsureRequest:
    schema_version: str = field(metadata={"doc": "Tag ensure request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    tags: List[str] = field(metadata={"doc": "Tag slugs to ensure exist."})
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )


@dataclass(frozen=True)
class WordPressTagEnsureResponse:
    schema_version: str = field(metadata={"doc": "Tag ensure response schema version."})
    slug_to_id: Dict[str, int] = field(
        metadata={"doc": "Mapping of tag slug to WordPress term ID."}
    )


@dataclass(frozen=True)
class WordPressPostUpdateRequest:
    schema_version: str = field(metadata={"doc": "Post update request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    post_id: int = field(metadata={"doc": "WordPress post ID."})
    categories: List[int] = field(
        metadata={"doc": "Category IDs to assign to the post."}
    )
    ssl_verify: bool = field(
        default=True,
        metadata={
            "doc": "Whether HTTPS certificates should be verified for this request."
        },
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional CA bundle path used when verifying HTTPS certificates."
        },
    )
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )


@dataclass(frozen=True)
class WordPressPostUpdateResponse:
    schema_version: str = field(
        metadata={"doc": "Post update response schema version."}
    )
    post_id: int = field(metadata={"doc": "Updated WordPress post ID."})
    link: Optional[str] = field(
        default=None, metadata={"doc": "Updated WordPress post URL, if returned."}
    )
