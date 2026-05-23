from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.context_category_fit import (
    CategoryFitCandidate,
    ContextCategoryFitResponse,
    ReportCategoryContext,
)
from src.contracts.artifact_generation import ArtifactRenderTask
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
from src.generators.report_generation_dependencies import (
    ReportAnalysisDependencies,
)
from src.generators.report_generation_shared import derive_title, report_slug
from src.orchestrators import retry_orchestrator as retry_orch
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


def _artifacts(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "summary",
            "executive_summary": "Summary",
            "claim_evidence_map": [],
        },
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Candidate 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
                "score": 0.9,
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Insight 1",
                "evidence_id": "f1",
                "evidence": "Evidence 1",
                "metric": {},
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Insight 2",
                "evidence_id": "f2",
                "evidence": "Evidence 2",
                "metric": {},
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Insight 3",
                "evidence_id": "f3",
                "evidence": "Evidence 3",
                "metric": {},
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Insight 4",
                "evidence_id": "f4",
                "evidence": "Evidence 4",
                "metric": {},
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Insight 5",
                "evidence_id": "f5",
                "evidence": "Evidence 5",
                "metric": {},
                "pages": [5],
            },
        ],
        "quotes_final": [
            {
                "text": "Quote",
                "speaker": "Author",
                "citation": "p. 1",
                "page": 1,
                "evidence_id": "q1",
            }
        ],
        "expert_comment": "Expert comment",
        "linkedin_post": "LinkedIn post",
        "source_status": {
            "schema_version": "1.0",
            "not_available": False,
            "reason": "",
        },
    }
    payload.update(overrides)
    return payload


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


def _fit_response(
    *,
    report_id: str = "file-1",
    categories: list[str] | None = None,
    category_labels: list[str] | None = None,
) -> ContextCategoryFitResponse:
    resolved_categories = list(categories or ["cat"])
    resolved_labels = list(category_labels or ["Category"])
    return ContextCategoryFitResponse(
        schema_version="1.0",
        report_id=report_id,
        categories=resolved_categories,
        category_labels=resolved_labels,
        fits=[
            CategoryFitCandidate(
                category_id=resolved_categories[0],
                label=resolved_labels[0],
                fit_score=0.9,
                decision="primary",
                why_fit="The report strongly aligns with this category.",
                why_not_fit="",
                evidence_sections=["Overview"],
            )
        ],
        request_id="req-1",
        model="gpt-5-mini",
        raw_response="{}",
    )


