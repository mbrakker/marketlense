from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ReportSourceRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Report-source record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the report landing page lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report name derived from the downloaded file."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Landing-page URL where the report download path was found."}
    )
    downloaded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the report download completed."}
    )
    md5: str = field(metadata={"doc": "MD5 checksum of the downloaded report file."})


@dataclass(frozen=True)
class ReportSourceRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Report-source record response schema version."}
    )
    record_id: int = field(
        metadata={"doc": "Auto-incremented SQLite row ID for the stored source record."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the report landing page lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report name derived from the downloaded file."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Landing-page URL where the report download path was found."}
    )
    downloaded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the report download completed."}
    )
    md5: str = field(metadata={"doc": "MD5 checksum of the downloaded report file."})


@dataclass(frozen=True)
class ReportDownloadDriveFolderLookupRequest:
    schema_version: str = field(
        metadata={"doc": "Report-download Drive-folder lookup request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_landing_page_url: str = field(
        metadata={
            "doc": "Normalized report landing-page URL used to find a report_sources row."
        }
    )
    publisher_insights_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher insights URL used to find the publisher row directly."
        },
    )


@dataclass(frozen=True)
class ReportDownloadDriveFolderLookupResponse:
    schema_version: str = field(
        metadata={"doc": "Report-download Drive-folder lookup response schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for the resolved folder."}
    )
    google_folder: str = field(
        metadata={"doc": "Curated publisher Google Drive folder URL or folder ID."}
    )
    resolution_source: str = field(
        metadata={
            "doc": "Lookup path used to resolve the folder: publisher_insights_url or report_source_publisher."
        }
    )


@dataclass(frozen=True)
class ReportSourceDiscoveryRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Report-source discovery record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved during inventory discovery."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the discovered report URL lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report title from the discovery diff."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Discovered report URL queued for future download."}
    )
    source_page_url: str = field(
        metadata={
            "doc": "Publisher insights page URL where the report URL was discovered."
        }
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the inventory diff was discovered."}
    )
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the report URL was discovered."
        }
    )


@dataclass(frozen=True)
class ReportSourceDiscoveryRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Report-source discovery record response schema version."}
    )
    record_id: int = field(
        metadata={
            "doc": "Auto-incremented SQLite row ID for the stored or updated source record."
        }
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name resolved during inventory discovery."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the discovered report URL lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report title from the discovery diff."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Discovered report URL queued for future download."}
    )
    source_page_url: str = field(
        metadata={
            "doc": "Publisher insights page URL where the report URL was discovered."
        }
    )
    discovered_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the inventory diff was discovered."}
    )
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the report URL was discovered."
        }
    )
    created_new: bool = field(
        metadata={
            "doc": "True when this discovery created a new report_sources row instead of updating an existing one."
        }
    )

