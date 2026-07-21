# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
        and event.get("fields", {}).get("poll_interval_s") == 0.5
        and event.get("fields", {}).get("poll_schedule_s") == [0.5, 1.0, 2.0, 5.0]
        for event in events
    )


def test_report_payload_ready_logs_only_bounded_summary(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_analysis_orchestrator")
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    source_paragraph = "Known source paragraph that must not enter standard logs. " * 8
    generated_linkedin = "Generated LinkedIn paragraph that must not enter logs. " * 8
    source.payload.commentary = source_paragraph
    selection = _selection(runtime, source)
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _artifacts(
            linkedin_post=generated_linkedin
        ),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
    )

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

    events = _orchestrator_events(caplog)
    assert_logs_have_required_fields(events)
    ready = next(event for event in events if event["event"] == "report_payload_ready")
    serialized = json.dumps(ready, ensure_ascii=True)
    assert source_paragraph not in serialized
    assert generated_linkedin not in serialized
    assert set(ready["fields"]) == {
        "artifact_family_statuses",
        "category_count",
        "evidence_pack_count",
        "evidence_pack_names",
        "file_id",
        "output_schema_version",
        "retained_snapshot_path",
        "validation_issue_count",
        "validation_status",
    }
    assert ready["fields"]["retained_snapshot_path"].endswith(
        "analysis_vector_store.json"
    )
    assert len(serialized.encode("utf-8")) <= MAX_LOG_EVENT_BYTES


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
    assert exc_info.value.context["poll_schedule_s"] == [0.5, 1.0, 2.0, 5.0]


def test_start_vector_store_indexing_reuses_vector_store_by_md5(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
):
    caplog.set_level(logging.INFO, logger="market_lense.report_generator")
    runtime = replace(_runtime(tmp_path), md5="same-md5")
    source = _source(runtime)
    lookup_requests = []
    status_requests = []

    deps = _deps(
        state_get=lambda req, ctx: None,
        state_get_by_md5=lambda req, ctx: (
            lookup_requests.append(req)
            or SimpleNamespace(
                schema_version="1.0",
                file_id="previous-file",
                md5=req.md5,
                processed_at=1,
                openai_file_id="openai-file-1",
                vector_store_id="vs-md5",
                vector_store_status="completed",
                indexed_at_utc="2026-01-01T00:00:00Z",
                last_error=None,
            )
        ),
        vector_store_get_status=lambda req, ctx: (
            status_requests.append(req)
            or SimpleNamespace(
                status="completed",
                indexed_at_utc="2026-01-01T00:00:00Z",
                last_error=None,
            )
        ),
        vector_store_create=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("md5 reuse must not create a new vector store")
        ),
        vector_store_upload_file=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("md5 reuse must not upload a duplicate file")
        ),
        vector_store_attach_file=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("md5 reuse must not attach a duplicate file")
        ),
    )

    state = start_vector_store_indexing(runtime, source, deps)

    assert state.vector_store_id == "vs-md5"
    assert state.openai_file_id == "openai-file-1"
    assert state.vector_store_status == "completed"
    assert [request.md5 for request in lookup_requests] == ["same-md5"]
    assert [request.vector_store_id for request in status_requests] == ["vs-md5"]
    events = []
    for record in caplog.records:
        try:
            events.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue
    assert_logs_have_required_fields(events)
    assert any(
        event.get("event") == "vector_store_reuse"
        and event.get("fields", {}).get("reuse_scope") == "md5"
        and event.get("fields", {}).get("source_file_id") == "previous-file"
        for event in events
    )


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

    assert exc_info.value.code == "artifact_step_failed"
    assert exc_info.value.retryable is True
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
                "semantic_rule_status": "not_evaluated",
                "supported_topic_rules": [],
                "rejected_topic_rules": [],
                "remediation_signal": "",
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


__all__ = [
    "test_run_report_analysis_polls_vector_store_status_until_ready",
    "test_run_report_analysis_surfaces_vector_store_timeout",
    "test_start_vector_store_indexing_reuses_vector_store_by_md5",
    "test_artifact_render_task_contract_round_trip",
    "test_run_report_analysis_schedules_artifact_batches_with_orchestrator_budget",
    "test_run_report_analysis_logs_artifact_scheduler_failure_propagation",
    "test_run_report_analysis_falls_back_when_validation_raises",
    "test_run_report_analysis_surfaces_doc_map_empty",
    "test_run_report_analysis_uses_context_fit_categories_not_taxonomy_tags",
    "test_run_report_analysis_returns_complete_report_payload_contract",
    "test_run_report_analysis_fails_on_incomplete_report_payload_contract",
]
