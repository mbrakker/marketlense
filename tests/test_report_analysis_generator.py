from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.categories import CategoryAssignment
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_generation import (
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.generators.report_analysis_generator import (
    VectorStoreIndexingState,
    complete_report_analysis,
)
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.utils.errors import AppError


def _runtime(tmp_path: Path) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "cats.yaml"),
        cover_style_path=str(tmp_path / "cover.yaml"),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
        report_worker_limit=1,
    )
    ctx = RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / "report.pdf"),
        settings=settings,
        md5="md5",
        ctx=ctx,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )


def _payload() -> ReportPayload:
    return ReportPayload(
        schema_version="1.1",
        tldr="TLDR",
        title="Base Title",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(schema_version="1.0", title="Figure", evidence="Evidence"),
        commentary="Commentary",
        source="https://example.com",
        publisher="",
    )


def _source(runtime: ReportRuntimeState) -> ReportSourceState:
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version="1.0",
            path=runtime.local_pdf_path,
            page_count=2,
            metadata={},
        ),
        contents_page_number=0,
        contents_heading="",
        contents_image="",
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="body",
            pages_extracted=1,
            char_count=100,
            text_density=100.0,
        ),
        text_status={"schema_version": "1.0", "text_density": 100.0},
        text_validation_status="pass",
        text_validation_reason="",
        text_validation_pages=[1],
        payload=_payload(),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )


def _selection(runtime: ReportRuntimeState, source: ReportSourceState) -> ReportSelectionState:
    return ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=source.payload,
        rank_usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        candidate_count=0,
    )


def _deps(**overrides) -> ReportGeneratorDependencies:
    base = ReportGeneratorDependencies.default()
    seeded = replace(
        base,
        vector_store_wait_until_indexed=lambda req, ctx: SimpleNamespace(
            status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        extract_taxonomy=lambda req, ctx: TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["tag"],
            region="US",
            time_period="2026",
        ),
        load_category_mappings=lambda req, ctx: SimpleNamespace(
            mappings=SimpleNamespace(uncategorized=[], categories=[])
        ),
        categorize_taxonomy=lambda taxonomy, mappings, ctx: CategoryAssignment(
            schema_version="1.0",
            categories=["cat"],
            category_labels=["Category"],
            unmapped_tags=[],
        ),
        update_uncategorized_tags=lambda req, ctx: None,
        vector_store_update_metadata=lambda req, ctx: None,
    )
    return replace(seeded, **overrides)


def test_complete_report_analysis_falls_back_when_validation_raises(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    stored: list[str] = []
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: {"summary": {"tldr": "summary"}},
        run_validation=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
        analysis_store_pack=lambda req, ctx: (
            stored.append(req.pack_name)
            or SimpleNamespace(
                output_path=str(Path(req.output_dir) / req.pack_name / "payload.json")
            )
        ),
    )

    state = complete_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="indexing",
            indexed_at_utc=None,
            last_error=None,
        ),
        deps,
    )

    assert state.payload.title == "Doc Title"
    assert state.payload.publisher == "Doc Publisher"
    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert "validation" in state.evidence_paths
    assert "analysis_vector_store" in stored


def test_complete_report_analysis_surfaces_doc_map_empty(tmp_path, assert_app_error):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: (_ for _ in ()).throw(
            AppError(
                code="doc_map_empty",
                message="doc_map_empty:no_content",
                retryable=False,
                context={"sections_count": 0, "not_found_reason": "model_returned_no_json"},
            )
        )
    )

    with pytest.raises(AppError) as exc_info:
        complete_report_analysis(
            runtime,
            source,
            selection,
            VectorStoreIndexingState(
                vector_store_id="vs_1",
                openai_file_id="file_1",
                vector_store_status="completed",
                indexed_at_utc="2026-01-01T00:00:00Z",
                last_error=None,
            ),
            deps,
        )

    assert_app_error(
        exc_info.value,
        code="doc_map_empty",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["sections_count"] == 0
