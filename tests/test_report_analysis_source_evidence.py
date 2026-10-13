from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz

from src.contracts.openai import OpenAIResponseResult
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_text import (
    PdfTextChartIdentityEvidence,
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextPage,
)
from src.contracts.run_context import RunContext
from src.orchestrators._report_analysis_orchestrator.source_evidence import (
    build_findings_source_spans,
)
from src.services.pdf_service import build_pdf_context, extract_pdf_text
from src.utils.pdf_text_layout import two_panel_chart_image_bbox
from src.generators.pdf_chart_panel_identity_generator import (
    transcribe_chart_panel_identity,
)
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.claim_validation_generator import validate_evidence_fidelity
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


def _build_platform_chart_pdf(
    path, *, title: str, omit_axis_index: int | None = None
) -> None:
    """Build a compact two-panel fixture from Activate p. 53's chart geometry."""

    doc = fitz.open()
    page = doc.new_page(width=1024, height=768)
    page.insert_text((60, 90), "Evaluating creators with over 10M views", fontsize=14)
    page.insert_textbox(fitz.Rect(55, 165, 970, 205), title, fontsize=10)

    for x, top, bottom in ((44, 300, 480), (520, 305, 485)):
        page.insert_textbox(
            fitz.Rect(x, top - 20, x + 80, top + 35),
            "CREATORS\nWITH 50M+\nTOTAL VIEWS",
            fontsize=9,
        )
        page.insert_textbox(
            fitz.Rect(x, bottom - 20, x + 90, bottom + 35),
            "CREATORS\nWITH 10-50M\nTOTAL VIEWS",
            fontsize=9,
        )

    values = (
        (190, 325, "24%"),
        (375, 410, "71%"),
        (190, 500, "76%"),
        (375, 585, "29%"),
        (667, 330, "26%"),
        (852, 420, "77%"),
        (667, 505, "74%"),
        (852, 595, "23%"),
    )
    for x, y, label in values:
        page.insert_text((x, y), label, fontsize=14)

    for axis_index, (x, label) in enumerate(
        (
            (174, "Creators"),
            (369, "Views"),
            (651, "Creators"),
            (846, "Views"),
        )
    ):
        if axis_index != omit_axis_index:
            page.insert_text((x, 660), label, fontsize=14)
    page.insert_text(
        (230, 720),
        "Top creators defined as those with over 10M total views.",
        fontsize=9,
    )
    doc.save(path)
    doc.close()


def _extract_chart_source_spans(
    pdf_path,
    *,
    page_count: int = 1,
    visual_labels: tuple[str, str] | None = None,
):
    ctx = RunContext("1.0", "run", "analysis", "span")
    pdf_context = build_pdf_context(
        PdfContextBuildRequest("1.0", pdf_path.as_posix()), ctx
    ).context
    try:
        extracted = extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=pdf_path.as_posix(),
                max_pages=page_count,
                max_chars=20_000,
                pdf_context=pdf_context,
            ),
            ctx,
        )
        source_md5 = hashlib.md5(pdf_path.read_bytes()).hexdigest()
        if visual_labels is not None:
            page = extracted.pages[0]
            identity = PdfTextChartIdentityEvidence(
                schema_version="1.0",
                status="transcribed",
                source_pdf_md5=source_md5,
                physical_page_number=1,
                crop_image_path=str(pdf_path.with_name("chart-crop.png")),
                crop_image_sha256=hashlib.sha256(b"chart-crop").hexdigest(),
                label_left=visual_labels[0],
                label_right=visual_labels[1],
                confidence_left=0.99,
                confidence_right=0.99,
                model="fixture-vision-model",
                request_id="req_fixture_chart_labels",
                prompt_sha256=hashlib.sha256(b"chart-label-prompt").hexdigest(),
            )
            extracted = replace(
                extracted,
                pages=[
                    replace(
                        page,
                        chart_identity_status="transcribed",
                        chart_identity_evidence=identity,
                    ),
                    *extracted.pages[1:],
                ],
            )
        source = SimpleNamespace(
            runtime=SimpleNamespace(
                settings=SimpleNamespace(
                    pdf_text_max_pages=page_count,
                    pdf_text_max_chars=20_000,
                ),
                local_pdf_path=pdf_path.as_posix(),
                md5=source_md5,
            ),
            analysis_pdf_path=pdf_path.as_posix(),
            info_response=SimpleNamespace(page_count=page_count),
            text_response=extracted,
            pdf_context_for_tasks=pdf_context,
        )
        spans = build_findings_source_spans(
            source,
            extract_pdf_text=extract_pdf_text,
            ctx=ctx,
        )
        return extracted, spans
    finally:
        pdf_context.close()


