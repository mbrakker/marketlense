from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Literal, cast, get_type_hints

from src.contracts.cross_report_analysis import (
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
)
from src.contracts.schema_validation import (
    empty_required_value as _empty_required_value,
    field_is_list_typed as _field_is_list_typed,
    field_is_required as _field_is_required,
)
from src.utils.errors import AppError


SIGNAL_CANDIDATE_SCHEMA_VERSION = "1.0"

SignalCandidateType = Literal[
    "market_signal",
    "risk_signal",
    "opportunity_signal",
    "contradiction_signal",
    "weak_signal",
]
SignalCandidateSupportLevel = Literal[
    "single_report",
    "multi_report_convergent",
    "multi_report_divergent",
    "weak_coverage",
]
SignalCandidateValidationStatus = Literal["approved", "blocked"]
SignalCandidateExtractionStatus = Literal["stored", "skipped", "failed"]


@dataclass(frozen=True)
class SignalCandidateSourceRef:
    schema_version: str = field(
        metadata={"doc": "Signal candidate source-ref schema version."}
    )
    report_id: str = field(metadata={"doc": "Source report identifier."})
    evidence_id: str = field(metadata={"doc": "Projected evidence identifier."})
    source_table: str = field(
        metadata={"doc": "Projection table that produced the source reference."}
    )
    entity_uid: str = field(metadata={"doc": "Projected source entity UID."})
    content_class: str = field(
        metadata={
            "doc": "Projected content class such as claim, finding, quote, metric, or figure."
        }
    )
    page_refs: List[int] = field(
        metadata={
            "doc": "One-based source page references retained for traceability when available.",
            "required": False,
        }
    )
    source_metadata: Dict[str, Any] = field(
        metadata={"doc": "Sanitized source metadata carried from the projected row."}
    )


