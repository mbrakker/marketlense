from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.contracts.candidates import Candidate, CandidateFeatures
from src.contracts.pdf_context import PdfContext
from src.contracts.report_models import CropItem, RankedCandidate

REPORT_ASSETS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PdfDegradedPage:
    schema_version: str = field(
        metadata={"doc": "PDF degraded-page record schema version."}
    )
    page: int = field(metadata={"doc": "Zero-based page index affected."})
    stage: str = field(metadata={"doc": "Extraction stage that degraded."})
    reason_code: str = field(metadata={"doc": "Typed reason code for degradation."})
    policy: str = field(metadata={"doc": "Applied degraded-page policy."})
    message: str = field(metadata={"doc": "Sanitized degradation detail."})


@dataclass(frozen=True)
class PdfCandidatePageTriageRecord:
    schema_version: str = field(
        metadata={"doc": "Candidate page-triage record schema version."}
    )
    page: int = field(metadata={"doc": "Zero-based page index evaluated."})
    score: float = field(metadata={"doc": "Normalized candidate-page value score."})
    threshold: float = field(
        metadata={"doc": "Configured minimum score for direct page inclusion."}
    )
    action: str = field(
        metadata={
            "doc": "Triage action: include_score, include_recall_floor, include_disabled, include_table_only_full_scan, skip_low_score, or degraded_*."
        }
    )
    reasons: List[str] = field(
        default_factory=list,
        metadata={"doc": "Deterministic score/action reasons for this page."},
    )
    text_chars: int = field(
        default=0, metadata={"doc": "Text characters observed during triage."}
    )
    text_blocks: int = field(
        default=0, metadata={"doc": "Text blocks observed during triage."}
    )
    image_blocks: int = field(
        default=0, metadata={"doc": "Image blocks observed during triage."}
    )
    drawing_count: int = field(
        default=0, metadata={"doc": "Drawing objects observed during triage."}
    )


@dataclass(frozen=True)
class PdfCandidateExtractionStats:
    schema_version: str = field(
        metadata={"doc": "PDF candidate-extraction stats schema version."}
    )
    degraded_pages: List[PdfDegradedPage] = field(
        default_factory=list,
        metadata={"doc": "Pages processed under degraded extraction policy."},
    )
    triage_failure_count: int = field(
        default=0,
        metadata={"doc": "Count of page-triage failures encountered."},
    )
    extraction_failure_count: int = field(
        default=0,
        metadata={"doc": "Count of non-fatal extraction failures encountered."},
    )
    page_triage_records: List[PdfCandidatePageTriageRecord] = field(
        default_factory=list,
        metadata={"doc": "Per-page scored triage decisions for candidate extraction."},
    )
    page_triage_evaluated_count: int = field(
        default=0,
        metadata={"doc": "Number of pages evaluated by candidate page triage."},
    )
    page_triage_skipped_count: int = field(
        default=0,
        metadata={"doc": "Number of pages skipped by scored candidate page triage."},
    )


@dataclass(frozen=True)
class ExtractCandidatesRequest:
    schema_version: str = field(
        metadata={"doc": "Candidate extraction request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for any extracted assets."})
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )
    parallel_workers: int = field(
        default=0,
        metadata={
            "doc": "Optional extraction worker count. Values <=0 use service defaults."
        },
    )
    exclude_page_indices: List[int] = field(
        default_factory=list,
        metadata={
            "doc": "Zero-based PDF page indices to skip during candidate selection output filtering."
        },
    )
    degraded_page_policy: str = field(
        default="include_with_warning",
        metadata={
            "doc": "Policy for degraded page triage: fail, include_with_warning, or skip_with_warning."
        },
    )
    page_gate_enabled: bool = field(
        default=True,
        metadata={"doc": "Whether scored candidate-page gating is enabled."},
    )
    page_gate_min_score: float = field(
        default=0.2,
        metadata={"doc": "Minimum page score required for direct extraction."},
    )
    page_gate_min_recall_pages: int = field(
        default=12,
        metadata={"doc": "Minimum number of requested pages kept for recall safety."},
    )
    page_gate_min_recall_page_fraction: float = field(
        default=0.65,
        metadata={"doc": "Minimum fraction of requested pages kept for recall safety."},
    )


@dataclass(frozen=True)
class ExtractCandidatesResponse:
    schema_version: str = field(
        metadata={"doc": "Candidate extraction response schema version."}
    )
    candidates: List[Candidate] = field(metadata={"doc": "Extracted candidates."})
    stats: PdfCandidateExtractionStats = field(
        default_factory=lambda: PdfCandidateExtractionStats(
            schema_version=REPORT_ASSETS_SCHEMA_VERSION,
        ),
        metadata={"doc": "Typed candidate-extraction stats and degradation records."},
    )


