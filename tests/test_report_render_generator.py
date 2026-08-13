from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    ReportCardManifestWriteResponse,
)
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.report_store import (
    ReportMetadataGetResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.generators.report_generation_dependencies import ReportRenderDependencies
from src.generators.report_generation_shared import (
    derive_title,
    html_cache_key,
    report_slug,
)
from src.generators.report_render_generator import (
    _public_source_note,
    _resolved_report_title,
    render_preview_asset,
    render_report_output,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError


def _template_bundle_sha(template_contents: dict[str, str]) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "templates": {
                name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in template_contents.items()
            },
        }
    )


def _runtime(tmp_path: Path, *, md5: str | None) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="report.pdf",
        modified_time="2026-06-10T08:30:00Z",
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


def _selection(
    runtime: ReportRuntimeState, source: ReportSourceState
) -> ReportSelectionState:
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
        artifacts_payload={
            "summary": {
                "tldr": (
                    "A complete standard summary explains the report's strategic "
                    "finding."
                ),
                "card_tldr_compact": (
                    "Strategic demand is shifting toward more efficient channels."
                ),
            },
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "rising",
                "evidence_density": "balanced",
                "domain_layer": "grid",
                "selection_reason": (
                    "The report presents a sustained upward market trend."
                ),
            },
            "insights_final": [
                {"text": "Channel efficiency improved across the measured period."},
                {"text": "Investment shifted toward higher-return customer segments."},
            ],
            "publication_date": "2026-06-09",
        },
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


def _card_cover_assets(asset_dir: Path) -> CardCoverAssetSet:
    return CardCoverAssetSet(
        "1.0",
        CardCoverAsset(
            "1.0", "small", str(asset_dir / "report-card-small.png"), 1600, 900
        ),
        CardCoverAsset(
            "1.0", "medium", str(asset_dir / "report-card-medium.png"), 1200, 1500
        ),
        CardCoverAsset(
            "1.0", "large", str(asset_dir / "report-card-large.png"), 1200, 1600
        ),
    )


def _deps(**overrides) -> ReportRenderDependencies:
    base = ReportRenderDependencies.default()

    def _generated_covers(req, ctx):
        del ctx
        report = req.reports[0]
        return [
            SimpleNamespace(
                schema_version="2.0",
                file_id=report.file_id,
                title=report.title,
                status="generated",
                assets=_card_cover_assets(
                    Path(req.output_dir) / report.report_slug / "assets"
                ),
                error=None,
            )
        ]

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
        generate_cover_images=_generated_covers,
        write_report_card_manifest=lambda req, ctx: ReportCardManifestWriteResponse(
            schema_version="1.0",
            manifest_path=str(Path(req.output_dir) / "report-card-manifest.json"),
            bytes_written=1024,
        ),
    )
    return replace(seeded, **overrides)


def _cover_assets(runtime: ReportRuntimeState) -> CardCoverAssetSet:
    return _card_cover_assets(
        Path(runtime.settings.output_dir) / runtime.report_name / "assets"
    )


def test_public_source_note_keeps_title_when_publisher_is_absent(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            canonical_title="Publisher Evidence Report",
            publisher_name="",
        ),
    )

    assert _public_source_note(runtime) == "Source: Publisher Evidence Report"


def test_public_source_note_decodes_a_url_encoded_canonical_title(tmp_path) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        source_identity=SimpleNamespace(
            canonical_title="GWI%20Brand%20tracking%20guide",
            publisher_name="GWI",
        ),
    )

    assert _public_source_note(runtime) == "Source: GWI — GWI Brand tracking guide"


