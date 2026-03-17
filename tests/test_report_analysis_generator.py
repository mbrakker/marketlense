from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.context_category_fit import (
    ContextCategoryFitResponse,
    ReportCategoryContext,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.regeneration import ArtifactRegenerationResponse
from src.contracts.report_generation import (
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.report_analysis_generator import (
    VectorStoreIndexingState,
)
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.orchestrators.report_analysis_orchestrator import run_report_analysis
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


def _selection(
    runtime: ReportRuntimeState, source: ReportSourceState
) -> ReportSelectionState:
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
        build_report_category_context=lambda req, ctx: ReportCategoryContext(
            schema_version="1.0",
            report_id="file-1",
            title="Base Title",
            publisher="",
            region="US",
            time_period="2026",
            overview="Context overview",
            methods=[],
            key_findings=[],
            limitations=[],
            sections=[],
        ),
        fit_report_categories_from_context=lambda req, ctx: ContextCategoryFitResponse(
            schema_version="1.0",
            report_id="file-1",
            categories=["cat"],
            category_labels=["Category"],
            fits=[],
            request_id="req-1",
            model="gpt-5-mini",
            raw_response="{}",
        ),
        vector_store_update_metadata=lambda req, ctx: None,
    )
    return replace(seeded, **overrides)


def _orchestrator_events(caplog) -> list[dict]:
    parsed: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.report_analysis_orchestrator":
            parsed.append(payload)
    return parsed


def test_complete_report_analysis_falls_back_when_validation_raises(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    stored: list[str] = []
    regeneration_requests = []
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "summary",
                "executive_summary": "Summary",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("boom")
        ),
        regenerate_artifacts=lambda request: (
            regeneration_requests.append(request)
            or ArtifactRegenerationResponse(
                updated_artifacts=request.current_artifacts,
                regenerated_sections=[
                    "summary",
                    "insights_candidates",
                    "insights_final",
                    "quotes",
                    "expert_comment",
                    "linkedin_post",
                ],
                prompt_namespaces=[],
                artifacts_path=str(tmp_path / "out" / "artifacts.json"),
                artifacts_snapshot_path=str(
                    tmp_path / "out" / "artifacts_regen_attempt_1.json"
                ),
            )
        ),
        analysis_store_pack=lambda req, ctx: (
            stored.append(req.pack_name)
            or SimpleNamespace(
                output_path=str(Path(req.output_dir) / req.pack_name / "payload.json")
            )
        ),
    )

    state = run_report_analysis(
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
    assert len(regeneration_requests) == 1
    assert regeneration_requests[0].plan.mode == "broad"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.attempt_count == 1
    assert state.regeneration_loop_state.final_status == "skipped"
    assert "validation" in state.evidence_paths
    assert "validation_regen_attempt_1" in state.evidence_paths
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
                context={
                    "sections_count": 0,
                    "not_found_reason": "model_returned_no_json",
                },
            )
        )
    )

    with pytest.raises(AppError) as exc_info:
        run_report_analysis(
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


def test_run_report_analysis_uses_context_fit_categories_not_taxonomy_tags(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    stored: list[str] = []
    metadata_updates = []

    deps = _deps(
        extract_taxonomy=lambda req, ctx: TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["metadata_only_tag"],
            region="US",
            time_period="2026",
        ),
        build_report_category_context=lambda req, ctx: ReportCategoryContext(
            schema_version="1.0",
            report_id=req.report.file_id,
            title=req.report.title,
            publisher=req.report.publisher or "",
            region=req.report.region or "",
            time_period=req.report.time_period or "",
            overview="Report context overview",
            methods=["Survey"],
            key_findings=["AI is reshaping retail execution."],
            limitations=[],
            sections=[],
        ),
        fit_report_categories_from_context=lambda req, ctx: ContextCategoryFitResponse(
            schema_version="1.0",
            report_id=req.context.report_id,
            categories=["agentic_commerce", "ai_automation"],
            category_labels=["Agentic Commerce", "AI & Automation"],
            fits=[],
            request_id="req-ctx",
            model="gpt-5-mini",
            raw_response="{}",
        ),
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
                "summary": "A report about AI-led shopping journeys.",
                "sections": [],
            },
            "scope": {"scope": "Retail commerce strategy"},
            "methods": {"methods": ["Survey"]},
            "findings": {"findings": [{"id": "f1", "text": "AI is reshaping retail execution."}]},
            "limitations": {"limitations": []},
        },
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "summary",
                "executive_summary": "Summary",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
        analysis_store_pack=lambda req, ctx: (
            stored.append(req.pack_name)
            or SimpleNamespace(
                output_path=str(Path(req.output_dir) / req.pack_name / "payload.json")
            )
        ),
        vector_store_update_metadata=lambda req, ctx: metadata_updates.append(req),
    )

    state = run_report_analysis(
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

    assert state.payload.taxonomy == ["metadata_only_tag"]
    assert state.payload.categories == ["agentic_commerce", "ai_automation"]
    assert state.category_labels == ["Agentic Commerce", "AI & Automation"]
    assert {"report_context", "context_category_fit"}.issubset(set(stored))
    assert metadata_updates[0].metadata.taxonomy == ["metadata_only_tag"]
    assert metadata_updates[0].metadata.categories == [
        "agentic_commerce",
        "ai_automation",
    ]


def test_run_report_analysis_regenerates_failed_section_until_pass(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(
            f"{pack_name}:{req.artifacts.get('summary', {}).get('tldr', '')}"
        )
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[grounding] Unsupported summary claim",
                        severity="error",
                        affected_section="executive_summary",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts={
                "schema_version": "1.0",
                "toc_topics": ["Topic"],
                "summary": {
                    "tldr": "repaired",
                    "executive_summary": "Grounded summary",
                    "claim_evidence_map": [],
                },
                "insights_candidates": [],
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
                "source_status": {
                    "schema_version": "1.0",
                    "not_available": False,
                    "reason": "",
                },
            },
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
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

    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.attempt_count == 1
    assert state.regeneration_loop_state.final_status == "pass"
    assert state.regeneration_attempts[0].regenerated_sections == ["summary"]
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "summary"
    assert "artifacts_regen_attempt_1" in state.evidence_paths
    assert "validation_regen_attempt_1" in state.evidence_paths

    events = _orchestrator_events(caplog)
    regen_events = [
        event
        for event in events
        if str(event.get("event", "")).startswith("validation_regen_")
    ]
    assert_logs_have_required_fields(regen_events)
    assert {event["event"] for event in regen_events} >= {
        "validation_regen_loop_start",
        "validation_regen_plan_built",
        "validation_regen_attempt_start",
        "validation_regen_attempt_complete",
        "validation_regen_pass",
    }


def test_run_report_analysis_maps_topic_section_failures_to_topics_regeneration(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    validation_calls: list[str] = []
    regeneration_requests = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del settings, ctx, report_name, md5
        validation_calls.append(pack_name)
        if len(validation_calls) == 1:
            return ValidationReport(
                schema_version="1.1",
                status="fail",
                issues=[
                    ValidationIssue(
                        schema_version="1.0",
                        message="[toc_integrity] TOC coverage is missing section 'Media brands'.",
                        severity="error",
                        affected_section="toc_entries:section-1",
                        rule_id="toc_integrity",
                        repair_target="topics",
                        entity_id="section-1",
                    )
                ],
                severity="error",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        regeneration_requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=[
                "toc_entries",
                "toc_topics",
                "toc_topics_expanded",
            ],
            prompt_namespaces=[],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
                "sections": [
                    {
                        "id": "section-1",
                        "title": "Media brands",
                        "summary": "Media brand ad equity section.",
                        "key_points": [],
                        "pages": [17],
                    }
                ],
            }
        },
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_entries": [
                {
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "display_title": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "pages": [25],
                    "order": 1,
                }
            ],
            "toc_topics": ["Media brand ad equity"],
            "toc_topics_expanded": [
                {
                    "topic": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "pages": [25],
                }
            ],
            "summary": {
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
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

    assert state.validation_report is not None
    assert state.validation_report.status == "pass"
    assert len(regeneration_requests) == 1
    assert regeneration_requests[0].plan.mode == "targeted"
    assert regeneration_requests[0].plan.targets[0].target_section == "topics"
    assert regeneration_requests[0].plan.targets[0].regenerate_steps == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
    assert state.regeneration_attempts[0].regenerated_sections == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]


def test_run_report_analysis_stops_after_regeneration_max_attempts(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=3
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    attempts = []

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[metrics] Unsupported insight value",
                    severity="error",
                    affected_section="insights:insight-1",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        attempts.append(request.attempt_index)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=["insights_candidates", "insights_final"],
            prompt_namespaces=[
                "report_vs/artifacts/regenerate/insights_candidates",
                "report_vs/artifacts/regenerate/insights_final",
            ],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path
                / "out"
                / f"artifacts_regen_attempt_{request.attempt_index}.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            },
            "insights_candidates": [
                {
                    "id": "insight-1",
                    "text": "x",
                    "evidence_id": "e1",
                    "evidence": "",
                    "metric": {},
                    "pages": [],
                    "score": 0.0,
                }
            ],
            "insights_final": [
                {
                    "id": "insight-1",
                    "text": "x",
                    "evidence_id": "e1",
                    "evidence": "",
                    "metric": {},
                    "pages": [],
                }
            ],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
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

    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert attempts == [1, 2, 3]
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.max_reached is True
    assert state.regeneration_loop_state.attempt_count == 3


def test_run_report_analysis_uses_one_broad_retry_for_unmappable_failures(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    requests = []
    validation_calls = {"count": 0}

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        validation_calls["count"] += 1
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[semantic] Global semantic mismatch",
                    severity="error",
                    affected_section="semantic",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    def _regenerate(request):
        requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=request.current_artifacts,
            regenerated_sections=[
                "summary",
                "insights_candidates",
                "insights_final",
                "quotes",
                "expert_comment",
                "linkedin_post",
            ],
            prompt_namespaces=[],
            artifacts_path=str(tmp_path / "out" / "artifacts.json"),
            artifacts_snapshot_path=str(
                tmp_path / "out" / "artifacts_regen_attempt_1.json"
            ),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=_run_validation,
        regenerate_artifacts=_regenerate,
    )

    state = run_report_analysis(
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

    assert validation_calls["count"] == 2
    assert len(requests) == 1
    assert requests[0].plan.mode == "broad"
    assert [target.target_section for target in requests[0].plan.targets] == [
        "summary",
        "insights_bundle",
        "quotes",
        "expert_comment",
        "linkedin_post",
    ]
    assert state.validation_report is not None
    assert state.validation_report.status == "fail"
    assert state.regeneration_loop_state is not None
    assert state.regeneration_loop_state.final_status == "skipped"


def test_run_report_analysis_snapshot_preserves_internal_payload_metadata(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    source.payload._text_density = 100.0
    source.payload._text_pages_sampled = 3
    source.payload._text_char_count = 100
    source.payload._text_not_available = False
    selection = _selection(runtime, source)
    stored_payloads: dict[str, dict] = {}

    def _analysis_pack_path(req, ctx):
        del ctx
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    def _analysis_store_pack(req, ctx):
        del ctx
        stored_payloads[req.pack_name] = req.payload
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
            },
            "findings": {"schema_version": "1.0", "findings": []},
        },
        generate_artifacts=lambda **kwargs: {
            "schema_version": "1.0",
            "toc_topics": ["Topic"],
            "summary": {
                "tldr": "summary",
                "executive_summary": "Summary",
                "claim_evidence_map": [],
            },
            "insights_candidates": [],
            "insights_final": [],
            "quotes_final": [],
            "expert_comment": "",
            "linkedin_post": "",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
        analysis_pack_path=_analysis_pack_path,
        analysis_store_pack=_analysis_store_pack,
    )

    state = run_report_analysis(
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

    snapshot = stored_payloads["analysis_vector_store"]
    assert state.normalized_payload._vector_store_id == "vs_1"
    assert state.normalized_payload._text_density == 100.0
    assert state.normalized_payload._text_pages_sampled == 3
    assert state.normalized_payload._text_char_count == 100
    assert snapshot["_vector_store_id"] == "vs_1"
    assert snapshot["_text_density"] == 100.0
    assert snapshot["_text_pages_sampled"] == 3
    assert snapshot["_text_char_count"] == 100
    assert snapshot["_evidence_packs"]["doc_map"].endswith("doc_map.json")
    assert snapshot["_evidence_packs"]["validation"].endswith("validation.json")