def _deps(
    *,
    figure_caption_overrides: dict | None = None,
    **overrides,
) -> ReportAnalysisDependencies:
    base = ReportAnalysisDependencies.default()
    figure_caption = replace(
        base.figure_caption,
        **(figure_caption_overrides or {}),
    )
    seeded = replace(
        replace(base, figure_caption=figure_caption),
        vector_store_get_status=lambda req, ctx: SimpleNamespace(
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
        fit_report_categories_from_context=lambda req, ctx: _fit_response(),
        vector_store_update_metadata=lambda req, ctx: None,
    )
    return replace(seeded, **overrides)


def test_run_report_analysis_polls_vector_store_status_until_ready(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, openai_timeout_seconds=10.0),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    statuses = iter(
        [
            SimpleNamespace(
                status="in_progress",
                indexed_at_utc=None,
                last_error=None,
            ),
            SimpleNamespace(
                status="completed",
                indexed_at_utc="2026-01-01T00:00:00Z",
                last_error=None,
            ),
        ]
    )
    status_calls: list[str] = []

    deps = _deps(
        vector_store_get_status=lambda req, ctx: (
            status_calls.append(req.vector_store_id) or next(statuses)
        ),
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
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

    assert state.vector_store_status == "completed"
    assert status_calls == ["vs_1", "vs_1"]
    events = _orchestrator_events(caplog)
    assert_logs_have_required_fields(events)
    assert any(
        event.get("event") == "vector_store_wait_retry"
        and event.get("fields", {}).get("status") == "in_progress"
        and event.get("fields", {}).get("poll_interval_s") == 5
        for event in events
    )


def test_run_report_analysis_surfaces_vector_store_timeout(
    tmp_path,
    external_boundary_mocks_only,
    assert_app_error,
):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, openai_timeout_seconds=5.0),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    external_boundary_mocks_only.setattr(
        retry_orch.time, "sleep", lambda _seconds: None
    )

    deps = _deps(
        vector_store_get_status=lambda req, ctx: SimpleNamespace(
            status="in_progress",
            indexed_at_utc=None,
            last_error=None,
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
                vector_store_status="indexing",
                indexed_at_utc=None,
                last_error=None,
            ),
            deps,
        )

    assert_app_error(
        exc_info.value,
        code="vector_store_index_timeout",
        retryable=True,
        severity="error",
    )
    assert exc_info.value.context["last_status"] == "in_progress"


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


def test_artifact_render_task_contract_round_trip():
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    task = ArtifactRenderTask(
        schema_version="1.0",
        step_name="summary",
        namespace="report_vs/artifacts/summary",
        variables={"report_title": "Report"},
        ctx=ctx,
    )

    restored = ArtifactRenderTask(**task.__dict__)

    assert restored == task
    assert restored.variables["report_title"] == "Report"
    assert restored.ctx.task_id == "t"


def test_run_report_analysis_schedules_artifact_batches_with_orchestrator_budget(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings,
            artifact_parallel_workers=4,
            artifact_global_max_in_flight=2,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()
    batch_order: list[str] = []

    def _task(name: str, ctx: RunContext) -> ArtifactRenderTask:
        return ArtifactRenderTask(
            schema_version="1.0",
            step_name=name,
            namespace=f"report_vs/artifacts/{name}",
            variables={"step": name},
            ctx=ctx,
        )

    def _generate_artifacts(**kwargs):
        nonlocal in_flight, max_in_flight
        executor = kwargs["artifact_step_executor"]

        def _render(task: ArtifactRenderTask) -> dict:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            try:
                time.sleep(0.03)
                return {"step": task.step_name}
            finally:
                with lock:
                    in_flight -= 1

        batch_order.append("stage_one")
        stage_one = executor(
            [
                _task("summary", kwargs["ctx"]),
                _task("insights_candidates", kwargs["ctx"]),
                _task("quotes", kwargs["ctx"]),
            ],
            _render,
            kwargs["ctx"],
            "stage_one",
        )
        assert set(stage_one) == {"summary", "insights_candidates", "quotes"}

        batch_order.append("distribution")
        distribution = executor(
            [
                _task("expert_comment", kwargs["ctx"]),
                _task("linkedin_post", kwargs["ctx"]),
            ],
            _render,
            kwargs["ctx"],
            "distribution",
        )
        assert set(distribution) == {"expert_comment", "linkedin_post"}
        return _artifacts()

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=_generate_artifacts,
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
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

    assert state.artifacts_payload["summary"]["tldr"] == "summary"
    assert batch_order == ["stage_one", "distribution"]
    assert max_in_flight == 2
    events = _orchestrator_events(caplog)
    assert_logs_have_required_fields(events)
    schedule_events = [
        event for event in events if event.get("event") == "artifact_step_batch_start"
    ]
    assert [event["fields"]["batch_name"] for event in schedule_events] == [
        "stage_one",
        "distribution",
    ]
    assert schedule_events[0]["fields"]["max_workers"] == 2
    assert schedule_events[0]["fields"]["configured_parallel_workers"] == 4
    assert schedule_events[0]["fields"]["global_max_in_flight"] == 2
    assert schedule_events[1]["fields"]["max_workers"] == 2


def test_run_report_analysis_logs_artifact_scheduler_failure_propagation(
    tmp_path,
    caplog,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)

    def _generate_artifacts(**kwargs):
        executor = kwargs["artifact_step_executor"]

        def _render(task: ArtifactRenderTask) -> dict:
            if task.step_name == "quotes":
                raise AppError(
                    code="artifact_step_failed",
                    message="quotes failed",
                    retryable=True,
                    severity="error",
                    context={"step": task.step_name},
                )
            return {"step": task.step_name}

        executor(
            [
                ArtifactRenderTask(
                    schema_version="1.0",
                    step_name="summary",
                    namespace="report_vs/artifacts/summary",
                    variables={},
                    ctx=kwargs["ctx"],
                ),
                ArtifactRenderTask(
                    schema_version="1.0",
                    step_name="quotes",
                    namespace="report_vs/artifacts/quotes",
                    variables={},
                    ctx=kwargs["ctx"],
                ),
            ],
            _render,
            kwargs["ctx"],
            "stage_one",
        )
        raise AssertionError("artifact scheduler failure should propagate")

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=_generate_artifacts,
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
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

    assert state.artifacts_payload is None
    events = _orchestrator_events(caplog)
    assert any(
        event.get("event") == "artifact_step_failed"
        and event.get("fields", {}).get("step") == "quotes"
        and event.get("fields", {}).get("batch_name") == "stage_one"
        for event in events
    )
    assert any(
        event.get("event") == "artifacts_generation_failed"
        and "quotes failed" in event.get("fields", {}).get("error", "")
        for event in events
    )


def test_run_report_analysis_falls_back_when_validation_raises(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    stored: list[str] = []
    regeneration_requests = []
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
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


def test_run_report_analysis_surfaces_doc_map_empty(tmp_path, assert_app_error):
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
    stored_payloads: dict[str, dict] = {}
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
        fit_report_categories_from_context=lambda req, ctx: _fit_response(
            report_id=req.context.report_id,
            categories=["agentic_commerce", "ai_automation"],
            category_labels=["Agentic Commerce", "AI & Automation"],
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
            "findings": {
                "findings": [{"id": "f1", "text": "AI is reshaping retail execution."}]
            },
            "limitations": {"limitations": []},
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
        analysis_store_pack=lambda req, ctx: (
            stored.append(req.pack_name),
            stored_payloads.setdefault(req.pack_name, req.payload),
            SimpleNamespace(
                output_path=str(Path(req.output_dir) / req.pack_name / "payload.json")
            ),
        )[-1],
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
    assert stored_payloads["context_category_fit"] == {
        "schema_version": "1.0",
        "selected_category_ids": ["agentic_commerce", "ai_automation"],
        "category_fits": [
            {
                "category_id": "agentic_commerce",
                "label": "Agentic Commerce",
                "fit_score": 0.9,
                "decision": "primary",
                "why_fit": "The report strongly aligns with this category.",
                "why_not_fit": "",
                "evidence_sections": ["Overview"],
            }
        ],
    }
    assert metadata_updates[0].metadata.taxonomy == ["metadata_only_tag"]
    assert metadata_updates[0].metadata.categories == [
        "agentic_commerce",
        "ai_automation",
    ]


def test_run_report_analysis_returns_complete_report_payload_contract(
    tmp_path,
    assert_no_defaulted_required_fields,
):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
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

    assert_no_defaulted_required_fields(
        state.payload,
        sentinel_values={"Not available from text"},
    )
    assert_no_defaulted_required_fields(
        state.payload.quote, sentinel_values={"Unknown"}
    )
    assert_no_defaulted_required_fields(state.payload.figure)


def test_run_report_analysis_fails_on_incomplete_report_payload_contract(
    tmp_path,
    assert_app_error,
):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, figure_caption_enabled=False),
    )
    source = _source(runtime)
    source.payload.tldr = "Not available from text"
    source.payload.commentary = ""
    source.payload.insights = ["", "", "", "", ""]
    source.payload.quote.text = ""
    selection = _selection(runtime, source)
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
            "expert_comment": "Expert comment",
            "linkedin_post": "LinkedIn post",
            "source_status": {
                "schema_version": "1.0",
                "not_available": False,
                "reason": "",
            },
        },
        run_validation=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("validation should not run for incomplete payloads")
        ),
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
        code="report_payload_incomplete",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["stage"] == "pre_validation"
    assert "insights[0]" in exc_info.value.context["missing_fields"]
    assert "quote.text" in exc_info.value.context["missing_fields"]


