from types import SimpleNamespace

from src.contracts.pdf_text import (
    PdfTextChartIdentityEvidence,
    PdfTextExtractResponse,
    PdfTextLayoutEvidence,
    PdfTextPage,
)
from src.contracts.run_context import RunContext
from src.orchestrators._report_analysis_orchestrator.source_evidence import (
    build_findings_source_spans,
)


def test_refreshed_page_does_not_keep_stale_layout_or_chart_identity():
    identity = PdfTextChartIdentityEvidence(
        schema_version="1.0",
        status="transcribed",
        source_pdf_md5="source-md5",
        physical_page_number=1,
        crop_image_path="crop.png",
        crop_image_sha256="a" * 64,
        label_left="Old left",
        label_right="Old right",
        confidence_left=0.9,
        confidence_right=0.9,
        model="fixture",
        request_id="request",
        prompt_sha256="b" * 64,
    )
    original = PdfTextPage(
        page_number=1,
        text="old text",
        layout_evidence=[
            PdfTextLayoutEvidence("1.0", "native_pdf_geometry", "old 91%")
        ],
        layout_analysis_complete=True,
        chart_identity_status="transcribed",
        chart_identity_evidence=identity,
    )
    replacement = PdfTextPage(
        page_number=1, text="new text", layout_analysis_complete=True
    )
    source = SimpleNamespace(
        runtime=SimpleNamespace(
            settings=SimpleNamespace(pdf_text_max_pages=1, pdf_text_max_chars=100),
            local_pdf_path="report.pdf",
            md5="source-md5",
        ),
        analysis_pdf_path="",
        info_response=SimpleNamespace(page_count=2),
        text_response=PdfTextExtractResponse("1.0", "old text", 1, 8, 8.0, [original]),
        pdf_context_for_tasks=None,
    )

    def extract(_request, _ctx):
        return PdfTextExtractResponse("1.0", "new text", 1, 8, 8.0, [replacement])

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=extract,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )
    assert spans == [{"id": "source:page:1", "page": 1, "text": "new text"}]
