"""Contracts for pipeline-owned WordPress intelligence projections."""

from __future__ import annotations

# ruff: noqa: E501
from dataclasses import dataclass, field
from typing import Literal

WORDPRESS_INTELLIGENCE_SCHEMA_VERSION = "1.0"
WORDPRESS_INTELLIGENCE_PROJECTION_VERSION = "wordpress_intelligence_projection.v1"


@dataclass(frozen=True)
class WordPressIntelligenceTerm:
    """A public WordPress taxonomy term included in a source entity."""

    schema_version: str = field(metadata={"doc": "Term contract schema version."})
    name: str = field(metadata={"doc": "Public term display name."})
    url: str = field(metadata={"doc": "Public WordPress term URL, if available."})
    homepage: str = field(metadata={"doc": "Publisher homepage URL, if applicable."})


@dataclass(frozen=True)
class WordPressIntelligenceEntity:
    """One approved public entity read from WordPress before aggregation."""

    schema_version: str = field(metadata={"doc": "Entity contract schema version."})
    entity_id: str = field(metadata={"doc": "Stable WordPress entity identifier."})
    entity_type: Literal["ml_report", "ml_briefing", "ml_signal"] = field(
        metadata={"doc": "Published WordPress entity type."}
    )
    published_at_utc: str = field(metadata={"doc": "Published UTC timestamp."})
    url: str = field(metadata={"doc": "Public entity URL."})
    publishers: list[WordPressIntelligenceTerm] = field(
        metadata={"doc": "Publisher terms attached to this entity."}
    )
    topics: list[WordPressIntelligenceTerm] = field(
        metadata={"doc": "Topic terms attached to this entity."}
    )


