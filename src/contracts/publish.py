from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.publish_readiness import PublishReadinessArtifact
from src.contracts.run_budget import RunBudget, RunBudgetLimits, RunBudgetUsage
from src.contracts.wordpress import (
    WordPressAuthSettings,
    WordPressPostReadCheck,
    WordPressPostReadExpectation,
    WordPressTransactionOutcome,
)


@dataclass(frozen=True)
class PublishEntityMetadata:
    schema_version: str = field(
        metadata={"doc": "Generated public entity metadata schema version."}
    )
    entity_type: str = field(
        metadata={
            "doc": "Public entity type represented by the generated HTML artifact."
        }
    )
    source_artifact_id: str = field(
        metadata={
            "doc": "Stable source artifact identifier used to trace the published entity."
        }
    )
    canonical_route_intent: str = field(
        metadata={
            "doc": "Canonical publication route intent, for example wordpress:ml_report."
        }
    )
    publish_eligible: bool = field(
        metadata={
            "doc": "True when the generated artifact is eligible for WordPress publication."
        }
    )


@dataclass(frozen=True)
class PublishSettings:
    schema_version: str = field(metadata={"doc": "Publish settings schema version."})
    output_dir: str = field(metadata={"doc": "Output directory containing HTML files."})
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    reports_db: str = field(
        metadata={"doc": "SQLite path for report metadata (for category updates)."}
    )
    category_mapping_path: str = field(
        metadata={"doc": "Filesystem path to category mappings YAML."}
    )
    wp: WordPressAuthSettings = field(metadata={"doc": "WordPress auth settings."})
    media_upload_workers: int = field(
        default=4,
        metadata={
            "doc": "Maximum number of parallel WordPress media uploads used during one publish run."
        },
    )
    publish_interval_seconds: int = field(
        default=0,
        metadata={
            "doc": "Minimum elapsed seconds between starts of WordPress publication writes."
        },
    )
    validation_policy: str = field(
        default="block",
        metadata={
            "doc": "Validation handling: block (skip publish on fail) or warn (log and continue)."
        },
    )
    run_budget_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether final WordPress publication writes use the canonical run budget."
        },
    )
    usage_db_path: str = field(
        default="",
        metadata={
            "doc": "Canonical SQLite usage-ledger path for publication budgeting."
        },
    )
    projection_ledger_path: str = field(
        default="",
        metadata={
            "doc": "Derived usage JSONL checked for publication release evidence."
        },
    )
    projection_daily_path: str = field(
        default="",
        metadata={
            "doc": "Derived daily usage rollup checked for publication release evidence."
        },
    )
    projection_pending_event_threshold: int = field(
        default=50,
        metadata={
            "doc": "Pending canonical events allowed as accounted normal projection lag."
        },
    )
    run_budget_max_wordpress_writes: int | None = field(
        default=None,
        metadata={
            "doc": "Maximum final WordPress publication writes per governed scope."
        },
    )
    run_budget_enabled_effect_kinds: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "Independently feature-gated side-effect kinds; empty enables all."
        },
    )
    run_budget_limit_decision: str = field(
        default="stop",
        metadata={"doc": "Action when the WordPress publication budget is reached."},
    )
    run_budget_policy_version: str = field(
        default="budget-authority-v2",
        metadata={"doc": "Canonical budget policy version for publication writes."},
    )
    run_budget_reservation_ttl_seconds: int = field(
        default=300, metadata={"doc": "Bounded publication budget reservation TTL."}
    )
    run_budget_limits_run: RunBudgetLimits | None = field(
        default=None, metadata={"doc": "Explicit run-scoped publication limits."}
    )
    run_budget_limits_day: RunBudgetLimits | None = field(
        default=None, metadata={"doc": "Explicit UTC-day publication limits."}
    )
    run_budget_limits_publisher: RunBudgetLimits | None = field(
        default=None, metadata={"doc": "Explicit publisher publication limits."}
    )


@dataclass(frozen=True)
class PublishResolvedTerms:
    schema_version: str = field(
        metadata={"doc": "Resolved publish-term assignment schema version."}
    )
    category_ids: List[int] = field(
        default_factory=list,
        metadata={"doc": "Resolved native WordPress category IDs for the publish."},
    )
    tag_ids: List[int] = field(
        default_factory=list,
        metadata={"doc": "Resolved native WordPress tag IDs for the publish."},
    )
    taxonomy_terms: Dict[str, List[int]] = field(
        default_factory=dict,
        metadata={
            "doc": "Resolved custom taxonomy REST-base mappings to WordPress term IDs."
        },
    )


@dataclass(frozen=True)
class PublishHtmlSnapshot:
    schema_version: str = field(
        metadata={"doc": "Publish HTML snapshot schema version."}
    )
    html_text: str = field(
        metadata={"doc": "Loaded HTML artifact text reused across the publish path."}
    )
    file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Parsed Drive file ID extracted from the HTML, if present."},
    )
    title: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Parsed publish title extracted from h1/title tags, if present."
        },
    )
    body_html: str = field(
        default="",
        metadata={"doc": "Parsed HTML body fragment extracted from the full document."},
    )
    image_sources: List[str] = field(
        default_factory=list,
        metadata={"doc": "Ordered image src values extracted from the HTML payload."},
    )
    preview_image_src: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Preview image src extracted from the dedicated preview block, if present."
        },
    )
    entity_metadata: Optional[PublishEntityMetadata] = field(
        default=None,
        metadata={
            "doc": "Typed public entity metadata embedded in the generated HTML artifact."
        },
    )
    briefing_card: Dict[str, object] = field(
        default_factory=dict,
        metadata={"doc": "Briefing-card metadata and generated cover asset paths."},
    )
    signal_card: Dict[str, object] = field(
        default_factory=dict,
        metadata={"doc": "Signal-card metadata and generated cover asset paths."},
    )


