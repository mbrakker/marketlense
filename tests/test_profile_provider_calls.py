from __future__ import annotations

import json
import sqlite3

from scripts.quality.profile_provider_calls import aggregate_report_provider_calls


def test_profile_groups_one_report_and_keeps_legacy_rows_untimed(tmp_path) -> None:
    usage_db = tmp_path / "usage.sqlite"
    with sqlite3.connect(usage_db) as connection:
        connection.execute(
            """
            create table llm_usage_events (
                provider text,
                action text,
                request_id text,
                timestamp_utc text,
                model text,
                report_id text,
                input_tokens integer,
                cached_input_tokens integer,
                output_tokens integer,
                total_tokens integer,
                tool_calls integer,
                estimated_cost_usd real,
                prompt_namespace text,
                provider_call_status text,
                stage text,
                metadata_json text
            )
            """
        )
        connection.executemany(
            """
            insert into llm_usage_events values (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                (
                    "openai", "analyze", "req-1", "2026-10-06T00:00:00Z",
                    "gpt-5", "report-1", 100, 20, 30, 150, 1, 0.01,
                    "report/figure", "completed", "report_analysis",
                    json.dumps({
                        "reasoning_effort": "high",
                        "reasoning_tokens": 8,
                        "provider_operation": "responses.create",
                        "provider_elapsed_ms": 400.0,
                        "limiter_wait_ms": 20,
                        "in_flight_wait_ms": 15,
                        "rate_spacing_wait_ms": 5,
                        "file_search_call_count": 1,
                        "repair_attempt": 0,
                        "workflow": "report_generation",
                        "artifact_family": "figure",
                    }),
                ),
                (
                    "openai", "analyze", "req-2", "2026-10-06T00:00:01Z",
                    "gpt-5", "report-1", 200, 0, 40, 240, 0, 0.02,
                    "report/figure", "failed", "report_analysis",
                    json.dumps({
                        "reasoning_effort": "high",
                        "reasoning_tokens": None,
                        "provider_operation": "responses.create",
                        "provider_elapsed_ms": 600.0,
                        "limiter_wait_ms": 0,
                        "provider_error_type": "TimeoutError",
                        "workflow": "report_generation",
                        "artifact_family": "figure",
                    }),
                ),
                (
                    "openai", "analyze", "legacy", "2026-10-06T00:00:02Z",
                    "gpt-4.1", "report-1", 5, None, 2, 7, 0, 0.001,
                    "report/legacy", "completed", "report_analysis", "{}",
                ),
                (
                    "openai", "analyze", "other", "2026-10-06T00:00:03Z",
                    "gpt-5", "report-2", 999, 0, 999, 1998, 0, 1.0,
                    "other", "completed", "other_stage", "{}",
                ),
            ],
        )

    profile = aggregate_report_provider_calls(
        usage_db=usage_db, report_id="report-1", top_n=1
    )

    assert profile["usage_event_count"] == 3
    assert profile["timed_call_count"] == 2
    assert profile["untimed_call_count"] == 1
    assert profile["provider_elapsed_ms_total"] == 1000.0
    assert profile["limiter_wait_ms_total"] == 20.0
    assert profile["input_tokens"] == 305
    assert profile["total_tokens"] == 397
    assert profile["cached_input_tokens"] == 20
    assert profile["cached_input_token_reported_call_count"] == 2
    assert profile["reasoning_tokens"] == 8
    assert profile["reasoning_token_reported_call_count"] == 1
    assert profile["estimated_cost_usd"] == 0.031
    assert len(profile["groups_by_provider_elapsed"]) == 2
    family = profile["groups_by_prompt_namespace"][0]
    assert family["prompt_namespace"] == "report/figure"
    assert family["call_count"] == 2
    assert family["provider_elapsed_ms_total"] == 1000.0
    assert family["total_tokens"] == 390
    assert family["workflows"] == ["report_generation"]
    assert family["artifact_families"] == ["figure"]
    stage = profile["groups_by_stage"][0]
    assert stage["stage"] == "report_analysis"
    assert stage["call_count"] == 3
    effort = profile["groups_by_reasoning_effort"][0]
    assert effort["reasoning_effort"] == "high"
    assert effort["call_count"] == 2
    top = profile["slowest_provider_calls"]
    assert len(top) == 1
    assert top[0]["request_id"] == "req-2"
    assert top[0]["provider_elapsed_ms"] == 600.0
    assert top[0]["workflow"] == "report_generation"
    assert top[0]["artifact_family"] == "figure"


def test_profile_uses_interval_union_and_distinguishes_aggregate_work(tmp_path) -> None:
    usage_db = tmp_path / "usage.sqlite"
    _create_profile_db(
        usage_db,
        [
            _profile_row(
                "overlap-1", "family/a", 400, 0, 400,
                reasoning_tokens=5, effort="medium", cost=0.01,
            ),
            _profile_row(
                "overlap-2", "family/a", 600, 100, 700,
                reasoning_tokens=7, effort="medium", cost=0.02,
            ),
            _profile_row(
                "cross-family-overlap", "family/c", 100, 50, 150,
                reasoning_tokens=2, effort="low", cost=0.001,
            ),
            _profile_row(
                "serial", "family/b", 200, 800, 1000,
                reasoning_tokens=3, effort="low", cost=0.005,
            ),
            _profile_row("legacy", "family/legacy", 100, None, None),
        ],
    )

    profile = aggregate_report_provider_calls(
        usage_db=usage_db, report_id="report-1", top_n=10
    )

    assert profile["provider_elapsed_ms_total"] == 1400.0
    assert profile["provider_active_wall_ms"] == 900.0
    assert profile["max_provider_concurrency"] == 3
    assert profile["report_analysis_provider_active_wall_ms"] == 900.0
    assert profile["report_analysis_max_provider_concurrency"] == 3
    assert profile["aggregate_provider_work_semantics"] == (
        "sum of per-call elapsed time; not critical-path duration"
    )
    assert profile["critical_path_attribution"] == "not_reconstructed"

    family_a = next(
        group
        for group in profile["groups_by_prompt_namespace"]
        if group["prompt_namespace"] == "family/a"
    )
    assert family_a["provider_elapsed_ms_total"] == 1000.0
    assert family_a["provider_active_wall_ms"] == 700.0
    assert family_a["exclusive_exposed_wall_time_ms"] == 350.0
    assert family_a["max_simultaneous_calls"] == 2
    assert family_a["reasoning_efforts"] == ["medium"]
    assert family_a["reasoning_tokens"] == 12
    assert family_a["input_tokens"] == 300
    assert family_a["output_tokens"] == 60
    assert family_a["estimated_cost_usd"] == 0.03

    family_b = next(
        group
        for group in profile["groups_by_prompt_namespace"]
        if group["prompt_namespace"] == "family/b"
    )
    assert family_b["provider_active_wall_ms"] == 200.0
    assert family_b["provider_elapsed_ms_total"] == 200.0
    assert family_b["max_simultaneous_calls"] == 1
    family_c = next(
        group
        for group in profile["groups_by_prompt_namespace"]
        if group["prompt_namespace"] == "family/c"
    )
    assert family_c["provider_active_wall_ms"] == 100.0
    assert family_c["exclusive_exposed_wall_time_ms"] == 0.0
    assert profile["wall_clock_exposure_ranking"][0]["prompt_namespace"] == "family/a"
    assert profile["wall_clock_exposure_ranking"][0]["provider_active_wall_ms"] == 700.0
    assert all(
        call["provider_request_start_monotonic_ms"] is None
        for call in profile["slowest_provider_calls"]
        if call["request_id"] == "legacy"
    )


def test_profile_reads_monotonic_report_wall_and_stage_execution(tmp_path) -> None:
    usage_db = tmp_path / "usage.sqlite"
    _create_profile_db(
        usage_db,
        [_profile_row("one", "family/a", 200, 0, 200)],
    )
    workflow_db = tmp_path / "workflow.sqlite"
    with sqlite3.connect(workflow_db) as connection:
        connection.executescript(
            """
            create table workflow_jobs (
                job_id text, report_id text, queue_name text
            );
            create table performance_telemetry_spans (
                span_id text, stage text, attributes_json text
            );
            create table performance_telemetry_measurements (
                span_id text, metric text, status text, integer_value integer
            );
            insert into workflow_jobs values (
                'analysis-job', 'report-1', 'report_analysis'
            );
            insert into performance_telemetry_spans values (
                'analysis-span', 'report_analysis', '{"job_id":"analysis-job"}'
            );
            insert into performance_telemetry_measurements values (
                'analysis-span', 'wall_time_ms', 'observed', 12500
            );
            """
        )
    result_json = tmp_path / "result.json"
    result_json.write_text(
        json.dumps({"report_id": "report-1", "total_duration_seconds": 30.0}),
        encoding="utf-8",
    )

    profile = aggregate_report_provider_calls(
        usage_db=usage_db,
        report_id="report-1",
        workflow_db=workflow_db,
        run_result_json=result_json,
    )

    assert profile["report_wall_clock_seconds"] == 30.0
    assert profile["report_analysis_execution_seconds"] == 12.5
    assert profile["provider_active_wall_ms"] == 200.0
    assert profile["report_wall_non_provider_residual_ms"] == 29800.0
    assert profile["report_analysis_non_provider_residual_ms"] == 12300.0


def _create_profile_db(path, rows) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            create table llm_usage_events (
                provider text,
                action text,
                request_id text,
                timestamp_utc text,
                model text,
                report_id text,
                input_tokens integer,
                cached_input_tokens integer,
                output_tokens integer,
                total_tokens integer,
                tool_calls integer,
                estimated_cost_usd real,
                prompt_namespace text,
                provider_call_status text,
                stage text,
                metadata_json text
            )
            """
        )
        connection.executemany(
            """
            insert into llm_usage_events values (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )


def _profile_row(
    request_id, namespace, elapsed_ms, start_ms, finish_ms,
    *, reasoning_tokens=None, effort="", cost=0.0,
):
    metadata = {
        "provider_elapsed_ms": elapsed_ms,
        "reasoning_tokens": reasoning_tokens,
        "reasoning_effort": effort,
        "workflow": "report_analysis",
        "artifact_family": namespace.rsplit("/", 1)[-1],
    }
    if start_ms is not None and finish_ms is not None:
        metadata.update(
            {
                "provider_request_start_monotonic_ms": start_ms,
                "provider_request_finish_monotonic_ms": finish_ms,
            }
        )
    return (
        "openai", "analyze", request_id, "2026-10-06T00:00:00Z", "gpt-5",
        "report-1", 150, 0, 30, 180, 0, cost, namespace, "completed",
        "report_analysis", json.dumps(metadata),
    )
