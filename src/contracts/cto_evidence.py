"""Versioned contracts for run-scoped and historical CTO evidence."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal, TypeAlias

SCHEMA_VERSION = "1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SAFE_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]{0,127}$")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
FORMAT_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_./:-]{0,127}$")
EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
FORBIDDEN_KEY_PARTS = (
    "api_key",
    "access_token",
    "credential",
    "email",
    "password",
    "phone",
    "prompt",
    "raw_response",
    "report_id",
    "source_text",
    "token_value",
)

MetricStatus = Literal["observed", "partial", "unavailable", "not_applicable"]
CriterionDisposition = Literal["pass", "fail", "not_evaluated", "insufficient_evidence"]
Completeness = Literal["complete", "incomplete", "invalid"]
RunDisposition = Literal["pass", "fail", "not_evaluated", "insufficient_evidence"]
ScalarValue: TypeAlias = str | int | float | bool


def _bounded_text(value: str, *, field_name: str, maximum: int = 512) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(
            f"{field_name} must be non-empty and at most {maximum} characters"
        )
    if "\x00" in value or EMAIL_RE.search(value) or URL_RE.search(value):
        raise ValueError(f"{field_name} contains disallowed personal or link content")


def _identifier(
    value: str, *, field_name: str, pattern: re.Pattern[str] = SAFE_ID_RE
) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{field_name} must be a bounded identifier")


def _safe_key(value: str, *, field_name: str = "key") -> None:
    _identifier(value, field_name=field_name, pattern=SAFE_KEY_RE)
    normalized = value.casefold()
    if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
        raise ValueError(f"{field_name} uses a forbidden sensitive field name")


def _sha256(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _git_sha(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not GIT_SHA_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a full repository SHA")


def _timestamp(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")


def _scalar(value: object, *, field_name: str, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, (bool, str)):
        if isinstance(value, str):
            _bounded_text(value, field_name=field_name, maximum=512)
        return
    if isinstance(value, int):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise ValueError(f"{field_name} must be a finite scalar value")


def _unique(values: tuple[str, ...], *, field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


@dataclass(frozen=True)
class CTOEvidenceIdentity:
    """One safe, comparable configuration or compatibility identity value."""

    schema_version: str = field(metadata={"doc": "Identity schema version."})
    key: str = field(metadata={"doc": "Stable identity field name."})
    value: str = field(metadata={"doc": "Bounded non-secret identity value."})

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceIdentity")
        _safe_key(self.key)
        _bounded_text(self.value, field_name="identity value", maximum=192)


@dataclass(frozen=True)
class CTOEvidenceSourceReference:
    """Hash-pinned reference to one authoritative retained evidence artifact."""

    schema_version: str = field(metadata={"doc": "Source reference schema version."})
    source_id: str
    producer: str
    format_id: str
    path: str
    sha256: str
    tested_repository_sha: str | None
    role: Literal["run", "baseline", "candidate", "supporting"] = "run"
    status: Literal["declared", "verified", "missing", "mismatch"] = "declared"
    byte_count: int | None = None
    observed_sha256: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceSourceReference")
        _identifier(self.source_id, field_name="source_id")
        _bounded_text(self.producer, field_name="producer", maximum=128)
        _identifier(self.format_id, field_name="format_id", pattern=FORMAT_ID_RE)
        _relative_path(self.path)
        _sha256(self.sha256, field_name="sha256")
        if self.tested_repository_sha is not None:
            _git_sha(self.tested_repository_sha, field_name="tested_repository_sha")
        if self.role not in {"run", "baseline", "candidate", "supporting"}:
            raise ValueError("source role is invalid")
        if self.status not in {"declared", "verified", "missing", "mismatch"}:
            raise ValueError("source status is invalid")
        if self.byte_count is not None and self.byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        if self.observed_sha256 is not None:
            _sha256(self.observed_sha256, field_name="observed_sha256")
        if self.status == "verified" and (
            self.observed_sha256 != self.sha256 or self.byte_count is None
        ):
            raise ValueError("verified source must match its declared SHA and size")
        if self.status == "missing" and self.observed_sha256 is not None:
            raise ValueError("missing source cannot have an observed SHA")
        if self.status == "mismatch" and (
            self.observed_sha256 is None or self.observed_sha256 == self.sha256
        ):
            raise ValueError("mismatched source must retain its differing observed SHA")


@dataclass(frozen=True)
class CTOEvidenceSubject:
    """An immutable subject alias and hashed identity, free of source identifiers."""

    schema_version: str = field(metadata={"doc": "Subject schema version."})
    subject_id: str
    identity_sha256: str
    immutable: bool
    source_identity_sha256: str | None = None
    terminal_outcome: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceSubject")
        _identifier(self.subject_id, field_name="subject_id")
        _sha256(self.identity_sha256, field_name="identity_sha256")
        if self.source_identity_sha256 is not None:
            _sha256(self.source_identity_sha256, field_name="source_identity_sha256")
        if self.terminal_outcome is not None:
            _safe_key(self.terminal_outcome, field_name="terminal_outcome")


@dataclass(frozen=True)
class CTOEvidenceMetric:
    """A scalar measurement whose status distinguishes missing from observed zero."""

    schema_version: str = field(metadata={"doc": "Metric schema version."})
    metric_id: str
    status: MetricStatus
    value: ScalarValue | None
    unit: str
    source_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    numerator: float | None = None
    denominator: float | None = None
    measurement_semantics: str = ""
    subject_id: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceMetric")
        _identifier(self.metric_id, field_name="metric_id")
        if self.subject_id is not None:
            _identifier(self.subject_id, field_name="subject_id")
        if self.status not in {"observed", "partial", "unavailable", "not_applicable"}:
            raise ValueError("metric status is invalid")
        _bounded_text(self.unit, field_name="unit", maximum=64)
        if self.status in {"observed", "partial"} and self.value is None:
            raise ValueError("observed and partial metrics require a value")
        if self.status in {"unavailable", "not_applicable"} and self.value is not None:
            raise ValueError(
                "unavailable and not_applicable metrics cannot carry values"
            )
        if self.value is not None:
            _scalar(self.value, field_name="metric value")
        if self.numerator is not None and (
            isinstance(self.numerator, bool)
            or not isinstance(self.numerator, (int, float))
            or not math.isfinite(self.numerator)
        ):
            raise ValueError("metric numerator must be finite")
        if self.denominator is not None and (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, (int, float))
            or not math.isfinite(self.denominator)
            or self.denominator < 0
        ):
            raise ValueError("metric denominator must be finite")
        for source_id in self.source_ids:
            _identifier(source_id, field_name="source_id")
        for limitation in self.limitations:
            _bounded_text(limitation, field_name="limitation", maximum=320)
        if self.measurement_semantics:
            _bounded_text(
                self.measurement_semantics,
                field_name="measurement_semantics",
                maximum=320,
            )


@dataclass(frozen=True)
class CTOEvidenceCriterion:
    """A required or informational deterministic evaluation condition."""

    schema_version: str = field(metadata={"doc": "Criterion schema version."})
    criterion_id: str
    description: str
    metric_id: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "truthy"]
    expected_value: ScalarValue
    required: bool
    stage: str | None = None
    actual_value: ScalarValue | None = None
    disposition: CriterionDisposition = "not_evaluated"

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceCriterion")
        _identifier(self.criterion_id, field_name="criterion_id")
        _bounded_text(self.description, field_name="criterion description")
        _identifier(self.metric_id, field_name="metric_id")
        if self.operator not in {"eq", "ne", "gt", "gte", "lt", "lte", "truthy"}:
            raise ValueError("criterion operator is invalid")
        if self.disposition not in {
            "pass",
            "fail",
            "not_evaluated",
            "insufficient_evidence",
        }:
            raise ValueError("criterion disposition is invalid")
        _scalar(self.expected_value, field_name="expected_value")
        if self.actual_value is not None:
            _scalar(self.actual_value, field_name="actual_value")
        if self.stage is not None:
            _identifier(self.stage, field_name="stage")
        if self.disposition in {"pass", "fail"} and self.actual_value is None:
            raise ValueError("evaluated criterion requires an actual value")


@dataclass(frozen=True)
class CTOEvidenceInvariant:
    """A declared invariant compared across baseline and candidate."""

    schema_version: str = field(metadata={"doc": "Invariant schema version."})
    key: str
    baseline_value: str
    candidate_value: str

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceInvariant")
        _safe_key(self.key)
        _bounded_text(self.baseline_value, field_name="baseline invariant", maximum=192)
        _bounded_text(
            self.candidate_value, field_name="candidate invariant", maximum=192
        )


@dataclass(frozen=True)
class CTOEvidenceComparison:
    """Compatible before/after references with explicit invariants and caveats."""

    schema_version: str = field(metadata={"doc": "Comparison schema version."})
    comparison_id: str
    baseline_source_id: str
    candidate_source_id: str
    baseline_selector: str
    candidate_selector: str
    baseline_repository_sha: str
    candidate_repository_sha: str
    baseline_identity: tuple[CTOEvidenceIdentity, ...]
    candidate_identity: tuple[CTOEvidenceIdentity, ...]
    invariants: tuple[CTOEvidenceInvariant, ...]
    changed_variables: tuple[str, ...]
    limitations: tuple[str, ...]
    status: Literal["declared", "compatible", "incompatible", "unavailable"] = (
        "declared"
    )
    metric_deltas: tuple[CTOEvidenceMetric, ...] = ()
    causal_attribution: Literal["not_established"] = "not_established"

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceComparison")
        _identifier(self.comparison_id, field_name="comparison_id")
        _identifier(self.baseline_source_id, field_name="baseline_source_id")
        _identifier(self.candidate_source_id, field_name="candidate_source_id")
        _safe_selector(self.baseline_selector)
        _safe_selector(self.candidate_selector)
        _git_sha(self.baseline_repository_sha, field_name="baseline_repository_sha")
        _git_sha(self.candidate_repository_sha, field_name="candidate_repository_sha")
        if self.status not in {"declared", "compatible", "incompatible", "unavailable"}:
            raise ValueError("comparison status is invalid")
        _unique(
            tuple(item.key for item in self.baseline_identity),
            field_name="baseline identity key",
        )
        _unique(
            tuple(item.key for item in self.candidate_identity),
            field_name="candidate identity key",
        )
        _unique(
            tuple(item.key for item in self.invariants),
            field_name="comparison invariant key",
        )
        for variable in self.changed_variables:
            _safe_key(variable, field_name="changed variable")
        for limitation in self.limitations:
            _bounded_text(limitation, field_name="comparison limitation", maximum=320)


@dataclass(frozen=True)
class CTOEvidenceAttempt:
    """Append-only per-subject execution or recovery attempt."""

    schema_version: str = field(metadata={"doc": "Attempt schema version."})
    subject_id: str
    attempt_number: int
    kind: Literal[
        "initial_execution",
        "deterministic_recovery",
        "structured_output_recovery",
        "evidence_claim_reuse",
        "semantic_repair",
        "targeted_regeneration",
        "workflow_retry",
        "operator_retry",
        "manual_intervention",
        "abstention",
        "terminal_failure",
    ]
    outcome: Literal["success", "failed", "abstained", "not_evaluated"]
    failure_code: str | None = None
    parent_attempt_number: int | None = None
    operator_intervention: bool = False
    source_id: str | None = None

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceAttempt")
        _identifier(self.subject_id, field_name="subject_id")
        if self.kind not in {
            "initial_execution",
            "deterministic_recovery",
            "structured_output_recovery",
            "evidence_claim_reuse",
            "semantic_repair",
            "targeted_regeneration",
            "workflow_retry",
            "operator_retry",
            "manual_intervention",
            "abstention",
            "terminal_failure",
        }:
            raise ValueError("attempt kind is invalid")
        if self.outcome not in {"success", "failed", "abstained", "not_evaluated"}:
            raise ValueError("attempt outcome is invalid")
        if (
            isinstance(self.attempt_number, bool)
            or not isinstance(self.attempt_number, int)
            or self.attempt_number < 1
        ):
            raise ValueError("attempt_number must be positive")
        if self.parent_attempt_number is not None and not (
            isinstance(self.parent_attempt_number, int)
            and not isinstance(self.parent_attempt_number, bool)
            and 1 <= self.parent_attempt_number < self.attempt_number
        ):
            raise ValueError("parent attempt must precede its recovery")
        if not isinstance(self.operator_intervention, bool):
            raise ValueError("operator_intervention must be a boolean")
        if self.failure_code is not None:
            _identifier(self.failure_code, field_name="failure_code")
        if self.source_id is not None:
            _identifier(self.source_id, field_name="source_id")


@dataclass(frozen=True)
class CTOEvidenceReuseDecision:
    """Subject-level reusable work, newly executed work, and avoided calls."""

    schema_version: str = field(metadata={"doc": "Reuse decision schema version."})
    subject_id: str
    eligible_candidates: int | None
    reused_validations: int | None
    newly_executed_validations: int | None
    avoided_grounding_calls: int | None
    avoided_provider_calls: int | None
    fallback_reason_code: str | None
    source_id: str

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceReuseDecision")
        _identifier(self.subject_id, field_name="subject_id")
        _identifier(self.source_id, field_name="source_id")
        for name in (
            "eligible_candidates",
            "reused_validations",
            "newly_executed_validations",
            "avoided_grounding_calls",
            "avoided_provider_calls",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} cannot be negative")
        if self.fallback_reason_code is not None:
            _identifier(self.fallback_reason_code, field_name="fallback_reason_code")


@dataclass(frozen=True)
class CTOEvidenceQualityDimension:
    """Optional semantic, editorial, or visual quality evidence."""

    schema_version: str = field(metadata={"doc": "Quality dimension schema version."})
    dimension: str
    status: MetricStatus
    reviewed_subject_count: int | None
    rubric_id: str | None
    reviewer_attribution: Literal["available", "unavailable", "not_applicable"]
    metric_ids: tuple[str, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceQualityDimension")
        _safe_key(self.dimension, field_name="dimension")
        if self.status not in {"observed", "partial", "unavailable", "not_applicable"}:
            raise ValueError("quality status is invalid")
        if self.reviewed_subject_count is not None and (
            isinstance(self.reviewed_subject_count, bool)
            or not isinstance(self.reviewed_subject_count, int)
            or self.reviewed_subject_count < 0
        ):
            raise ValueError("reviewed_subject_count cannot be negative")
        if self.rubric_id is not None:
            _identifier(self.rubric_id, field_name="rubric_id")
        for metric_id in self.metric_ids:
            _identifier(metric_id, field_name="metric_id")
        for source_id in self.source_ids:
            _identifier(source_id, field_name="source_id")


@dataclass(frozen=True)
class CTOEvidenceExternalAction:
    """External action evidence that separates attempts, writes, and verification."""

    schema_version: str = field(metadata={"doc": "External action schema version."})
    system: str
    attempted_actions: int | None
    actual_writes: int | None
    skipped_actions: int | None
    blocked_actions: int | None
    failed_actions: int | None
    authenticated_readback: Literal["verified", "failed", "not_run", "unavailable"]
    repeat_result: Literal["zero_write", "writes", "failed", "not_run", "unavailable"]
    idempotency_result: Literal["passed", "failed", "not_evaluated", "unavailable"]
    source_id: str

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceExternalAction")
        _safe_key(self.system, field_name="system")
        _identifier(self.source_id, field_name="source_id")
        if self.authenticated_readback not in {
            "verified",
            "failed",
            "not_run",
            "unavailable",
        }:
            raise ValueError("authenticated_readback status is invalid")
        if self.repeat_result not in {
            "zero_write",
            "writes",
            "failed",
            "not_run",
            "unavailable",
        }:
            raise ValueError("repeat_result status is invalid")
        if self.idempotency_result not in {
            "passed",
            "failed",
            "not_evaluated",
            "unavailable",
        }:
            raise ValueError("idempotency_result status is invalid")
        for name in (
            "attempted_actions",
            "actual_writes",
            "skipped_actions",
            "blocked_actions",
            "failed_actions",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True)
class CTOEvidenceRun:
    """Open-taxonomy identity and scope for one declared engineering or product run."""

    schema_version: str = field(metadata={"doc": "Evidence run schema version."})
    run_id: str
    run_type: str
    objective: str
    tested_repository_sha: str
    producer_repository_sha: str | None
    started_at_utc: str | None
    ended_at_utc: str | None
    subjects: tuple[CTOEvidenceSubject, ...]
    configuration_identities: tuple[CTOEvidenceIdentity, ...]
    stages_in_scope: tuple[str, ...]
    stages_out_of_scope: tuple[str, ...]
    external_side_effects_enabled: bool | None
    operator_intervention_policy: str
    sources: tuple[CTOEvidenceSourceReference, ...]
    required_evidence_classes: tuple[str, ...]
    criteria: tuple[CTOEvidenceCriterion, ...]
    comparison: CTOEvidenceComparison | None = None

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceRun")
        if not isinstance(self.run_type, str) or not self.run_type.strip():
            raise ValueError("run_type must be a non-empty open value")
        _identifier(self.run_id, field_name="run_id")
        _safe_key(self.run_type, field_name="run_type")
        _bounded_text(self.objective, field_name="objective")
        _git_sha(self.tested_repository_sha, field_name="tested_repository_sha")
        if self.producer_repository_sha is not None:
            _git_sha(self.producer_repository_sha, field_name="producer_repository_sha")
        if (self.started_at_utc is None) != (self.ended_at_utc is None):
            raise ValueError(
                "run start and end timestamps must both be present or null"
            )
        if self.started_at_utc is not None and self.ended_at_utc is not None:
            _timestamp(self.started_at_utc, field_name="started_at_utc")
            _timestamp(self.ended_at_utc, field_name="ended_at_utc")
            if datetime.fromisoformat(
                self.ended_at_utc.replace("Z", "+00:00")
            ) < datetime.fromisoformat(self.started_at_utc.replace("Z", "+00:00")):
                raise ValueError("run end timestamp precedes start timestamp")
        _bounded_text(
            self.operator_intervention_policy,
            field_name="operator_intervention_policy",
        )
        _unique(
            tuple(item.subject_id for item in self.subjects), field_name="subject_id"
        )
        _unique(tuple(item.source_id for item in self.sources), field_name="source_id")
        _unique(
            tuple(item.criterion_id for item in self.criteria),
            field_name="criterion_id",
        )
        _unique(
            tuple(item.key for item in self.configuration_identities),
            field_name="identity key",
        )
        _unique(self.stages_in_scope, field_name="stages_in_scope")
        _unique(self.stages_out_of_scope, field_name="stages_out_of_scope")
        _unique(self.required_evidence_classes, field_name="required_evidence_classes")
        for value in (*self.stages_in_scope, *self.stages_out_of_scope):
            _safe_key(value, field_name="stage")
        for value in self.required_evidence_classes:
            _safe_key(value, field_name="required evidence class")
        overlap = set(self.stages_in_scope) & set(self.stages_out_of_scope)
        if overlap:
            raise ValueError("in-scope and out-of-scope stages must be disjoint")
        source_shas = {
            source.source_id: source.tested_repository_sha for source in self.sources
        }
        for source in self.sources:
            if source.role == "run" and source.tested_repository_sha not in {
                None,
                self.tested_repository_sha,
            }:
                raise ValueError("source tested SHA does not match the declared run")
        for criterion in self.criteria:
            if (
                criterion.stage in self.stages_out_of_scope
                and criterion.disposition != "not_evaluated"
            ):
                raise ValueError("out-of-scope criterion must be not_evaluated")
        if self.comparison is not None:
            if (
                self.comparison.baseline_source_id not in source_shas
                or self.comparison.candidate_source_id not in source_shas
            ):
                raise ValueError("comparison references an undeclared source")
            if self.comparison.baseline_identity != self.comparison.candidate_identity:
                raise ValueError("comparison compatibility identities do not match")
            if any(
                item.baseline_value != item.candidate_value
                for item in self.comparison.invariants
            ):
                raise ValueError("comparison invariant values do not match")
            if source_shas[self.comparison.candidate_source_id] not in {
                None,
                self.comparison.candidate_repository_sha,
            }:
                raise ValueError(
                    "candidate source tested SHA does not match comparison"
                )
            if source_shas[self.comparison.baseline_source_id] not in {
                None,
                self.comparison.baseline_repository_sha,
            }:
                raise ValueError("baseline source tested SHA does not match comparison")


@dataclass(frozen=True)
class CTOEvidenceOutcomeCount:
    schema_version: str = field(metadata={"doc": "Outcome count schema version."})
    outcome: str
    count: int

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceOutcomeCount")
        _safe_key(self.outcome, field_name="outcome")
        if self.count < 0:
            raise ValueError("outcome count cannot be negative")


@dataclass(frozen=True)
class CTOEvidenceRunEvidence:
    """Run-scoped projection, kept apart from historical system metrics."""

    schema_version: str = field(metadata={"doc": "Run evidence schema version."})
    subjects: tuple[CTOEvidenceSubject, ...]
    metrics: tuple[CTOEvidenceMetric, ...]
    criteria: tuple[CTOEvidenceCriterion, ...]
    outcomes: tuple[CTOEvidenceOutcomeCount, ...]
    attempts: tuple[CTOEvidenceAttempt, ...]
    reuse_decisions: tuple[CTOEvidenceReuseDecision, ...]
    quality_dimensions: tuple[CTOEvidenceQualityDimension, ...]
    external_actions: tuple[CTOEvidenceExternalAction, ...]
    comparison: CTOEvidenceComparison | None
    attempt_history_status: MetricStatus
    reuse_evidence_status: MetricStatus
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceRunEvidence")
        if self.attempt_history_status not in {
            "observed",
            "partial",
            "unavailable",
            "not_applicable",
        }:
            raise ValueError("attempt_history_status is invalid")
        if self.reuse_evidence_status not in {
            "observed",
            "partial",
            "unavailable",
            "not_applicable",
        }:
            raise ValueError("reuse_evidence_status is invalid")
        _unique(tuple(item.outcome for item in self.outcomes), field_name="outcome")


@dataclass(frozen=True)
class CTOEvidenceHistoricalState:
    """Explicit historical/system metrics, never included in run totals."""

    schema_version: str = field(metadata={"doc": "Historical state schema version."})
    status: Literal["available", "partial", "unavailable"]
    metrics: tuple[CTOEvidenceMetric, ...]
    source_ids: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceHistoricalState")
        if self.status not in {"available", "partial", "unavailable"}:
            raise ValueError("historical state status is invalid")
        for source_id in self.source_ids:
            _identifier(source_id, field_name="source_id")
        for limitation in self.limitations:
            _bounded_text(limitation, field_name="historical limitation", maximum=320)


@dataclass(frozen=True)
class CTOEvidenceCriterionCounts:
    schema_version: str = field(metadata={"doc": "Criterion totals schema version."})
    pass_count: int
    fail_count: int
    not_evaluated_count: int
    insufficient_evidence_count: int

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceCriterionCounts")
        if (
            min(
                self.pass_count,
                self.fail_count,
                self.not_evaluated_count,
                self.insufficient_evidence_count,
            )
            < 0
        ):
            raise ValueError("criterion counts cannot be negative")


@dataclass(frozen=True)
class CTOEvidenceExecutiveSummary:
    """Bounded run-first executive view with historical totals separately labelled."""

    schema_version: str = field(metadata={"doc": "Executive summary schema version."})
    mode: Literal["declared_run", "historical_system_snapshot"]
    run_id: str | None
    run_type: str | None
    objective: str | None
    tested_repository_sha: str | None
    subject_count: int | None
    required_criteria: CTOEvidenceCriterionCounts
    outcomes: tuple[CTOEvidenceOutcomeCount, ...]
    key_metrics: tuple[CTOEvidenceMetric, ...]
    recovery_attempt_count: int | None
    reused_validation_count: int | None
    avoided_provider_call_count: int | None
    quality_dimensions: tuple[CTOEvidenceQualityDimension, ...]
    external_actions: tuple[CTOEvidenceExternalAction, ...]
    historical_metric_count: int
    completeness: Completeness
    disposition: RunDisposition
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceExecutiveSummary")
        if self.completeness not in {"complete", "incomplete", "invalid"}:
            raise ValueError("summary completeness is invalid")
        if self.disposition not in {
            "pass",
            "fail",
            "not_evaluated",
            "insufficient_evidence",
        }:
            raise ValueError("summary disposition is invalid")
        if self.run_id is not None:
            _identifier(self.run_id, field_name="run_id")
        if self.run_type is not None:
            _safe_key(self.run_type, field_name="run_type")
        if self.objective is not None:
            _bounded_text(self.objective, field_name="objective")
        if self.tested_repository_sha is not None:
            _git_sha(self.tested_repository_sha, field_name="tested_repository_sha")
        if self.subject_count is not None and self.subject_count < 0:
            raise ValueError("subject_count cannot be negative")
        if self.historical_metric_count < 0:
            raise ValueError("historical_metric_count cannot be negative")
        if self.mode == "historical_system_snapshot" and any(
            value is not None
            for value in (
                self.run_id,
                self.run_type,
                self.objective,
                self.tested_repository_sha,
            )
        ):
            raise ValueError("historical summary cannot claim a declared run")
        if any(item.metric_id.startswith("historical.") for item in self.key_metrics):
            raise ValueError(
                "historical metrics cannot appear in the executive run summary"
            )


@dataclass(frozen=True)
class CTOEvidenceBundle:
    """Canonical bounded bundle consumed by CTO review and future R1 projections."""

    schema_version: str = field(metadata={"doc": "CTO evidence bundle schema version."})
    generated_at_utc: str
    collector_repository_sha: str
    mode: Literal["declared_run", "historical_system_snapshot"]
    run: CTOEvidenceRun | None
    run_evidence: CTOEvidenceRunEvidence | None
    historical_state: CTOEvidenceHistoricalState
    source_references: tuple[CTOEvidenceSourceReference, ...]
    completeness: Completeness
    disposition: RunDisposition
    executive_summary: CTOEvidenceExecutiveSummary
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _schema(self.schema_version, "CTOEvidenceBundle")
        if self.mode not in {"declared_run", "historical_system_snapshot"}:
            raise ValueError("bundle mode is invalid")
        if self.completeness not in {"complete", "incomplete", "invalid"}:
            raise ValueError("bundle completeness is invalid")
        if self.disposition not in {
            "pass",
            "fail",
            "not_evaluated",
            "insufficient_evidence",
        }:
            raise ValueError("bundle disposition is invalid")
        _timestamp(self.generated_at_utc, field_name="generated_at_utc")
        _git_sha(self.collector_repository_sha, field_name="collector_repository_sha")


def _schema(value: str, contract_name: str) -> None:
    if value != SCHEMA_VERSION:
        raise ValueError(f"{contract_name}.schema_version must be {SCHEMA_VERSION}")


def _relative_path(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError("source path must be a bounded repository-relative path")
    if "\\" in value or ":" in value:
        raise ValueError("source path must use repository-relative POSIX form")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("source path must not be absolute or traverse directories")
    _bounded_text(value, field_name="source path", maximum=512)


def _safe_selector(value: str) -> None:
    if value in {"", "."}:
        return
    for part in value.split("."):
        _safe_key(part, field_name="comparison selector")


def _expect_mapping(
    value: object, *, field_name: str, allowed: set[str]
) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object")
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(
            f"{field_name} has unexpected fields: {', '.join(sorted(unexpected))}"
        )
    return value


def _expect_list(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return value


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _identity(value: object, *, field_name: str) -> CTOEvidenceIdentity:
    item = _expect_mapping(
        value,
        field_name=field_name,
        allowed={"schema_version", "key", "value"},
    )
    return CTOEvidenceIdentity(
        schema_version=_required_text(item, "schema_version"),
        key=_required_text(item, "key"),
        value=_required_text(item, "value"),
    )


def _source(value: object) -> CTOEvidenceSourceReference:
    item = _expect_mapping(
        value,
        field_name="source",
        allowed={
            "schema_version",
            "source_id",
            "producer",
            "format_id",
            "path",
            "sha256",
            "tested_repository_sha",
            "role",
            "status",
            "byte_count",
            "observed_sha256",
        },
    )
    return CTOEvidenceSourceReference(
        schema_version=_required_text(item, "schema_version"),
        source_id=_required_text(item, "source_id"),
        producer=_required_text(item, "producer"),
        format_id=_required_text(item, "format_id"),
        path=_required_text(item, "path"),
        sha256=_required_text(item, "sha256"),
        tested_repository_sha=_optional_text(item, "tested_repository_sha"),
        role=str(item.get("role", "run")),  # type: ignore[arg-type]
        status=str(item.get("status", "declared")),  # type: ignore[arg-type]
        byte_count=_optional_int(item.get("byte_count"), field_name="byte_count"),
        observed_sha256=_optional_text(item, "observed_sha256"),
    )


def _subject(value: object) -> CTOEvidenceSubject:
    item = _expect_mapping(
        value,
        field_name="subject",
        allowed={
            "schema_version",
            "subject_id",
            "identity_sha256",
            "immutable",
            "source_identity_sha256",
            "terminal_outcome",
        },
    )
    immutable = item.get("immutable")
    if not isinstance(immutable, bool):
        raise ValueError("subject immutable must be a boolean")
    return CTOEvidenceSubject(
        schema_version=_required_text(item, "schema_version"),
        subject_id=_required_text(item, "subject_id"),
        identity_sha256=_required_text(item, "identity_sha256"),
        immutable=immutable,
        source_identity_sha256=_optional_text(item, "source_identity_sha256"),
        terminal_outcome=_optional_text(item, "terminal_outcome"),
    )


def _criterion(value: object) -> CTOEvidenceCriterion:
    item = _expect_mapping(
        value,
        field_name="criterion",
        allowed={
            "schema_version",
            "criterion_id",
            "description",
            "metric_id",
            "operator",
            "expected_value",
            "required",
            "stage",
            "actual_value",
            "disposition",
        },
    )
    required = item.get("required")
    if not isinstance(required, bool):
        raise ValueError("criterion required must be a boolean")
    return CTOEvidenceCriterion(
        schema_version=_required_text(item, "schema_version"),
        criterion_id=_required_text(item, "criterion_id"),
        description=_required_text(item, "description"),
        metric_id=_required_text(item, "metric_id"),
        operator=str(item.get("operator") or "eq"),  # type: ignore[arg-type]
        expected_value=item.get("expected_value"),  # type: ignore[arg-type]
        required=required,
        stage=_optional_text(item, "stage"),
        actual_value=item.get("actual_value"),  # type: ignore[arg-type]
        disposition=str(item.get("disposition") or "not_evaluated"),  # type: ignore[arg-type]
    )


def _invariant(value: object) -> CTOEvidenceInvariant:
    item = _expect_mapping(
        value,
        field_name="invariant",
        allowed={"schema_version", "key", "baseline_value", "candidate_value"},
    )
    return CTOEvidenceInvariant(
        schema_version=_required_text(item, "schema_version"),
        key=_required_text(item, "key"),
        baseline_value=_required_text(item, "baseline_value"),
        candidate_value=_required_text(item, "candidate_value"),
    )


def _comparison(
    value: object, *, include_projection: bool = False
) -> CTOEvidenceComparison | None:
    if value is None:
        return None
    allowed = {
        "schema_version",
        "comparison_id",
        "baseline_source_id",
        "candidate_source_id",
        "baseline_selector",
        "candidate_selector",
        "baseline_repository_sha",
        "candidate_repository_sha",
        "baseline_identity",
        "candidate_identity",
        "invariants",
        "changed_variables",
        "limitations",
        "status",
    }
    if include_projection:
        allowed.update({"metric_deltas", "causal_attribution"})
    item = _expect_mapping(
        value,
        field_name="comparison",
        allowed=allowed,
    )
    return CTOEvidenceComparison(
        schema_version=_required_text(item, "schema_version"),
        comparison_id=_required_text(item, "comparison_id"),
        baseline_source_id=_required_text(item, "baseline_source_id"),
        candidate_source_id=_required_text(item, "candidate_source_id"),
        baseline_selector=str(item.get("baseline_selector", ".")),
        candidate_selector=str(item.get("candidate_selector", ".")),
        baseline_repository_sha=_required_text(item, "baseline_repository_sha"),
        candidate_repository_sha=_required_text(item, "candidate_repository_sha"),
        baseline_identity=tuple(
            _identity(part, field_name="baseline identity")
            for part in _expect_list(
                item.get("baseline_identity", []), field_name="baseline_identity"
            )
        ),
        candidate_identity=tuple(
            _identity(part, field_name="candidate identity")
            for part in _expect_list(
                item.get("candidate_identity", []), field_name="candidate_identity"
            )
        ),
        invariants=tuple(
            _invariant(part)
            for part in _expect_list(
                item.get("invariants", []), field_name="invariants"
            )
        ),
        changed_variables=tuple(
            str(part)
            for part in _expect_list(
                item.get("changed_variables", []), field_name="changed_variables"
            )
        ),
        limitations=tuple(
            str(part)
            for part in _expect_list(
                item.get("limitations", []), field_name="limitations"
            )
        ),
        status=str(item.get("status", "declared")),  # type: ignore[arg-type]
        metric_deltas=tuple(
            _metric(part)
            for part in _expect_list(
                item.get("metric_deltas", []), field_name="metric_deltas"
            )
        )
        if include_projection
        else (),
        causal_attribution=str(item.get("causal_attribution", "not_established")),  # type: ignore[arg-type]
    )


def parse_cto_evidence_run(
    payload: object, *, include_projection: bool = False
) -> CTOEvidenceRun:
    """Parse a declared run or its projected bundle representation."""

    item = _expect_mapping(
        payload,
        field_name="run manifest",
        allowed={
            "schema_version",
            "run_id",
            "run_type",
            "objective",
            "tested_repository_sha",
            "producer_repository_sha",
            "started_at_utc",
            "ended_at_utc",
            "subjects",
            "configuration_identities",
            "stages_in_scope",
            "stages_out_of_scope",
            "external_side_effects_enabled",
            "operator_intervention_policy",
            "sources",
            "required_evidence_classes",
            "criteria",
            "comparison",
        },
    )
    side_effects = item.get("external_side_effects_enabled")
    if side_effects is not None and not isinstance(side_effects, bool):
        raise ValueError("external_side_effects_enabled must be a boolean or null")
    run = CTOEvidenceRun(
        schema_version=_required_text(item, "schema_version"),
        run_id=_required_text(item, "run_id"),
        run_type=_required_text(item, "run_type"),
        objective=_required_text(item, "objective"),
        tested_repository_sha=_required_text(item, "tested_repository_sha"),
        producer_repository_sha=_optional_text(item, "producer_repository_sha"),
        started_at_utc=_optional_text(item, "started_at_utc"),
        ended_at_utc=_optional_text(item, "ended_at_utc"),
        subjects=tuple(
            _subject(part)
            for part in _expect_list(item.get("subjects"), field_name="subjects")
        ),
        configuration_identities=tuple(
            _identity(part, field_name="configuration identity")
            for part in _expect_list(
                item.get("configuration_identities", []),
                field_name="configuration_identities",
            )
        ),
        stages_in_scope=tuple(
            str(part)
            for part in _expect_list(
                item.get("stages_in_scope", []), field_name="stages_in_scope"
            )
        ),
        stages_out_of_scope=tuple(
            str(part)
            for part in _expect_list(
                item.get("stages_out_of_scope", []), field_name="stages_out_of_scope"
            )
        ),
        external_side_effects_enabled=side_effects,
        operator_intervention_policy=_required_text(
            item, "operator_intervention_policy"
        ),
        sources=tuple(
            _source(part)
            for part in _expect_list(item.get("sources"), field_name="sources")
        ),
        required_evidence_classes=tuple(
            str(part)
            for part in _expect_list(
                item.get("required_evidence_classes", []),
                field_name="required_evidence_classes",
            )
        ),
        criteria=tuple(
            _criterion(part)
            for part in _expect_list(item.get("criteria", []), field_name="criteria")
        ),
        comparison=_comparison(
            item.get("comparison"), include_projection=include_projection
        ),
    )
    validate_cto_evidence_run(run)
    return run


def _text_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    values = _expect_list(value, field_name=field_name)
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"{field_name} entries must be strings")
    return tuple(item for item in values if isinstance(item, str))


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _required_int(value, field_name=field_name)


def _optional_number(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric or null")
    return float(value)


def _metric(value: object) -> CTOEvidenceMetric:
    item = _expect_mapping(
        value,
        field_name="metric",
        allowed={
            "schema_version",
            "metric_id",
            "status",
            "value",
            "unit",
            "source_ids",
            "limitations",
            "numerator",
            "denominator",
            "measurement_semantics",
            "subject_id",
        },
    )
    metric_value = item.get("value")
    if metric_value is not None:
        _scalar(metric_value, field_name="metric value")
    measurement_semantics = item.get("measurement_semantics", "")
    if not isinstance(measurement_semantics, str):
        raise ValueError("measurement_semantics must be a string")
    return CTOEvidenceMetric(
        schema_version=_required_text(item, "schema_version"),
        metric_id=_required_text(item, "metric_id"),
        status=_required_text(item, "status"),  # type: ignore[arg-type]
        value=metric_value,  # type: ignore[arg-type]
        unit=_required_text(item, "unit"),
        source_ids=_text_tuple(item.get("source_ids"), field_name="source_ids"),
        limitations=_text_tuple(item.get("limitations"), field_name="limitations"),
        numerator=_optional_number(item.get("numerator"), field_name="numerator"),
        denominator=_optional_number(item.get("denominator"), field_name="denominator"),
        measurement_semantics=measurement_semantics,
        subject_id=_optional_text(item, "subject_id"),
    )


def _attempt(value: object) -> CTOEvidenceAttempt:
    item = _expect_mapping(
        value,
        field_name="attempt",
        allowed={
            "schema_version",
            "subject_id",
            "attempt_number",
            "kind",
            "outcome",
            "failure_code",
            "parent_attempt_number",
            "operator_intervention",
            "source_id",
        },
    )
    operator_intervention = item.get("operator_intervention")
    if not isinstance(operator_intervention, bool):
        raise ValueError("operator_intervention must be a boolean")
    return CTOEvidenceAttempt(
        schema_version=_required_text(item, "schema_version"),
        subject_id=_required_text(item, "subject_id"),
        attempt_number=_required_int(
            item.get("attempt_number"), field_name="attempt_number"
        ),
        kind=_required_text(item, "kind"),  # type: ignore[arg-type]
        outcome=_required_text(item, "outcome"),  # type: ignore[arg-type]
        failure_code=_optional_text(item, "failure_code"),
        parent_attempt_number=_optional_int(
            item.get("parent_attempt_number"), field_name="parent_attempt_number"
        ),
        operator_intervention=operator_intervention,
        source_id=_optional_text(item, "source_id"),
    )


def _reuse_decision(value: object) -> CTOEvidenceReuseDecision:
    item = _expect_mapping(
        value,
        field_name="reuse decision",
        allowed={
            "schema_version",
            "subject_id",
            "eligible_candidates",
            "reused_validations",
            "newly_executed_validations",
            "avoided_grounding_calls",
            "avoided_provider_calls",
            "fallback_reason_code",
            "source_id",
        },
    )
    return CTOEvidenceReuseDecision(
        schema_version=_required_text(item, "schema_version"),
        subject_id=_required_text(item, "subject_id"),
        eligible_candidates=_optional_int(
            item.get("eligible_candidates"), field_name="eligible_candidates"
        ),
        reused_validations=_optional_int(
            item.get("reused_validations"), field_name="reused_validations"
        ),
        newly_executed_validations=_optional_int(
            item.get("newly_executed_validations"),
            field_name="newly_executed_validations",
        ),
        avoided_grounding_calls=_optional_int(
            item.get("avoided_grounding_calls"), field_name="avoided_grounding_calls"
        ),
        avoided_provider_calls=_optional_int(
            item.get("avoided_provider_calls"), field_name="avoided_provider_calls"
        ),
        fallback_reason_code=_optional_text(item, "fallback_reason_code"),
        source_id=_required_text(item, "source_id"),
    )


def _quality_dimension(value: object) -> CTOEvidenceQualityDimension:
    item = _expect_mapping(
        value,
        field_name="quality dimension",
        allowed={
            "schema_version",
            "dimension",
            "status",
            "reviewed_subject_count",
            "rubric_id",
            "reviewer_attribution",
            "metric_ids",
            "source_ids",
        },
    )
    return CTOEvidenceQualityDimension(
        schema_version=_required_text(item, "schema_version"),
        dimension=_required_text(item, "dimension"),
        status=_required_text(item, "status"),  # type: ignore[arg-type]
        reviewed_subject_count=_optional_int(
            item.get("reviewed_subject_count"), field_name="reviewed_subject_count"
        ),
        rubric_id=_optional_text(item, "rubric_id"),
        reviewer_attribution=_required_text(item, "reviewer_attribution"),  # type: ignore[arg-type]
        metric_ids=_text_tuple(item.get("metric_ids"), field_name="metric_ids"),
        source_ids=_text_tuple(item.get("source_ids"), field_name="source_ids"),
    )


def _external_action(value: object) -> CTOEvidenceExternalAction:
    item = _expect_mapping(
        value,
        field_name="external action",
        allowed={
            "schema_version",
            "system",
            "attempted_actions",
            "actual_writes",
            "skipped_actions",
            "blocked_actions",
            "failed_actions",
            "authenticated_readback",
            "repeat_result",
            "idempotency_result",
            "source_id",
        },
    )
    return CTOEvidenceExternalAction(
        schema_version=_required_text(item, "schema_version"),
        system=_required_text(item, "system"),
        attempted_actions=_optional_int(
            item.get("attempted_actions"), field_name="attempted_actions"
        ),
        actual_writes=_optional_int(
            item.get("actual_writes"), field_name="actual_writes"
        ),
        skipped_actions=_optional_int(
            item.get("skipped_actions"), field_name="skipped_actions"
        ),
        blocked_actions=_optional_int(
            item.get("blocked_actions"), field_name="blocked_actions"
        ),
        failed_actions=_optional_int(
            item.get("failed_actions"), field_name="failed_actions"
        ),
        authenticated_readback=_required_text(item, "authenticated_readback"),  # type: ignore[arg-type]
        repeat_result=_required_text(item, "repeat_result"),  # type: ignore[arg-type]
        idempotency_result=_required_text(item, "idempotency_result"),  # type: ignore[arg-type]
        source_id=_required_text(item, "source_id"),
    )


def _outcome_count(value: object) -> CTOEvidenceOutcomeCount:
    item = _expect_mapping(
        value,
        field_name="outcome count",
        allowed={"schema_version", "outcome", "count"},
    )
    return CTOEvidenceOutcomeCount(
        schema_version=_required_text(item, "schema_version"),
        outcome=_required_text(item, "outcome"),
        count=_required_int(item.get("count"), field_name="count"),
    )


def _run_evidence(value: object) -> CTOEvidenceRunEvidence:
    item = _expect_mapping(
        value,
        field_name="run evidence",
        allowed={
            "schema_version",
            "subjects",
            "metrics",
            "criteria",
            "outcomes",
            "attempts",
            "reuse_decisions",
            "quality_dimensions",
            "external_actions",
            "comparison",
            "attempt_history_status",
            "reuse_evidence_status",
            "limitations",
        },
    )
    return CTOEvidenceRunEvidence(
        schema_version=_required_text(item, "schema_version"),
        subjects=tuple(
            _subject(part)
            for part in _expect_list(item.get("subjects"), field_name="subjects")
        ),
        metrics=tuple(
            _metric(part)
            for part in _expect_list(item.get("metrics"), field_name="metrics")
        ),
        criteria=tuple(
            _criterion(part)
            for part in _expect_list(item.get("criteria"), field_name="criteria")
        ),
        outcomes=tuple(
            _outcome_count(part)
            for part in _expect_list(item.get("outcomes"), field_name="outcomes")
        ),
        attempts=tuple(
            _attempt(part)
            for part in _expect_list(item.get("attempts"), field_name="attempts")
        ),
        reuse_decisions=tuple(
            _reuse_decision(part)
            for part in _expect_list(
                item.get("reuse_decisions"), field_name="reuse_decisions"
            )
        ),
        quality_dimensions=tuple(
            _quality_dimension(part)
            for part in _expect_list(
                item.get("quality_dimensions"), field_name="quality_dimensions"
            )
        ),
        external_actions=tuple(
            _external_action(part)
            for part in _expect_list(
                item.get("external_actions"), field_name="external_actions"
            )
        ),
        comparison=_comparison(item.get("comparison"), include_projection=True),
        attempt_history_status=_required_text(item, "attempt_history_status"),  # type: ignore[arg-type]
        reuse_evidence_status=_required_text(item, "reuse_evidence_status"),  # type: ignore[arg-type]
        limitations=_text_tuple(item.get("limitations"), field_name="limitations"),
    )


def _historical_state(value: object) -> CTOEvidenceHistoricalState:
    item = _expect_mapping(
        value,
        field_name="historical state",
        allowed={"schema_version", "status", "metrics", "source_ids", "limitations"},
    )
    return CTOEvidenceHistoricalState(
        schema_version=_required_text(item, "schema_version"),
        status=_required_text(item, "status"),  # type: ignore[arg-type]
        metrics=tuple(
            _metric(part)
            for part in _expect_list(item.get("metrics"), field_name="metrics")
        ),
        source_ids=_text_tuple(item.get("source_ids"), field_name="source_ids"),
        limitations=_text_tuple(item.get("limitations"), field_name="limitations"),
    )


def _criterion_counts(value: object) -> CTOEvidenceCriterionCounts:
    item = _expect_mapping(
        value,
        field_name="criterion counts",
        allowed={
            "schema_version",
            "pass_count",
            "fail_count",
            "not_evaluated_count",
            "insufficient_evidence_count",
        },
    )
    return CTOEvidenceCriterionCounts(
        schema_version=_required_text(item, "schema_version"),
        pass_count=_required_int(item.get("pass_count"), field_name="pass_count"),
        fail_count=_required_int(item.get("fail_count"), field_name="fail_count"),
        not_evaluated_count=_required_int(
            item.get("not_evaluated_count"), field_name="not_evaluated_count"
        ),
        insufficient_evidence_count=_required_int(
            item.get("insufficient_evidence_count"),
            field_name="insufficient_evidence_count",
        ),
    )


def parse_cto_evidence_bundle(payload: object) -> CTOEvidenceBundle:
    """Parse and validate a persisted canonical CTO evidence bundle."""
    item = _expect_mapping(
        payload,
        field_name="CTO evidence bundle",
        allowed={
            "schema_version",
            "generated_at_utc",
            "collector_repository_sha",
            "mode",
            "run",
            "run_evidence",
            "historical_state",
            "source_references",
            "completeness",
            "disposition",
            "executive_summary",
            "limitations",
        },
    )
    raw_summary = _expect_mapping(
        item.get("executive_summary"),
        field_name="executive summary",
        allowed={
            "schema_version",
            "mode",
            "run_id",
            "run_type",
            "objective",
            "tested_repository_sha",
            "subject_count",
            "required_criteria",
            "outcomes",
            "key_metrics",
            "recovery_attempt_count",
            "reused_validation_count",
            "avoided_provider_call_count",
            "quality_dimensions",
            "external_actions",
            "historical_metric_count",
            "completeness",
            "disposition",
            "limitations",
        },
    )
    summary = CTOEvidenceExecutiveSummary(
        schema_version=_required_text(raw_summary, "schema_version"),
        mode=_required_text(raw_summary, "mode"),  # type: ignore[arg-type]
        run_id=_optional_text(raw_summary, "run_id"),
        run_type=_optional_text(raw_summary, "run_type"),
        objective=_optional_text(raw_summary, "objective"),
        tested_repository_sha=_optional_text(raw_summary, "tested_repository_sha"),
        subject_count=_optional_int(
            raw_summary.get("subject_count"), field_name="subject_count"
        ),
        required_criteria=_criterion_counts(raw_summary.get("required_criteria")),
        outcomes=tuple(
            _outcome_count(part)
            for part in _expect_list(
                raw_summary.get("outcomes"), field_name="summary outcomes"
            )
        ),
        key_metrics=tuple(
            _metric(part)
            for part in _expect_list(
                raw_summary.get("key_metrics"), field_name="key_metrics"
            )
        ),
        recovery_attempt_count=_optional_int(
            raw_summary.get("recovery_attempt_count"),
            field_name="recovery_attempt_count",
        ),
        reused_validation_count=_optional_int(
            raw_summary.get("reused_validation_count"),
            field_name="reused_validation_count",
        ),
        avoided_provider_call_count=_optional_int(
            raw_summary.get("avoided_provider_call_count"),
            field_name="avoided_provider_call_count",
        ),
        quality_dimensions=tuple(
            _quality_dimension(part)
            for part in _expect_list(
                raw_summary.get("quality_dimensions"),
                field_name="summary quality_dimensions",
            )
        ),
        external_actions=tuple(
            _external_action(part)
            for part in _expect_list(
                raw_summary.get("external_actions"),
                field_name="summary external_actions",
            )
        ),
        historical_metric_count=_required_int(
            raw_summary.get("historical_metric_count"),
            field_name="historical_metric_count",
        ),
        completeness=_required_text(raw_summary, "completeness"),  # type: ignore[arg-type]
        disposition=_required_text(raw_summary, "disposition"),  # type: ignore[arg-type]
        limitations=_text_tuple(
            raw_summary.get("limitations"), field_name="summary limitations"
        ),
    )
    raw_run = item.get("run")
    raw_evidence = item.get("run_evidence")
    bundle = CTOEvidenceBundle(
        schema_version=_required_text(item, "schema_version"),
        generated_at_utc=_required_text(item, "generated_at_utc"),
        collector_repository_sha=_required_text(item, "collector_repository_sha"),
        mode=_required_text(item, "mode"),  # type: ignore[arg-type]
        run=(
            parse_cto_evidence_run(raw_run, include_projection=True)
            if raw_run is not None
            else None
        ),
        run_evidence=_run_evidence(raw_evidence) if raw_evidence is not None else None,
        historical_state=_historical_state(item.get("historical_state")),
        source_references=tuple(
            _source(part)
            for part in _expect_list(
                item.get("source_references"), field_name="source_references"
            )
        ),
        completeness=_required_text(item, "completeness"),  # type: ignore[arg-type]
        disposition=_required_text(item, "disposition"),  # type: ignore[arg-type]
        executive_summary=summary,
        limitations=_text_tuple(item.get("limitations"), field_name="limitations"),
    )
    validate_cto_evidence_bundle(bundle)
    return bundle


def validate_cto_evidence_run(run: CTOEvidenceRun) -> None:
    """Validate run-wide references, scope, and comparison invariants."""

    source_ids = {item.source_id for item in run.sources}
    if not run.subjects and "immutable_subjects" in run.required_evidence_classes:
        raise ValueError("required immutable subjects are missing")
    if "immutable_subjects" in run.required_evidence_classes and any(
        not subject.immutable for subject in run.subjects
    ):
        raise ValueError("required subject identities must be immutable")
    if not run.sources:
        raise ValueError("declared run requires at least one evidence source")
    for criterion in run.criteria:
        if (
            criterion.stage in run.stages_out_of_scope
            and criterion.disposition != "not_evaluated"
        ):
            raise ValueError("out-of-scope criterion must be not_evaluated")
    if run.comparison is not None:
        if (
            run.comparison.baseline_source_id not in source_ids
            or run.comparison.candidate_source_id not in source_ids
        ):
            raise ValueError("comparison references an undeclared source")
        if run.comparison.baseline_identity != run.comparison.candidate_identity:
            raise ValueError("comparison compatibility identities do not match")
        if run.comparison.candidate_repository_sha != run.tested_repository_sha:
            raise ValueError("comparison candidate SHA does not match the declared run")
        if any(
            item.baseline_value != item.candidate_value
            for item in run.comparison.invariants
        ):
            raise ValueError("comparison invariant values do not match")


def derive_required_criteria_disposition(
    criteria: tuple[CTOEvidenceCriterion, ...],
) -> RunDisposition:
    required = [
        item
        for item in criteria
        if item.required and item.disposition != "not_evaluated"
    ]
    if not required:
        return "not_evaluated"
    if any(item.disposition == "fail" for item in required):
        return "fail"
    if any(item.disposition == "insufficient_evidence" for item in required) or any(
        item.disposition == "not_evaluated" for item in required
    ):
        return "insufficient_evidence"
    return "pass"


def validate_cto_evidence_bundle(bundle: CTOEvidenceBundle) -> None:
    """Validate bundle namespaces and derive required-criteria disposition."""

    if bundle.mode == "declared_run":
        if bundle.run is None or bundle.run_evidence is None:
            raise ValueError("declared-run bundle requires run and run_evidence")
        validate_cto_evidence_run(bundle.run)
        if bundle.executive_summary.mode != "declared_run":
            raise ValueError("executive summary mode differs from declared run")
        if bundle.run.run_id != bundle.executive_summary.run_id:
            raise ValueError("executive summary run identity mismatch")
        if bundle.run_evidence.metrics and bundle.historical_state.metrics:
            run_ids = {item.metric_id for item in bundle.run_evidence.metrics}
            history_ids = {item.metric_id for item in bundle.historical_state.metrics}
            if run_ids & history_ids:
                raise ValueError(
                    "run and historical metric identifiers must be disjoint"
                )
        expected_disposition = (
            "fail"
            if bundle.completeness == "invalid"
            else derive_required_criteria_disposition(bundle.run_evidence.criteria)
        )
        if bundle.completeness == "incomplete" and expected_disposition == "pass":
            expected_disposition = "insufficient_evidence"
        if bundle.disposition != expected_disposition:
            raise ValueError("bundle disposition does not match required criteria")
        subject_ids = {item.subject_id for item in bundle.run_evidence.subjects}
        declared_ids = {item.subject_id for item in bundle.run.subjects}
        if subject_ids != declared_ids:
            raise ValueError(
                "projected subject set differs from declared immutable subjects"
            )
        if bundle.completeness != "invalid":
            _validate_metric_reconciliation(bundle.run_evidence.metrics, subject_ids)
            _validate_attempt_order(bundle.run_evidence.attempts, subject_ids)
            outcome_counts = Counter(
                {item.outcome: item.count for item in bundle.run_evidence.outcomes}
            )
            terminal_outcomes = Counter(
                item.terminal_outcome
                for item in bundle.run_evidence.subjects
                if item.terminal_outcome is not None
            )
            if (
                "outcomes" in bundle.run.required_evidence_classes
                and bundle.completeness == "complete"
            ):
                if not terminal_outcomes and bundle.run.subjects:
                    raise ValueError(
                        "complete required outcomes need terminal subject outcomes"
                    )
                if sum(terminal_outcomes.values()) != len(bundle.run.subjects):
                    raise ValueError(
                        "complete required outcomes must cover every declared subject"
                    )
                if outcome_counts != terminal_outcomes:
                    raise ValueError(
                        "run outcome totals do not reconcile to terminal subjects"
                    )
            elif terminal_outcomes and outcome_counts != terminal_outcomes:
                raise ValueError(
                    "run outcome totals do not reconcile to terminal subjects"
                )
        _validate_source_links(bundle.run_evidence, bundle.source_references)
        declared_criteria = {item.criterion_id: item for item in bundle.run.criteria}
        projected_criteria = {
            item.criterion_id: item for item in bundle.run_evidence.criteria
        }
        if set(declared_criteria) != set(projected_criteria):
            raise ValueError("projected criteria differ from the declared criteria")
        for criterion_id, declared in declared_criteria.items():
            projected = projected_criteria[criterion_id]
            if (
                declared.description,
                declared.metric_id,
                declared.operator,
                declared.expected_value,
                declared.required,
                declared.stage,
            ) != (
                projected.description,
                projected.metric_id,
                projected.operator,
                projected.expected_value,
                projected.required,
                projected.stage,
            ):
                raise ValueError("projected criterion definition changed")
        if bundle.run_evidence.comparison is not None and (
            bundle.run.comparison is None
            or any(
                getattr(bundle.run.comparison, field_name)
                != getattr(bundle.run_evidence.comparison, field_name)
                for field_name in (
                    "comparison_id",
                    "baseline_source_id",
                    "candidate_source_id",
                    "baseline_selector",
                    "candidate_selector",
                    "baseline_repository_sha",
                    "candidate_repository_sha",
                    "baseline_identity",
                    "candidate_identity",
                    "invariants",
                    "changed_variables",
                )
            )
        ):
            raise ValueError(
                "projected comparison identity differs from its declaration"
            )
        if bundle.executive_summary.subject_count != len(bundle.run.subjects):
            raise ValueError("executive subject count does not reconcile")
        if bundle.executive_summary.outcomes != bundle.run_evidence.outcomes:
            raise ValueError("executive outcomes do not reconcile")
        if (
            bundle.executive_summary.quality_dimensions
            != bundle.run_evidence.quality_dimensions
        ):
            raise ValueError("executive quality dimensions do not reconcile")
        if (
            bundle.executive_summary.external_actions
            != bundle.run_evidence.external_actions
        ):
            raise ValueError("executive external actions do not reconcile")
        counts = bundle.executive_summary.required_criteria
        criteria = [item for item in bundle.run_evidence.criteria if item.required]
        expected_counts = (
            sum(item.disposition == "pass" for item in criteria),
            sum(item.disposition == "fail" for item in criteria),
            sum(item.disposition == "not_evaluated" for item in criteria),
            sum(item.disposition == "insufficient_evidence" for item in criteria),
        )
        if expected_counts != (
            counts.pass_count,
            counts.fail_count,
            counts.not_evaluated_count,
            counts.insufficient_evidence_count,
        ):
            raise ValueError("executive criteria totals do not reconcile")
    else:
        if bundle.run is not None or bundle.run_evidence is not None:
            raise ValueError("historical snapshot cannot contain run-scoped evidence")
        if bundle.executive_summary.mode != "historical_system_snapshot":
            raise ValueError(
                "historical snapshot requires a historical executive summary"
            )
        if bundle.disposition != "not_evaluated":
            raise ValueError("historical snapshot has no run disposition")
        if any(
            not metric.metric_id.startswith("historical.")
            for metric in bundle.historical_state.metrics
        ):
            raise ValueError("historical namespace contains a run metric")
    summary = bundle.executive_summary
    if (
        summary.completeness != bundle.completeness
        or summary.disposition != bundle.disposition
    ):
        raise ValueError("executive summary status does not match the bundle")
    if summary.historical_metric_count != len(bundle.historical_state.metrics):
        raise ValueError("historical metric count does not reconcile")
    if bundle.run_evidence is not None:
        for limitation in bundle.run_evidence.limitations:
            _bounded_text(limitation, field_name="run limitation", maximum=320)


def _validate_attempt_order(
    attempts: tuple[CTOEvidenceAttempt, ...], subject_ids: set[str]
) -> None:
    last_attempt: dict[str, int] = {}
    for attempt in attempts:
        if attempt.subject_id not in subject_ids:
            raise ValueError("attempt references an undeclared subject")
        prior = last_attempt.get(attempt.subject_id, 0)
        if attempt.attempt_number <= prior:
            raise ValueError("attempt history must be append-only and strictly ordered")
        if (
            attempt.parent_attempt_number is not None
            and attempt.parent_attempt_number > prior
        ):
            raise ValueError("attempt recovery references a missing earlier attempt")
        last_attempt[attempt.subject_id] = attempt.attempt_number


def _validate_metric_reconciliation(
    metrics: tuple[CTOEvidenceMetric, ...], subject_ids: set[str]
) -> None:
    per_subject: dict[str, list[float]] = {}
    subjects_with_metric: dict[str, set[str]] = {}
    aggregate: dict[str, float] = {}
    for metric in metrics:
        if metric.subject_id is not None:
            if metric.subject_id not in subject_ids:
                raise ValueError("metric references an undeclared subject")
            if (
                metric.status in {"observed", "partial"}
                and isinstance(metric.value, (int, float))
                and not isinstance(metric.value, bool)
            ):
                per_subject.setdefault(metric.metric_id, []).append(float(metric.value))
                subjects_with_metric.setdefault(metric.metric_id, set()).add(
                    metric.subject_id
                )
        elif (
            metric.status in {"observed", "partial"}
            and isinstance(metric.value, (int, float))
            and not isinstance(metric.value, bool)
        ):
            aggregate[metric.metric_id] = float(metric.value)
    for metric_id, values in per_subject.items():
        if metric_id not in aggregate or subjects_with_metric[metric_id] != subject_ids:
            continue
        if not math.isclose(
            sum(values), aggregate[metric_id], rel_tol=0.0, abs_tol=0.000001
        ):
            raise ValueError(f"per-subject metric totals do not reconcile: {metric_id}")


def _validate_source_links(
    evidence: CTOEvidenceRunEvidence,
    source_references: tuple[CTOEvidenceSourceReference, ...],
) -> None:
    source_ids = {item.source_id for item in source_references}
    if len(source_ids) != len(source_references):
        raise ValueError("bundle source IDs must be unique")
    for metric in evidence.metrics:
        if not set(metric.source_ids) <= source_ids:
            raise ValueError("metric references an undeclared source")
    for attempt in evidence.attempts:
        if attempt.source_id is not None and attempt.source_id not in source_ids:
            raise ValueError("attempt references an undeclared source")
    for decision in evidence.reuse_decisions:
        if decision.source_id not in source_ids:
            raise ValueError("reuse decision references an undeclared source")
    for action in evidence.external_actions:
        if action.source_id not in source_ids:
            raise ValueError("external action references an undeclared source")


def cto_evidence_bundle_payload(bundle: CTOEvidenceBundle) -> dict[str, object]:
    """Return a JSON-safe, validated payload with no undeclared fields."""

    validate_cto_evidence_bundle(bundle)
    return json.loads(json.dumps(asdict(bundle), allow_nan=False))
