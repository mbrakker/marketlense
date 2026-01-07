from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.candidates import Candidate
from src.contracts.pdf_context import PdfContext
from src.contracts.report_models import CropItem, RankedCandidate


@dataclass(frozen=True)
class ExtractCandidatesRequest:
    schema_version: str = field(metadata={"doc": "Candidate extraction request schema version."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for any extracted assets."})
    report_name: str = field(metadata={"doc": "Normalized report name for asset paths."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class ExtractCandidatesResponse:
    schema_version: str = field(metadata={"doc": "Candidate extraction response schema version."})
    candidates: List[Candidate] = field(metadata={"doc": "Extracted candidates."})


@dataclass(frozen=True)
class FigureExtractRequest:
    schema_version: str = field(metadata={"doc": "Figure extraction request schema version."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for extracted assets."})
    report_name: str = field(metadata={"doc": "Normalized report name for asset paths."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class FigureExtractResponse:
    schema_version: str = field(metadata={"doc": "Figure extraction response schema version."})
    image_path: Optional[str] = field(metadata={"doc": "Relative image path, if extracted."})
    caption: Optional[str] = field(metadata={"doc": "Detected caption text, if any."})


@dataclass(frozen=True)
class PreviewRequest:
    schema_version: str = field(metadata={"doc": "Preview render request schema version."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for preview assets."})
    report_name: str = field(metadata={"doc": "Normalized report name for asset paths."})
    page_number: int = field(default=0, metadata={"doc": "Zero-based page number to render for the preview image."})
    variant: str = field(default="", metadata={"doc": "Optional variant label appended to the preview filename."})
    dpi: int = field(default=144, metadata={"doc": "Render DPI for preview PNG."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class PreviewResponse:
    schema_version: str = field(metadata={"doc": "Preview render response schema version."})
    image_path: Optional[str] = field(metadata={"doc": "Relative preview image path, if rendered."})
    page_number: int = field(default=0, metadata={"doc": "Zero-based page number that was rendered."})


@dataclass(frozen=True)
class CropRequest:
    schema_version: str = field(metadata={"doc": "Crop request schema version."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for cropped assets."})
    report_name: str = field(metadata={"doc": "Normalized report name for asset paths."})
    items: List[CropItem] = field(metadata={"doc": "Crop targets."})
    pad: int = field(default=8, metadata={"doc": "Padding applied around crop boxes."})
    pdf_context: Optional[PdfContext] = field(default=None, metadata={"doc": "Optional pre-opened PDF context to reuse handles."})


@dataclass(frozen=True)
class CropResponse:
    schema_version: str = field(metadata={"doc": "Crop response schema version."})
    paths: List[str] = field(metadata={"doc": "Relative paths to cropped images."})


@dataclass(frozen=True)
class RankRequest:
    schema_version: str = field(metadata={"doc": "Rank request schema version."})
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    prompt_system_sha256: str = field(metadata={"doc": "SHA-256 hash of the system prompt template."})
    prompt_user_sha256: str = field(metadata={"doc": "SHA-256 hash of the user prompt template."})
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(default=None, metadata={"doc": "Optional seed for deterministic sampling."})
    candidate_count: int = field(default=0, metadata={"doc": "Number of candidates included in the prompt."})
    timeout_seconds: Optional[float] = field(default=None, metadata={"doc": "Request timeout in seconds, if set."})


@dataclass(frozen=True)
class RankResponse:
    schema_version: str = field(metadata={"doc": "Rank response schema version."})
    results: List[RankedCandidate] = field(metadata={"doc": "Ranked candidate results."})
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    prompt_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider prompt token count, if available."})
    completion_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider completion token count, if available."})
    total_tokens: Optional[int] = field(default=None, metadata={"doc": "Provider total token count, if available."})
    request_id: Optional[str] = field(default=None, metadata={"doc": "Provider request ID, if available."})


@dataclass(frozen=True)
class RenderRequest:
    schema_version: str = field(metadata={"doc": "Render request schema version."})
    data: Dict[str, Any] = field(metadata={"doc": "Report data payload (dict form)."})
    doc_name: str = field(metadata={"doc": "Original document name."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    out_dir: str = field(metadata={"doc": "Output directory for rendered HTML."})
    preview_png: Optional[str] = field(default=None, metadata={"doc": "Relative preview image path, if any."})


@dataclass(frozen=True)
class RenderResponse:
    schema_version: str = field(metadata={"doc": "Render response schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to rendered HTML."})