def test_findings_source_spans_bind_two_panel_chart_values_from_page_geometry(
    tmp_path,
):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    extracted, spans = _extract_chart_source_spans(pdf_path)

    assert len(spans) == 2
    assert spans[0]["id"] == "source:page:1"
    assert spans[0]["text"] == extracted.pages[0].text
    layout_span = spans[1]
    assert layout_span["id"] == "source:page:1:layout:1"
    assert layout_span["source_pack"] == "source_pdf_layout"
    assert layout_span["page"] == 1
    assert "YOUTUBE:" not in layout_span["text"]
    assert "FACEBOOK:" not in layout_span["text"]
    assert (
        "Panel 1: the 50M+ total-view cohort is 24% of creators" in layout_span["text"]
    )
    assert (
        "Panel 1: the 50M+ total-view cohort is 71% of creators"
        not in layout_span["text"]
    )
    assert "with 71% of views" in layout_span["text"]
    assert (
        "Panel 2: the 50M+ total-view cohort is 26% of creators" in layout_span["text"]
    )
    assert "with 77% of views" in layout_span["text"]
    assert "YOUTUBE:" not in layout_span["text"]
    assert "FACEBOOK:" not in layout_span["text"]
    assert "Q2 2017" in layout_span["text"]
    assert "over 10M total views" in layout_span["text"]
    assert "not verbatim native PDF text" in layout_span["text"]
    assert extracted.pages[0].layout_analysis_complete is True
    assert extracted.pages[0].chart_identity_status == "pending"


def test_chart_relationship_fidelity_rejects_swaps_and_population_expansion(
    tmp_path,
):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    _extracted, spans = _extract_chart_source_spans(
        pdf_path, visual_labels=("YOUTUBE", "FACEBOOK")
    )
    claims = {
        "correct": (
            "In global Q2 2017, among creators with over 10M total views, "
            "the 50M+ YouTube cohort represented 24% of creators and 71% of "
            "views; the 50M+ Facebook cohort represented 26% of creators and "
            "77% of views."
        ),
        "platform_swap": (
            "In global Q2 2017, among creators with over 10M total views, "
            "the 50M+ YouTube cohort represented 26% of creators and 77% of "
            "views; the 50M+ Facebook cohort represented 24% of creators and "
            "71% of views."
        ),
        "metric_swap": (
            "In global Q2 2017, among creators with over 10M total views, "
            "the 50M+ YouTube cohort represented 71% of creators and 24% of "
            "views; the 50M+ Facebook cohort represented 77% of creators and "
            "26% of views."
        ),
        "population_expansion": (
            "In global Q2 2017, 50M+ YouTube creators were 24% of all YouTube "
            "creators and accounted for 71% of all YouTube views."
        ),
        "missing_cohort": (
            "In global Q2 2017, among creators with over 10M total views, "
            "YouTube represented 24% of creators and 71% of views, while "
            "Facebook represented 26% of creators and 77% of views."
        ),
    }
    results = {}
    for case, claim in claims.items():
        package = validate_evidence_fidelity(
            {"findings": {"findings": [{"id": case, "text": claim, "pages": [1]}]}},
            source_spans=spans,
        )
        results[case] = package.results[0]

    assert results["correct"].status == "supported"
    for case in (
        "platform_swap",
        "metric_swap",
        "population_expansion",
        "missing_cohort",
    ):
        assert results[case].status == "unsupported"
        assert any(
            check.name == "chart_relationship_fidelity" and check.status == "failed"
            for check in results[case].checks
        )


