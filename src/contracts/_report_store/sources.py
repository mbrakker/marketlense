from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
    publisher_name: str = field(
        default="",
        metadata={
            "doc": "Publisher display name attached to this downloaded source, when known."
        },
    )
    source_page_url: str = field(
        default="",
        metadata={
            "doc": "Publisher resource or inventory page URL where this report was found, when known."
        },
    )


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


@dataclass(frozen=True)
class ReportValueScoreComponent:
    schema_version: str = field(
        metadata={"doc": "Report value-score component schema version."}
    )
    dimension: str = field(
        metadata={
            "doc": "Stable report-value dimension name: market_insight_depth, evidence_specificity, decision_relevance, recency_timeliness, or source_authority_originality."
        }
    )
    score: float = field(
        metadata={"doc": "Normalized component score from 0.0 to 100.0."}
    )
    rationale: str = field(
        metadata={
            "doc": "Short rationale explaining the deterministic component score."
        }
    )


@dataclass(frozen=True)
class ReportValueScoreRequest:
    schema_version: str = field(
        metadata={"doc": "Report value-score request schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name when known, else empty string."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the report landing page lives."}
    )
    report_name: str = field(metadata={"doc": "Human-readable report title to score."})
    landing_page_url: str = field(
        metadata={"doc": "Canonical report landing page URL."}
    )
    source_page_url: str = field(
        metadata={
            "doc": "Publisher resource or inventory page URL where this report was found, when known."
        }
    )
    source_status: str = field(
        metadata={
            "doc": "Current report_sources status, for example discovered or downloaded."
        }
    )
    discovered_at_utc: str = field(
        default="",
        metadata={"doc": "Discovery timestamp when known."},
    )
    downloaded_at_utc: str = field(
        default="",
        metadata={"doc": "Download timestamp when known."},
    )
    md5: str = field(
        default="",
        metadata={"doc": "Downloaded file checksum when known."},
    )
    evaluation_year: int = field(
        default=2026,
        metadata={"doc": "Reference year used to score recency deterministically."},
    )


@dataclass(frozen=True)
class ReportValueScoreResponse:
    schema_version: str = field(
        metadata={"doc": "Report value-score response schema version."}
    )
    overall_score: float = field(
        metadata={"doc": "Weighted normalized value score from 0.0 to 100.0."}
    )
    value_band: str = field(metadata={"doc": "Value band: high, medium, low, or weak."})
    components: List[ReportValueScoreComponent] = field(
        metadata={"doc": "Five deterministic report-value component scores."}
    )
    rationale: str = field(
        metadata={"doc": "Short deterministic rationale for the overall report score."}
    )


@dataclass(frozen=True)
class ReportValueScoreRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Report value-score persistence request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    record_id: int = field(
        metadata={"doc": "report_sources row ID to update with the value score."}
    )
    score: ReportValueScoreResponse = field(
        metadata={"doc": "Typed value score to persist on the report_sources row."}
    )
    scored_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the score was computed."}
    )


