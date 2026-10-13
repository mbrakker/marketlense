from __future__ import annotations

import logging
from typing import Callable

from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextPage,
)
from src.contracts.report_generation import ReportSourceState
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.pdf_text_layout import (
    detached_percent_label_tokens,
    has_two_panel_percent_chart_candidate,
)

logger = logging.getLogger(__name__)

_MAX_FINDINGS_SOURCE_CHARS = 5_000_000


def build_findings_source_spans(
    source: ReportSourceState,
    *,
    extract_pdf_text: Callable[
        [PdfTextExtractRequest, RunContext], PdfTextExtractResponse
    ],
    ctx: RunContext,
    chart_identity_enricher: Callable[[PdfTextPage], PdfTextPage] | None = None,
) -> list[dict[str, object]]:
    """Reuse prompt-context pages and load remaining pages for evidence checks."""

    page_count = max(0, int(source.info_response.page_count))
    pages_by_number = {
        page.page_number: page.text
        for page in source.text_response.pages
        if page.page_number > 0
    }
    layout_evidence_by_page = {
        page.page_number: list(getattr(page, "layout_evidence", ()) or ())
        for page in source.text_response.pages
        if page.page_number > 0 and getattr(page, "layout_evidence", None)
    }
    chart_identity_by_page = {
        page.page_number: page.chart_identity_evidence
        for page in source.text_response.pages
        if page.page_number > 0 and page.chart_identity_evidence is not None
    }
    chart_identity_status_by_page = {
        page.page_number: str(getattr(page, "chart_identity_status", "not_applicable"))
        for page in source.text_response.pages
        if page.page_number > 0
    }
    layout_analysis_complete_by_page = {
        page.page_number: bool(getattr(page, "layout_analysis_complete", False))
        for page in source.text_response.pages
        if page.page_number > 0
    }
    missing_pages = any(
        page_number not in pages_by_number for page_number in range(1, page_count + 1)
    )
    has_detached_chart_rows = any(
        detached_percent_label_tokens(text) for text in pages_by_number.values()
    )
    has_unresolved_chart_layout = any(
        has_two_panel_percent_chart_candidate(text)
        and (
            not layout_analysis_complete_by_page.get(page_number, False)
            or chart_identity_status_by_page.get(page_number)
            not in {"transcribed", "abstained", "geometry_unresolved"}
        )
        for page_number, text in pages_by_number.items()
    )
    if missing_pages or has_detached_chart_rows or has_unresolved_chart_layout:
        runtime = source.runtime
        path = source.analysis_pdf_path or runtime.local_pdf_path
        settings = runtime.settings
        context_pages = max(1, int(settings.pdf_text_max_pages))
        context_chars = max(1, int(settings.pdf_text_max_chars))
        context_windows = max(1, (page_count + context_pages - 1) // context_pages)
        max_chars = min(
            _MAX_FINDINGS_SOURCE_CHARS,
            max(context_chars, context_chars * context_windows),
        )
        pdf_context = source.pdf_context_for_tasks
        if getattr(pdf_context, "path", None) != path:
            pdf_context = None
        request = PdfTextExtractRequest(
            schema_version="1.0",
            path=path,
            max_pages=page_count,
            max_chars=max_chars,
            pdf_context=pdf_context,
        )
        extract_ctx = child_context(ctx, task_id=f"{ctx.task_id}:findings_source_text")
        try:
            expanded = extract_pdf_text(request, extract_ctx)
        except AppError as exc:
            logger.warning(
                log_event(
                    extract_ctx,
                    role="orchestrator",
                    event="findings_source_text_expansion_failed",
                    module=logger.name,
                    fields={
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                        "existing_page_count": len(pages_by_number),
                        "requested_page_count": page_count,
                    },
                )
            )
        else:
            for extracted_page in expanded.pages:
                page = extracted_page
                if (
                    page.chart_identity_status == "pending"
                    and chart_identity_enricher is not None
                ):
                    page = chart_identity_enricher(page)
                if page.page_number <= 0:
                    continue
                if page.text.strip():
                    pages_by_number[page.page_number] = page.text
                if getattr(page, "layout_evidence", None):
                    layout_evidence_by_page[page.page_number] = list(
                        page.layout_evidence
                    )
                if getattr(page, "layout_analysis_complete", False):
                    layout_analysis_complete_by_page[page.page_number] = True
                chart_identity = getattr(page, "chart_identity_evidence", None)
                if chart_identity is not None:
                    chart_identity_by_page[page.page_number] = chart_identity
                chart_identity_status_by_page[page.page_number] = str(
                    getattr(page, "chart_identity_status", "not_applicable")
                )
            logger.info(
                log_event(
                    extract_ctx,
                    role="orchestrator",
                    event="findings_source_text_expansion_complete",
                    module=logger.name,
                    fields={
                        "requested_page_count": page_count,
                        "extracted_page_count": expanded.pages_extracted,
                        "source_span_count": sum(
                            1 for text in pages_by_number.values() if text.strip()
                        ),
                        "char_count": expanded.char_count,
                        "char_limit": max_chars,
                        "char_limit_reached": expanded.char_count >= max_chars,
                    },
                )
            )

    source_spans = [
        {
            "id": f"source:page:{page_number}",
            "page": page_number,
            "text": text,
        }
        for page_number, text in sorted(pages_by_number.items())
        if 1 <= page_number <= page_count and text.strip()
    ]
    for page_number, layout_evidence in sorted(layout_evidence_by_page.items()):
        if not 1 <= page_number <= page_count:
            continue
        for index, evidence in enumerate(layout_evidence, start=1):
            evidence_text = str(getattr(evidence, "text", "") or "").strip()
            if not evidence_text:
                continue
            source_spans.append(
                {
                    "id": f"source:page:{page_number}:layout:{index}",
                    "page": page_number,
                    "text": evidence_text,
                    "source_pack": "source_pdf_layout",
                    "evidence_kind": str(
                        getattr(evidence, "evidence_kind", "native_pdf_geometry")
                    ),
                    "verbatim": False,
                }
            )
    for page_number, evidence in sorted(chart_identity_by_page.items()):
        if (
            not 1 <= page_number <= page_count
            or getattr(evidence, "status", "") != "transcribed"
            or getattr(evidence, "physical_page_number", None) != page_number
            or str(getattr(evidence, "source_pdf_md5", "")).casefold()
            != str(source.runtime.md5 or "").casefold()
            or not getattr(evidence, "label_left", "")
            or not getattr(evidence, "label_right", "")
            or not getattr(evidence, "crop_image_sha256", "")
        ):
            continue
        visual_text = "\n".join(
            (
                "Model-derived visual transcription; not native PDF text.",
                f"Original source PDF MD5: {evidence.source_pdf_md5}.",
                f"Physical source PDF page: {page_number}.",
                f"Rendered chart crop SHA-256: {evidence.crop_image_sha256}.",
                f"Left panel visible label: {evidence.label_left}.",
                f"Right panel visible label: {evidence.label_right}.",
            )
        )
        source_spans.append(
            {
                "id": f"source:page:{page_number}:visual:1",
                "page": page_number,
                "text": visual_text,
                "source_pack": "source_pdf_visual",
                "evidence_kind": "visual_model_transcription",
                "verbatim": False,
                "source_pdf_md5": evidence.source_pdf_md5,
                "image_path": evidence.crop_image_path,
                "image_sha256": evidence.crop_image_sha256,
                "model": evidence.model,
                "request_id": evidence.request_id,
                "prompt_sha256": evidence.prompt_sha256,
            }
        )
    return source_spans
