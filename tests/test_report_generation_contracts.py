from __future__ import annotations

from dataclasses import asdict

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport


def _payload() -> ReportPayload:
    return ReportPayload(
        schema_version="1.1",
        tldr="TLDR",
        title="Report Title",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(schema_version="1.0", title="Figure", evidence="Evidence"),
        commentary="Commentary",
        source="https://example.com",
        publisher="Publisher",
        taxonomy=["tag"],
        categories=["cat"],
        region="US",
        time_period="2026",
        contents_page_number=1,
        contents_heading="Contents",
        _contents_image="contents.png",
        _figure_assets=[
            ReportFigureAsset(
                image_path="report/slices/primary.png",
                page=2,
                candidate_id="chart-1",
                kind="chart",
                is_primary=True,
                detected_caption="Detected caption",
                preview_text="Preview text",
                generated_caption="Generated caption",
                display_caption="Generated caption",
                caption_source="generated",
            )
        ],
    )


def _runtime() -> ReportRuntimeState:
    return ReportRuntimeState(
        schema_version="1.0",
        file=DriveFile(
            schema_version="1.0",
            file_id="file-1",
            name="report.pdf",
            modified_time=None,
            md5_checksum="md5",
        ),
        local_pdf_path="C:/tmp/report.pdf",
        settings=IngestSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5-mini",
            batch_limit=1,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state.sqlite",
            reports_db="./reports.sqlite",
            category_mapping_path="./cats.yaml",
            cover_style_path="./cover.yaml",
            ingest_lock_path="./ingest.lock",
            temperature=0.0,
        ),
        md5="md5",
        ctx=RunContext(
            schema_version="1.0",
            run_id="run",
            task_id="task",
            span_id="span",
        ),
        file_name="report.pdf",
        report_name="report",
        report_title="Report",
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=2,
        parallel_within_file=True,
    )


def _source(runtime: ReportRuntimeState) -> ReportSourceState:
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version="1.0",
            path=runtime.local_pdf_path,
            page_count=5,
            metadata={"Author": "ACME"},
        ),
        contents_page_number=1,
        contents_heading="Contents",
        contents_image="contents.png",
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="body",
            pages_extracted=2,
            char_count=200,
            text_density=100.0,
        ),
        text_status={
            "schema_version": "1.0",
            "text_density": 100.0,
            "density_threshold": 250.0,
            "pages_sampled": 2,
            "char_count": 200,
            "not_available": True,
            "reason": "text_density_below_threshold",
        },
        text_validation_status="pass",
        text_validation_reason="",
        text_validation_pages=[1, 3],
        payload=_payload(),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )


def test_report_generation_contract_roundtrip(assert_no_defaulted_required_fields):
    runtime = _runtime()
    runtime_dict = asdict(runtime)
    runtime_roundtrip = ReportRuntimeState(
        schema_version=runtime_dict["schema_version"],
        file=DriveFile(**runtime_dict["file"]),
        local_pdf_path=runtime_dict["local_pdf_path"],
        settings=IngestSettings(**runtime_dict["settings"]),
        md5=runtime_dict["md5"],
        ctx=RunContext(**runtime_dict["ctx"]),
        file_name=runtime_dict["file_name"],
        report_name=runtime_dict["report_name"],
        report_title=runtime_dict["report_title"],
        analysis_mode=runtime_dict["analysis_mode"],
        analysis_modes=runtime_dict["analysis_modes"],
        report_worker_limit=runtime_dict["report_worker_limit"],
        parallel_within_file=runtime_dict["parallel_within_file"],
    )
    assert runtime_roundtrip == runtime

    source = _source(runtime)
    source_dict = asdict(source)
    source_roundtrip = ReportSourceState(
        schema_version=source_dict["schema_version"],
        runtime=runtime_roundtrip,
        info_response=PdfInfoResponse(**source_dict["info_response"]),
        contents_page_number=source_dict["contents_page_number"],
        contents_heading=source_dict["contents_heading"],
        contents_image=source_dict["contents_image"],
        text_response=PdfTextExtractResponse(**source_dict["text_response"]),
        text_status=source_dict["text_status"],
        text_validation_status=source_dict["text_validation_status"],
        text_validation_reason=source_dict["text_validation_reason"],
        text_validation_pages=source_dict["text_validation_pages"],
        payload=ReportPayload(
            **{
                **source_dict["payload"],
                "quote": Quote(**source_dict["payload"]["quote"]),
                "figure": Figure(**source_dict["payload"]["figure"]),
                "_figure_assets": [
                    ReportFigureAsset(**asset)
                    for asset in source_dict["payload"].get("_figure_assets", [])
                ],
            }
        ),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )
    assert source_roundtrip == source

    selection = ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=source.payload,
        rank_usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        candidate_count=4,
    )
    assert_no_defaulted_required_fields(selection)

    analysis = ReportAnalysisState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        selection=selection,
        payload=source.payload,
        normalized_payload=source.payload,
        data_dict={"title": "Report Title"},
        evidence_paths={"doc_map": "doc_map.json"},
        evidence_packs={"doc_map": {"title": "Report Title"}},
        artifacts_payload={"summary": {"tldr": "TLDR"}},
        validation_report=ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path="validation.json",
        ),
        category_labels=["Category"],
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        openai_file_id="file_1",
        last_error=None,
    )
    assert_no_defaulted_required_fields(analysis)
