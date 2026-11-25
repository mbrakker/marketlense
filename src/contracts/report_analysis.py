from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class AnalysisPackPathRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Analysis pack path request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: ReportId = field(
        metadata={
            "doc": "Report identifier used as slug fallback when report_slug is missing."
        }
    )
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    report_slug: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional normalized report slug for per-report layout."},
    )


@dataclass(frozen=True)
class AnalysisPackPathResponse:
    schema_version: str = field(
        metadata={"doc": "Analysis pack path response schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Resolved JSON output path for the pack."}
    )


@dataclass(frozen=True)
class AnalysisStorePackRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Analysis pack store request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: ReportId = field(metadata={"doc": "Report identifier."})
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    payload: Dict[str, Any] = field(
        metadata={"doc": "JSON-serializable payload to write."}
    )
    report_slug: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional normalized report slug for per-report layout."},
    )


@dataclass(frozen=True)
class AnalysisStorePackResponse:
    schema_version: str = field(
        metadata={"doc": "Analysis pack store response schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Primary output path where payload was stored."}
    )


@dataclass(frozen=True)
class AnalysisGenerationReadRequest(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Request schema version, 1.0."})
    output_dir: str = field(metadata={"doc": "Analysis output root."})
    report_id: ReportId = field(metadata={"doc": "Report identifier."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Report slug."})


@dataclass(frozen=True)
class AnalysisGenerationByIdReadRequest(AnalysisGenerationReadRequest):
    generation: str = field(default="", metadata={"doc": "Generation hash to read."})


@dataclass(frozen=True)
class AnalysisGenerationCommitRequest(AnalysisGenerationReadRequest):
    expected_generation: str = field(
        default="",
        metadata={
            "doc": "Expected current generation; empty means no manifest exists."
        },
    )
    packs: Dict[str, Dict[str, Any]] = field(
        default_factory=dict,
        metadata={"doc": "Complete pack set for the immutable generation."},
    )


@dataclass(frozen=True)
class AnalysisGenerationResponse:
    schema_version: str = field(metadata={"doc": "Response schema version, 1.0."})
    generation: str = field(
        metadata={
            "doc": "Hash of the generation contents with its validation path normalized."
        }
    )
    packs: Dict[str, Dict[str, Any]] = field(
        metadata={"doc": "Complete pack set from the selected generation."}
    )
    pack_paths: Dict[str, str] = field(
        metadata={"doc": "Immutable JSON paths for packs in the selected generation."}
    )
    parent_generation: str = field(
        default="", metadata={"doc": "Authenticated parent generation, or empty."}
    )