def test_chart_relationship_fidelity_accepts_both_platforms_in_one_clause(tmp_path):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    _extracted, spans = _extract_chart_source_spans(
        pdf_path, visual_labels=("YOUTUBE", "FACEBOOK")
    )
    claim = (
        "Among creators with over 10M total views in global Q2 2017, the "
        "50M+ YouTube cohort represented 24% of creators and 71% of views, "
        "while the 50M+ Facebook cohort represented 26% of creators and "
        "77% of views."
    )

    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [{"id": "both-platforms", "text": claim, "pages": [1]}]
            }
        },
        source_spans=spans,
    )

    assert package.results[0].status == "supported"


def test_chart_relationship_fidelity_rejects_visual_identity_from_another_page(
    tmp_path,
):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    _extracted, spans = _extract_chart_source_spans(
        pdf_path, visual_labels=("YOUTUBE", "FACEBOOK")
    )
    mismatched_spans = [dict(span) for span in spans]
    for span in mismatched_spans:
        if span.get("source_pack") == "source_pdf_visual":
            span["page"] = 2

    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "cross-page-chart-identity",
                        "text": (
                            "Among creators with over 10M total views in global "
                            "Q2 2017, the 50M+ YouTube cohort represented 24% of "
                            "creators and 71% of views, while the 50M+ Facebook "
                            "cohort represented 26% of creators and 77% of views."
                        ),
                        "pages": [1, 2],
                    }
                ]
            }
        },
        source_spans=mismatched_spans,
    )

    assert package.results[0].status == "unsupported"
    assert any(
        check.name == "chart_relationship_fidelity"
        and check.status == "failed"
        and check.reason == "chart_visual_identity_unresolved"
        for check in package.results[0].checks
    )


def test_ambiguous_two_panel_chart_is_not_promoted_as_bound_evidence(tmp_path):
    pdf_path = tmp_path / "ambiguous-two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
        omit_axis_index=1,
    )
    extracted, spans = _extract_chart_source_spans(pdf_path)

    assert extracted.pages[0].layout_evidence == []
    assert extracted.pages[0].layout_analysis_complete is True
    assert all(span.get("source_pack") != "source_pdf_layout" for span in spans)
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "ambiguous-chart",
                        "text": (
                            "Among creators with over 10M total views, 50M+ "
                            "YouTube creators represented 24% of creators and "
                            "71% of views."
                        ),
                        "pages": [1],
                    }
                ]
            }
        },
        source_spans=spans,
    )

    assert package.results[0].status == "unsupported"
    assert any(
        check.name == "chart_relationship_fidelity" and check.status == "failed"
        for check in package.results[0].checks
    )

    def unexpected_reextraction(_request, _ctx):
        raise AssertionError("a checked ambiguous page must reuse its retained state")

    spans_again = build_findings_source_spans(
        SimpleNamespace(
            runtime=SimpleNamespace(
                settings=SimpleNamespace(
                    pdf_text_max_pages=1, pdf_text_max_chars=20_000
                ),
                local_pdf_path=pdf_path.as_posix(),
            ),
            analysis_pdf_path=pdf_path.as_posix(),
            info_response=SimpleNamespace(page_count=1),
            text_response=extracted,
            pdf_context_for_tasks=None,
        ),
        extract_pdf_text=unexpected_reextraction,
        ctx=RunContext("1.0", "run", "analysis", "span"),
    )
    assert spans_again == spans