@dataclass(frozen=True)
class SignalCandidate:
    schema_version: str = field(metadata={"doc": "Signal candidate schema version."})
    candidate_id: str = field(metadata={"doc": "Stable Signal candidate identifier."})
    candidate_type: SignalCandidateType = field(
        metadata={"doc": "Signal kind used for downstream publishing and review."}
    )
    title: str = field(metadata={"doc": "Human-readable Signal candidate title."})
    summary: str = field(metadata={"doc": "Source-backed candidate summary."})
    confidence: float = field(metadata={"doc": "Bounded confidence score from 0 to 1."})
    strength: float = field(metadata={"doc": "Deterministic source strength score."})
    support_level: SignalCandidateSupportLevel = field(
        metadata={"doc": "Support classification across source reports."}
    )
    caveats: List[str] = field(
        metadata={"doc": "Explicit uncertainty, weak coverage, or contradiction notes."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Report IDs represented by source-backed evidence."}
    )
    evidence_ids: List[str] = field(
        metadata={"doc": "Projected evidence IDs grounding the candidate."}
    )
    source_refs: List[SignalCandidateSourceRef] = field(
        metadata={
            "doc": "Traceable links to projected claims, findings, quotes, metrics, figures, and pages."
        }
    )
    raw_source_context: Dict[str, Any] = field(
        metadata={
            "doc": "Raw deterministic scoring and source context without metric normalization."
        }
    )
    validation_status: SignalCandidateValidationStatus = field(
        metadata={"doc": "Validation state after source-backed checks."}
    )
    validation_notes: List[str] = field(
        metadata={"doc": "Validation notes explaining approval or rejection."}
    )
    group_id: str = field(metadata={"doc": "Stable Signal group identifier."})
    extraction_request_id: str = field(
        metadata={"doc": "Extraction request that produced this candidate."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the candidate was generated."}
    )


@dataclass(frozen=True)
class SignalCandidateGroup:
    schema_version: str = field(
        metadata={"doc": "Signal candidate group schema version."}
    )
    group_id: str = field(metadata={"doc": "Stable Signal group identifier."})
    stable_key: str = field(
        metadata={"doc": "Deterministic clustering key independent of row order."}
    )
    title: str = field(metadata={"doc": "Human-readable Signal group title."})
    summary: str = field(metadata={"doc": "Source-backed group summary."})
    support_level: SignalCandidateSupportLevel = field(
        metadata={"doc": "Dominant support classification for grouped candidates."}
    )
    candidate_ids: List[str] = field(
        metadata={"doc": "Signal candidate IDs assigned to this group."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Source report IDs represented by the group."}
    )
    evidence_ids: List[str] = field(
        metadata={"doc": "Evidence IDs represented by the group."}
    )
    caveats: List[str] = field(
        metadata={"doc": "Union of source caveats retained for the group."}
    )
    raw_group_context: Dict[str, Any] = field(
        metadata={"doc": "Raw deterministic grouping context and agreement labels."}
    )
    validation_status: SignalCandidateValidationStatus = field(
        metadata={"doc": "Validation state for the group."}
    )
    extraction_request_id: str = field(
        metadata={"doc": "Extraction request that produced this group."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the group was generated."}
    )


@dataclass(frozen=True)
class SignalCandidateBatch:
    schema_version: str = field(
        metadata={"doc": "Signal candidate batch schema version."}
    )
    extraction_request_id: str = field(
        metadata={"doc": "Stable extraction request identifier."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when extraction built this batch."}
    )
    candidates: List[SignalCandidate] = field(
        metadata={"doc": "Signal candidates extracted from projected report evidence."}
    )
    groups: List[SignalCandidateGroup] = field(
        metadata={"doc": "Stable Signal groups for related candidates."}
    )


@dataclass(frozen=True)
class SignalCandidateStoreRequest:
    schema_version: str = field(
        metadata={"doc": "Signal candidate store request schema version."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    extraction_request_id: str = field(
        metadata={"doc": "Extraction request whose rows should be upserted."}
    )
    candidates: List[SignalCandidate] = field(
        metadata={"doc": "Signal candidates to persist."}
    )
    groups: List[SignalCandidateGroup] = field(
        metadata={"doc": "Signal groups to persist."}
    )


@dataclass(frozen=True)
class SignalCandidateStoreResponse:
    schema_version: str = field(
        metadata={"doc": "Signal candidate store response schema version."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    extraction_request_id: str = field(
        metadata={"doc": "Extraction request that was persisted."}
    )
    candidate_count: int = field(metadata={"doc": "Number of candidate rows stored."})
    group_count: int = field(metadata={"doc": "Number of group rows stored."})
    stale_candidate_count: int = field(
        metadata={"doc": "Number of stale candidate rows removed for this request."}
    )
    stale_group_count: int = field(
        metadata={"doc": "Number of stale group rows removed for this request."}
    )


@dataclass(frozen=True)
class SignalCandidateReadRequest:
    schema_version: str = field(
        metadata={"doc": "Signal candidate read request schema version."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    extraction_request_id: str = field(
        default="",
        metadata={"doc": "Optional extraction request filter.", "required": False},
    )
    candidate_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional candidate ID filter.", "required": False},
    )
    group_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional group ID filter.", "required": False},
    )
    validation_statuses: List[SignalCandidateValidationStatus] = field(
        default_factory=list,
        metadata={"doc": "Optional validation status filter.", "required": False},
    )
    source_report_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional source report filter.", "required": False},
    )
    evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional evidence ID filter.", "required": False},
    )
    topic_filters: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Optional topic text filters matched against title and context.",
            "required": False,
        },
    )
    limit: int = field(
        default=20,
        metadata={"doc": "Maximum candidates returned after deterministic ordering."},
    )


@dataclass(frozen=True)
class SignalCandidateReadResponse:
    schema_version: str = field(
        metadata={"doc": "Signal candidate read response schema version."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    candidates: List[SignalCandidate] = field(
        metadata={
            "doc": "Signal candidates returned by the read query.",
            "required": False,
        }
    )
    groups: List[SignalCandidateGroup] = field(
        metadata={"doc": "Signal groups for returned candidates.", "required": False}
    )


@dataclass(frozen=True)
class SignalCandidateExtractionRequest:
    schema_version: str = field(
        metadata={"doc": "Signal candidate extraction request schema version."}
    )
    extraction_request_id: str = field(
        metadata={"doc": "Stable extraction request identifier."}
    )
    analysis_request: CrossReportAnalysisRequest = field(
        metadata={
            "doc": "Cross-report source/theme request used for candidate extraction."
        }
    )
    projected_data_request: CrossReportProjectedDataReadRequest = field(
        metadata={"doc": "Analytics-store projected data read request."}
    )
    db_path: str = field(metadata={"doc": "Analytics projection SQLite database path."})
    max_evidence_items: int = field(
        default=48,
        metadata={"doc": "Maximum evidence rows retained for signal scoring."},
    )
    max_signals: int = field(
        default=8,
        metadata={"doc": "Maximum Signal candidates retained."},
    )
    generated_at_utc: str = field(
        default="",
        metadata={
            "doc": "Optional UTC timestamp override for reproducible extraction.",
            "required": False,
        },
    )


@dataclass(frozen=True)
class SignalCandidateExtractionOutcome:
    schema_version: str = field(
        metadata={"doc": "Signal candidate extraction outcome schema version."}
    )
    extraction_request_id: str = field(
        metadata={"doc": "Stable extraction request identifier."}
    )
    status: SignalCandidateExtractionStatus = field(
        metadata={"doc": "Final extraction status."}
    )
    batch: SignalCandidateBatch = field(
        metadata={"doc": "Candidate batch produced by the generator."}
    )
    stored_response: SignalCandidateStoreResponse = field(
        metadata={"doc": "Analytics-store persistence result."}
    )
    candidate_count: int = field(metadata={"doc": "Number of candidates generated."})
    group_count: int = field(metadata={"doc": "Number of groups generated."})
    state_transitions: List[str] = field(
        metadata={"doc": "Ordered orchestrator state transitions."}
    )


def validate_signal_candidate_contract(contract: object) -> None:
    contract_type = type(contract)
    if not is_dataclass(contract) or contract_type.__module__ != __name__:
        _raise_invalid(
            contract_type.__name__,
            "<root>",
            "expected signal-candidate dataclass contract",
        )
    _validate_contract_value(contract, path=contract_type.__name__)


def _raise_invalid(path: str, field_name: str, reason: str) -> None:
    raise AppError(
        code="signal_candidate_contract_invalid",
        message=f"Invalid Signal candidate contract field {path}: {reason}",
        retryable=False,
        severity="error",
        context={"path": path, "field": field_name, "reason": reason},
    )


def _validate_contract_value(value: object, *, path: str) -> None:
    if is_dataclass(value):
        _validate_dataclass_instance(value, path=path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_contract_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_contract_value(item, path=f"{path}.{key}")


def _validate_dataclass_instance(instance: object, *, path: str) -> None:
    type_hints = get_type_hints(type(instance))
    for field_def in fields(cast(Any, instance)):
        field_value = getattr(instance, field_def.name)
        field_path = f"{path}.{field_def.name}"
        field_annotation = type_hints.get(field_def.name, field_def.type)
        if (
            field_def.name == "schema_version"
            and field_value != SIGNAL_CANDIDATE_SCHEMA_VERSION
        ):
            _raise_invalid(field_path, field_def.name, "unsupported schema version")
        if _field_is_list_typed(field_annotation) and field_value is None:
            _raise_invalid(field_path, field_def.name, "list field cannot be null")
        if _field_is_required(field_def) and _empty_required_value(field_value):
            _raise_invalid(field_path, field_def.name, "required value is empty")
        if field_def.name == "confidence" and not 0.0 <= float(field_value) <= 1.0:
            _raise_invalid(
                field_path, field_def.name, "confidence must be between 0 and 1"
            )
        if field_def.name == "limit" and int(field_value) < 1:
            _raise_invalid(field_path, field_def.name, "limit must be positive")
        _validate_contract_value(field_value, path=field_path)
