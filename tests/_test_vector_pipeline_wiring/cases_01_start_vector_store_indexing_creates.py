# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_start_vector_store_indexing_creates_without_wait_loop(tmp_path):
    settings = _ingest_settings(tmp_path)
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    file = DriveFile(
        schema_version="1.0",
        file_id="file_1",
        name="report.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls: list[str] = []

    deps = _analysis_dependencies(
        state_get=lambda req, ctx: None,
        vector_store_create=lambda req, ctx: (
            calls.append("create") or SimpleNamespace(vector_store_id="vs_123")
        ),
        vector_store_upload_file=lambda req, ctx: (
            calls.append("upload") or SimpleNamespace(openai_file_id="file_upload_1")
        ),
        vector_store_attach_file=lambda req, ctx: calls.append("attach") or None,
        vector_store_get_status=lambda req, ctx: (
            calls.append("status")
            or SimpleNamespace(
                status="completed",
                indexed_at_utc="2024-01-01T00:00:00Z",
                last_error=None,
            )
        ),
    )

    runtime = _runtime_state(
        file,
        settings,
        local_pdf_path="local.pdf",
        md5="md5",
        ctx=ctx,
    )
    state = rag.start_vector_store_indexing(runtime, None, deps)

    assert calls == ["create", "upload", "attach"]
    assert state.vector_store_id == "vs_123"
    assert state.openai_file_id == "file_upload_1"
    assert state.vector_store_status == "indexing"
    assert state.indexed_at_utc is None
    assert state.last_error is None


def test_ingest_orchestrator_records_vector_events(
    caplog,
    tmp_path,
    assert_logs_have_required_fields,
) -> None:
    settings = _ingest_settings(tmp_path)
    file = DriveFile(
        schema_version="1.0",
        file_id="file",
        name="name.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5="md5",
        html_path="out/name.html",
        status="processed",
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2024-01-01T00:00:00Z",
        openai_file_id="file_upload_1",
        evidence_packs={"doc_map": "path"},
        vector_store_last_error=None,
    )
    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        process_file=_make_ingest_process(
            generate_report=lambda current_file, cache_path, current_settings, md5, ctx: (
                outcome
            )
        ),
    )

    with caplog.at_level(logging.INFO, logger=orch.logger.name):
        results = orch.run_ingest(settings, limit=1, dependencies=deps)

    events = _decode_log_events(caplog, orch.logger.name)
    assert_logs_have_required_fields(events)
    assert results[0].vector_store_id == "vs_1"
    assert any(event.get("event") == "VECTOR_STORE_CREATED" for event in events)
    assert any(event.get("event") == "EVIDENCE_READY" for event in events)

    rec = state_get(
        StateGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=file.file_id,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    assert rec is not None
    assert rec.vector_store_id == "vs_1"
    assert rec.vector_store_status == "completed"
    assert rec.indexed_at_utc == "2024-01-01T00:00:00Z"
    assert rec.openai_file_id == "file_upload_1"


def test_ingest_orchestrator_records_doc_map_summary(tmp_path) -> None:
    settings = _ingest_settings(tmp_path)
    file = DriveFile(
        schema_version="1.0",
        file_id="file",
        name="name.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    summary = {"sections_count": 0, "not_found_reason": "model_returned_no_json"}
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5="md5",
        html_path=None,
        status="error",
        error="doc_map_empty:no_content",
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2024-01-01T00:00:00Z",
        openai_file_id="file_upload_1",
        evidence_packs=None,
        vector_store_last_error=None,
        doc_map_summary=summary,
    )
    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        process_file=_make_ingest_process(
            generate_report=lambda current_file, cache_path, current_settings, md5, ctx: (
                outcome
            )
        ),
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert results[0].status == "error"
    rec = state_get(
        StateGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=file.file_id,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    assert rec is not None
    assert rec.doc_map_summary == summary


def test_generate_report_vector_store_with_validation(
    tmp_path,
    assert_no_defaulted_required_fields,
    caplog,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{**settings.__dict__, "openai_timeout_seconds": 3600.0}
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    validation_calls: list[str] = []
    analysis_store: list[tuple[str, object]] = []
    metadata_upserts = []
    vector_calls: list[tuple[str, dict[str, object]]] = []
    execution_trace: list[str] = []
    taxonomy_started = threading.Event()
    evidence_started = threading.Event()
    overlap_flags = {
        "taxonomy_saw_evidence": False,
        "evidence_saw_taxonomy": False,
    }
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )

    def _create_vector_store(req, ctx):
        execution_trace.append("vector_create")
        vector_calls.append(
            (
                "create",
                {
                    "name": req.name,
                    "report_id": req.metadata.report_id,
                    "report_name": req.metadata.report_name,
                },
            )
        )
        return SimpleNamespace(vector_store_id="vs_new")

    def _upload_file(req, ctx):
        execution_trace.append("vector_upload")
        vector_calls.append(
            (
                "upload",
                {
                    "vector_store_id": req.vector_store_id,
                    "file_path": req.file_path,
                },
            )
        )
        return SimpleNamespace(openai_file_id="file_upload")

    def _attach_file(req, ctx):
        execution_trace.append("vector_attach")
        vector_calls.append(
            (
                "attach",
                {
                    "vector_store_id": req.vector_store_id,
                    "openai_file_id": req.openai_file_id,
                },
            )
        )

    def _get_vector_store_status(req, ctx):
        execution_trace.append("vector_status")
        vector_calls.append(
            (
                "status",
                {
                    "vector_store_id": req.vector_store_id,
                },
            )
        )
        return SimpleNamespace(
            status="completed",
            indexed_at_utc="2024-01-01T00:00:00Z",
            last_error=None,
        )

    def _extract_best_figure(req, ctx):
        execution_trace.append("pdf_figure")
        return SimpleNamespace(image_path=None, caption=None)

    def _collect_candidates(req, ctx):
        execution_trace.append("pdf_candidates")
        assert req.parallel_workers == settings.report_worker_limit
        return SimpleNamespace(candidates=[])

    def _render_preview(req, ctx):
        execution_trace.append("pdf_preview")
        return SimpleNamespace(
            schema_version="1.1",
            image_path=str(tmp_path / "preview.png"),
            page_number=0,
        )

    def _extract_taxonomy(req, ctx):
        execution_trace.append("taxonomy_start")
        taxonomy_started.set()
        overlap_flags["taxonomy_saw_evidence"] = evidence_started.wait(1.0)
        return TaxonomyExtractResponse(
            schema_version="1.0",
            taxonomy=["tag"],
            region="US",
            time_period="2024",
        )

    def _store_pack(request, ctx):
        analysis_store.append((request.pack_name, request.payload))
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

    def _fake_evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        execution_trace.append("evidence_start")
        evidence_started.set()
        overlap_flags["evidence_saw_taxonomy"] = taxonomy_started.wait(1.0)
        assert settings.openai_timeout_seconds == 3600.0
        return {
            "doc_map": {
                "docMap": {
                    "title": "DocMap Title",
                    "publisher": "DocMap Publisher",
                    "sections": [{"title": "Overview"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _fake_artifacts(
        report_id,
        doc_map,
        evidence_packs,
        settings,
        vector_store_id=None,
        source_status=None,
        ctx=None,
        report_name=None,
        **kwargs,
    ):
        payload = _analysis_artifacts()
        _store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name="artifacts",
                payload=payload,
                report_slug=report_name,
            ),
            ctx,
        )
        return payload

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        validation_calls.append(req.report_id)
        slug = slugify(kwargs.get("report_name") or req.report_id)
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slug
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        assert req.data.get("_figure_section_enabled") is False
        assert req.data.get("_figure_gallery") in ([], None)
        assert req.data.get("_figure_top", "") == ""
        assert req.data.get("title") == "DB Title"
        assert req.data.get("publisher") == "DB Publisher"
        assert req.data.get("time_period") == "Q1-Q3 2026"
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        vector_store_create=_create_vector_store,
        vector_store_upload_file=_upload_file,
        vector_store_attach_file=_attach_file,
        vector_store_get_status=_get_vector_store_status,
        extract_best_figure=_extract_best_figure,
        collect_candidates=_collect_candidates,
        render_preview=_render_preview,
        extract_taxonomy=_extract_taxonomy,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, ctx: metadata_upserts.append(req),
        get_report_metadata=lambda req, ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file_vs",
            title="DB Title",
            created_at=1,
            updated_at=2,
            file_name="vector.pdf",
            publisher="DB Publisher",
            taxonomy=["tag"],
            categories=[],
            region="US",
            time_period="Q1-Q3 2026",
            source_url=None,
            html_path=None,
            md5="md5",
            page_count=1,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id="vs_new",
            evidence_pack_paths={},
        ),
    )

    projection_requests = []

    def _failing_projection(req):
        projection_requests.append(req)
        raise AppError(
            code="analytics_projection_test_failure",
            message="projection failed",
            retryable=False,
            severity="error",
        )

    with caplog.at_level(logging.ERROR, logger=rgo.logger.name):
        outcome = rgo.run_report_generation(
            file,
            str(pdf_path),
            settings,
            md5="md5",
            ctx=ctx,
            dependencies=deps,
            analytics_projection_fn=_failing_projection,
        )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "processed"
    assert projection_requests[0].rendered_html_path == outcome.html_path
    events = _decode_log_events(caplog, rgo.logger.name)
    assert any(
        event.get("event") == "analytics_projection_failed_nonblocking"
        and event.get("fields", {}).get("error_code")
        == "analytics_projection_test_failure"
        for event in events
    )
    assert outcome.vector_store_id == "vs_new"
    assert outcome.evidence_packs is not None
    assert "doc_map" in outcome.evidence_packs
    assert "validation" in outcome.evidence_packs
    assert outcome.html_path is not None
    assert Path(outcome.html_path).exists()
    assert metadata_upserts[0].title == "DocMap Title"
    assert metadata_upserts[0].publisher == "DocMap Publisher"
    assert validation_calls == ["file_vs"]
    assert overlap_flags["taxonomy_saw_evidence"] is True
    assert overlap_flags["evidence_saw_taxonomy"] is True
    assert execution_trace.index("pdf_figure") < execution_trace.index("vector_status")
    assert execution_trace.index("pdf_candidates") < execution_trace.index(
        "vector_status"
    )
    assert execution_trace.index("pdf_preview") < execution_trace.index("vector_status")
    assert vector_calls == [
        (
            "create",
            {
                "name": "file_vs",
                "report_id": "file_vs",
                "report_name": "vector.pdf",
            },
        ),
        (
            "upload",
            {
                "vector_store_id": "vs_new",
                "file_path": str(pdf_path),
            },
        ),
        (
            "attach",
            {
                "vector_store_id": "vs_new",
                "openai_file_id": "file_upload",
            },
        ),
        (
            "status",
            {
                "vector_store_id": "vs_new",
            },
        ),
    ]
    artifacts_entries = [
        payload for pack_name, payload in analysis_store if pack_name == "artifacts"
    ]
    assert len(artifacts_entries) == 1
    assert artifacts_entries[0]["summary"]["tldr"] == "Complete standard TLDR."
    assert len(artifacts_entries[0]["insights_final"]) == 5
    assert artifacts_entries[0]["quotes_final"][0]["text"] == "Quote"


def test_generate_report_adds_signal_artifact_pack_after_projection(tmp_path) -> None:
    settings = _ingest_settings(tmp_path)
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    file = DriveFile(
        schema_version="1.0",
        file_id="file_signal",
        name="signal.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-signal",
        task_id="task-signal",
        span_id="span-signal",
    )
    execution_trace: list[str] = []
    signal_requests = []

    def _store_pack(request, ctx):
        path = (
            Path(request.output_dir)
            / slugify(request.report_slug or request.report_id)
            / "report_analysis"
            / f"{request.pack_name}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request.payload), encoding="utf-8")
        return SimpleNamespace(output_path=str(path))

    def _fake_artifacts(
        report_id,
        doc_map,
        evidence_packs,
        settings,
        vector_store_id=None,
        source_status=None,
        ctx=None,
        report_name=None,
        **kwargs,
    ):
        payload = _analysis_artifacts()
        _store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name="artifacts",
                payload=payload,
                report_slug=report_name,
            ),
            ctx,
        )
        return payload

    def _fake_evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        return {
            "doc_map": {
                "docMap": {
                    "title": "Signal Report",
                    "publisher": "Signal Publisher",
                    "sections": [{"title": "Market movement"}],
                },
                "doc_id": "d",
            },
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slugify(kwargs.get("report_name") or req.report_id)
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, ctx):
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    def _projection(req):
        execution_trace.append("projection")
        return SimpleNamespace(rows_upserted=3)

    def _signal_extraction(request, ctx):
        execution_trace.append("signal_extraction")
        signal_requests.append(request)
        batch = SignalCandidateBatch(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            extraction_request_id=request.extraction_request_id,
            generated_at_utc="2026-06-02T00:00:00+00:00",
            candidates=[],
            groups=[],
        )
        stored = SignalCandidateStoreResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=request.db_path,
            extraction_request_id=request.extraction_request_id,
            candidate_count=0,
            group_count=0,
            stale_candidate_count=0,
            stale_group_count=0,
        )
        return SignalCandidateExtractionOutcome(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            extraction_request_id=request.extraction_request_id,
            status="stored",
            batch=batch,
            stored_response=stored,
            candidate_count=0,
            group_count=0,
            state_transitions=["started", "completed"],
        )

    deps = _base_vector_report_dependencies(
        tmp_path,
        generate_evidence_packs=_fake_evidence,
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        run_signal_candidate_extraction=_signal_extraction,
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
        analytics_projection_fn=_projection,
    )

    assert execution_trace == ["projection", "signal_extraction"]
    assert signal_requests
    signal_request = signal_requests[0]
    assert signal_request.projected_data_request.db_path == settings.reports_db
    assert signal_request.db_path == settings.signal_store_db
    assert signal_request.analysis_request.publisher_filters == ["Signal Publisher"]
    assert signal_request.analysis_request.max_source_reports == 1
    assert outcome.evidence_packs is not None
    signal_path = outcome.evidence_packs["signals"]
    assert Path(signal_path).exists()
    payload = json.loads(Path(signal_path).read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "signals"
    assert payload["source_report_id"] == "file_signal"
    assert payload["signal_store_db"] == settings.signal_store_db
    assert payload["candidate_count"] == 0


__all__ = [
    "test_start_vector_store_indexing_creates_without_wait_loop",
    "test_ingest_orchestrator_records_vector_events",
    "test_ingest_orchestrator_records_doc_map_summary",
    "test_generate_report_vector_store_with_validation",
    "test_generate_report_adds_signal_artifact_pack_after_projection",
]