def test_layout_evidence_is_generic_to_caption_platform_names(tmp_path):
    pdf_path = tmp_path / "renamed-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 NORTHSTAR AND REDWOOD CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )

    extracted, spans = _extract_chart_source_spans(
        pdf_path, visual_labels=("NORTHSTAR", "REDWOOD")
    )

    assert len(extracted.pages[0].layout_evidence) == 1
    assert "Panel 1: the 50M+" in extracted.pages[0].layout_evidence[0].text
    assert "Panel 2: the 50M+" in extracted.pages[0].layout_evidence[0].text
    assert "NORTHSTAR:" not in extracted.pages[0].layout_evidence[0].text
    assert "REDWOOD:" not in extracted.pages[0].layout_evidence[0].text
    assert spans[-1]["source_pack"] == "source_pdf_visual"
    assert spans[-1]["evidence_kind"] == "visual_model_transcription"
    assert spans[-1]["source_pdf_md5"] == hashlib.md5(pdf_path.read_bytes()).hexdigest()


def test_expanded_chart_page_is_visually_bound_before_findings_validation(tmp_path):
    chart_path = tmp_path / "single-chart-page.pdf"
    _build_platform_chart_pdf(
        chart_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    chart_doc = fitz.open(chart_path)
    source_doc = fitz.open()
    source_doc.new_page().insert_text((72, 72), "Ordinary introduction")
    source_doc.insert_pdf(chart_doc)
    pdf_path = tmp_path / "two-page-source.pdf"
    source_doc.save(pdf_path)
    source_doc.close()
    chart_doc.close()

    source_md5 = hashlib.md5(pdf_path.read_bytes()).hexdigest()
    source = SimpleNamespace(
        runtime=SimpleNamespace(
            settings=SimpleNamespace(pdf_text_max_pages=1, pdf_text_max_chars=20_000),
            local_pdf_path=pdf_path.as_posix(),
            md5=source_md5,
        ),
        analysis_pdf_path=pdf_path.as_posix(),
        info_response=SimpleNamespace(page_count=2),
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="Ordinary introduction",
            pages_extracted=1,
            char_count=22,
            text_density=22.0,
            pages=[PdfTextPage(page_number=1, text="Ordinary introduction")],
        ),
        pdf_context_for_tasks=None,
    )
    enriched_page_numbers = []

    def enrich_chart_page(page):
        enriched_page_numbers.append(page.page_number)
        identity = PdfTextChartIdentityEvidence(
            schema_version="1.0",
            status="transcribed",
            source_pdf_md5=source_md5,
            physical_page_number=page.page_number,
            crop_image_path=str(tmp_path / "page-2-chart-crop.png"),
            crop_image_sha256=hashlib.sha256(b"targeted-page-2-chart-crop").hexdigest(),
            label_left="YOUTUBE",
            label_right="FACEBOOK",
            confidence_left=0.99,
            confidence_right=0.99,
            model="fixture-visual-model",
            request_id="req_expanded_chart_fixture",
            prompt_sha256=hashlib.sha256(b"chart-label-prompt").hexdigest(),
        )
        return replace(
            page,
            chart_identity_status="transcribed",
            chart_identity_evidence=identity,
        )

    spans = build_findings_source_spans(
        source,
        extract_pdf_text=extract_pdf_text,
        ctx=RunContext("1.0", "run", "analysis", "span"),
        chart_identity_enricher=enrich_chart_page,
    )

    assert enriched_page_numbers == [2]
    page_two_spans = [span for span in spans if span.get("page") == 2]
    assert [span["id"] for span in page_two_spans] == [
        "source:page:2",
        "source:page:2:layout:1",
        "source:page:2:visual:1",
    ]
    assert (
        "Panel 1: the 50M+ total-view cohort is 24% of creators"
        in page_two_spans[1]["text"]
    )
    assert "with 71% of views" in page_two_spans[1]["text"]
    assert (
        "Panel 2: the 50M+ total-view cohort is 26% of creators"
        in page_two_spans[1]["text"]
    )
    assert "with 77% of views" in page_two_spans[1]["text"]
    assert page_two_spans[2]["source_pdf_md5"] == source_md5
    assert page_two_spans[2]["evidence_kind"] == "visual_model_transcription"
    package = validate_evidence_fidelity(
        {
            "findings": {
                "findings": [
                    {
                        "id": "expanded-chart-binding",
                        "text": (
                            "In global Q2 2017, among creators with over 10M total "
                            "views, the 50M+ YouTube cohort represented 24% of "
                            "creators and 71% of views; the 50M+ Facebook cohort "
                            "represented 26% of creators and 77% of views."
                        ),
                        "pages": [2],
                    }
                ]
            }
        },
        source_spans=page_two_spans,
    )
    assert package.results[0].status == "supported"


