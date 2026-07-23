from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.run_budget import RunBudget, RunBudgetUsage


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
class WordPressPublishTargetPreflightRequest:
    schema_version: str = field(
        metadata={"doc": "WordPress publish-target preflight request schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    post_type: str = field(metadata={"doc": "REST post type endpoint slug."})
    ssl_verify: bool = field(
        default=True,
        metadata={"doc": "Whether HTTPS certificates should be verified."},
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional CA bundle path used for HTTPS verification."},
    )


@dataclass(frozen=True)
class WordPressPublishTargetPreflightResponse:
    schema_version: str = field(
        metadata={"doc": "WordPress publish-target preflight response schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL checked."})
    post_type: str = field(metadata={"doc": "REST post type endpoint slug checked."})
    endpoint: str = field(metadata={"doc": "Resolved REST endpoint checked."})
    reachable: bool = field(metadata={"doc": "True when the REST target is usable."})
    status_code: int = field(metadata={"doc": "HTTP status code returned."})


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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional governed budget for this WordPress write."},
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before this WordPress write."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
    )


@dataclass(frozen=True)
class WordPressMediaUploadResponse:
    schema_version: str = field(
        metadata={"doc": "Media upload response schema version."}
    )
    media_id: int = field(metadata={"doc": "WordPress media ID."})
    source_url: str = field(metadata={"doc": "WordPress media URL."})


@dataclass(frozen=True)
class WordPressMediaPrepareRequest:
    schema_version: str = field(
        metadata={"doc": "WordPress media preparation request schema version."}
    )
    filename: str = field(metadata={"doc": "Original upload filename."})
    mime_type: str = field(metadata={"doc": "Original upload MIME type."})
    data: bytes = field(metadata={"doc": "Original media bytes."})


@dataclass(frozen=True)
class WordPressMediaPrepareResponse:
    schema_version: str = field(
        metadata={"doc": "WordPress media preparation response schema version."}
    )
    filename: str = field(metadata={"doc": "Prepared upload filename."})
    mime_type: str = field(metadata={"doc": "Prepared upload MIME type."})
    data: bytes = field(metadata={"doc": "Prepared upload bytes."})
    optimized: bool = field(metadata={"doc": "True when image bytes were optimized."})
    reason: str = field(metadata={"doc": "Stable preparation outcome reason."})
    original_size_bytes: int = field(
        metadata={"doc": "Original payload size in bytes."}
    )
    prepared_size_bytes: int = field(
        metadata={"doc": "Prepared payload size in bytes."}
    )


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
    meta: Optional[Dict[str, object]] = field(
        default=None,
        metadata={
            "doc": "Validated WordPress post meta keyed by registered REST field name."
        },
    )
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional governed budget for this WordPress write."},
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before this WordPress write."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
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
class WordPressCardUpdateRequest:
    schema_version: str = field(
        metadata={"doc": "Card-contract update schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    post_id: int = field(metadata={"doc": "Existing WordPress post ID to update."})
    featured_media: int = field(
        metadata={"doc": "Canonical large card cover media ID."}
    )
    meta: Dict[str, object] = field(
        metadata={"doc": "Complete validated canonical card metadata."}
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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional governed budget for this WordPress write."},
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before this WordPress write."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
    )


# Preserve the report-only contract name for existing callers during migration.
WordPressReportCardUpdateRequest = WordPressCardUpdateRequest


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
class WordPressPostReadRequest:
    schema_version: str = field(metadata={"doc": "Post read request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    post_id: int = field(metadata={"doc": "WordPress post ID to read."})
    file_id: str = field(
        metadata={"doc": "Expected immutable Drive file ID for verification."}
    )
    ssl_verify: bool = field(
        default=True,
        metadata={"doc": "Whether HTTPS certificates should be verified."},
    )
    ca_bundle_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional CA bundle path used when verifying HTTPS."},
    )
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )


@dataclass(frozen=True)
class WordPressPostLookupBatchRequest:
    schema_version: str = field(
        metadata={"doc": "Batch post lookup request schema version."}
    )
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(metadata={"doc": "Authorization header value."})
    file_ids: List[str] = field(
        metadata={"doc": "Drive file IDs to search for in one preflight batch."}
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
    per_page: int = field(default=5, metadata={"doc": "Max posts to inspect per file."})
    post_type: str = field(
        default="posts", metadata={"doc": "REST post type endpoint slug."}
    )


@dataclass(frozen=True)
class WordPressPostLookupBatchItem:
    schema_version: str = field(
        metadata={"doc": "Batch post lookup item schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID searched in WordPress."})
    found: bool = field(metadata={"doc": "True when a matching post was found."})
    post_id: Optional[int] = field(
        default=None, metadata={"doc": "Matching post ID, if found."}
    )
    link: Optional[str] = field(
        default=None, metadata={"doc": "Matching post URL, if found."}
    )
    error_code: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed lookup error code captured for this file, if any."},
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Lookup error message captured for this file, if any."},
    )
    retryable: Optional[bool] = field(
        default=None,
        metadata={"doc": "Whether the captured lookup error is retryable, if any."},
    )


@dataclass(frozen=True)
class WordPressPostLookupBatchResponse:
    schema_version: str = field(
        metadata={"doc": "Batch post lookup response schema version."}
    )
    items: List[WordPressPostLookupBatchItem] = field(
        metadata={"doc": "Per-file batch lookup results for publish preflight."}
    )


@dataclass(frozen=True)
class WordPressTaxonomyTerm:
    schema_version: str = field(
        metadata={"doc": "WordPress taxonomy term schema version."}
    )
    slug: str = field(metadata={"doc": "WordPress taxonomy term slug."})
    name: str = field(metadata={"doc": "WordPress taxonomy term display name."})
    description: str = field(
        default="",
        metadata={
            "doc": "Approved public term description written to the WordPress term description."
        },
    )
    definition: str = field(
        default="",
        metadata={
            "doc": "Approved topic definition stored as WordPress term metadata."
        },
    )
    include_when: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Approved topic inclusion rules stored as WordPress term metadata."
        },
    )
    exclude_when: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Approved topic exclusion rules stored as WordPress term metadata."
        },
    )
    semantics_version: str = field(
        default="",
        metadata={
            "doc": "Source category/topic semantics schema version stored as term metadata."
        },
    )


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
    run_budget: RunBudget | None = field(
        default=None, metadata={"doc": "Optional governed budget for taxonomy writes."}
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before taxonomy writes."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
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
    run_budget: RunBudget | None = field(
        default=None, metadata={"doc": "Optional governed budget for tag writes."}
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before tag writes."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
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
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional governed budget for this WordPress write."},
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None, metadata={"doc": "Observed usage before this WordPress write."}
    )
    budget_override_actor: str = field(
        default="", metadata={"doc": "Authorized budget override actor."}
    )
    budget_override_reason: str = field(
        default="", metadata={"doc": "Authorized budget override reason."}
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