def test_resolved_report_title_replaces_a_runtime_slug_with_document_map_title(
    tmp_path,
) -> None:
    runtime = replace(
        _runtime(tmp_path, md5="md5"),
        file=DriveFile(
            schema_version="1.0",
            file_id="file-1",
            name="gwi-20brand-20tracking-20guide-pdf",
            modified_time="2026-06-10T08:30:00Z",
            md5_checksum="md5",
        ),
        file_name="gwi-20brand-20tracking-20guide-pdf",
        report_name="gwi-20brand-20tracking-20guide-pdf",
        report_title="gwi-20brand-20tracking-20guide-pdf",
        source_identity=SimpleNamespace(
            identity_status="resolved",
            canonical_title="GWI%20Brand%20tracking%20guide",
            publisher_name="GWI",
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        payload=replace(source.payload, title=runtime.report_title),
        evidence_packs={"doc_map": {"title": "GWI%20Brand%20tracking%20guide"}},
    )

    assert _resolved_report_title(runtime, source, analysis) == (
        "GWI Brand tracking guide"
    )


def test_resolved_report_title_replaces_source_identifier_with_document_map_title(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        evidence_packs={"doc_map": {"title": "Document Map Report Title"}},
    )

    assert _resolved_report_title(
        runtime,
        source,
        analysis,
        "source-12345678901234567890",
    ) == "Document Map Report Title"


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

    deps = _deps(render_report=_render_report)

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
    assert outcome.status == "error"
    assert outcome.error == "publish_readiness_failed"
    assert render_calls == ["DB Title"]


def test_render_report_output_passes_db_source_url_to_public_renderer(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["source"] = req.data["source"]
        captured["canonical_url"] = req.data["canonical_url"]
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        get_report_metadata=lambda req, ctx: replace(
            _deps().get_report_metadata(req, ctx),
            source_url="https://publisher.example/reports/original-study",
        ),
    )

    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert captured == {"source": "", "canonical_url": ""}


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

    deps = _deps(
        render_report=_render_report, get_report_metadata=lambda req, ctx: None
    )

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


def test_render_report_output_omits_private_pdf_download_href(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    Path(runtime.local_pdf_path).write_bytes(b"%PDF-1.4\n")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    captured = {}
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del ctx
        captured["has_download_href"] = "_source_download_href" in req.data
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(render_report=_render_report)

    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert captured["has_download_href"] is False


def test_render_report_citations_use_report_page_labels_without_internal_targets(
    tmp_path, run_context
):
    from src.contracts.report_assets import RenderRequest
    from src.services.render_service import render_report

    out_dir = tmp_path / "out"
    data = {
        "title": "Retail Forecast 2026",
        "publisher": "Forecast Co",
        "source": "https://forecast.example/report",
        "_figure_section_enabled": False,
        "artifacts": {
            "summary": {
                "tldr": "Retail demand is changing.",
                "executive_summary": "Retail demand is changing across channels.",
                "claim_evidence_map": [
                    {
                        "claim": "Retail demand is changing.",
                        "evidence_id": "local-evidence-123",
                        "evidence": "Demand moved across channels.",
                        "pages": [7],
                        "evidence_spans": [
                            {
                                "evidence_id": "local-evidence-123",
                                "source_pack": "cache/evidence-window.json",
                                "page": 7,
                            }
                        ],
                    }
                ],
            },
            "insights_final": [
                {
                    "text": "Demand moved across channels.",
                    "evidence_id": "local-insight-456",
                    "pages": [8],
                }
            ],
            "quotes_final": [
                {
                    "text": "Consumers are shifting channels.",
                    "speaker": "Analyst",
                    "citation": "C:/tmp/evidence-window.json",
                    "page": 9,
                    "evidence_id": "local-quote-789",
                }
            ],
        },
        "evidence_packs": {"doc_map": {"title": "Retail Forecast 2026"}},
    }

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="retail-forecast.pdf",
            file_id="file-1",
            out_dir=str(out_dir),
            preview_png="",
            tag_acronyms=[],
        ),
        run_context,
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    assert "Retail Forecast 2026, page 7" in html
    assert "Retail Forecast 2026, page 8" in html
    assert "Retail Forecast 2026, page 9" in html
    assert "local-evidence-123" not in html
    assert "local-insight-456" not in html
    assert "local-quote-789" not in html
    assert "cache/evidence-window.json" not in html
    assert "C:/tmp/evidence-window.json" not in html


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
        "canonical_url": "",
        "source": "",
    }
    template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "css",
        "_report_macros.j2": "macros",
    }
    cache_key = html_cache_key(
        "md5",
        _template_bundle_sha(template_contents),
        sha256_json(cached_data),
        "preview.png",
        runtime.file_name,
        render_contract_version="2.0",
    )

    def _read_text(req, ctx):
        if req.path == str(expected_html):
            return SimpleNamespace(content=expected_html.read_text(encoding="utf-8"))
        if req.path.endswith(f"{runtime.report_name}.html.cache.json"):
            return SimpleNamespace(content=json.dumps({"key": cache_key}))
        for name, content in template_contents.items():
            if req.path.endswith(name):
                return SimpleNamespace(content=content)
        raise AssertionError(f"Unexpected read: {req.path}")

    def _read_cache(req, ctx):
        del ctx
        assert req.path.endswith(f"{runtime.report_name}.html.cache.json")
        return SimpleNamespace(found=True, payload={"key": cache_key})

    def _hash_bundle(req, ctx):
        del ctx
        assert {Path(path).name for path in req.paths} == set(template_contents)
        return SimpleNamespace(sha256=_template_bundle_sha(template_contents))

    def _file_stat(req, ctx):
        del ctx
        return SimpleNamespace(exists=Path(req.path) == expected_html)

    deps = _deps(
        read_text=_read_text,
        read_json_object_cache=_read_cache,
        hash_file_bundle=_hash_bundle,
        file_stat=_file_stat,
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


def test_render_report_output_invalidates_cache_when_css_template_changes(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    expected_html = Path(runtime.settings.output_dir) / f"{runtime.report_name}.html"
    expected_html.parent.mkdir(parents=True, exist_ok=True)
    expected_html.write_text("<html>stale</html>", encoding="utf-8")

    preview_resp = SimpleNamespace(
        schema_version="1.1", image_path="preview.png", page_number=0
    )
    cached_data = {
        **analysis.data_dict,
        "title": "DB Title",
        "publisher": "DB Publisher",
        "time_period": "Q1 2026",
        "source": "",
    }
    stale_template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "old-css",
        "_report_macros.j2": "macros",
    }
    current_template_contents = {
        "report.html.j2": "template",
        "report.css.j2": "new-css",
        "_report_macros.j2": "macros",
    }
    stale_cache_key = html_cache_key(
        "md5",
        _template_bundle_sha(stale_template_contents),
        sha256_json(cached_data),
        "preview.png",
        runtime.file_name,
        render_contract_version="2.0",
    )
    render_calls: list[str] = []

    def _read_text(req, ctx):
        if req.path == str(expected_html):
            return SimpleNamespace(content=expected_html.read_text(encoding="utf-8"))
        if req.path.endswith(f"{runtime.report_name}.html.cache.json"):
            return SimpleNamespace(content=json.dumps({"key": stale_cache_key}))
        for name, content in current_template_contents.items():
            if req.path.endswith(name):
                return SimpleNamespace(content=content)
        raise AssertionError(f"Unexpected read: {req.path}")

    def _read_cache(req, ctx):
        del ctx
        assert req.path.endswith(f"{runtime.report_name}.html.cache.json")
        return SimpleNamespace(found=True, payload={"key": stale_cache_key})

    def _hash_bundle(req, ctx):
        del ctx
        assert {Path(path).name for path in req.paths} == set(current_template_contents)
        return SimpleNamespace(sha256=_template_bundle_sha(current_template_contents))

    def _render_report(req, ctx):
        del ctx
        render_calls.append(req.data["title"])
        expected_html.write_text("<html>fresh</html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(expected_html))

    def _file_stat(req, ctx):
        del ctx
        return SimpleNamespace(exists=Path(req.path) == expected_html)

    deps = _deps(
        read_text=_read_text,
        read_json_object_cache=_read_cache,
        hash_file_bundle=_hash_bundle,
        file_stat=_file_stat,
        render_report=_render_report,
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
    assert render_calls == ["DB Title"]
    assert expected_html.read_text(encoding="utf-8") == "<html>fresh</html>"


def test_html_cache_key_changes_when_render_contract_changes() -> None:
    shared = (
        "md5",
        "template-sha",
        "data-sha",
        "preview.png",
        "report.pdf",
    )

    assert html_cache_key(*shared, render_contract_version="1.0") != html_cache_key(
        *shared,
        render_contract_version="2.0",
    )


def test_render_preview_asset_reuses_contents_preview_when_contents_is_first_page(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = replace(
        _source(runtime),
        contents_page_number=1,
        contents_image="report/assets/report-contents.png",
    )
    render_calls: list[tuple[str, int, str]] = []
    deps = _deps(
        render_preview=lambda req, ctx: (
            render_calls.append((req.pdf_path, req.page_number, req.variant))
            or SimpleNamespace(
                schema_version="1.1",
                image_path="preview.png",
                page_number=req.page_number,
            )
        )
    )

    preview_resp = render_preview_asset(runtime, source, deps)

    assert preview_resp.image_path == "report/assets/report-contents.png"
    assert preview_resp.page_number == 0
    assert render_calls == []


def test_render_preview_asset_renders_when_contents_page_does_not_overlap(
    tmp_path,
):
    runtime = _runtime(tmp_path, md5="md5")
    source = replace(
        _source(runtime),
        contents_page_number=2,
        contents_image="report/assets/report-contents.png",
    )
    render_calls: list[tuple[str, int, str]] = []
    deps = _deps(
        render_preview=lambda req, ctx: (
            render_calls.append((req.pdf_path, req.page_number, req.variant))
            or SimpleNamespace(
                schema_version="1.1",
                image_path="preview.png",
                page_number=req.page_number,
            )
        )
    )

    preview_resp = render_preview_asset(runtime, source, deps)

    assert preview_resp.image_path == "preview.png"
    assert render_calls == [(runtime.local_pdf_path, 0, "")]


def test_render_report_output_propagates_retryable_cover_error(
    tmp_path, assert_app_error
):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="cover_render_failed",
                message="temporary cover render failure",
                retryable=True,
            )
        ),
    )

    with pytest.raises(AppError) as err:
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            deps,
            preview_resp=render_preview_asset(runtime, source, deps),
        )

    assert_app_error(
        err.value,
        code="cover_render_failed",
        retryable=True,
        severity="error",
    )