def test_chart_panel_identity_uses_targeted_crop_and_keeps_image_provenance(
    ingest_settings, run_context, tmp_path
):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    settings = replace(
        ingest_settings,
        cache_dir=str(tmp_path / "cache"),
        llm_execution_policies={
            "pdf_text/chart_panel_identity": {
                "schema_version": "1.0",
                "provider": "openai",
                "model": "gpt-6-luna",
                "reasoning_effort": "low",
                "max_output_tokens": 128,
                "timeout_seconds": 60,
                "provider_retry_count": 0,
                "structured_output_mode": "json_object",
                "structured_output_schema_identity": "pdf_chart_panel_identity.v1",
                "fallback_policy": "disabled",
            }
        },
    )
    runtime = SimpleNamespace(
        settings=settings,
        report_name="fixture-report",
        report_title="Fixture report",
        source_report_name="Fixture report",
        source_url="",
        publisher_name="Fixture publisher",
        md5=hashlib.md5(pdf_path.read_bytes()).hexdigest(),
        ctx=run_context,
    )
    dependencies = ReportSourceDependencies.default()
    context = build_pdf_context(
        PdfContextBuildRequest(schema_version="1.0", path=pdf_path.as_posix()),
        run_context,
    ).context
    extraction = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=pdf_path.as_posix(),
            max_pages=1,
            max_chars=20_000,
            pdf_context=context,
        ),
        run_context,
    )
    chart_page = context.fitz_doc[0]
    label_bbox = two_panel_chart_image_bbox(
        extraction.pages[0].text,
        chart_page.get_text("words", sort=True),
        (
            chart_page.rect.x0,
            chart_page.rect.y0,
            chart_page.rect.x1,
            chart_page.rect.y1,
        ),
    )
    assert label_bbox is not None
    assert label_bbox[3] - label_bbox[1] < chart_page.rect.height / 2
    axis_label_top = min(
        float(word[1])
        for word in chart_page.get_text("words", sort=True)
        if str(word[4]) in {"Creators", "Views"}
    )
    assert label_bbox[3] < axis_label_top
    calls = []

    class FakeVisualClient:
        def openai_chat_json_with_images(self, request, _ctx):
            calls.append(request)
            assert len(request.image_paths) == 1
            assert Path(request.image_paths[0]).is_file()
            assert request.prompt_namespace == "pdf_text/chart_panel_identity"
            assert "Do not infer identity" in request.system_prompt
            return OpenAIResponseResult(
                schema_version="1.0",
                text=(
                    '{"left_label":"YouTube","right_label":"Facebook",'
                    '"left_confidence":0.99,"right_confidence":0.98}'
                ),
                parsed_json={
                    "left_label": "YouTube",
                    "right_label": "Facebook",
                    "left_confidence": 0.99,
                    "right_confidence": 0.98,
                },
                input_tokens=120,
                output_tokens=32,
                total_tokens=152,
                model="gpt-6-luna",
                request_id="req_chart_identity_fixture",
            )

    try:
        result = transcribe_chart_panel_identity(
            runtime,
            extraction.pages[0],
            pdf_path=pdf_path.as_posix(),
            pdf_context=context,
            dependencies=dependencies,
            llm_client=FakeVisualClient(),
        )
    finally:
        context.close()

    assert len(calls) == 1
    identity = result.chart_identity_evidence
    assert result.chart_identity_status == "transcribed"
    assert identity is not None
    assert identity.label_left == "YOUTUBE"
    assert identity.label_right == "FACEBOOK"
    assert identity.source_pdf_md5 == runtime.md5
    assert identity.physical_page_number == 1
    assert hashlib.sha256(Path(identity.crop_image_path).read_bytes()).hexdigest() == (
        identity.crop_image_sha256
    )
    assert identity.request_id == "req_chart_identity_fixture"


