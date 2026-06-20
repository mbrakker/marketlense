from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts._cross_report_analysis import (
    CrossReportPublishStatus,
    CrossReportValidationStatus,
    PublicationMode,
)


@dataclass(frozen=True)
class CrossReportPublishRequestSummary:
    schema_version: str = field(
        metadata={"doc": "Publish request summary contract schema version."}
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Publication mode requested by the operator or orchestrator."}
    )
    target_route: str = field(
        metadata={"doc": "Existing publish route or target surface identifier."}
    )
    title: str = field(metadata={"doc": "Publish-ready title."})
    slug: str = field(metadata={"doc": "Publish-ready slug."})
    artifact_path: str = field(
        metadata={"doc": "Canonical local analysis artifact path."}
    )
    validation_status: CrossReportValidationStatus = field(
        metadata={"doc": "Validation status used for publish gating."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected source report IDs used in publish idempotency."}
    )
    selected_theme_id: str = field(
        metadata={"doc": "Selected theme ID used in publish idempotency."}
    )


@dataclass(frozen=True)
class CrossReportPublishResultSummary:
    schema_version: str = field(
        metadata={"doc": "Publish result summary contract schema version."}
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Publication mode that was evaluated."}
    )
    status: CrossReportPublishStatus = field(
        metadata={"doc": "Publish outcome status from the existing publish pathway."}
    )
    target_route: str = field(metadata={"doc": "Publish route that was evaluated."})
    idempotency_reused: bool = field(
        metadata={"doc": "Whether an existing publish outcome was reused."}
    )
    target_post_type: Optional[str] = field(
        default=None,
        metadata={"doc": "Resolved WordPress REST post type for the evaluated route."},
    )
    target_slug: Optional[str] = field(
        default=None,
        metadata={"doc": "Deterministic WordPress post slug for the publish payload."},
    )
    category_slugs: List[str] = field(
        default_factory=list,
        metadata={"doc": "Native WordPress category slugs assigned to the payload."},
    )
    tag_slugs: List[str] = field(
        default_factory=list,
        metadata={"doc": "Native WordPress tag slugs assigned to the payload."},
    )
    taxonomy_term_slugs: Dict[str, List[str]] = field(
        default_factory=dict,
        metadata={
            "doc": "Custom taxonomy REST base to assigned term slugs for the payload."
        },
    )
    post_id: Optional[int] = field(
        default=None,
        metadata={"doc": "WordPress post ID when live publication produced one."},
    )
    post_url: Optional[str] = field(
        default=None,
        metadata={"doc": "WordPress post URL when live publication produced one."},
    )
    error_code: Optional[str] = field(
        default=None, metadata={"doc": "Typed publish error code when status is error."}
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Sanitized publish error message when status is error."},
    )


@dataclass(frozen=True)
class CrossReportPublishPackage:
    schema_version: str = field(
        metadata={"doc": "Cross-report publish package contract schema version."}
    )
    package_id: str = field(
        metadata={"doc": "Stable package identifier used as the publish file marker."}
    )
    file_id: str = field(
        metadata={
            "doc": "Canonical pseudo file ID used by the existing publish lookup path."
        }
    )
    target_route: str = field(
        metadata={"doc": "Existing publish route or target surface identifier."}
    )
    title: str = field(metadata={"doc": "Publish-ready title."})
    slug: str = field(metadata={"doc": "Publish-ready slug."})
    excerpt: str = field(metadata={"doc": "Publish-ready excerpt or summary."})
    body_html: str = field(
        metadata={"doc": "Publish-ready body HTML fragment for WordPress."}
    )
    html_text: str = field(
        metadata={"doc": "Complete HTML document persisted for review and publishing."}
    )
    html_path: str = field(
        metadata={"doc": "Canonical local HTML publish package path."}
    )
    canonical_artifact_path: str = field(
        metadata={"doc": "Canonical local analysis JSON artifact path."}
    )
    artifact_sha256: str = field(
        metadata={"doc": "Deterministic hash of generated artifact-relevant payload."}
    )
    validation_sha256: str = field(
        metadata={"doc": "Deterministic hash of validation result payload."}
    )
    selected_theme_id: str = field(
        metadata={"doc": "Selected theme ID used in publish idempotency."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected source report IDs represented by the package."}
    )
    source_metadata: List[Dict[str, Any]] = field(
        metadata={
            "doc": "Source report metadata map rendered and published for provenance."
        }
    )
    category_labels: List[str] = field(
        metadata={
            "doc": "Category labels carried into publish metadata.",
            "required": False,
        }
    )
    tag_labels: List[str] = field(
        metadata={"doc": "Tag labels carried into publish metadata.", "required": False}
    )
    evidence_reference_ids: List[str] = field(
        metadata={"doc": "Evidence IDs rendered into the evidence reference map."}
    )
    raw_metric_ids: List[str] = field(
        metadata={
            "doc": "Raw metric IDs rendered into the raw metric appendix when source metrics are available.",
            "required": False,
        }
    )
    prompt_hashes: Dict[str, str] = field(
        metadata={"doc": "Prompt hashes used to generate the package."}
    )
    machine_metadata: Dict[str, Any] = field(
        metadata={"doc": "Machine-readable cross-report metadata embedded in HTML."}
    )
    briefing_card: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Validated briefing-card fields and generated cover assets."},
    )
    signal_card: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Validated signal-card fields and generated cover assets."},
    )
