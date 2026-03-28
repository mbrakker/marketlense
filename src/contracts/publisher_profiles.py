from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PublisherProfileRecord:
    schema_version: str = field(
        metadata={"doc": "Publisher-profile record schema version."}
    )
    notion_page_id: str = field(
        metadata={"doc": "Notion page identifier for the publisher row."}
    )
    notion_page_url: str = field(
        metadata={"doc": "Canonical Notion page URL for the publisher row."}
    )
    name: str = field(metadata={"doc": "Publisher display name."})
    homepage: str = field(
        metadata={"doc": "Publisher homepage URL, or an empty string when missing."}
    )
    self_presentation: str = field(
        metadata={"doc": "Publisher self-description text, or an empty string when missing."}
    )
    insights_url: str = field(
        metadata={"doc": "Publisher insights or reports landing-page URL, or an empty string when missing."}
    )
    icon_source: str = field(
        metadata={"doc": "Publisher icon source URL or data URI, or an empty string when missing."}
    )


@dataclass(frozen=True)
class PublisherProfilesSnapshotLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher snapshot load request schema version."}
    )
    snapshot_path: str = field(
        metadata={"doc": "Filesystem path to the publisher snapshot JSON file."}
    )


@dataclass(frozen=True)
class PublisherProfilesSnapshotLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher snapshot load response schema version."}
    )
    snapshot_path: str = field(
        metadata={"doc": "Filesystem path to the publisher snapshot JSON file."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion source page URL captured in the snapshot."}
    )
    publisher_count: int = field(
        metadata={"doc": "Number of publisher rows loaded from the snapshot."}
    )
    publishers: List[PublisherProfileRecord] = field(
        metadata={"doc": "Validated publisher rows loaded from the snapshot."}
    )


@dataclass(frozen=True)
class PublisherSyncRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher sync request schema version."}
    )
    snapshot_path: str = field(
        metadata={"doc": "Filesystem path to the publisher snapshot JSON file."}
    )
    reports_db: str = field(
        metadata={"doc": "Filesystem path to the reports SQLite database."}
    )


@dataclass(frozen=True)
class PublisherSyncResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher sync response schema version."}
    )
    snapshot_path: str = field(
        metadata={"doc": "Filesystem path to the publisher snapshot JSON file."}
    )
    reports_db: str = field(
        metadata={"doc": "Filesystem path to the reports SQLite database."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion source page URL captured in the snapshot."}
    )
    replaced_count: int = field(
        metadata={"doc": "Number of publisher rows written into the reports database."}
    )