@dataclass(frozen=True)
class PublishRequest:
    schema_version: str = field(metadata={"doc": "Publish request schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to HTML file."})
    auth_header: str = field(
        metadata={
            "doc": "Pre-resolved WordPress authorization header passed through the publish workflow."
        }
    )
    file_id: Optional[str] = field(
        default=None, metadata={"doc": "Drive file ID, if known."}
    )
    html_text: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional preloaded HTML content. When omitted, generator reads html_path."
        },
    )
    html_snapshot: Optional[PublishHtmlSnapshot] = field(
        default=None,
        metadata={
            "doc": "Optional preloaded publish HTML snapshot carrying loaded HTML plus parsed metadata for reuse across the publish path."
        },
    )
    slug: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional deterministic WordPress slug supplied by prebuilt publish packages."
        },
    )
    resolved_terms: Optional[PublishResolvedTerms] = field(
        default=None,
        metadata={
            "doc": "Optional pre-resolved WordPress category/tag/custom-taxonomy IDs computed during batch publish preflight."
        },
    )
    existing_post_id: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Existing WordPress post ID to update in place during an explicit migration."
        },
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={
            "doc": "Canonical budget evaluated before final WordPress publication writes."
        },
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None,
        metadata={
            "doc": "Observed canonical usage supplied to final WordPress publication writes."
        },
    )
    publish_readiness: PublishReadinessArtifact | None = field(
        default=None,
        metadata={
            "doc": "Hash-bound readiness decision verified before any publication side effect."
        },
    )


@dataclass(frozen=True)
class PublishOutcome:
    schema_version: str = field(metadata={"doc": "Publish outcome schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to HTML file."})
    file_id: Optional[str] = field(metadata={"doc": "Drive file ID, if available."})
    status: str = field(metadata={"doc": "Outcome status: published|skipped|error."})
    post_id: Optional[int] = field(
        default=None, metadata={"doc": "WordPress post ID, if created."}
    )
    post_url: Optional[str] = field(
        default=None, metadata={"doc": "WordPress post URL, if created."}
    )
    error: Optional[str] = field(
        default=None,
        metadata={"doc": "Error code/message when status=error or skipped."},
    )
    validation_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Validation result applied at publish time: pass|fail|missing|error."
        },
    )
    validation_issues: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Validation issues summarised for the publish attempt, if any."
        },
    )
    publication_outcome: WordPressTransactionOutcome = field(
        default="preflight_blocked",
        metadata={
            "doc": "Terminal typed publication disposition; never a generic completed marker."
        },
    )
    transaction_outcomes: List[WordPressTransactionOutcome] = field(
        default_factory=list,
        metadata={
            "doc": "Ordered distinct WordPress transaction outcomes retained with idempotency evidence."
        },
    )
    requested_write_count: int = field(
        default=0, metadata={"doc": "Requested final WordPress post writes."}
    )
    actual_write_count: int = field(
        default=0, metadata={"doc": "Observed final WordPress post writes."}
    )
    lookup_count: int = field(
        default=0, metadata={"doc": "Authenticated WordPress lookup/readback calls."}
    )
    authenticated_readback_verified: bool = field(
        default=False,
        metadata={"doc": "Whether authenticated WordPress readback matched the post."},
    )
    readback_expectation: WordPressPostReadExpectation | None = field(
        default=None,
        metadata={
            "doc": "Expected WordPress transaction identity persisted for future authenticated readback."
        },
    )
    readback_checks: List[WordPressPostReadCheck] = field(
        default_factory=list,
        metadata={
            "doc": "Bounded authenticated readback proof without post content or source prose."
        },
    )


@dataclass(frozen=True)
class PublishQueueRequest:
    schema_version: str = field(
        metadata={"doc": "Publish queue orchestrator request schema version."}
    )
    output_dir: str = field(
        metadata={"doc": "Directory containing generated HTML files."}
    )
    state_db: str = field(metadata={"doc": "SQLite path storing publish state."})
    reports_db: str = field(
        default="",
        metadata={
            "doc": "Optional report metadata SQLite path used for html_path->file_id mapping."
        },
    )
    post_type: str = field(
        default="ml_report",
        metadata={"doc": "WordPress post type slug used when resolving publish state."},
    )


@dataclass(frozen=True)
class PublishQueueItem:
    schema_version: str = field(metadata={"doc": "Publish queue item schema version."})
    html_path: str = field(
        metadata={"doc": "HTML file path queued for publish evaluation."}
    )
    file_id: str = field(
        metadata={
            "doc": "Resolved report file identifier (reports DB mapping first, HTML fallback)."
        }
    )
    published: bool = field(
        metadata={"doc": "True when publish state already exists for this file."}
    )
    wp_post_id: Optional[int] = field(
        default=None, metadata={"doc": "WordPress post ID when already published."}
    )
    wp_post_url: Optional[str] = field(
        default=None, metadata={"doc": "WordPress post URL when already published."}
    )


@dataclass(frozen=True)
class PublishQueueResponse:
    schema_version: str = field(
        metadata={"doc": "Publish queue orchestrator response schema version."}
    )
    items: List[PublishQueueItem] = field(
        metadata={"doc": "Resolved publish queue records."}
    )
