"""Typed boundary for handing a verified acquisition to governed ingest."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerifiedAcquisitionIngestHandoffRequest:
    """Verified scalar acquisition context required before source-ingest submission."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    reports_db: str = field(
        default="",
        metadata={
            "doc": "Reports SQLite database that owns source and report records."
        },
    )
    source_artifact_reference: str = field(
        default="",
        metadata={
            "doc": "Retained local PDF path verified immediately before handoff."
        },
    )
    expected_content_hash: str = field(
        default="",
        metadata={"doc": "Optional lower-case MD5 expected from acquisition evidence."},
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Canonical HTTP(S) URL that produced the retained artifact."},
    )
    report_title: str = field(
        default="",
        metadata={"doc": "Publisher-observed report title used for provenance only."},
    )
    publisher_name: str = field(
        default="",
        metadata={
            "doc": "Publisher display name observed during acquisition, if known."
        },
    )
    publisher_id: str = field(
        default="",
        metadata={"doc": "Stable publisher identifier when already available."},
    )
    acquisition_route: str = field(
        default="",
        metadata={"doc": "Observed direct, browser, or mailbox acquisition route."},
    )
    processing_version: str = field(
        default="",
        metadata={
            "doc": "Required parser/OCR compatibility version for ingest idempotency."
        },
    )
    report_id: str = field(
        default="",
        metadata={
            "doc": (
                "Optional retained Drive report ID; blank selects a content-derived ID."
            )
        },
    )
