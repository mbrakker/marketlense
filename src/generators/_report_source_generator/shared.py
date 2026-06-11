from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, TypedDict, cast

from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.pdf_context import PdfContext, PdfContextBuildRequest
from src.contracts.pdf_ocr import PdfOcrFallbackResponse
from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSampleRequest,
)
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.contracts.report_assets import PreviewRequest
from src.contracts.report_generation import ReportRuntimeState, ReportSourceState
from src.contracts.report_models import ReportPayload
from src.generators.pdf_text_ocr_generator import recover_pdf_text_with_ocr
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import (
    base_payload,
    contents_cache_key,
    logger,
    pdf_info_cache_key,
    resolve_publisher,
    text_cache_key,
)
from src.generators.report_source_cache import (
    bind_report_source_cache,
    load_report_source_cache,
    write_report_source_cache,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


class TextStatus(TypedDict):
    schema_version: str
    text_density: float
    density_threshold: float
    pages_sampled: int
    char_count: int
    not_available: bool
    reason: str
    native_sample_confidence_score: float
    native_density_confidence_score: float
    native_confidence_score: float
    native_confidence_threshold: float
    native_page_confidence_threshold: float
    low_confidence_pages: list[int]
    ocr_recommended: bool
    ocr_recommendation_reason: str
    ocr_policy: str
    native_text_density: float
    native_text_not_available: bool


@dataclass(frozen=True)
class _NativeTextValidationResult:
    schema_version: str
    status: str
    reason: str
    pages: list[int]
    sample_confidence_score: float
    density_confidence_score: float
    native_confidence_score: float
    low_confidence_pages: list[int]
    ocr_recommended: bool


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
