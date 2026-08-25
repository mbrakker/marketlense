from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PdfOcrPageText:
    page_number: int = field(
        metadata={"doc": "One-based page number from the source PDF."}
    )
    text: str = field(metadata={"doc": "OCR text extracted for the page."})
    schema_version: str = field(
        default="1.0", metadata={"doc": "PDF OCR page text schema version."}
    )


@dataclass(frozen=True)
class PdfOcrAggregateResponse:
    schema_version: str = field(
        metadata={"doc": "Aggregated OCR response schema version."}
    )
    pages: List[PdfOcrPageText] = field(
        metadata={"doc": "Ordered OCR page text across the full source PDF."}
    )
    raw_text: str = field(
        metadata={
            "doc": "Serialized raw OCR chunk responses collected across the full source PDF."
        }
    )
    models: List[str] = field(
        metadata={"doc": "Resolved OCR model identifiers used across OCR chunks."}
    )
    request_ids: List[str] = field(
        metadata={"doc": "Provider request identifiers collected across OCR chunks."}
    )
    chunk_count: int = field(
        metadata={"doc": "Number of OCR chunks processed for the source PDF."}
    )


@dataclass(frozen=True)
class PdfTextRenderRequest:
    schema_version: str = field(
        metadata={"doc": "Text-to-PDF render request schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Filesystem path where the rendered PDF should be written."}
    )
    pages: List[PdfOcrPageText] = field(
        metadata={"doc": "Ordered OCR page text to render into the PDF."}
    )


@dataclass(frozen=True)
class PdfTextRenderResponse:
    schema_version: str = field(
        metadata={"doc": "Text-to-PDF render response schema version."}
    )
    output_path: str = field(metadata={"doc": "Filesystem path of the rendered PDF."})
    rendered_page_count: int = field(
        metadata={"doc": "Number of synthetic pages written to the rendered PDF."}
    )


@dataclass(frozen=True)
class PdfImageRenderRequest:
    schema_version: str = field(
        metadata={"doc": "Image-to-PDF render request schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Filesystem path where the rendered PDF should be written."}
    )
    image_bytes: List[bytes] = field(
        metadata={"doc": "Ordered encoded image pages to preserve in the rendered PDF."}
    )


@dataclass(frozen=True)
class PdfImageRenderResponse:
    schema_version: str = field(
        metadata={"doc": "Image-to-PDF render response schema version."}
    )
    output_path: str = field(metadata={"doc": "Filesystem path of the rendered PDF."})
    rendered_page_count: int = field(
        metadata={"doc": "Number of image pages written and verified in the PDF."}
    )


@dataclass(frozen=True)
class PdfHtmlRenderRequest:
    schema_version: str = field(
        metadata={"doc": "HTML-to-PDF render request schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Filesystem path where the rendered PDF should be written."}
    )
    html: str = field(metadata={"doc": "Sanitized HTML content to render locally."})
    max_pages: int = field(
        metadata={"doc": "Hard maximum number of rendered pages before failure."}
    )


@dataclass(frozen=True)
class PdfHtmlRenderResponse:
    schema_version: str = field(
        metadata={"doc": "HTML-to-PDF render response schema version."}
    )
    output_path: str = field(metadata={"doc": "Filesystem path of the rendered PDF."})
    rendered_page_count: int = field(
        metadata={"doc": "Number of HTML pages written and verified in the PDF."}
    )


@dataclass(frozen=True)
class PdfOcrChunk:
    chunk_index: int = field(
        metadata={"doc": "One-based index of the OCR chunk within the source PDF."}
    )
    source_pdf_path: str = field(
        metadata={"doc": "Filesystem path to the full source PDF."}
    )
    chunk_pdf_path: str = field(
        metadata={"doc": "Filesystem path to the chunk PDF submitted for OCR."}
    )
    start_page_number: int = field(
        metadata={"doc": "One-based starting page number in the full source PDF."}
    )
    end_page_number: int = field(
        metadata={"doc": "One-based ending page number in the full source PDF."}
    )
    page_count: int = field(
        metadata={"doc": "Number of pages contained in the OCR chunk PDF."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "OCR chunk schema version."}
    )


@dataclass(frozen=True)
class PdfOcrSplitRequest:
    schema_version: str = field(
        metadata={"doc": "PDF OCR split request schema version."}
    )
    source_pdf_path: str = field(
        metadata={"doc": "Filesystem path to the source PDF to split for OCR."}
    )
    output_dir: str = field(
        metadata={"doc": "Filesystem directory where chunk PDFs should be written."}
    )
    chunk_page_count: int = field(
        metadata={"doc": "Maximum number of pages per OCR chunk PDF."}
    )


@dataclass(frozen=True)
class PdfOcrSplitResponse:
    schema_version: str = field(
        metadata={"doc": "PDF OCR split response schema version."}
    )
    chunks: List[PdfOcrChunk] = field(
        metadata={"doc": "Ordered OCR chunk PDFs derived from the source PDF."}
    )


@dataclass(frozen=True)
class PdfOcrFallbackResponse:
    schema_version: str = field(
        metadata={"doc": "OCR fallback response schema version."}
    )
    ocr_response: PdfOcrAggregateResponse = field(
        metadata={"doc": "Structured OCR response aggregated across OCR chunks."}
    )
    render_response: PdfTextRenderResponse = field(
        metadata={"doc": "Rendered OCR PDF output details."}
    )
    cache_hit: bool = field(
        metadata={"doc": "Whether the OCR fallback was served from cache."}
    )
