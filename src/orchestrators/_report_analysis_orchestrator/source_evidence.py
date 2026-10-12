from __future__ import annotations

import logging
from typing import Callable

from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextExtractResponse
from src.contracts.report_generation import ReportSourceState
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.pdf_text_layout import detached_percent_label_tokens

logger = logging.getLogger(__name__)

_MAX_FINDINGS_SOURCE_CHARS = 5_000_000


def build_findings_source_spans(
    source: ReportSourceState,
    *,
    extract_pdf_text: Callable[
        [PdfTextExtractRequest, RunContext], PdfTextExtractResponse
    ],
    ctx: RunContext,
) -> list[dict[str, object]]:
    """Reuse prompt-context pages and load remaining pages for evidence checks."""

    page_count = max(0, int(source.info_response.page_count))
    pages_by_number = {
        page.page_number: page.text
        for page in source.text_response.pages
        if page.page_number > 0
    }
    missing_pages = any(
        page_number not in pages_by_number for page_number in range(1, page_count + 1)
    )
    has_detached_chart_rows = any(
        detached_percent_label_tokens(text) for text in pages_by_number.values()
    )
    if missing_pages or has_detached_chart_rows:
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
            for page in expanded.pages:
                if page.page_number > 0 and page.text.strip():
                    pages_by_number[page.page_number] = page.text
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

    return [
        {
            "id": f"source:page:{page_number}",
            "page": page_number,
            "text": text,
        }
        for page_number, text in sorted(pages_by_number.items())
        if 1 <= page_number <= page_count and text.strip()
    ]
