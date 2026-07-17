from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts._cross_report_analysis import (
    CrossReportReadContentClass,
    ProjectionReadinessStatus,
    PublicationMode,
)
from src.contracts.run_budget import RunBudget


@dataclass(frozen=True)
class CrossReportAnalysisRequest:
    schema_version: str = field(metadata={"doc": "Request contract schema version."})
    request_id: str = field(
        metadata={"doc": "Stable operator or orchestrator request identifier."}
    )
    topic: str = field(
        metadata={
            "doc": "Explicit requested analysis topic; empty only when auto-theme selection is enabled.",
            "required": False,
        }
    )
    auto_theme: bool = field(
        metadata={"doc": "Whether deterministic theme selection may choose the topic."}
    )
    category_filters: List[str] = field(
        metadata={
            "doc": "Normalized category filters applied to projected reports.",
            "required": False,
        }
    )
    tag_filters: List[str] = field(
        metadata={
            "doc": "Normalized tag filters applied to projected reports.",
            "required": False,
        }
    )
    publisher_filters: List[str] = field(
        metadata={
            "doc": "Normalized publisher filters applied to projected reports.",
            "required": False,
        }
    )
    date_range_start: Optional[str] = field(
        metadata={
            "doc": "Inclusive report date lower bound in ISO format, if set.",
            "required": False,
        }
    )
    date_range_end: Optional[str] = field(
        metadata={
            "doc": "Inclusive report date upper bound in ISO format, if set.",
            "required": False,
        }
    )
    max_source_reports: int = field(
        metadata={"doc": "Maximum selected projected reports for synthesis."}
    )
    diagnostic: bool = field(
        metadata={
            "doc": "Whether diagnostic mode may inspect otherwise unpublishable source sets."
        }
    )
    override_publishability: bool = field(
        metadata={
            "doc": "Explicit operator override for publishability gates; logged by orchestrators."
        }
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Requested publication mode for this workflow."}
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional scoped budget forwarded to the model call."},
    )


@dataclass(frozen=True)
class CrossReportProjectedDataReadRequest:
    schema_version: str = field(
        metadata={"doc": "Projected data read request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite reports database path containing projection tables."}
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive publisher names or IDs to include."},
    )
    date_range_start: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Inclusive projection/report date lower bound in YYYY-MM-DD format."
        },
    )
    date_range_end: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Inclusive projection/report date upper bound in YYYY-MM-DD format."
        },
    )
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive category IDs or labels to include."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive projected tags to include."},
    )
    content_classes: List[CrossReportReadContentClass] = field(
        default_factory=list,
        metadata={
            "doc": "Projected evidence classes to return; empty means claims, findings, quotes, and metrics."
        },
    )
    minimum_projection_status: ProjectionReadinessStatus = field(
        default="projected",
        metadata={
            "doc": "Minimum projection status to include: projected includes only ready reports."
        },
    )


@dataclass(frozen=True)
class CrossReportAnalysisOrchestratorRequest:
    schema_version: str = field(
        metadata={"doc": "Cross-report orchestrator request schema version."}
    )
    analysis_request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Business request for cross-report analysis generation."}
    )
    projected_data_request: "CrossReportProjectedDataReadRequest" = field(
        metadata={"doc": "Analytics-store projected data read request."}
    )
    idempotency_db_path: str = field(
        metadata={"doc": "SQLite idempotency database path for orchestrator reuse."}
    )
    output_root: str = field(
        metadata={"doc": "Output root used to derive the planned artifact path."}
    )
    max_evidence_items: int = field(
        default=48,
        metadata={"doc": "Maximum evidence items assembled before synthesis."},
    )
    max_signals: int = field(
        default=8,
        metadata={"doc": "Maximum signal scores retained before synthesis."},
    )
    max_prompt_chars: int = field(
        default=60000,
        metadata={"doc": "Maximum prompt/input character budget for validation."},
    )
    retry_retries: int = field(
        default=2,
        metadata={"doc": "Maximum retries for retryable service/generator failures."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base retry delay controlled by the orchestrator."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear retry backoff step controlled by the orchestrator."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Retry jitter controlled by the orchestrator."},
    )
    publish_target_route: str = field(
        default="wordpress:ml_briefing",
        metadata={"doc": "Publication target route for cross-report Briefing posts."},
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={"doc": "Optional scoped budget for cross-report retries and models."},
    )
    state_db: str = field(
        default="",
        metadata={"doc": "Optional canonical remediation-ledger state database."},
    )
