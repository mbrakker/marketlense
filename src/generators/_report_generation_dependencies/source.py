from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.files import (
    FileStatRequest,
    JsonObjectCacheReadRequest,
    JsonObjectCacheWriteRequest,
    ReadTextRequest,
    WriteBytesRequest,
)
from src.contracts.openai import (
    OpenAIPdfOcrRequest,
    OpenAIPdfOcrResponse,
)
from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_ocr import (
    PdfOcrSplitRequest,
    PdfOcrSplitResponse,
    PdfTextRenderRequest,
    PdfTextRenderResponse,
)
from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSampleRequest,
)
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services import llm_service
from src.services.file_service import (
    file_stat,
    read_json_object_cache,
    read_text,
    write_json_object_cache,
    write_bytes,
)
from src.services.pdf_service import (
    build_pdf_context,
    detect_contents_page as detect_contents_page_service,
    extract_pdf_info,
    extract_pdf_text,
    render_preview as render_preview_service,
    render_text_pdf,
    sample_pdf_text,
    split_pdf_for_ocr,
)
from src.services.prompt_service import load_prompt_set, render_prompt


@dataclass(frozen=True)
class ReportSourceDependencies:
    build_pdf_context: Callable[[PdfContextBuildRequest, RunContext], Any]
    extract_pdf_info: Callable[[PdfInfoRequest, RunContext], PdfInfoResponse]
    detect_contents_page: Callable[
        [PdfContentsDetectionRequest, RunContext], PdfContentsDetectionResponse
    ]
    render_preview: Callable[[Any, RunContext], Any]
    render_text_pdf: Callable[[PdfTextRenderRequest, RunContext], PdfTextRenderResponse]
    split_pdf_for_ocr: Callable[[PdfOcrSplitRequest, RunContext], PdfOcrSplitResponse]
    extract_pdf_text: Callable[
        [PdfTextExtractRequest, RunContext], PdfTextExtractResponse
    ]
    sample_pdf_text: Callable[[PdfTextSampleRequest, RunContext], Any]
    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    openai_ocr_pdf: Callable[[OpenAIPdfOcrRequest, RunContext], OpenAIPdfOcrResponse]
    file_stat: Callable[[FileStatRequest, RunContext], Any]
    read_text: Callable[[ReadTextRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]
    read_json_object_cache: Callable[[JsonObjectCacheReadRequest, RunContext], Any] = (
        read_json_object_cache
    )
    write_json_object_cache: Callable[
        [JsonObjectCacheWriteRequest, RunContext], Any
    ] = write_json_object_cache

    @classmethod
    def default(cls) -> "ReportSourceDependencies":
        return cls(
            build_pdf_context=build_pdf_context,
            extract_pdf_info=extract_pdf_info,
            detect_contents_page=detect_contents_page_service,
            render_preview=render_preview_service,
            render_text_pdf=render_text_pdf,
            split_pdf_for_ocr=split_pdf_for_ocr,
            extract_pdf_text=extract_pdf_text,
            sample_pdf_text=sample_pdf_text,
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            openai_ocr_pdf=llm_service.openai_ocr_pdf,
            file_stat=file_stat,
            read_text=read_text,
            write_bytes=write_bytes,
            read_json_object_cache=read_json_object_cache,
            write_json_object_cache=write_json_object_cache,
        )