@dataclass(frozen=True)
class FigureExtractRequest:
    schema_version: str = field(
        metadata={"doc": "Figure extraction request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for extracted assets."})
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class FigureExtractResponse:
    schema_version: str = field(
        metadata={"doc": "Figure extraction response schema version."}
    )
    image_path: Optional[str] = field(
        metadata={"doc": "Relative image path, if extracted."}
    )
    caption: Optional[str] = field(metadata={"doc": "Detected caption text, if any."})
    page: int = field(
        default=-1,
        metadata={
            "doc": "Zero-based source page index for the extracted figure; -1 when unknown."
        },
    )


@dataclass(frozen=True)
class PreviewRequest:
    schema_version: str = field(
        metadata={"doc": "Preview render request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for preview assets."})
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    page_number: int = field(
        default=0,
        metadata={"doc": "Zero-based page number to render for the preview image."},
    )
    variant: str = field(
        default="",
        metadata={"doc": "Optional variant label appended to the preview filename."},
    )
    dpi: int = field(default=144, metadata={"doc": "Render DPI for preview PNG."})
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class PreviewResponse:
    schema_version: str = field(
        metadata={"doc": "Preview render response schema version."}
    )
    image_path: Optional[str] = field(
        metadata={"doc": "Relative preview image path, if rendered."}
    )
    page_number: int = field(
        default=0, metadata={"doc": "Zero-based page number that was rendered."}
    )


@dataclass(frozen=True)
class CropRequest:
    schema_version: str = field(metadata={"doc": "Crop request schema version."})
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for cropped assets."})
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    items: List[CropItem] = field(metadata={"doc": "Crop targets."})
    subdir: str = field(
        default="slices",
        metadata={
            "doc": "Report subdirectory for cropped assets (e.g., slices, candidates)."
        },
    )
    pad: int = field(default=8, metadata={"doc": "Padding applied around crop boxes."})
    mode: str = field(
        default="legacy",
        metadata={
            "doc": "Crop mode: legacy|figure_strict|table_strict|chart_strict|publication_strict."
        },
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class CropResponse:
    schema_version: str = field(metadata={"doc": "Crop response schema version."})
    paths: List[str] = field(metadata={"doc": "Relative paths to cropped images."})


@dataclass(frozen=True)
class CropRefinePageRenderRequest:
    schema_version: str = field(
        metadata={"doc": "Crop-refine page render request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    out_dir: str = field(metadata={"doc": "Output directory for page renders."})
    report_name: str = field(
        metadata={"doc": "Normalized report name for asset paths."}
    )
    page: int = field(metadata={"doc": "Zero-based page index to render."})
    dpi: int = field(
        default=110, metadata={"doc": "Render DPI for page context image."}
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class CropRefinePageRenderResponse:
    schema_version: str = field(
        metadata={"doc": "Crop-refine page render response schema version."}
    )
    image_path: str = field(metadata={"doc": "Relative path to rendered page image."})
    page: int = field(metadata={"doc": "Zero-based page index rendered."})
    image_width: int = field(metadata={"doc": "Rendered image width in pixels."})
    image_height: int = field(metadata={"doc": "Rendered image height in pixels."})
    page_width: float = field(metadata={"doc": "Original PDF page width in points."})
    page_height: float = field(metadata={"doc": "Original PDF page height in points."})
    scale_x: float = field(
        metadata={"doc": "Horizontal conversion scale from PDF points to image pixels."}
    )
    scale_y: float = field(
        metadata={"doc": "Vertical conversion scale from PDF points to image pixels."}
    )


@dataclass(frozen=True)
class CropRefineBBoxApplyRequest:
    schema_version: str = field(
        metadata={"doc": "Crop-refine bbox apply request schema version."}
    )
    pdf_path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    page: int = field(metadata={"doc": "Zero-based page index for bbox clamping."})
    bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Proposed PDF-space bbox to clamp."}
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class CropRefineBBoxApplyResponse:
    schema_version: str = field(
        metadata={"doc": "Crop-refine bbox apply response schema version."}
    )
    page: int = field(metadata={"doc": "Zero-based page index for clamped bbox."})
    bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Clamped and normalized PDF-space bbox."}
    )


@dataclass(frozen=True)
class CropRefineCandidate:
    schema_version: str = field(
        metadata={"doc": "Crop-refine candidate schema version."}
    )
    id: str = field(metadata={"doc": "Candidate identifier."})
    type: str = field(metadata={"doc": "Candidate type: chart|table."})
    page: int = field(metadata={"doc": "Zero-based page index."})
    bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Candidate bbox in PDF-space coordinates."}
    )
    caption: str = field(
        default="", metadata={"doc": "Candidate caption/title text if available."}
    )
    preview_text: str = field(
        default="", metadata={"doc": "Candidate preview text snippet."}
    )
    meta: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Candidate metadata with heuristic signals."},
    )
    features: Optional[CandidateFeatures] = field(
        default=None,
        metadata={
            "doc": "Typed candidate features used for crop refinement decisions."
        },
    )


@dataclass(frozen=True)
class CropRefineResult:
    schema_version: str = field(metadata={"doc": "Crop-refine result schema version."})
    id: str = field(metadata={"doc": "Candidate identifier."})
    is_valid_candidate: bool = field(
        metadata={"doc": "Whether candidate is valid for final HTML figure output."}
    )
    refined_bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Refined PDF-space bbox."}
    )
    include_title: bool = field(
        metadata={"doc": "Whether title/caption should be included in final crop."}
    )
    include_note_if_present: bool = field(
        metadata={"doc": "Whether note/source line should be included when attached."}
    )
    confidence: float = field(
        metadata={"doc": "Model confidence score between 0 and 1."}
    )
    reason: str = field(
        default="", metadata={"doc": "Model-provided reason for decision."}
    )


