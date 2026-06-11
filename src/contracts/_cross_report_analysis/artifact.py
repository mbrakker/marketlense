from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .common import (
    CrossReportOutcomeStatus,
    CrossReportValidationStatus,
)
from .generation import CrossReportGeneratedAnalysisResult, CrossReportValidationResult
from .publication import (
    CrossReportPublishPackage,
    CrossReportPublishRequestSummary,
    CrossReportPublishResultSummary,
)
from .requests import CrossReportAnalysisRequest

@dataclass(frozen=True)
class CrossReportAnalysisArtifact:
    schema_version: str = field(
        metadata={"doc": "Persisted analysis artifact contract schema version."}
    )
    artifact_type: str = field(
        metadata={"doc": "Stable artifact type identifier for replay and review."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the artifact was generated."}
    )
    request_fingerprint: str = field(
        metadata={
            "doc": "Deterministic fingerprint of request, source, prompt, and config inputs."
        }
    )
    idempotency_key: str = field(
        metadata={"doc": "Orchestrator idempotency key associated with this artifact."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected projected report IDs represented in the artifact."}
    )
    projection_content_hashes: Dict[str, Dict[str, str]] = field(
        metadata={"doc": "Projection content hashes keyed by report ID and entity UID."}
    )
    prompt_hashes: Dict[str, str] = field(
        metadata={"doc": "Prompt hashes used to generate the analysis."}
    )
    config_fingerprint: Dict[str, Any] = field(
        metadata={"doc": "Generation-relevant configuration values used for replay."}
    )
    validation_status: CrossReportValidationStatus = field(
        metadata={"doc": "Deterministic validation status at persistence time."}
    )
    request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Validated business request used for synthesis."}
    )
    generated_result: CrossReportGeneratedAnalysisResult = field(
        metadata={"doc": "Generated analysis payload."}
    )
    validation_result: CrossReportValidationResult = field(
        metadata={"doc": "Validation result for the generated analysis."}
    )
    publish_request: CrossReportPublishRequestSummary = field(
        metadata={"doc": "Publish request summary derived for downstream routing."}
    )
    publish_result: CrossReportPublishResultSummary = field(
        metadata={"doc": "Publish result summary known at persistence time."}
    )
    publish_package: CrossReportPublishPackage = field(
        metadata={"doc": "Publish package generated for review or publication."}
    )


@dataclass(frozen=True)
class CrossReportOrchestratorOutcome:
    schema_version: str = field(
        metadata={"doc": "Orchestrator outcome contract schema version."}
    )
    run_id: str = field(metadata={"doc": "Run identifier for structured logs."})
    task_id: str = field(metadata={"doc": "Task identifier for structured logs."})
    status: CrossReportOutcomeStatus = field(
        metadata={"doc": "Final orchestrator workflow status."}
    )
    artifact_path: str = field(
        metadata={"doc": "Canonical generated analysis artifact path."}
    )
    request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Validated request that started the workflow."}
    )
    generated_result: CrossReportGeneratedAnalysisResult = field(
        metadata={"doc": "Generated analysis result, if synthesis completed."}
    )
    validation_result: CrossReportValidationResult = field(
        metadata={"doc": "Deterministic validation result."}
    )
    publish_request: CrossReportPublishRequestSummary = field(
        metadata={"doc": "Publish request summary evaluated by the orchestrator."}
    )
    publish_result: CrossReportPublishResultSummary = field(
        metadata={"doc": "Publish result summary from the publish boundary."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Idempotency key for generation and publication reuse."}
    )
    idempotency_reused: bool = field(
        metadata={"doc": "Whether this orchestrator outcome reused a prior result."}
    )
    state_transitions: List[str] = field(
        metadata={"doc": "Ordered workflow state transitions recorded by orchestrator."}
    )
