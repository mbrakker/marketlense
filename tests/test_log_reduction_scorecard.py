from __future__ import annotations

import json

from scripts.quality._cto_review_evidence.log_reduction_scorecard import (
    LogReductionAccumulator,
)


def _log_line(
    *,
    timestamp: str = "2026-10-10T12:00:00+00:00",
    module: str = "src.services.example",
    event: str = "bounded_event",
    fields: dict[str, object] | None = None,
    run_id: str = "run-one",
    producer_commit_sha: str = "a" * 40,
) -> str:
    payload: dict[str, object] = {
        "timestamp_utc": timestamp,
        "run_id": run_id,
        "module": module,
        "event": event,
        "producer_commit_sha": producer_commit_sha,
        "fields": fields or {},
    }
    return f"12:00:00 | INFO | market_lense.test | {json.dumps(payload)}\n"


def test_empty_and_unavailable_log_corpora_have_distinct_states() -> None:
    unavailable = LogReductionAccumulator(
        evidence_run_id="r6-empty",
        repository_commit_sha="b" * 40,
        full_scan_available=False,
    ).build(scanned_log_file_count=0)
    empty = LogReductionAccumulator(
        evidence_run_id="r6-empty",
        repository_commit_sha="b" * 40,
    ).build(scanned_log_file_count=1)

    assert unavailable["status"] == "unavailable"
    assert unavailable["reduction_count"] is None
    assert unavailable["group_summary"]["module_event_group_count"] is None
    assert empty["status"] == "zero"
    assert empty["reduction_count"] == 0
    assert empty["attempted_size_bytes"] == {
        "status": "unavailable",
        "sample_count": 0,
        "p50": None,
        "p90": None,
        "p95": None,
        "p99": None,
        "max": None,
    }


def test_normal_structured_events_report_zero_and_retained_identity() -> None:
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-normal",
        repository_commit_sha="b" * 40,
    )
    accumulator.observe_line(
        _log_line(fields={"message": "synthetic safe operational text"}),
        log_date="2026-10-10",
    )

    scorecard = accumulator.build(scanned_log_file_count=1)

    assert scorecard["status"] == "zero"
    assert scorecard["reduction_count"] == 0
    assert scorecard["corpus"]["structured_event_count"] == 1
    assert scorecard["time_window"]["timestamp_utc"] == {
        "status": "observed",
        "start": "2026-10-10T12:00:00+00:00",
        "end": "2026-10-10T12:00:00+00:00",
    }
    assert scorecard["build_identity"]["collector_commit_sha"] == "b" * 40
    assert scorecard["build_identity"]["producer_commit_shas"] == ["a" * 40]


def test_oversized_groups_have_deterministic_percentiles_and_review_mapping() -> None:
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-oversized",
        repository_commit_sha="b" * 40,
    )
    for attempted_size, run_id in (
        (20_000, "run-one"),
        (24_000, "run-one"),
        (40_000, "run-two"),
    ):
        accumulator.observe_line(
            _log_line(
                fields={
                    "log_payload_reduced": {
                        "attempted_size_bytes": attempted_size,
                        "maximum_size_bytes": 16_384,
                        "original_field_count": 3,
                    }
                },
                run_id=run_id,
            ),
            log_date="2026-10-10",
        )

    scorecard = accumulator.build(scanned_log_file_count=1)
    group = scorecard["groups"][0]

    assert scorecard["status"] == "available"
    assert scorecard["reduction_count"] == 3
    assert scorecard["attempted_size_bytes"] == {
        "status": "available",
        "sample_count": 3,
        "p50": 24_000,
        "p90": 40_000,
        "p95": 40_000,
        "p99": 40_000,
        "max": 40_000,
    }
    assert group["module"] == "src.services.example"
    assert group["event"] == "bounded_event"
    assert group["recurring"] is True
    assert group["distinct_run_count"] == 2
    assert group["remediation"] == {
        "owner_role": "module owner",
        "owner_reference": "src.services.example",
        "remediation_reference": (
            "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
            "and-remediate-recurring-callers"
        ),
    }
    assert scorecard["automatic_remediation"] is False
    assert scorecard["group_summary"]["recurring_group_count"] == 1


def test_observed_market_lense_module_namespace_is_grouped() -> None:
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-legacy-module",
        repository_commit_sha="b" * 40,
    )
    accumulator.observe_line(
        _log_line(
            module="market_lense.report_analysis_orchestrator",
            fields={
                "log_payload_reduced": {
                    "attempted_size_bytes": 20_000,
                    "maximum_size_bytes": 16_384,
                }
            },
        ),
        log_date="2026-10-10",
    )

    scorecard = accumulator.build(scanned_log_file_count=1)

    assert scorecard["groups"][0]["module"] == (
        "market_lense.report_analysis_orchestrator"
    )
    assert scorecard["groups"][0]["identity_status"] == "available"


