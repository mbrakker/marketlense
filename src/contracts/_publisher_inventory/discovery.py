from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .routing import (
    PublisherInventoryRouteTrace,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryScenarioSummary,
)
from .settings import PublisherInventorySettings
from .snapshot import (
    PublisherInventoryCandidateTrace,
    PublisherInventoryDiffItem,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
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
        metadata={
            "doc": "SQLite reports DB path used for publisher lookup and state persistence."
        }
    )
    settings: PublisherInventorySettings = field(
        metadata={"doc": "Loaded publisher inventory discovery settings."}
    )
    state_db: str = field(
        default="",
        metadata={"doc": "Optional canonical remediation-ledger state database."},
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
        metadata={
            "doc": "List of report URLs that are new versus the previous snapshot."
        }
    )
    current_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the current snapshot."}
    )
    previous_report_count: int = field(
        metadata={"doc": "Number of normalized reports in the previous snapshot."}
    )
    used_memory_route: bool = field(
        metadata={
            "doc": "Whether a remembered route hint was used on the successful run."
        }
    )
    snapshot_changed: bool = field(
        metadata={
            "doc": "Whether the normalized current snapshot differed from the previous snapshot."
        }
    )
    run_quality_summary: PublisherInventoryRunQualitySummary = field(
        metadata={
            "doc": "Deterministic run-quality summary persisted for future route planning and drift monitoring."
        }
    )
    current_candidates: List[PublisherInventoryCandidateTrace] = field(
        default_factory=list,
        metadata={
            "doc": "Current normalized report candidates from the discovery run, enriched with discovery provenance for audit/report-download follow-up."
        },
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
        metadata={
            "doc": "Previously successful route summary used to bias browser-render discovery."
        },
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful route kind when known: http_parse or browser_render."
        },
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
        metadata={
            "doc": "Discovery route kind used successfully: http_parse or browser_render."
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
    used_route_hint: bool = field(
        metadata={"doc": "Whether the discovery run used a remembered route hint."}
    )
    pages: List[PublisherInventoryPage] = field(
        metadata={"doc": "Inventory pages traversed during this run."}
    )
    candidates: List[PublisherInventoryRawCandidate] = field(
        metadata={"doc": "Raw report candidates extracted across all traversed pages."}
    )
    route_trace: Optional[PublisherInventoryRouteTrace] = field(
        default=None,
        metadata={
            "doc": "Optional structured trace capturing actual traversal decisions for future reuse."
        },
    )
    scenario_summary: Optional[PublisherInventoryScenarioSummary] = field(
        default=None,
        metadata={
            "doc": "Optional scenario summary describing the discovery surface encountered during the run."
        },
    )
