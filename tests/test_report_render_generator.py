from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import (
    derive_title,
    html_cache_key,
    report_slug,
)
from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.utils.cache_utils import sha256_json
import hashlib


def _runtime(tmp_path: Path, *, md5: str | None) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time=None,
        md5_checksum=md5,
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
        md5=md5,
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
        title="Doc Title",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="Quote", author="Author"),
        figure=Figure(schema_version="1.0", title="Figure", evidence="Evidence"),
        commentary="Commentary",
        source="https://example.com",
        publisher="Doc Publisher",
        categories=["cat"],
        taxonomy=["tag"],
        region="US",
        time_period="2026",
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
        candidate_count=1,
    )


def _analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
) -> ReportAnalysisState:
    return ReportAnalysisState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        selection=selection,
        payload=source.payload,
        normalized_payload=source.payload,
        data_dict={
            "title": source.payload.title,
            "publisher": source.payload.publisher,
            "time_period": source.payload.time_period,
            "_figure_section_enabled": False,
            "_figure_gallery": [],
            "_figure_top": "",
        },
        evidence_paths={"doc_map": "doc_map.json"},
        evidence_packs={"doc_map": {"title": source.payload.title}},
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


def _deps(**overrides) -> ReportGeneratorDependencies:
    base = ReportGeneratorDependencies.default()
    seeded = replace(
        base,
        render_preview=lambda req, ctx: SimpleNamespace(
            schema_version="1.1", image_path="preview.png", page_number=0
        ),
        upsert_report_metadata=lambda req, ctx: None,
        get_report_metadata=lambda req, ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file-1",
            title="DB Title",
            created_at=1,
            updated_at=2,
            file_name="report.pdf",
            publisher="DB Publisher",
            taxonomy=["tag"],
            categories=["cat"],
            region="US",
            time_period="Q1 2026",
            source_url=None,
            html_path=None,
            md5="md5",
            page_count=2,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id="vs_1",
            evidence_pack_paths={"doc_map": "doc_map.json"},
        ),
        generate_cover_images=lambda req, ctx: [
            SimpleNamespace(status="processed", output_path="cover.png", error="")
        ],
    )
    return replace(seeded, **overrides)


def test_render_report_output_sources_metadata_from_db_and_returns_complete_outcome(
    tmp_path, assert_no_defaulted_required_fields
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    render_calls: list[str] = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        render_calls.append(req.data["title"])
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report
    )

    preview_resp = render_preview_asset(runtime, source, deps)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "processed"
    assert render_calls == ["DB Title"]
    assert Path(outcome.html_path).exists()


def test_render_report_output_preserves_analysis_metadata_when_db_metadata_missing(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["title"] = req.data["title"]
        captured["publisher"] = req.data["publisher"]
        captured["time_period"] = req.data["time_period"]
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(render_report=_render_report, get_report_metadata=lambda req, ctx: None)

    preview_resp = render_preview_asset(runtime, source, deps)
    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert captured == {
        "title": "Doc Title",
        "publisher": "Doc Publisher",
        "time_period": "2026",
    }


def test_render_report_output_uses_html_cache_hit_and_skips_render(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    expected_html = Path(runtime.settings.output_dir) / f"{runtime.report_name}.html"
    expected_html.parent.mkdir(parents=True, exist_ok=True)
    expected_html.write_text("<html>cached</html>", encoding="utf-8")

    preview_resp = SimpleNamespace(
        schema_version="1.1", image_path="preview.png", page_number=0
    )
    cached_data = {
        **analysis.data_dict,
        "title": "DB Title",
        "publisher": "DB Publisher",
        "time_period": "Q1 2026",
    }
    cache_key = html_cache_key(
        "md5",
        hashlib.sha256("template".encode("utf-8")).hexdigest(),
        sha256_json(cached_data),
        "preview.png",
        runtime.file_name,
    )

    def _read_text(req, ctx):
        if req.path.endswith(f"{runtime.report_name}.html.cache.json"):
            return SimpleNamespace(content=json.dumps({"key": cache_key}))
        if req.path.endswith("report.html.j2"):
            return SimpleNamespace(content="template")
        raise AssertionError(f"Unexpected read: {req.path}")

    deps = _deps(
        read_text=_read_text,
        file_stat=lambda req, ctx: SimpleNamespace(exists=True),
        render_report=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("render_report should be skipped on cache hit")
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=preview_resp,
    )

    assert outcome.html_path == str(expected_html)
