from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.contracts.cross_report_analysis import (
    CrossReportProjectedDataReadRequest,
    CrossReportPublishResultSummary,
    PublicationMode,
)


WORDPRESS_ENTITY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class SignalPublishProjection:
    schema_version: str = field(
        metadata={"doc": "Signal publish projection schema version."}
    )
    title: str = field(metadata={"doc": "Public Signal title."})
    slug: str = field(metadata={"doc": "Deterministic WordPress Signal slug."})
    summary_html: str = field(
        metadata={"doc": "Escaped summary HTML approved for archive cards."}
    )
    body_html: str = field(
        metadata={"doc": "Escaped body HTML approved for the Signal detail page."}
    )
    evidence_ids: List[str] = field(
        metadata={"doc": "Projected evidence IDs grounding this Signal."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Source report IDs that contributed evidence."}
    )
    topic_ids: List[str] = field(
        metadata={"doc": "Canonical topic/category IDs assigned to the Signal."}
    )
    confidence: float = field(
        metadata={"doc": "Validated confidence score in the inclusive range 0..1."}
    )
    uncertainty: str = field(
        metadata={"doc": "Operator-visible uncertainty or coverage limitation note."}
    )
    validation_status: str = field(
        metadata={"doc": "Signal validation status, for example approved or blocked."}
    )
    file_id: str = field(
        default="",
        metadata={"doc": "Stable pseudo file ID used for WordPress idempotency."},
    )
    html_text: str = field(
        default="",
        metadata={"doc": "Complete Signal HTML document used for review/publish."},
    )
    topic_labels: List[str] = field(
        default_factory=list,
        metadata={"doc": "Human-readable category/topic labels assigned to the Signal."},
    )
    tag_labels: List[str] = field(
        default_factory=list,
        metadata={"doc": "Human-readable tag labels assigned to the Signal."},
    )
    publisher_labels: List[str] = field(
        default_factory=list,
        metadata={"doc": "Publisher names represented by grounded evidence."},
    )
    target_route: str = field(
        default="wordpress:ml_signal",
        metadata={"doc": "Canonical WordPress route for durable Signal posts."},
    )


@dataclass(frozen=True)
class SignalPostGenerationRequest:
    schema_version: str = field(metadata={"doc": "Signal generation request schema version."})
    request_id: str = field(metadata={"doc": "Stable Signal generation request ID."})
    topic: str = field(metadata={"doc": "Operator-selected Signal topic."})
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected category labels/IDs used to scope Signal evidence."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected tags used to scope Signal evidence."},
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Publisher names or IDs used to scope Signal evidence."},
    )
    date_range_start: str | None = field(
        default=None,
        metadata={"doc": "Inclusive projected report date lower bound."},
    )
    date_range_end: str | None = field(
        default=None,
        metadata={"doc": "Inclusive projected report date upper bound."},
    )
    max_source_reports: int = field(
        default=3,
        metadata={"doc": "Maximum projected source reports retained for one Signal."},
    )
    max_evidence_items: int = field(
        default=6,
        metadata={"doc": "Maximum projected evidence rows retained for one Signal."},
    )
    minimum_source_reports: int = field(
        default=2,
        metadata={"doc": "Minimum distinct source reports required for approval."},
    )
    minimum_evidence_items: int = field(
        default=2,
        metadata={"doc": "Minimum projected evidence rows required for approval."},
    )
    target_route: str = field(
        default="wordpress:ml_signal",
        metadata={"doc": "Canonical WordPress route for generated Signal posts."},
    )


@dataclass(frozen=True)
class SignalPostWorkflowRequest:
    schema_version: str = field(metadata={"doc": "Signal workflow request schema version."})
    request_id: str = field(metadata={"doc": "Stable Signal workflow request ID."})
    generation_request: SignalPostGenerationRequest = field(
        metadata={"doc": "Deterministic Signal generation request."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    output_root: str = field(metadata={"doc": "Output root for Signal publish artifacts."})
    publication_mode: PublicationMode = field(
        default="publish_dry_run",
        metadata={"doc": "Publication mode for the Signal workflow."},
    )


@dataclass(frozen=True)
class SignalPostWorkflowResult:
    schema_version: str = field(metadata={"doc": "Signal workflow result schema version."})
    request_id: str = field(metadata={"doc": "Signal workflow request ID."})
    projected_data_request: CrossReportProjectedDataReadRequest = field(
        metadata={"doc": "Projected-data service request used by the workflow."}
    )
    projection: SignalPublishProjection = field(
        metadata={"doc": "Generated durable Signal publish projection."}
    )
    publish_result: CrossReportPublishResultSummary = field(
        metadata={"doc": "WordPress publish result for the Signal projection."}
    )
