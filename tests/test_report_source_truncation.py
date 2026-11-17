from types import SimpleNamespace

import pymupdf as fitz

from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.run_context import RunContext
from src.orchestrators._report_analysis_orchestrator.source_evidence import (
    build_findings_source_spans,
)
from src.services.pdf_service import extract_pdf_text


def test_findings_source_spans_reextract_pages_cut_by_character_budget(tmp_path):
    path = tmp_path / "source.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "First page with retained and missing text")
    doc.new_page().insert_text((72, 72), "Second page contains source evidence")
    doc.save(str(path))
    doc.close()
    ctx = RunContext("1.0", "run", "analysis", "span")
    initial = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0", path=str(path), max_pages=2, max_chars=10
        ),
        ctx,
    )
    source = SimpleNamespace(
        runtime=SimpleNamespace(
            settings=SimpleNamespace(pdf_text_max_pages=2, pdf_text_max_chars=10),
            local_pdf_path=str(path),
        ),
        analysis_pdf_path=str(path),
        info_response=SimpleNamespace(page_count=2),
        text_response=initial,
        pdf_context_for_tasks=None,
    )
    spans = build_findings_source_spans(
        source, extract_pdf_text=extract_pdf_text, ctx=ctx
    )
    assert [span["page"] for span in spans] == [1, 2]
    assert "retained and missing text" in spans[0]["text"]
    assert "Second page contains source evidence" in spans[1]["text"]


def test_findings_source_spans_do_not_reextract_genuinely_blank_pages(tmp_path):
    path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "First page")
    doc.new_page()
    doc.save(str(path))
    doc.close()
    ctx = RunContext("1.0", "run", "analysis", "span")
    initial = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0", path=str(path), max_pages=2, max_chars=1000
        ),
        ctx,
    )
    source = SimpleNamespace(
        runtime=SimpleNamespace(
            settings=SimpleNamespace(pdf_text_max_pages=2, pdf_text_max_chars=1000),
            local_pdf_path=str(path),
        ),
        analysis_pdf_path=str(path),
        info_response=SimpleNamespace(page_count=2),
        text_response=initial,
        pdf_context_for_tasks=None,
    )

    def unexpected_extraction(_request, _ctx):
        raise AssertionError("a genuinely blank page is already complete")

    spans = build_findings_source_spans(
        source, extract_pdf_text=unexpected_extraction, ctx=ctx
    )
    assert [span["page"] for span in spans] == [1]
