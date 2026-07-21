"""Typed contracts for the canonical bounded-validation run manifest."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.contracts.semantic_ids import RunId, SemanticIdContract, ValidationRunId


@dataclass(frozen=True)
class ValidationRunManifestCreateRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Manifest create request schema version."}
    )
    db_path: str
    validation_run_id: ValidationRunId
    cohort_id: str
    workflow_run_id: RunId
    configuration_hash: str
    policy_hash: str
    producer_build_identity: str
    created_at_utc: str


@dataclass(frozen=True)
class ValidationRunManifestStageRecord(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Manifest stage record schema version."}
    )
    validation_run_id: ValidationRunId
    cohort_id: str
    workflow_run_id: RunId
    entity_type: str
    publisher_id: str
    report_id: str
    source_identity_id: str
    stage: str
    attempt_number: int
    parent_attempt_number: int
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    started_at_utc: str
    completed_at_utc: str
    terminal_outcome: str
    failure_code: str
    retryable: bool
    repair_disposition: str
    duplicate_disposition: str
    supersession_state: str
    idempotency_state: str
    configuration_hash: str
    policy_hash: str
    producer_build_identity: str
    cohort_disposition: str = "final_validation"
    entity_terminal: bool = False


@dataclass(frozen=True)
class ValidationRunManifestRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Manifest record request schema version."}
    )
    db_path: str
    record: ValidationRunManifestStageRecord


@dataclass(frozen=True)
class ValidationRunManifestRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Manifest record response schema version."}
    )
    stage_record_id: str
    inserted: bool
    superseded_attempts: int


@dataclass(frozen=True)
class ValidationRunManifestAuditRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Manifest audit request schema version."}
    )
    db_path: str
    validation_run_id: ValidationRunId


@dataclass(frozen=True)
class ValidationRunManifestStageTotal:
    schema_version: str = field(
        metadata={"doc": "Manifest stage total schema version."}
    )
    stage: str
    terminal_outcome: str
    entity_count: int


@dataclass(frozen=True)
class ValidationRunManifestAuditResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Manifest audit response schema version."}
    )
    validation_run_id: ValidationRunId
    complete: bool
    final_cohort_report_ids: tuple[str, ...]
    stage_totals: tuple[ValidationRunManifestStageTotal, ...]
    incomplete_entity_ids: tuple[str, ...]
    duplicate_current_entity_ids: tuple[str, ...]
