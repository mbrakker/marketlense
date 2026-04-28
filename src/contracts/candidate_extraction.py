from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class CandidateExtractRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Candidate extraction request schema version."}
    )
    report_id: ReportId = field(
        metadata={"doc": "Stable report identifier for outputs."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    output_dir: str = field(
        metadata={"doc": "Root output directory for candidate artifacts."}
    )
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    subdir: str = field(
        default="candidates", metadata={"doc": "Subdirectory for cropped images."}
    )
    save_crops: bool = field(
        default=True, metadata={"doc": "Whether to crop and save candidate images."}
    )


@dataclass(frozen=True)
class CandidateExtractOutcome(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Candidate extraction outcome schema version."}
    )
    report_id: ReportId = field(metadata={"doc": "Report identifier used for outputs."})
    report_name: str = field(metadata={"doc": "Normalized report name."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    candidates_path: str = field(
        metadata={"doc": "Filesystem path to the saved candidates JSON."}
    )
    candidate_count: int = field(
        metadata={"doc": "Total number of candidates extracted."}
    )
    chart_count: int = field(metadata={"doc": "Number of chart candidates."})
    table_count: int = field(metadata={"doc": "Number of table candidates."})
    crop_count: int = field(
        metadata={"doc": "Number of cropped candidate images saved."}
    )
    crop_paths: List[str] = field(
        metadata={"doc": "Relative paths to cropped candidate images."}
    )
    error: Optional[str] = field(
        default=None, metadata={"doc": "Error message when extraction fails."}
    )