@dataclass(frozen=True)
class ReportSourceQualityHistoryItem:
    schema_version: str = field(
        metadata={"doc": "Publisher resource quality history item schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name attached to the source row."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain for the report source row."}
    )
    source_page_url: str = field(
        metadata={"doc": "Publisher resource page that produced this report source."}
    )
    landing_page_url: str = field(metadata={"doc": "Report landing-page URL."})
    report_name: str = field(metadata={"doc": "Report title."})
    overall_score: float = field(
        metadata={"doc": "Persisted report value score from 0.0 to 100.0."}
    )
    value_band: str = field(metadata={"doc": "Persisted report value band."})
    source_status: str = field(metadata={"doc": "Report source status."})
    discovered_at_utc: str = field(metadata={"doc": "Discovery timestamp when known."})
    downloaded_at_utc: str = field(metadata={"doc": "Download timestamp when known."})
    scored_at_utc: str = field(metadata={"doc": "Score timestamp."})


@dataclass(frozen=True)
class ReportSourceQualityHistoryRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher resource quality history request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    publisher_name: str = field(
        metadata={
            "doc": "Publisher display name whose report-source score history should be listed."
        }
    )
    limit: int = field(
        default=100,
        metadata={"doc": "Maximum scored report-source rows to return."},
    )


@dataclass(frozen=True)
class ReportSourceQualityHistoryResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher resource quality history response schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name queried."})
    items: List[ReportSourceQualityHistoryItem] = field(
        metadata={"doc": "Scored report-source history rows for this publisher."}
    )


@dataclass(frozen=True)
class PublisherResourceRankingPolicy:
    schema_version: str = field(
        metadata={"doc": "Publisher resource ranking policy schema version."}
    )
    score_window_size: int = field(
        metadata={"doc": "Maximum recent scored reports per resource used for ranking."}
    )
    min_sample_size: int = field(
        metadata={
            "doc": "Minimum history sample size before consistency can promote a resource."
        }
    )
    consistency_weight: float = field(
        metadata={"doc": "Weight assigned to rolling score consistency."}
    )
    average_score_weight: float = field(
        metadata={"doc": "Weight assigned to average report value score."}
    )
    confidence_weight: float = field(
        metadata={"doc": "Weight assigned to history sample confidence."}
    )
    low_score_demotion_threshold: float = field(
        metadata={"doc": "Average score below which a resource is demoted."}
    )


@dataclass(frozen=True)
class PublisherResourceRankingRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher resource ranking request schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    candidate_source_page_urls: List[str] = field(
        metadata={"doc": "Current candidate source/resource URLs that need ordering."}
    )
    history_items: List[ReportSourceQualityHistoryItem] = field(
        metadata={"doc": "Historical scored report sources for the publisher."}
    )
    policy: PublisherResourceRankingPolicy = field(
        metadata={"doc": "Configurable rolling consistency ranking policy."}
    )


@dataclass(frozen=True)
class PublisherResourceRankingItem:
    schema_version: str = field(
        metadata={"doc": "Publisher resource ranking item schema version."}
    )
    resource_url: str = field(metadata={"doc": "Publisher resource/source page URL."})
    sample_size: int = field(metadata={"doc": "Number of scored history rows used."})
    score_window_size: int = field(metadata={"doc": "Configured score window size."})
    average_value_score: float = field(
        metadata={"doc": "Average report value score in the rolling window."}
    )
    latest_value_score: float = field(
        metadata={"doc": "Most recent report value score in the window."}
    )
    consistency_score: float = field(
        metadata={"doc": "0.0-1.0 consistency score derived from score variance."}
    )
    confidence: float = field(
        metadata={"doc": "0.0-1.0 sample-size confidence for this resource."}
    )
    rank_score: float = field(
        metadata={"doc": "Final ranking score used to order resources."}
    )
    demotion_reason: str = field(
        metadata={"doc": "Typed demotion reason, or empty string when not demoted."}
    )


@dataclass(frozen=True)
class PublisherResourceRankingResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher resource ranking response schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    items: List[PublisherResourceRankingItem] = field(
        metadata={
            "doc": "Ranked publisher resources ordered by rolling quality consistency."
        }
    )


@dataclass(frozen=True)
class PublicPublisherReportValueAggregateRequest:
    schema_version: str = field(metadata={"doc": "Aggregate request schema version."})
    db_path: str = field(metadata={"doc": "Report metadata SQLite path."})
    published_file_ids: List[str] = field(
        metadata={"doc": "Public WordPress report file identifiers eligible for aggregation."}
    )


@dataclass(frozen=True)
class PublicPublisherReportValueAggregate:
    schema_version: str = field(metadata={"doc": "Aggregate schema version."})
    publisher_name: str = field(metadata={"doc": "Publisher name from scored public reports."})
    average_score: float = field(metadata={"doc": "Average report-value score from public reports."})
    value_band: str = field(metadata={"doc": "Canonical report-value band for the average score."})
    sample_size: int = field(metadata={"doc": "Number of scored public reports in the aggregate."})


@dataclass(frozen=True)
class PublicPublisherReportValueAggregateResponse:
    schema_version: str = field(metadata={"doc": "Aggregate response schema version."})
    aggregates: List[PublicPublisherReportValueAggregate] = field(
        metadata={"doc": "Public report-value aggregates grouped by publisher."}
    )
