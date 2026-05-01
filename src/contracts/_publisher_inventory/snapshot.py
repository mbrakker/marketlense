from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .routing import PublisherInventoryRunQualitySummary

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
        metadata={
            "doc": "Absolute URL of the inventory page where this candidate was found."
        }
    )
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where this candidate was found."
        }
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional raw PDF URL associated with this candidate."},
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional raw published-date text extracted for this candidate."
        },
    )
    provenance: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional extraction provenance for the raw candidate, for example browser_dom, browser_rendered_html_supplement, http_supplement, http_parse, or direct_pdf_source."
        },
    )
    confidence: Optional[float] = field(
        default=None,
        metadata={
            "doc": "Optional deterministic extraction-confidence score in the range 0.0-1.0 when a route computes candidate-quality confidence before acceptance."
        },
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
        metadata={
            "doc": "One-based inventory page number where the item was first found."
        }
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Normalized PDF URL when the report link points directly to a PDF or one is known."
        },
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized published-date text when available."},
    )


@dataclass(frozen=True)
class PublisherInventoryCandidateTrace:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory candidate-trace schema version."}
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized canonical report URL for the current candidate."}
    )
    title: str = field(metadata={"doc": "Normalized candidate title."})
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the candidate was first found."
        }
    )
    source_page_urls: List[str] = field(
        metadata={
            "doc": "Distinct inventory page URLs where the candidate was observed during the run."
        }
    )
    discovery_provenances: List[str] = field(
        metadata={
            "doc": "Distinct extraction provenance labels observed for the candidate during the run."
        }
    )
    pdf_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Normalized PDF URL when the candidate directly exposes a PDF or one was observed."
        },
    )
    published_at_text: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized published-date text when available."},
    )
    max_confidence: Optional[float] = field(
        default=None,
        metadata={
            "doc": "Maximum raw extraction-confidence value observed for the candidate during the run when available."
        },
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
        metadata={
            "doc": "Discovery route kind used for this snapshot: http_parse or browser_render."
        }
    )
    route_summary: str = field(
        metadata={
            "doc": "Summary of the successful discovery route for reuse on later runs."
        }
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
        metadata={
            "doc": "Normalized canonical report URL that is new in the current snapshot."
        }
    )
    title: str = field(metadata={"doc": "Normalized title for the new report."})
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the new report link was found."
        }
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
    current_candidates: List[PublisherInventoryCandidateTrace] = field(
        default_factory=list,
        metadata={
            "doc": "Current normalized report candidates from the discovery run, enriched with discovery provenance details."
        },
    )

