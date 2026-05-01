from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.publisher_inventory import PublisherInventoryRecoveryRecord, PublisherInventoryRoutePolicySignal, PublisherInventoryRouteTrace, PublisherInventoryRunQualitySummary, PublisherInventoryScenarioSummary

@dataclass(frozen=True)
class PublisherInventoryStateGetRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state get request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used to find the matching publisher row."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryStateResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state response schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    insights_url: str = field(metadata={"doc": "Stored publisher insights URL."})
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the lookup key."}
    )
    google_folder: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Curated Google Drive folder URL or folder ID for this publisher."
        },
    )
    discovery_test_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last recorded discovery test outcome for this publisher row, for example `passed` or `failed:<error_code>`."
        },
    )
    inventory_route_kind: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered discovery route kind for this publisher URL."},
    )
    inventory_route_summary: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered discovery route summary for this publisher URL."},
    )
    inventory_route_trace: Optional[PublisherInventoryRouteTrace] = field(
        default=None,
        metadata={
            "doc": "Remembered structured discovery route trace for this publisher URL when available."
        },
    )
    inventory_scenario_summary: Optional[PublisherInventoryScenarioSummary] = field(
        default=None,
        metadata={
            "doc": "Remembered scenario summary for this publisher URL when available."
        },
    )
    inventory_route_last_final_page_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last final page URL observed for the remembered discovery route."
        },
    )
    inventory_route_updated_at: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Unix timestamp when the remembered discovery route was last updated."
        },
    )
    inventory_snapshot_drive_file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file ID of the latest stored inventory snapshot."},
    )
    inventory_snapshot_drive_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file name of the latest stored inventory snapshot."},
    )
    inventory_snapshot_sha256: Optional[str] = field(
        default=None,
        metadata={"doc": "SHA-256 hash of the latest stored inventory snapshot JSON."},
    )
    inventory_snapshot_updated_at: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Unix timestamp when the latest stored inventory snapshot index was updated."
        },
    )
    inventory_run_quality_summary: Optional[PublisherInventoryRunQualitySummary] = (
        field(
            default=None,
            metadata={
                "doc": "Last persisted publisher-inventory run-quality summary used for future route planning and drift monitoring."
            },
        )
    )
    inventory_run_quality_updated_at: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Unix timestamp when the last publisher-inventory run-quality summary was recorded."
        },
    )
    inventory_route_policy: List[PublisherInventoryRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked discovery route-kind policy signals learned from publisher inventory history."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryStateRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used to identify the publisher row."
        }
    )
    source_url: str = field(
        metadata={"doc": "Stored source insights URL for the publisher."}
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
    route_trace: Optional[PublisherInventoryRouteTrace] = field(
        default=None,
        metadata={
            "doc": "Optional structured discovery route trace captured during the successful run."
        },
    )
    scenario_summary: Optional[PublisherInventoryScenarioSummary] = field(
        default=None,
        metadata={
            "doc": "Optional scenario summary captured during the successful run."
        },
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last final page URL observed for the successful discovery route."
        },
    )
    snapshot_drive_file_id: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Drive file ID of the latest stored snapshot, when changed or already known."
        },
    )
    snapshot_drive_file_name: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Drive file name of the latest stored snapshot, when changed or already known."
        },
    )
    snapshot_sha256: Optional[str] = field(
        default=None,
        metadata={
            "doc": "SHA-256 hash of the latest stored snapshot JSON, when changed or already known."
        },
    )


@dataclass(frozen=True)
class PublisherInventoryTestStatusRecordRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory test-status record request schema version."
        }
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used to identify the publisher row."
        }
    )
    status: str = field(
        metadata={
            "doc": "Last recorded discovery test outcome string, for example `passed` or `failed:<error_code>`."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryRunQualityRecordRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory run-quality record request schema version."
        }
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used to identify the publisher row."
        }
    )
    summary: PublisherInventoryRunQualitySummary = field(
        metadata={
            "doc": "Run-quality summary to persist for future route planning and drift monitoring."
        }
    )


@dataclass(frozen=True)
class PublisherInventoryRecoveryCacheGetRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory recovery-cache get request schema version."
        }
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={
            "doc": "Normalized publisher insights URL used to scope the recovery cache lookup."
        }
    )
    canonical_url: str = field(
        metadata={"doc": "Normalized candidate URL used as the recovery cache key."}
    )


@dataclass(frozen=True)
class PublisherInventoryRecoveryCacheRecordRequest:
    schema_version: str = field(
        metadata={
            "doc": "Publisher inventory recovery-cache record request schema version."
        }
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    record: PublisherInventoryRecoveryRecord = field(
        metadata={"doc": "Recovery-cache record to upsert for the candidate."}
    )

