from __future__ import annotations

from src.contracts.tracing import TraceBuildRequest
from src.generators.trace_generator import build_trace_summary


def test_build_trace_summary_reconstructs_nested_spans() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "root",
            "span_id": "span-root",
            "parent_span_id": "",
            "span_name": "root",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "m.root",
            "event": "root_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "child",
            "span_id": "span-child",
            "parent_span_id": "span-root",
            "span_name": "child",
            "span_depth": 1,
            "role": "service",
            "module": "m.child",
            "event": "child_start",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "child",
            "span_id": "span-child",
            "parent_span_id": "span-root",
            "span_name": "child",
            "span_depth": 1,
            "role": "service",
            "module": "m.child",
            "event": "child_complete",
            "timestamp_utc": "2026-05-01T20:00:03+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    assert result.event_count == 3
    assert result.span_count == 2
    assert result.root_span_ids == ["span-root"]
    root = next(span for span in result.spans if span.span_id == "span-root")
    child = next(span for span in result.spans if span.span_id == "span-child")
    assert root.child_span_ids == ["span-child"]
    assert child.parent_span_id == "span-root"
    assert child.duration_ms == 2000.0


def test_build_trace_summary_filters_by_run_and_task() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "keep",
            "span_id": "span-keep",
            "parent_span_id": "",
            "span_name": "keep",
            "span_depth": 0,
            "role": "generator",
            "module": "m.keep",
            "event": "kept",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-2",
            "trace_id": "trace-2",
            "task_id": "drop",
            "span_id": "span-drop",
            "parent_span_id": "",
            "span_name": "drop",
            "span_depth": 0,
            "role": "generator",
            "module": "m.drop",
            "event": "dropped",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(
            schema_version="1.0",
            events=events,
            run_id="run-1",
            task_id="keep",
        )
    )

    assert result.event_count == 1
    assert result.span_count == 1
    assert result.spans[0].span_id == "span-keep"


def test_build_trace_summary_detects_missing_required_fields_and_orphan_spans() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "root",
            "span_id": "span-root",
            "parent_span_id": "",
            "span_name": "root",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.report_generation_orchestrator",
            "event": "report_generate_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "broken",
            "span_id": "span-broken",
            "parent_span_id": "span-missing",
            "span_name": "broken",
            "span_depth": 1,
            "role": "service",
            "event": "read_text_complete",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    assert result.valid is False
    assert result.diagnostic_count == 2
    assert [
        (diagnostic.code, diagnostic.field_name, diagnostic.span_id)
        for diagnostic in result.diagnostics
    ] == [
        ("trace_event_missing_required_field", "module", "span-broken"),
        ("trace_orphan_span", "parent_span_id", "span-broken"),
    ]