@dataclass(frozen=True)
class CropRefineRequest:
    schema_version: str = field(metadata={"doc": "Crop-refine request schema version."})
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    prompt_system_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the system prompt template."}
    )
    prompt_user_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the user prompt template."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(
        metadata={"doc": "Sampling temperature for crop refinement."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    page_image_path: str = field(
        metadata={"doc": "Filesystem path to rendered page context image."}
    )
    page: int = field(
        metadata={"doc": "Zero-based page index for supplied image context."}
    )
    page_width: float = field(metadata={"doc": "Original PDF page width in points."})
    page_height: float = field(metadata={"doc": "Original PDF page height in points."})
    candidates: List[CropRefineCandidate] = field(
        metadata={"doc": "Candidates to evaluate and refine on this page."}
    )
    seed: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional deterministic seed for crop refinement."},
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    tool_calls: int = field(
        default=0, metadata={"doc": "Number of tool calls billed (if any)."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )


@dataclass(frozen=True)
class CropRefineResponse:
    schema_version: str = field(
        metadata={"doc": "Crop-refine response schema version."}
    )
    results: List[CropRefineResult] = field(
        metadata={"doc": "Crop refinement decisions for submitted candidates."}
    )
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    prompt_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider prompt token count, if available."}
    )
    completion_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider completion token count, if available."}
    )
    total_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider total token count, if available."}
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID, if available."}
    )


@dataclass(frozen=True)
class RankRequest:
    schema_version: str = field(metadata={"doc": "Rank request schema version."})
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    prompt_system_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the system prompt template."}
    )
    prompt_user_sha256: str = field(
        metadata={"doc": "SHA-256 hash of the user prompt template."}
    )
    model: str = field(metadata={"doc": "OpenAI model ID."})
    temperature: float = field(metadata={"doc": "Sampling temperature."})
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    candidate_count: int = field(
        default=0, metadata={"doc": "Number of candidates included in the prompt."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    tool_calls: int = field(
        default=0, metadata={"doc": "Number of tool calls billed (if any)."}
    )
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for the cost ledger JSONL output."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for daily cost rollups."},
    )
    model_pricing: dict = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    response_cache_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether semantic response caching is enabled for this request."
        },
    )
    response_cache_dir: str = field(
        default="./cache",
        metadata={"doc": "Root cache directory for semantic OpenAI responses."},
    )
    response_cache_ttl_seconds: Optional[float] = field(
        default=604800.0,
        metadata={
            "doc": "Semantic response cache TTL in seconds; None disables expiry."
        },
    )


@dataclass(frozen=True)
class RankResponse:
    schema_version: str = field(metadata={"doc": "Rank response schema version."})
    results: List[RankedCandidate] = field(
        metadata={"doc": "Ranked candidate results."}
    )
    raw_content: str = field(metadata={"doc": "Raw model response content."})
    prompt_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider prompt token count, if available."}
    )
    completion_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider completion token count, if available."}
    )
    total_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Provider total token count, if available."}
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID, if available."}
    )


@dataclass(frozen=True)
class RenderRequest:
    schema_version: str = field(metadata={"doc": "Render request schema version."})
    data: Dict[str, Any] = field(metadata={"doc": "Report data payload (dict form)."})
    doc_name: str = field(metadata={"doc": "Original document name."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    out_dir: str = field(metadata={"doc": "Output directory for rendered HTML."})
    preview_png: Optional[str] = field(
        default=None, metadata={"doc": "Relative preview image path, if any."}
    )
    tag_acronyms: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Acronyms preserved in uppercase while formatting HTML taxonomy/category/topic chip labels."
        },
    )


@dataclass(frozen=True)
class RenderResponse:
    schema_version: str = field(metadata={"doc": "Render response schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to rendered HTML."})
