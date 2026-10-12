from __future__ import annotations

from types import SimpleNamespace

from src.contracts.pdf_text import PdfTextExtractResponse, PdfTextPage
from src.contracts.run_context import RunContext
from src.orchestrators._report_analysis_orchestrator.source_evidence import (
    build_findings_source_spans,
)
from src.utils.errors import AppError


def test_findings_source_spans_expand_beyond_prompt_page_limit_without_changing_it():
    settings = SimpleNamespace(pdf_text_max_pages=2, pdf_text_max_chars=20_000)
    runtime = SimpleNamespace(
        settings=settings,
        local_pdf_path="report.pdf",
    )
    source = SimpleNamespace(
        runtime=runtime,
        analysis_pdf_path="",
        info_response=SimpleNamespace(page_count=3),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="intro",
            pages_extracted=2,
            char_count=5,
            text_density=2.5,
            pages=[PdfTextPage(page_number=1, text="intro")],
        ),
        pdf_context_for_tasks=None,
    )
    requests = []

    def extract_pdf_text(request, _ctx):
        requests.append(request)
        return PdfTextExtractResponse(
            schema_version="1.0",
            text="intro body",
            pages_extracted=3,
            char_count=10,
            text_density=3.3,
            pages=[
                PdfTextPage(page_number=1, text="intro"),
                PdfTextPage(page_number=2, text="methodology"),
                PdfTextPage(page_number=3, text="body result: installs +22%"),
            ],
        )

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=extract_pdf_text,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )

    assert len(requests) == 1
    assert requests[0].max_pages == 3
    assert requests[0].max_pages > settings.pdf_text_max_pages
    assert requests[0].path == "report.pdf"
    assert [span["page"] for span in spans] == [1, 2, 3]
    assert spans[-1]["text"] == "body result: installs +22%"


def test_findings_source_spans_reuse_complete_page_text_without_reextracting():
    settings = SimpleNamespace(pdf_text_max_pages=3, pdf_text_max_chars=20_000)
    runtime = SimpleNamespace(settings=settings, local_pdf_path="report.pdf")
    source = SimpleNamespace(
        runtime=runtime,
        analysis_pdf_path="report.pdf",
        info_response=SimpleNamespace(page_count=2),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="both pages",
            pages_extracted=2,
            char_count=10,
            text_density=5.0,
            pages=[
                PdfTextPage(page_number=1, text="intro"),
                PdfTextPage(page_number=2, text="body"),
            ],
        ),
        pdf_context_for_tasks=None,
    )

    def unexpected_extraction(_request, _ctx):
        raise AssertionError("complete page text should be reused")

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=unexpected_extraction,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )

    assert [span["page"] for span in spans] == [1, 2]


def test_findings_source_spans_refreshes_detached_chart_reading_order():
    detached = (
        "Main source of income\n"
        "Significant source of income\n"
        "Minor source of income\n"
        "0%\n20%\n49%"
    )
    paired = (
        "Main source of income 0%\n"
        "Significant source of income 20%\n"
        "Minor source of income 49%"
    )
    runtime = SimpleNamespace(
        settings=SimpleNamespace(pdf_text_max_pages=1, pdf_text_max_chars=20_000),
        local_pdf_path="report.pdf",
    )
    source = SimpleNamespace(
        runtime=runtime,
        analysis_pdf_path="report.pdf",
        info_response=SimpleNamespace(page_count=1),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text=detached,
            pages_extracted=1,
            char_count=len(detached),
            text_density=float(len(detached)),
            pages=[PdfTextPage(page_number=1, text=detached)],
        ),
        pdf_context_for_tasks=None,
    )
    requests = []

    def extract_pdf_text(request, _ctx):
        requests.append(request)
        return PdfTextExtractResponse(
            schema_version="1.0",
            text=paired,
            pages_extracted=1,
            char_count=len(paired),
            text_density=float(len(paired)),
            pages=[PdfTextPage(page_number=1, text=paired)],
        )

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=extract_pdf_text,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )

    assert len(requests) == 1
    assert spans[0]["text"] == paired


def test_findings_source_spans_keep_available_evidence_when_expansion_fails():
    settings = SimpleNamespace(pdf_text_max_pages=1, pdf_text_max_chars=20_000)
    runtime = SimpleNamespace(settings=settings, local_pdf_path="report.pdf")
    source = SimpleNamespace(
        runtime=runtime,
        analysis_pdf_path="report.pdf",
        info_response=SimpleNamespace(page_count=2),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="intro",
            pages_extracted=1,
            char_count=5,
            text_density=5.0,
            pages=[PdfTextPage(page_number=1, text="intro")],
        ),
        pdf_context_for_tasks=None,
    )

    def fail_extraction(_request, _ctx):
        raise AppError(
            code="pdf_read_failed",
            message="The evidence-only extraction failed.",
            retryable=True,
        )

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=fail_extraction,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )

    assert spans == [{"id": "source:page:1", "page": 1, "text": "intro"}]