def test_chart_panel_identity_skips_visual_call_when_layout_is_unresolved():
    page = PdfTextPage(
        page_number=53,
        text=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
        layout_analysis_complete=False,
        chart_identity_status="pending",
    )

    class UnexpectedVisualClient:
        def openai_chat_json_with_images(self, _request, _ctx):
            raise AssertionError("ambiguous layout must not trigger a model call")

    result = transcribe_chart_panel_identity(
        SimpleNamespace(),
        page,
        pdf_path="unused.pdf",
        pdf_context=None,
        dependencies=None,
        llm_client=UnexpectedVisualClient(),
    )

    assert result.chart_identity_status == "geometry_unresolved"
    assert result.chart_identity_evidence is None


def test_chart_panel_identity_abstains_on_ambiguous_labels(
    ingest_settings, run_context, tmp_path
):
    pdf_path = tmp_path / "two-platform-chart.pdf"
    _build_platform_chart_pdf(
        pdf_path,
        title=(
            "SHARE OF TOP1 YOUTUBE AND FACEBOOK CREATORS VS. SHARE OF VIEWS "
            "BY PLATFORM, GLOBAL, Q2 2017, % TOTAL"
        ),
    )
    settings = replace(
        ingest_settings,
        cache_dir=str(tmp_path / "cache"),
        llm_execution_policies={
            "pdf_text/chart_panel_identity": {
                "schema_version": "1.0",
                "provider": "openai",
                "model": "gpt-6-luna",
                "reasoning_effort": "low",
                "max_output_tokens": 128,
                "timeout_seconds": 60,
                "provider_retry_count": 0,
                "structured_output_mode": "json_object",
                "structured_output_schema_identity": "pdf_chart_panel_identity.v1",
                "fallback_policy": "disabled",
            }
        },
    )
    runtime = SimpleNamespace(
        settings=settings,
        report_name="fixture-report",
        report_title="Fixture report",
        source_report_name="Fixture report",
        source_url="",
        publisher_name="Fixture publisher",
        md5=hashlib.md5(pdf_path.read_bytes()).hexdigest(),
        ctx=run_context,
    )
    context = build_pdf_context(
        PdfContextBuildRequest(schema_version="1.0", path=pdf_path.as_posix()),
        run_context,
    ).context
    extraction = extract_pdf_text(
        PdfTextExtractRequest(
            schema_version="1.0",
            path=pdf_path.as_posix(),
            max_pages=1,
            max_chars=20_000,
            pdf_context=context,
        ),
        run_context,
    )

    class AmbiguousVisualClient:
        def openai_chat_json_with_images(self, _request, _ctx):
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"left_label":"","right_label":"Facebook"}',
                parsed_json={
                    "left_label": "",
                    "right_label": "Facebook",
                    "left_confidence": 0.0,
                    "right_confidence": 0.98,
                },
                model="gpt-6-luna",
                request_id="req_chart_identity_ambiguous",
            )

    try:
        result = transcribe_chart_panel_identity(
            runtime,
            extraction.pages[0],
            pdf_path=pdf_path.as_posix(),
            pdf_context=context,
            dependencies=ReportSourceDependencies.default(),
            llm_client=AmbiguousVisualClient(),
        )
    finally:
        context.close()

    assert result.chart_identity_status == "abstained"
    assert result.chart_identity_evidence is not None
    assert result.chart_identity_evidence.label_left == ""
    assert result.chart_identity_evidence.label_right == ""
