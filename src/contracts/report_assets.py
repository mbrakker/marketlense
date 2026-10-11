from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.contracts.candidates import Candidate, CandidateFeatures
from src.contracts.pdf_context import PdfContext
from src.contracts.report_models import CropItem, RankedCandidate
from src.contracts.run_budget import RunBudget

REPORT_ASSETS_SCHEMA_VERSION = "1.0"
CROP_REFINE_COORDINATE_TRANSFORM_VERSION = "pdf-page-affine-v1"


def _validate_bbox_contract(
    bbox: Tuple[float, float, float, float], *, field_name: str
) -> None:
    if len(bbox) != 4 or not all(math.isfinite(float(value)) for value in bbox):
        raise ValueError(f"{field_name} must contain four finite coordinates")
    x0, y0, x1, y1 = (float(value) for value in bbox)
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"{field_name} must be ordered and non-degenerate")


def _validate_affine_contract(
    transform: Tuple[float, float, float, float, float, float], *, field_name: str
) -> None:
    if len(transform) != 6 or not all(
        math.isfinite(float(value)) for value in transform
    ):
        raise ValueError(f"{field_name} must contain six finite affine coefficients")


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
    dpi: int = field(
        default=144,
        metadata={"doc": "Render DPI for final cropped PNG assets."},
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class CropResponse:
    schema_version: str = field(metadata={"doc": "Crop response schema version."})
    paths: List[str] = field(metadata={"doc": "Relative paths to cropped images."})
    outcomes: List["CropOutcome"] = field(
        default_factory=list,
        metadata={
            "doc": "Per-request crop outcomes keyed by candidate ID, including rejected strict crops."
        },
    )


@dataclass(frozen=True)
class CropOutcome:
    schema_version: str = field(metadata={"doc": "Crop outcome schema version."})
    candidate_id: str = field(metadata={"doc": "Candidate identifier."})
    path: str = field(default="", metadata={"doc": "Relative crop path when accepted."})
    accepted: bool = field(
        default=False, metadata={"doc": "Whether the crop is accepted for use."}
    )
    qa_sidecar_path: str = field(
        default="", metadata={"doc": "Relative final-crop QA sidecar path, if any."}
    )
    score: float = field(
        default=0.0, metadata={"doc": "Final crop QA score, if available."}
    )
    defects: List[str] = field(
        default_factory=list, metadata={"doc": "Final crop QA defect labels."}
    )
    detector_summary: dict[str, float] = field(
        default_factory=dict,
        metadata={
            "doc": "Maximum detector confidence by detector for selection telemetry."
        },
    )
    quality_profile: str = field(
        default="", metadata={"doc": "Crop quality profile or request mode."}
    )
    rejection_reason: str = field(
        default="", metadata={"doc": "Typed rejection reason for rejected crops."}
    )
    dpi: int = field(
        default=0, metadata={"doc": "Render DPI of the accepted crop artifact."}
    )
    image_sha256: str = field(
        default="", metadata={"doc": "SHA-256 of the materialized crop image."}
    )


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
    coordinate_transform_version: str = field(
        metadata={"doc": "Version of the page/image-to-canonical-PDF affine maps."}
    )
    display_to_pdf_transform: Tuple[float, float, float, float, float, float] = field(
        metadata={
            "doc": "Affine map from rotated displayed page points to canonical unrotated crop-relative PDF points."
        }
    )
    pdf_to_display_transform: Tuple[float, float, float, float, float, float] = field(
        metadata={
            "doc": "Affine map from canonical unrotated crop-relative PDF points to displayed page points."
        }
    )
    image_to_pdf_transform: Tuple[float, float, float, float, float, float] = field(
        metadata={
            "doc": "Affine map from rendered image pixels to canonical unrotated crop-relative PDF points."
        }
    )
    rotation: int = field(metadata={"doc": "PDF page rotation in degrees clockwise."})
    crop_box: Tuple[float, float, float, float] = field(
        metadata={"doc": "PDF crop box in source page coordinates."}
    )
    media_box: Tuple[float, float, float, float] = field(
        metadata={"doc": "PDF media box in source page coordinates."}
    )
    pdf_page_width: float = field(
        metadata={"doc": "Canonical unrotated crop-relative page width in points."}
    )
    pdf_page_height: float = field(
        metadata={"doc": "Canonical unrotated crop-relative page height in points."}
    )

    def __post_init__(self) -> None:
        if (
            self.coordinate_transform_version
            != CROP_REFINE_COORDINATE_TRANSFORM_VERSION
        ):
            raise ValueError("unsupported crop-refine coordinate transform version")
        _validate_affine_contract(
            self.display_to_pdf_transform, field_name="display_to_pdf_transform"
        )
        _validate_affine_contract(
            self.pdf_to_display_transform, field_name="pdf_to_display_transform"
        )
        _validate_affine_contract(
            self.image_to_pdf_transform, field_name="image_to_pdf_transform"
        )
        _validate_bbox_contract(self.crop_box, field_name="crop_box")
        _validate_bbox_contract(self.media_box, field_name="media_box")
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("rotation must be a right angle")
        if (
            min(
                self.image_width,
                self.image_height,
                self.pdf_page_width,
                self.pdf_page_height,
            )
            <= 0
        ):
            raise ValueError("crop-refine page dimensions must be positive")


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
    original_bbox: Tuple[float, float, float, float] = field(
        metadata={
            "doc": "Validated source candidate bbox used when the refined proposal is unsafe."
        }
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )
    full_page_target: bool = field(
        default=False,
        metadata={
            "doc": "Whether source candidate metadata explicitly identifies a full-page target."
        },
    )

    def __post_init__(self) -> None:
        _validate_bbox_contract(self.bbox, field_name="bbox")
        _validate_bbox_contract(self.original_bbox, field_name="original_bbox")


@dataclass(frozen=True)
class CropRefineBBoxApplyResponse:
    schema_version: str = field(
        metadata={"doc": "Crop-refine bbox apply response schema version."}
    )
    page: int = field(metadata={"doc": "Zero-based page index for clamped bbox."})
    bbox: Tuple[float, float, float, float] = field(
        metadata={"doc": "Clamped and normalized PDF-space bbox."}
    )
    degradation_reason: str = field(
        default="",
        metadata={
            "doc": "Stable reason an unsafe proposal fell back to its source bbox."
        },
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

    def __post_init__(self) -> None:
        _validate_bbox_contract(self.refined_bbox, field_name="refined_bbox")


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
    temperature: float | None = field(
        metadata={"doc": "Sampling temperature for crop refinement."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    page_image_path: str = field(
        metadata={"doc": "Filesystem path to rendered page context image."}
    )
    page: int = field(
        metadata={"doc": "Zero-based page index for supplied image context."}
    )
    page_width: float = field(
        metadata={"doc": "Displayed page width in PDF points after rotation/crop."}
    )
    page_height: float = field(
        metadata={"doc": "Displayed page height in PDF points after rotation/crop."}
    )
    candidates: List[CropRefineCandidate] = field(
        metadata={"doc": "Candidates to evaluate and refine on this page."}
    )
    run_budget: RunBudget = field(
        metadata={
            "doc": "Canonical budget that governs this crop-refinement provider call."
        }
    )
    coordinate_transform_version: str = field(
        default=CROP_REFINE_COORDINATE_TRANSFORM_VERSION,
        metadata={"doc": "Version of the displayed-page to canonical-PDF affine map."},
    )
    display_to_pdf_transform: Tuple[float, float, float, float, float, float] = field(
        default=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        metadata={
            "doc": "Affine map from model-reported displayed page points to canonical PDF points."
        },
    )
    reasoning_effort: str = field(
        default="", metadata={"doc": "Resolved provider reasoning effort."}
    )
    seed: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional deterministic seed for crop refinement."},
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    max_output_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Bounded provider output-token limit."}
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
    prompt_hash: str = field(default="")
    prompt_content_hash: str = field(default="")
    prompt_dependency_manifest: dict = field(default_factory=dict)
    execution_identity: str = field(default="")
    execution_identity_manifest: dict = field(default_factory=dict)
    execution_policy_hash: str = field(default="")
    execution_policy: dict = field(default_factory=dict)
    execution_policy_source: str = field(default="")

    def __post_init__(self) -> None:
        if (
            self.coordinate_transform_version
            != CROP_REFINE_COORDINATE_TRANSFORM_VERSION
        ):
            raise ValueError("unsupported crop-refine coordinate transform version")
        _validate_affine_contract(
            self.display_to_pdf_transform, field_name="display_to_pdf_transform"
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
    temperature: float | None = field(
        metadata={"doc": "Optional sampling temperature."}
    )
    api_key: str = field(metadata={"doc": "OpenAI API key (secret, loaded from env)."})
    reasoning_effort: str = field(
        default="", metadata={"doc": "Resolved provider reasoning effort."}
    )
    seed: Optional[int] = field(
        default=None, metadata={"doc": "Optional seed for deterministic sampling."}
    )
    candidate_count: int = field(
        default=0, metadata={"doc": "Number of candidates included in the prompt."}
    )
    timeout_seconds: Optional[float] = field(
        default=None, metadata={"doc": "Request timeout in seconds, if set."}
    )
    max_output_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Bounded provider output-token limit."}
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
    prompt_hash: str = field(default="")
    prompt_content_hash: str = field(default="")
    prompt_dependency_manifest: dict = field(default_factory=dict)
    execution_identity: str = field(default="")
    execution_identity_manifest: dict = field(default_factory=dict)
    execution_policy_hash: str = field(default="")
    execution_policy: dict = field(default_factory=dict)
    execution_policy_source: str = field(default="")
    run_budget: RunBudget | None = field(
        default=None,
        metadata={
            "doc": "Optional canonical budget that governs this ranking provider call."
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
    build_provenance: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Immutable, non-public render provenance emitted in the final HTML "
                "build comment."
            )
        },
    )
    final_crop_dpi: int = field(
        default=0,
        metadata={
            "doc": "Configured final publication-crop DPI; zero means the renderer has no trusted expected DPI."
        },
    )


@dataclass(frozen=True)
class RenderResponse:
    schema_version: str = field(metadata={"doc": "Render response schema version."})
    html_path: str = field(metadata={"doc": "Filesystem path to rendered HTML."})