@dataclass(frozen=True)
class WordPressIntelligenceSourceReadRequest:
    """Authenticated request for raw published entities without derived counts."""

    schema_version: str = field(metadata={"doc": "Request contract schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(
        metadata={"doc": "Authorization header for WordPress REST."}
    )
    ssl_verify: bool = field(metadata={"doc": "Whether TLS certificates are verified."})
    ca_bundle_path: str | None = field(metadata={"doc": "Optional TLS CA bundle path."})


@dataclass(frozen=True)
class WordPressIntelligenceSourceReadResponse:
    """Validated raw source entities returned by WordPress."""

    schema_version: str = field(metadata={"doc": "Response contract schema version."})
    entities: list[WordPressIntelligenceEntity] = field(
        metadata={"doc": "Published entities that the pipeline may aggregate."}
    )


@dataclass(frozen=True)
class WordPressIntelligenceMetric:
    """One display-safe projected trend or authority term."""

    schema_version: str = field(metadata={"doc": "Metric contract schema version."})
    name: str = field(metadata={"doc": "Projected public term name."})
    count: int = field(metadata={"doc": "Approved entity count for the term."})
    delta: int | None = field(
        metadata={"doc": "Current-minus-previous window count, if relevant."}
    )
    url: str = field(metadata={"doc": "Public WordPress term URL, if available."})
    homepage: str = field(metadata={"doc": "Publisher homepage URL, if available."})


@dataclass(frozen=True)
class WordPressHomepageMetrics:
    """Approved aggregate values rendered on WordPress homepage surfaces."""

    schema_version: str = field(metadata={"doc": "Metrics contract schema version."})
    report_count: int = field(metadata={"doc": "Published report count."})
    publisher_count: int = field(metadata={"doc": "Distinct approved publisher count."})
    topic_count: int = field(metadata={"doc": "Distinct approved topic count."})
    briefing_count: int = field(metadata={"doc": "Published briefing count."})
    signal_count: int = field(metadata={"doc": "Published signal count."})
    signal_label: str = field(metadata={"doc": "Label for the signal total."})
    citation_count: int = field(
        metadata={"doc": "Approved citation count; zero when not projected."}
    )
    latest_label: str = field(
        metadata={"doc": "Pipeline-calculated source freshness label."}
    )


@dataclass(frozen=True)
class WordPressWeeklyIntelligence:
    """Approved weekly topic and publisher movement projection."""

    schema_version: str = field(metadata={"doc": "Weekly projection schema version."})
    window_label: str = field(metadata={"doc": "Human-readable comparison window."})
    trending_topics: list[WordPressIntelligenceMetric] = field(
        metadata={"doc": "Ranked current topics."}
    )
    emerging_themes: list[WordPressIntelligenceMetric] = field(
        metadata={"doc": "Topics with positive movement."}
    )
    top_publishers: list[WordPressIntelligenceMetric] = field(
        metadata={"doc": "Ranked current publishers."}
    )


@dataclass(frozen=True)
class WordPressIntelligenceProjection:
    """Complete pipeline-owned payload rendered by the WordPress plugin."""

    schema_version: str = field(metadata={"doc": "Projection contract schema version."})
    projection_version: str = field(metadata={"doc": "Projection algorithm version."})
    generated_at_utc: str = field(
        metadata={"doc": "Projection generation UTC timestamp."}
    )
    homepage_metrics: WordPressHomepageMetrics = field(
        metadata={"doc": "Homepage aggregate projection."}
    )
    weekly_signals: WordPressWeeklyIntelligence = field(
        metadata={"doc": "Windowed trend projection."}
    )
    strategic_themes: list[WordPressIntelligenceMetric] = field(
        metadata={"doc": "Ranked strategic themes."}
    )
    publisher_authority: list[WordPressIntelligenceMetric] = field(
        metadata={"doc": "Ranked publisher authority rows."}
    )


@dataclass(frozen=True)
class WordPressIntelligenceBuildRequest:
    """Pure generator input for an approved source snapshot."""

    schema_version: str = field(metadata={"doc": "Build request schema version."})
    source: WordPressIntelligenceSourceReadResponse = field(
        metadata={"doc": "Raw published entity source."}
    )
    generated_at_utc: str = field(metadata={"doc": "UTC generation timestamp."})


@dataclass(frozen=True)
class WordPressIntelligenceProjectionWriteRequest:
    """Authenticated request that persists an approved projection in WordPress."""

    schema_version: str = field(metadata={"doc": "Write request schema version."})
    base_url: str = field(metadata={"doc": "WordPress site base URL."})
    auth_header: str = field(
        metadata={"doc": "Authorization header for WordPress REST."}
    )
    projection: WordPressIntelligenceProjection = field(
        metadata={"doc": "Validated pipeline projection."}
    )
    ssl_verify: bool = field(metadata={"doc": "Whether TLS certificates are verified."})
    ca_bundle_path: str | None = field(metadata={"doc": "Optional TLS CA bundle path."})


@dataclass(frozen=True)
class WordPressIntelligenceProjectionWriteResponse:
    """Durable confirmation that WordPress stored the approved projection."""

    schema_version: str = field(
        metadata={"doc": "Write response contract schema version."}
    )
    projection_version: str = field(
        metadata={"doc": "Stored projection algorithm version."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "Stored projection generation timestamp."}
    )
    status: Literal["stored"] = field(
        metadata={"doc": "Projection persistence outcome."}
    )


@dataclass(frozen=True)
class WordPressIntelligenceSyncRequest:
    """Control-plane request to read, build, and publish one projection."""

    schema_version: str = field(
        metadata={"doc": "Sync request contract schema version."}
    )
    source_request: WordPressIntelligenceSourceReadRequest = field(
        metadata={"doc": "Raw WordPress source request."}
    )
    generated_at_utc: str = field(metadata={"doc": "UTC timestamp for the projection."})
    state_db: str = field(
        default="",
        metadata={"doc": "Optional canonical remediation-ledger state database."},
    )


@dataclass(frozen=True)
class WordPressIntelligenceSyncResponse:
    """Outcome of the idempotent projection synchronization."""

    schema_version: str = field(
        metadata={"doc": "Sync response contract schema version."}
    )
    entity_count: int = field(
        metadata={"doc": "Source entities included in the projection."}
    )
    projection: WordPressIntelligenceProjection = field(
        metadata={"doc": "Projection that was written."}
    )
    write_response: WordPressIntelligenceProjectionWriteResponse = field(
        metadata={"doc": "WordPress persistence outcome."}
    )
