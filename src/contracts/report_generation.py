from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.regeneration import (
    RegenerationAttemptResult,
    RegenerationLoopState,
)
from src.contracts.report_models import ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport


@dataclass(frozen=True)
class ReportRuntimeState:
    schema_version: str = field(
        metadata={"doc": "Runtime state schema version for report-generation phases."}
    )
    file: DriveFile = field(metadata={"doc": "Drive file under report generation."})
    local_pdf_path: str = field(
        metadata={"doc": "Filesystem path to the cached local PDF."}
    )
    settings: IngestSettings = field(
        metadata={"doc": "Resolved ingest settings for the current run."}
    )
    md5: Optional[str] = field(
        metadata={"doc": "MD5 checksum of the source PDF, if available."}
    )
    ctx: RunContext = field(
        metadata={"doc": "Structured logging/run context for the current file."}
    )
    file_name: str = field(
        metadata={"doc": "Resolved source filename used for logs and outcomes."}
    )
    report_name: str = field(
        metadata={"doc": "Slugified report name used for output paths."}
    )
    report_title: str = field(
        metadata={"doc": "Human-readable report title derived before analysis."}
    )
    analysis_mode: str = field(
        metadata={"doc": "Active analysis mode for the pipeline."}
    )
    analysis_modes: List[str] = field(
        metadata={"doc": "Analysis modes logged with the final outcome."}
    )
    report_worker_limit: int = field(
        metadata={"doc": "Configured within-file worker count."}
    )
    parallel_within_file: bool = field(
        metadata={"doc": "Whether within-file phase overlap is enabled."}
    )


@dataclass(frozen=True)
class ReportSourceState:
    schema_version: str = field(
        metadata={"doc": "Source-phase state schema version."}
    )
    runtime: ReportRuntimeState = field(
        metadata={"doc": "Shared runtime state for the report."}
    )
    info_response: PdfInfoResponse = field(
        metadata={"doc": "PDF metadata/page-count response for the source PDF."}
    )
    contents_page_number: int = field(
        metadata={"doc": "Detected one-based contents/index page number, if any."}
    )
    contents_heading: str = field(
        metadata={"doc": "Detected contents/index heading text, if any."}
    )
    contents_image: str = field(
        metadata={"doc": "Rendered contents preview asset path, if any."}
    )
    text_response: PdfTextExtractResponse = field(
        metadata={"doc": "Extracted text response used for density checks."}
    )
    text_status: Dict[str, object] = field(
        metadata={"doc": "Text-density/source-status payload passed into artifacts."}
    )
    text_validation_status: str = field(
        metadata={"doc": "Extractable-text validation status: pass|fail."}
    )
    text_validation_reason: str = field(
        metadata={"doc": "Reason for extractable-text validation failure, if any."}
    )
    text_validation_pages: List[int] = field(
        metadata={"doc": "One-based sampled pages used for text validation."}
    )
    payload: ReportPayload = field(
        metadata={"doc": "Base report payload seeded from source-only inputs."}
    )
    pdf_context: Any = field(
        default=None,
        metadata={"doc": "Shared PDF context reused across phases when available."},
    )
    pdf_context_for_tasks: Any = field(
        default=None,
        metadata={"doc": "PDF context visible to concurrent PDF-only tasks."},
    )


@dataclass(frozen=True)
class ReportSelectionState:
    schema_version: str = field(
        metadata={"doc": "Selection-phase state schema version."}
    )
    runtime: ReportRuntimeState = field(
        metadata={"doc": "Shared runtime state for the report."}
    )
    source: ReportSourceState = field(
        metadata={"doc": "Completed source-phase state."}
    )
    payload: ReportPayload = field(
        metadata={"doc": "Report payload after figure/candidate selection updates."}
    )
    rank_usage: Dict[str, Optional[int]] = field(
        metadata={"doc": "Aggregated candidate-ranking token usage summary."}
    )
    candidate_count: int = field(
        metadata={"doc": "Raw extracted candidate count for downstream logging."}
    )


@dataclass(frozen=True)
class ReportAnalysisState:
    schema_version: str = field(
        metadata={"doc": "Analysis-phase state schema version."}
    )
    runtime: ReportRuntimeState = field(
        metadata={"doc": "Shared runtime state for the report."}
    )
    source: ReportSourceState = field(
        metadata={"doc": "Completed source-phase state."}
    )
    selection: ReportSelectionState = field(
        metadata={"doc": "Completed selection-phase state."}
    )
    payload: ReportPayload = field(
        metadata={"doc": "Mutable report payload after taxonomy/doc-map updates."}
    )
    normalized_payload: ReportPayload = field(
        metadata={"doc": "Normalized payload used for validation and HTML rendering."}
    )
    data_dict: Dict[str, object] = field(
        metadata={"doc": "Serialized normalized payload plus analysis artifacts."}
    )
    evidence_paths: Dict[str, str] = field(
        metadata={"doc": "Persisted evidence/analysis artifact paths for this report."}
    )
    evidence_packs: Dict[str, Dict[str, object]] = field(
        metadata={"doc": "Resolved evidence-pack payloads by pack name."}
    )
    artifacts_payload: Optional[Dict[str, object]] = field(
        default=None,
        metadata={"doc": "Generated artifacts payload, if available."},
    )
    validation_report: Optional[ValidationReport] = field(
        default=None,
        metadata={"doc": "Validation report for the rendered payload, if available."},
    )
    category_labels: List[str] = field(
        default_factory=list,
        metadata={"doc": "Human-readable category labels used by artifacts/rendering."},
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store ID used for this report, if any."},
    )
    vector_store_status: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store readiness status after analysis."},
    )
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "UTC timestamp when vector-store indexing completed."},
    )
    openai_file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Uploaded OpenAI file ID attached to the vector store."},
    )
    last_error: Optional[str] = field(
        default=None,
        metadata={"doc": "Last vector-store error captured during indexing, if any."},
    )
    regeneration_loop_state: Optional[RegenerationLoopState] = field(
        default=None,
        metadata={
            "doc": "Validation regeneration loop summary, if regeneration ran."
        },
    )
    regeneration_attempts: List[RegenerationAttemptResult] = field(
        default_factory=list,
        metadata={
            "doc": "Per-attempt regeneration audit results for this analysis run."
        },
    )
