from __future__ import annotations

from dataclasses import replace

from src.contracts.pdf_text import PdfTextExtractResponse, PdfTextPage
from src.contracts.report_identity import ReportTitleResolution
from src.generators.report_render_generator import _resolved_report_title
from tests._test_report_render_generator.cases_01_render_output_and_cards import (
    _analysis,
    _runtime,
    _selection,
    _source,
)


def test_resolved_report_title_accepts_cover_grounded_document_map_title(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    title = "Trust or trepidation?: How Brits feel about generative AI in media"
    source = replace(
        _source(runtime),
        title_resolution=ReportTitleResolution(issues=("generic_title_missing",)),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text=f"GREAT BRITAIN\n{title}/Research Reality",
            pages_extracted=1,
            char_count=100,
            pages=[
                PdfTextPage(
                    page_number=1,
                    text=f"GREAT BRITAIN\n{title}/Research Reality",
                )
            ],
        ),
    )
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        evidence_packs={"doc_map": {"title": title}},
    )

    assert _resolved_report_title(runtime, source, analysis) == title
    assert (
        _resolved_report_title(
            runtime,
            source,
            replace(
                analysis,
                evidence_packs={"doc_map": {"title": "Unsupported media title"}},
            ),
        )
        == ""
    )
