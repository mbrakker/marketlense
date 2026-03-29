from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PublisherInventoryPage:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory page schema version."}
    )
    page_number: int = field(
        metadata={"doc": "One-based inventory page number visited during discovery."}
    )
    page_url: str = field(
        metadata={"doc": "Absolute URL of the visited inventory page."}
    )


@dataclass(frozen=True)
class PublisherInventoryRawCandidate:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory raw candidate schema version."}
    )
    url: str = field(
        metadata={"doc": "Raw absolute or relative URL extracted from the source page."}
    )
    title: str = field(
        metadata={"doc": "Raw candidate title text extracted from the source page."}
    )
    source_page_url: str = field(
        metadata={"doc": "Absolute URL of the inventory page where this candidate was found."}
    )
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where this candidate was found."}
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional raw PDF URL associated with this candidate."},
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional raw published-date text extracted for this candidate."},
    )


@dataclass(frozen=True)
class PublisherInventoryItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized canonical report URL used as the diff identity."}
    )
    title: str = field(metadata={"doc": "Normalized report title."})
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the item was first found."}
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized PDF URL when the report link points directly to a PDF or one is known."},
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized published-date text when available."},
    )


@dataclass(frozen=True)
class PublisherInventorySnapshot:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory snapshot schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports database."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL used for discovery."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the snapshot was produced."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used for this snapshot: http_parse or browser_render."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route for reuse on later runs."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed to build this snapshot."}
    )
    items: List[PublisherInventoryItem] = field(
        metadata={"doc": "Normalized report inventory across all traversed pages."}
    )


@dataclass(frozen=True)
class PublisherInventoryDiffItem:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory diff item schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized canonical report URL that is new in the current snapshot."}
    )
    title: str = field(metadata={"doc": "Normalized title for the new report."})
    discovered_on_page_number: int = field(
        metadata={"doc": "One-based inventory page number where the new report link was found."}
    )


@dataclass(frozen=True)
class PublisherInventorySettings:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery settings schema version."}
    )
    openrouter_api_key: str = field(
        metadata={"doc": "OpenRouter API key used when browser-render fallback is required."}
    )
    model: str = field(
        metadata={"doc": "Model ID used by the browser-render fallback flow."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for browser-render discovery."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-model timeout in seconds for browser-render discovery."}
    )
    max_steps: int = field(
        metadata={"doc": "Maximum browser-use agent steps per discovery run."}
    )
    output_dir: str = field(
        metadata={"doc": "Root directory used for temporary browser discovery output."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB path used for publisher lookups and snapshot indexing."}
    )
    google_sa_path: str = field(
        metadata={"doc": "Filesystem path to the Google service account JSON used for Drive access."}
    )
    prompt_namespace: str = field(
        metadata={"doc": "Prompt namespace used for browser-render inventory discovery."}
    )
    pagination_max_pages: int = field(
        metadata={"doc": "Hard upper bound on inventory pages traversed in one discovery run."}
    )
    http_timeout_seconds: float = field(
        metadata={"doc": "HTTP timeout in seconds for direct HTML fetch discovery."}
    )
    openrouter_http_referer: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional HTTP-Referer header sent to OpenRouter."},
    )
    headed: bool = field(
        default=False,
        metadata={"doc": "Whether browser-render discovery should run in a visible browser."},
    )
    retry_retries: int = field(
        default=1,
        metadata={"doc": "Retry count for orchestrated inventory discovery attempts."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay before the first inventory discovery retry."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear backoff step added per inventory discovery retry."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter added to inventory discovery retry delays."},
    )


@dataclass(frozen=True)
class PublisherInventoryDiscoveryRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery request schema version."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL to crawl and diff."}
    )
    reports_db: str = field(
        metadata={"doc": "SQLite reports DB path used for publisher lookup and state persistence."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings."}
    )


@dataclass(frozen=True)
class PublisherInventoryDiscoveryResult:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory discovery result schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports DB."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    new_report_urls: List[PublisherInventoryDiffItem] = field(
        metadata={"doc": "List of report URLs that are new versus the previous snapshot."}
    )
    current_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the current snapshot."}
    )
    previous_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the previous snapshot."}
    )
    used_memory_route: bool = field(
        metadata={"doc": "Whether a remembered route hint was used on the successful run."}
    )
    snapshot_changed: bool = field(
        metadata={"doc": "Whether the normalized current snapshot differed from the previous snapshot."}
    )


@dataclass(frozen=True)
class PublisherInventoryServiceRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory service request schema version."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights URL to crawl for report inventory."}
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings."}
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Previously successful route summary used to bias browser-render discovery."},
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Previously successful route kind when known: http_parse or browser_render."},
    )


@dataclass(frozen=True)
class PublisherInventoryServiceResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory service response schema version."}
    )
    source_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully: http_parse or browser_render."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route for reuse on later runs."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    used_route_hint: bool = field(
        metadata={"doc": "Whether the discovery run used a remembered route hint."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed during this run."}
    )
    candidates: List[PublisherInventoryRawCandidate] = field(
        metadata={"doc": "Raw report candidates extracted across all traversed pages."}
    )


@dataclass(frozen=True)
class PublisherInventoryBuildRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory build request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved from the reports DB."}
    )
    insights_url: str = field(
        metadata={"doc": "Original publisher insights URL provided by the caller."}
    )
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the memory key."}
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp for the current discovery run."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully for this run."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final page URL observed at the end of the discovery run."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed during the discovery run."}
    )
    candidates: List[PublisherInventoryRawCandidate] = field(
        metadata={"doc": "Raw candidates extracted during the discovery run."}
    )
    previous_snapshot: Optional[PublisherInventorySnapshot] = field(
        default=None,
        metadata={"doc": "Previous snapshot used to compute the diff when available."},
    )


@dataclass(frozen=True)
class PublisherInventoryBuildResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory build response schema version."}
    )
    snapshot: PublisherInventorySnapshot = field(
        metadata={"doc": "Normalized current snapshot for this discovery run."}
    )
    new_items: List[PublisherInventoryDiffItem] = field(
        metadata={"doc": "New report URLs discovered versus the previous snapshot."}
    )
    current_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the current snapshot."}
    )
    previous_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the previous snapshot."}
    )
    snapshot_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the normalized snapshot JSON payload."}
    )
    snapshot_json: str = field(
        metadata={"doc": "Deterministic JSON serialization of the normalized snapshot."}
    )

