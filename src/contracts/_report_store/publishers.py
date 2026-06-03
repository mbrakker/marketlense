from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.publisher_profiles import PublisherProfileRecord
from src.contracts.publisher_inventory import PublisherInventoryRunQualitySummary

@dataclass(frozen=True)
class PublishersReplaceRequest:
    schema_version: str = field(
        metadata={"doc": "Publishers replace request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion page URL that the snapshot was sourced from."}
    )
    publishers: List[PublisherProfileRecord] = field(
        metadata={
            "doc": "Validated publisher rows to replace the current publishers table contents."
        }
    )


@dataclass(frozen=True)
class PublishersReplaceResponse:
    schema_version: str = field(
        metadata={"doc": "Publishers replace response schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion page URL that the snapshot was sourced from."}
    )
    previous_count: int = field(
        metadata={"doc": "Number of publisher rows present before replacement."}
    )
    replaced_count: int = field(
        metadata={"doc": "Number of publisher rows stored after replacement."}
    )


@dataclass(frozen=True)
class PublishersListRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher list request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    limit: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Optional maximum number of publisher rows to return, ordered by row ID ascending."
        },
    )


@dataclass(frozen=True)
class PublisherListItem:
    schema_version: str = field(metadata={"doc": "Publisher list item schema version."})
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    homepage: str = field(metadata={"doc": "Publisher homepage URL."})
    insights_url: str = field(metadata={"doc": "Publisher insights URL."})
    normalized_insights_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the lookup key."}
    )
    google_folder: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Curated Google Drive folder URL or folder ID for this publisher, if any."
        },
    )
    discovery_test_status: Optional[str] = field(
        default=None,
        metadata={"doc": "Last recorded discovery status for this publisher, if any."},
    )
    inventory_route_kind: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered publisher inventory route kind, if any."},
    )
    inventory_route_summary: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered publisher inventory route summary, if any."},
    )
    inventory_run_quality_summary: Optional[PublisherInventoryRunQualitySummary] = (
        field(
            default=None,
            metadata={
                "doc": "Last persisted publisher-inventory run-quality summary, if any."
            },
        )
    )


@dataclass(frozen=True)
class PublishersListResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher list response schema version."}
    )
    publishers: List[PublisherListItem] = field(
        metadata={"doc": "Publisher rows with non-empty insights URLs."}
    )


@dataclass(frozen=True)
class PublisherGoogleFolderUpdateRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher Google-folder update request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name whose google_folder should be set."}
    )
    google_folder: str = field(
        metadata={"doc": "Google Drive folder URL or folder ID to store."}
    )
    publisher_insights_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher insights URL used as the preferred update key."
        },
    )


@dataclass(frozen=True)
class PublisherGoogleFolderUpdateResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher Google-folder update response schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Updated publisher display name."})
    google_folder: str = field(metadata={"doc": "Persisted Google Drive folder URL."})
    updated_count: int = field(metadata={"doc": "Number of publisher rows updated."})
    resolution_source: str = field(
        metadata={"doc": "Update key used: publisher_insights_url or publisher_name."}
    )