def test_build_trace_summary_reports_workflow_boundary_coverage() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report",
            "span_id": "span-report-orchestrator",
            "parent_span_id": "",
            "span_name": "report",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.report_generation_orchestrator",
            "event": "report_generate_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report:render",
            "span_id": "span-report-generator",
            "parent_span_id": "span-report-orchestrator",
            "span_name": "report render",
            "span_depth": 1,
            "role": "generator",
            "module": "src.generators.report_render_generator",
            "event": "report_render_complete",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report:render:file",
            "span_id": "span-report-service",
            "parent_span_id": "span-report-generator",
            "span_name": "report file write",
            "span_depth": 2,
            "role": "service",
            "module": "src.services.file_service",
            "event": "write_text_complete",
            "timestamp_utc": "2026-05-01T20:00:02+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "publish",
            "span_id": "span-publish-orchestrator",
            "parent_span_id": "",
            "span_name": "publish",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.publish_orchestrator",
            "event": "publish_start",
            "timestamp_utc": "2026-05-01T20:01:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "publish:payload",
            "span_id": "span-publish-generator",
            "parent_span_id": "span-publish-orchestrator",
            "span_name": "publish payload",
            "span_depth": 1,
            "role": "generator",
            "module": "src.generators.publish_generator",
            "event": "publish_payload_complete",
            "timestamp_utc": "2026-05-01T20:01:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "publish:wordpress",
            "span_id": "span-publish-service",
            "parent_span_id": "span-publish-orchestrator",
            "span_name": "publish wordpress",
            "span_depth": 1,
            "role": "service",
            "module": "src.services.wordpress_service",
            "event": "wordpress_post_complete",
            "timestamp_utc": "2026-05-01T20:01:02+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "cross",
            "span_id": "span-cross-orchestrator",
            "parent_span_id": "",
            "span_name": "cross report",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.cross_report_analysis_orchestrator",
            "event": "cross_report_analysis_start",
            "timestamp_utc": "2026-05-01T20:02:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "cross:analysis",
            "span_id": "span-cross-generator",
            "parent_span_id": "span-cross-orchestrator",
            "span_name": "cross analysis",
            "span_depth": 1,
            "role": "generator",
            "module": "src.generators.cross_report_analysis_generator",
            "event": "cross_report_analysis_generated",
            "timestamp_utc": "2026-05-01T20:02:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "cross:store",
            "span_id": "span-cross-service",
            "parent_span_id": "span-cross-orchestrator",
            "span_name": "cross report store",
            "span_depth": 1,
            "role": "service",
            "module": "src.services.analytics_store_service",
            "event": "read_cross_report_data_complete",
            "timestamp_utc": "2026-05-01T20:02:02+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    stages_by_name = {stage.workflow_name: stage for stage in result.workflow_stages}
    assert sorted(stages_by_name) == ["cross_report", "publish", "report"]
    assert stages_by_name["report"].roles_seen == [
        "generator",
        "orchestrator",
        "service",
    ]
    assert stages_by_name["publish"].complete is True
    assert stages_by_name["cross_report"].complete is True


def test_build_trace_summary_uses_all_events_in_span_for_workflow_coverage() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report",
            "span_id": "span-report",
            "parent_span_id": "",
            "span_name": "report",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.report_generation_orchestrator",
            "event": "report_generate_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report",
            "span_id": "span-report",
            "parent_span_id": "",
            "span_name": "report",
            "span_depth": 0,
            "role": "generator",
            "module": "src.generators.normalize_generator",
            "event": "normalize_report_complete",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report:store",
            "span_id": "span-service",
            "parent_span_id": "span-report",
            "span_name": "report store",
            "span_depth": 1,
            "role": "service",
            "module": "src.services.report_store_service",
            "event": "report_metadata_upsert_complete",
            "timestamp_utc": "2026-05-01T20:00:02+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    report_stage = next(
        stage for stage in result.workflow_stages if stage.workflow_name == "report"
    )
    assert report_stage.roles_seen == ["generator", "orchestrator", "service"]
    assert report_stage.complete is True


def test_build_trace_summary_does_not_classify_publisher_metadata_as_publish() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report",
            "span_id": "span-report",
            "parent_span_id": "",
            "span_name": "report",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "src.orchestrators.report_generation_orchestrator",
            "event": "report_generate_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {"publisher": "Example"},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report:store",
            "span_id": "span-service",
            "parent_span_id": "span-report",
            "span_name": "report metadata",
            "span_depth": 1,
            "role": "service",
            "module": "src.services.report_store_service",
            "event": "report_metadata_upsert_complete",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {"publisher": "Example"},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "report:publisher",
            "span_id": "span-publisher",
            "parent_span_id": "span-report",
            "span_name": "publisher profile",
            "span_depth": 1,
            "role": "generator",
            "module": "src.generators.publisher_profiles_generator",
            "event": "publisher_profile_complete",
            "timestamp_utc": "2026-05-01T20:00:02+00:00",
            "fields": {"publisher": "Example"},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    assert {stage.workflow_name for stage in result.workflow_stages} == {"report"}
