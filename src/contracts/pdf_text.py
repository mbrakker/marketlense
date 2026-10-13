from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.pdf_context import PdfContext


@dataclass(frozen=True)
class PdfTextLayoutEvidence:
    """Derived relation text kept separately from verbatim PDF page text."""

    schema_version: str = field(metadata={"doc": "PDF layout-evidence schema version."})
    evidence_kind: str = field(
        metadata={
            "doc": "Derivation method; never implies the text is native PDF text."
        }
    )
    text: str = field(
        metadata={"doc": "Explicitly marked, deterministic layout-derived evidence."}
    )


@dataclass(frozen=True)
class PdfTextChartIdentityEvidence:
    """Model transcription of panel labels from a targeted source-page crop."""

    schema_version: str = field(
        metadata={"doc": "Visual chart-identity evidence schema version."}
    )
    status: str = field(
        metadata={"doc": "Transcription outcome: transcribed or abstained."}
    )
    source_pdf_md5: str = field(
        metadata={"doc": "MD5 identity of the original source PDF."}
    )
    physical_page_number: int = field(
        metadata={"doc": "One-based physical page in the original source PDF."}
    )
    crop_image_path: str = field(
        metadata={"doc": "Retained chart crop submitted for visual transcription."}
    )
    crop_image_sha256: str = field(
        metadata={"doc": "SHA-256 of the exact chart crop submitted to the model."}
    )
    label_left: str = field(
        metadata={"doc": "Transcribed visible label above the left panel."}
    )
    label_right: str = field(
        metadata={"doc": "Transcribed visible label above the right panel."}
    )
    confidence_left: float = field(
        metadata={"doc": "Model-reported confidence for the left visible label."}
    )
    confidence_right: float = field(
        metadata={"doc": "Model-reported confidence for the right visible label."}
    )
    model: str = field(metadata={"doc": "Resolved model used for transcription."})
    request_id: str = field(metadata={"doc": "Provider request ID, when returned."})
    prompt_sha256: str = field(
        metadata={"doc": "Hash of the rendered chart-label prompt."}
    )


@dataclass(frozen=True)
class PdfTextPage:
    """Extracted text and one-based provenance for a source-PDF page."""

    page_number: int = field(
        metadata={"doc": "One-based page number from the source PDF."}
    )
    text: str = field(metadata={"doc": "Extracted text retained for this page."})
    layout_evidence: List[PdfTextLayoutEvidence] = field(
        default_factory=list,
        metadata={
            "doc": (
                "Derived text relationships supported by page geometry; separate "
                "from verbatim extracted page text."
            )
        },
    )
    layout_analysis_complete: bool = field(
        default=False,
        metadata={
            "doc": (
                "Whether positioned text was inspected for supported layout-derived "
                "evidence; true also records a checked but ambiguous chart."
            )
        },
    )
    chart_identity_status: str = field(
        default="not_applicable",
        metadata={
            "doc": (
                "Visual panel-identity state: not_applicable, pending, transcribed, "
                "abstained, unavailable, or geometry_unresolved."
            )
        },
    )
    chart_identity_evidence: Optional[PdfTextChartIdentityEvidence] = field(
        default=None,
        metadata={
            "doc": (
                "Model-derived panel labels with original source PDF, physical page, "
                "retained image crop, model, request, and prompt provenance."
            )
        },
    )
    schema_version: str = field(
        default="1.3", metadata={"doc": "PDF extracted-text page schema version."}
    )


@dataclass(frozen=True)
class PdfTextExtractRequest:
    schema_version: str = field(
        metadata={"doc": "PDF text extract request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    max_pages: int = field(metadata={"doc": "Maximum number of pages to extract."})
    max_chars: int = field(metadata={"doc": "Maximum number of characters to return."})
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class PdfTextExtractResponse:
    schema_version: str = field(
        metadata={"doc": "PDF text extract response schema version."}
    )
    text: str = field(metadata={"doc": "Extracted text content."})
    pages_extracted: int = field(metadata={"doc": "Number of pages extracted."})
    char_count: int = field(metadata={"doc": "Number of characters returned."})
    text_density: float = field(
        default=0.0, metadata={"doc": "Characters per page across the sampled pages."}
    )
    pages: List[PdfTextPage] = field(
        default_factory=list,
        metadata={
            "doc": "Optional page-level extracted text retained with source provenance."
        },
    )


@dataclass(frozen=True)
class PdfTextContainsRequest:
    schema_version: str = field(
        metadata={"doc": "PDF text containment request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    text: str = field(
        metadata={"doc": "Whitespace-normalized text expected in one rendered page."}
    )


@dataclass(frozen=True)
class PdfTextContainsResponse:
    schema_version: str = field(
        metadata={"doc": "PDF text containment response schema version."}
    )
    contains_text: bool = field(
        metadata={"doc": "Whether any readable PDF page contains the requested text."}
    )


@dataclass(frozen=True)
class PdfTextSample:
    page_index: int = field(metadata={"doc": "Zero-based page index sampled."})
    page_number: int = field(metadata={"doc": "One-based page number sampled."})
    char_count: int = field(
        metadata={"doc": "Number of extracted characters for the page."}
    )
    has_text: bool = field(
        metadata={"doc": "Whether the sampled page contains extractable text."}
    )
    word_count: int = field(
        default=0,
        metadata={"doc": "Number of meaningful native words extracted for the page."},
    )
    confidence_score: float = field(
        default=0.0,
        metadata={
            "doc": "Deterministic native-text confidence score for the sampled page."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "PDF text sample schema version."}
    )


@dataclass(frozen=True)
class PdfTextSampleRequest:
    schema_version: str = field(
        metadata={"doc": "PDF text sample request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the PDF."})
    page_indices: List[int] = field(
        metadata={"doc": "Zero-based page indices to sample."}
    )
    pdf_context: Optional[PdfContext] = field(
        default=None,
        metadata={"doc": "Optional pre-opened PDF context to reuse handles."},
    )


@dataclass(frozen=True)
class PdfTextSampleResponse:
    schema_version: str = field(
        metadata={"doc": "PDF text sample response schema version."}
    )
    samples: List[PdfTextSample] = field(
        metadata={"doc": "Extracted text samples for requested pages."}
    )
    any_text: bool = field(
        metadata={"doc": "True when any sampled page contains extractable text."}
    )
    document_confidence_score: float = field(
        default=0.0,
        metadata={
            "doc": (
                "Deterministic native-text confidence score aggregated across "
                "sampled pages."
            )
        },
    )
