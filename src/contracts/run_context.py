from __future__ import annotations

from dataclasses import dataclass, field

from src.contracts.semantic_ids import RunId, SemanticIdContract, TaskId


@dataclass(frozen=True)
class RunContext(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Run context schema version."})
    run_id: RunId = field(metadata={"doc": "Unique run identifier."})
    task_id: TaskId = field(
        metadata={"doc": "Task identifier for grouping related events."}
    )
    span_id: str = field(metadata={"doc": "Span identifier for a specific operation."})
    trace_id: str = field(
        default="",
        metadata={"doc": "End-to-end trace identifier shared by all spans in one run."},
    )
    parent_span_id: str = field(
        default="",
        metadata={"doc": "Parent span identifier; empty only for the trace root span."},
    )
    span_name: str = field(
        default="",
        metadata={"doc": "Human-readable operation name for trace inspection."},
    )
    span_depth: int = field(
        default=0,
        metadata={"doc": "Zero-based nested depth of this span in the trace tree."},
    )
    producer_commit_sha: str = field(
        default="",
        metadata={
            "doc": "Trusted producer revision supplied by runtime environment, when available."
        },
    )
    validation_run_id: str = field(
        default="",
        metadata={
            "doc": "Immutable validation-run identity propagated to runtime events."
        },
    )
    cohort_id: str = field(
        default="",
        metadata={
            "doc": "Immutable admitted cohort identity when the run is cohort-bound."
        },
    )
    report_id: str = field(
        default="",
        metadata={"doc": "Current report identity when a span is report-scoped."},
    )
    source_identity_id: str = field(
        default="",
        metadata={
            "doc": "Immutable source checksum or equivalent identity for the current report."
        },
    )
    publisher_id: str = field(
        default="",
        metadata={
            "doc": "Current publisher identity, or an explicit unattributed sentinel."
        },
    )
    workflow: str = field(
        default="",
        metadata={"doc": "Workflow owning the current runtime span."},
    )
    stage: str = field(
        default="",
        metadata={"doc": "Workflow stage owning the current runtime span."},
    )
    artifact_family: str = field(
        default="",
        metadata={"doc": "Artifact family produced or validated by the current span."},
    )
    configuration_hash: str = field(
        default="",
        metadata={"doc": "Resolved configuration identity for validation attribution."},
    )
    policy_hash: str = field(
        default="",
        metadata={"doc": "Resolved policy identity for validation attribution."},
    )
    admission_decision_hash: str = field(
        default="",
        metadata={
            "doc": (
                "Deterministic source-admission decision required before report "
                "evidence or editorial work."
            )
        },
    )
    execution_plan_hash: str = field(
        default="",
        metadata={"doc": "Deterministic execution-plan identity when applicable."},
    )
    repair_attempt: int = field(
        default=0,
        metadata={
            "doc": "Bounded targeted-repair attempt number for the current span."
        },
    )