def test_scorecard_is_order_independent_for_the_same_retained_log_lines() -> None:
    lines = [
        _log_line(
            timestamp=f"2026-10-10T12:00:0{index}+00:00",
            module="src.services.example",
            event="bounded_event",
            fields={
                "log_payload_reduced": {
                    "attempted_size_bytes": attempted_size,
                    "maximum_size_bytes": 16_384,
                }
            },
            run_id="run-one" if index < 2 else "run-two",
        )
        for index, attempted_size in enumerate((20_000, 24_000, 40_000))
    ]

    scorecards = []
    for ordered_lines in (lines, list(reversed(lines))):
        accumulator = LogReductionAccumulator(
            evidence_run_id="r6-deterministic",
            repository_commit_sha="b" * 40,
        )
        for line in ordered_lines:
            accumulator.observe_line(line, log_date="2026-10-10")
        scorecards.append(accumulator.build(scanned_log_file_count=1))

    assert scorecards[0] == scorecards[1]


def test_large_caller_inventory_is_bounded_and_flags_omitted_recurrences() -> None:
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-bounded-inventory",
        repository_commit_sha="b" * 40,
    )
    for caller_index in range(101):
        for _ in range(3):
            accumulator.observe_line(
                _log_line(
                    module=f"src.services.owner_{caller_index:03d}",
                    event="bounded_event",
                    fields={
                        "log_payload_reduced": {
                            "attempted_size_bytes": 20_000,
                            "maximum_size_bytes": 16_384,
                        }
                    },
                ),
                log_date="2026-10-10",
            )

    scorecard = accumulator.build(scanned_log_file_count=1)

    assert scorecard["status"] == "partial"
    assert len(scorecard["groups"]) == 100
    assert scorecard["group_summary"] == {
        "status": "partial",
        "module_event_group_count": 101,
        "recurring_group_count": 101,
        "included_group_count": 100,
        "omitted_group_count": 1,
        "omitted_recurring_group_count": 1,
        "maximum_included_groups": 100,
        "overflow_remediation": {
            "owner_role": "module owners",
            "owner_reference": "omitted module/event groups",
            "remediation_reference": (
                "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                "and-remediate-recurring-callers"
            ),
        },
    }


def test_malformed_lines_and_reduction_metadata_are_counted_without_failing() -> None:
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-malformed",
        repository_commit_sha="b" * 40,
    )
    accumulator.observe_line(
        '12:00:00 | INFO | market_lense.test | {"fields": nope}\n',
        log_date="2026-10-10",
    )
    accumulator.observe_line(
        _log_line(
            fields={
                "log_payload_reduced": {
                    "attempted_size_bytes": True,
                    "maximum_size_bytes": 16_384,
                }
            }
        ),
        log_date="2026-10-10",
    )

    scorecard = accumulator.build(scanned_log_file_count=1)

    assert scorecard["status"] == "partial"
    assert scorecard["reduction_count"] == 0
    assert scorecard["corpus"]["malformed_structured_line_count"] == 1
    assert scorecard["corpus"]["invalid_reduction_metadata_count"] == 1
    assert scorecard["groups"] == []


def test_scorecard_never_emits_sensitive_event_fields_or_untrusted_identifiers() -> (
    None
):
    sentinels = (
        "SOURCE_SENTINEL_987654",
        "PROMPT_SENTINEL_987654",
        "MODEL_RESPONSE_SENTINEL_987654",
        "BROWSER_TERMINAL_SENTINEL_987654",
        "CREDENTIAL_SENTINEL_987654",
    )
    accumulator = LogReductionAccumulator(
        evidence_run_id="r6-sensitive",
        repository_commit_sha="b" * 40,
    )
    accumulator.observe_line(
        _log_line(
            module=f"{sentinels[4]}",
            event="unsafe event text",
            fields={
                "log_payload_reduced": {
                    "attempted_size_bytes": 20_000,
                    "maximum_size_bytes": 16_384,
                },
                "source_text": sentinels[0],
                "rendered_prompt": sentinels[1],
                "model_response": sentinels[2],
                "browser_terminal_text": sentinels[3],
            },
        ),
        log_date="2026-10-10",
    )

    serialized = json.dumps(
        accumulator.build(scanned_log_file_count=1),
        ensure_ascii=True,
        sort_keys=True,
    )

    assert all(sentinel not in serialized for sentinel in sentinels)