def test_run_report_analysis_allows_abstained_quote_family(tmp_path):
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(_runtime(tmp_path).settings, figure_caption_enabled=False),
    )
    source = _source(runtime)
    source.payload.quote.text = ""
    selection = _selection(runtime, source)
    validation_calls = []
    artifacts = _artifacts(
        quotes_final=[],
        family_status={
            "quotes": {
                "schema_version": "1.0",
                "family": "quotes",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.65,
                "policy_action": "regenerate",
                "reason": "quotes_missing_verbatim_source",
            }
        },
    )
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=lambda *args, **kwargs: (
            validation_calls.append(args[0])
            or ValidationReport(
                schema_version="1.1",
                status="pass",
                issues=[],
                severity="pass",
                source_path=str(tmp_path / "out" / "validation.json"),
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
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    assert validation_calls
    assert state.payload.quote.text == ""
    assert state.artifacts_payload["family_status"]["quotes"]["status"] == "abstained"


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
            updated_artifacts=_artifacts(
                summary={
                    "tldr": "repaired",
                    "executive_summary": "Grounded summary",
                    "claim_evidence_map": [],
                }
            ),
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
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            }
        ),
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
        generate_artifacts=lambda **kwargs: _artifacts(
            toc_entries=[
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
            toc_topics=["Media brand ad equity"],
            toc_topics_expanded=[
                {
                    "topic": "Media brand ad equity",
                    "summary": "Wrong section summary",
                    "key_points": [],
                    "section_id": "section-2",
                    "section_title": "Sentiments on GenAI",
                    "pages": [25],
                }
            ],
            summary={
                "tldr": "broken",
                "executive_summary": "Broken summary",
                "claim_evidence_map": [],
            },
        ),
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
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            },
            insights_candidates=[
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
            insights_final=[
                {
                    "id": "insight-1",
                    "text": "x",
                    "evidence_id": "e1",
                    "evidence": "",
                    "metric": {},
                    "pages": [],
                },
                {
                    "id": "insight-2",
                    "text": "Insight 2",
                    "evidence_id": "e2",
                    "evidence": "Evidence 2",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "insight-3",
                    "text": "Insight 3",
                    "evidence_id": "e3",
                    "evidence": "Evidence 3",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "insight-4",
                    "text": "Insight 4",
                    "evidence_id": "e4",
                    "evidence": "Evidence 4",
                    "metric": {},
                    "pages": [4],
                },
                {
                    "id": "insight-5",
                    "text": "Insight 5",
                    "evidence_id": "e5",
                    "evidence": "Evidence 5",
                    "metric": {},
                    "pages": [5],
                },
            ],
        ),
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
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            }
        ),
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
        generate_artifacts=lambda **kwargs: _artifacts(),
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