def test_render_report_output_does_not_use_file_modified_time_for_card_date(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload={
            "summary": {
                "tldr": "A complete standard summary explains the report.",
                "card_tldr_compact": "A compact report-card summary.",
            },
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "rising",
                "evidence_density": "balanced",
                "domain_layer": "grid",
                "selection_reason": "The report presents a sustained trend.",
            },
            "insights_final": [
                {"text": "Channel efficiency improved."},
                {"text": "Investment shifted."},
            ],
        },
        evidence_packs={"doc_map": {"title": source.payload.title}},
    )
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        write_report_card_manifest=lambda req, ctx: (
            writes.append(req)
            or SimpleNamespace(manifest_path="report-card-manifest.json")
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert len(writes) == 1
    assert writes[0].manifest.published_date == ""
    assert outcome.status == "error"
    assert outcome.error == "publish_readiness_failed"


def test_render_only_regenerates_card_manifest_when_it_is_missing(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []
    written_manifests = []

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: (
            generated_covers.append(req)
            or [
                SimpleNamespace(
                    status="generated",
                    assets=_cover_assets(runtime),
                    error=None,
                )
            ]
        ),
        write_report_card_manifest=lambda req, ctx: (
            written_manifests.append(req)
            or SimpleNamespace(
                manifest_path=str(Path(req.output_dir) / "report-card-manifest.json")
            )
        ),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
        reuse_report_card_assets=True,
    )

    assert len(generated_covers) == 1
    assert len(written_manifests) == 1
    assert outcome.report_card_manifest_path.endswith("report-card-manifest.json")


def test_render_normalizes_retained_cover_period_before_card_generation(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    generated_covers = []

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    def _metadata(req, ctx):
        metadata = _deps().get_report_metadata(req, ctx)
        return replace(
            metadata,
            time_period=(
                "2025 (primary coverage) with outlook into 2026 and beyond; "
                "return a valid JSON object with no text after it. "
                "The period field must contain only a compact normalized label."
            ),
        )

    deps = _deps(
        render_report=_render_report,
        get_report_metadata=_metadata,
        generate_cover_images=lambda req, ctx: (
            generated_covers.append(req)
            or [
                SimpleNamespace(
                    status="generated",
                    assets=_cover_assets(runtime),
                    error=None,
                )
            ]
        ),
    )

    render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert generated_covers[0].reports[0].time_period == "2025, 2026"


def test_render_report_output_does_not_write_manifest_after_cover_error(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title="DB Title",
                status="error",
                assets=None,
                error="cover failed",
            )
        ],
        write_report_card_manifest=lambda req, ctx: writes.append(req),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert writes == []
    assert outcome.status == "error"
    assert outcome.error == "cover_asset_set_incomplete: cover failed"
    assert outcome.report_card_manifest_path is None


def test_render_report_output_fails_closed_for_invalid_card_content(tmp_path):
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload={
            **_analysis(runtime, source, selection).artifacts_payload,
            "summary": {
                "tldr": "A complete standard summary explains the report finding.",
                "card_tldr_compact": "This summary is incomplete",
            },
        },
    )
    writes = []
    html_path = Path(tmp_path / "out" / "report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    def _render_report(req, ctx):
        del req, ctx
        html_path.write_text("<html></html>", encoding="utf-8")
        return SimpleNamespace(schema_version="1.0", html_path=str(html_path))

    deps = _deps(
        render_report=_render_report,
        generate_cover_images=lambda req, ctx: [
            SimpleNamespace(
                schema_version="2.0",
                file_id=runtime.file.file_id,
                title="DB Title",
                status="generated",
                assets=_cover_assets(runtime),
                error=None,
            )
        ],
        write_report_card_manifest=lambda req, ctx: writes.append(req),
    )

    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        deps,
        preview_resp=render_preview_asset(runtime, source, deps),
    )

    assert writes == []
    assert outcome.status == "error"
    assert outcome.error.startswith("card_tldr_compact_invalid:")
    assert outcome.report_card_manifest_path is None
