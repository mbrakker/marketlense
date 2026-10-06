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
