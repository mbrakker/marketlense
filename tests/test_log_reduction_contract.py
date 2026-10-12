from __future__ import annotations

from typing import Any

import pytest

from src.contracts.log_reduction import validate_log_reduction_scorecard

_SHA = "a" * 40
_DELETE = "<delete>"


def _summary(status: str, count: int | None) -> dict[str, Any]:
    if status == "unavailable":
        return {
            "status": "unavailable",
            "module_event_group_count": None,
            "recurring_group_count": None,
            "included_group_count": 0,
            "omitted_group_count": 0,
            "omitted_recurring_group_count": None,
            "maximum_included_groups": 100,
            "overflow_remediation": None,
        }
    group_count = 0 if status == "zero" else 1
    recurring = count == 3
    return {
        "status": "available",
        "module_event_group_count": group_count,
        "recurring_group_count": int(recurring),
        "included_group_count": group_count,
        "omitted_group_count": 0,
        "omitted_recurring_group_count": 0,
        "maximum_included_groups": 100,
        "overflow_remediation": None,
    }


def _percentiles(
    sample_count: int, values: tuple[int, int, int, int, int]
) -> dict[str, Any]:
    return {
        "status": "available",
        "sample_count": sample_count,
        "p50": values[0],
        "p90": values[1],
        "p95": values[2],
        "p99": values[3],
        "max": values[4],
    }


def _valid_scorecard(*, status: str = "available") -> dict[str, Any]:
    if status == "unavailable":
        unavailable = {
            "status": "unavailable",
            "sample_count": 0,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
        return {
            "schema_version": "1.0",
            "status": status,
            "evidence_run_id": "r6-contract-fixture",
            "repository_commit_sha": _SHA,
            "availability_reason": "no_readable_log_files",
            "corpus": {
                "log_files_scanned": 0,
                "log_files_unreadable": 0,
                "structured_event_count": None,
                "malformed_structured_line_count": None,
                "invalid_reduction_metadata_count": None,
            },
            "time_window": {
                name: {"status": "unavailable", "start": None, "end": None}
                for name in ("log_file_dates", "timestamp_utc")
            },
            "build_identity": {
                "collector_commit_sha": _SHA,
                "producer_status": "unavailable",
                "producer_commit_shas": [],
                "producer_commit_sha_count": 0,
            },
            "reduction_count": None,
            "attempted_size_bytes": unavailable.copy(),
            "retained_event_size_bytes": unavailable.copy(),
            "retained_budget": {
                "status": "unavailable",
                "declared_limit_bytes": None,
                "within_limit_count": 0,
                "over_limit_count": 0,
            },
            "recurring_threshold": {
                "minimum_reductions_per_module_event": 3,
                "basis": "same validated module/event pair in the scanned corpus",
            },
            "group_summary": _summary(status, None),
            "groups": [],
            "automatic_remediation": False,
        }

    effective_status = "available" if status == "normal" else status
    reduction_count = 3 if status == "available" else 1 if status == "normal" else 0
    is_recurring = reduction_count == 3
    size = (
        _percentiles(3, (20_000, 40_000, 40_000, 40_000, 40_000))
        if reduction_count == 3
        else _percentiles(1, (20_000, 20_000, 20_000, 20_000, 20_000))
        if reduction_count == 1
        else {
            "status": "unavailable",
            "sample_count": 0,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    )
    retained = (
        _percentiles(3, (400, 450, 450, 450, 450))
        if reduction_count == 3
        else _percentiles(1, (400, 400, 400, 400, 400))
        if reduction_count == 1
        else size.copy()
    )
    group = {
        "module": "src.services.example",
        "event": "bounded_event",
        "identity_status": "available",
        "reduction_count": reduction_count,
        "distinct_run_count": 2 if is_recurring else 0,
        "attempted_size_bytes": size.copy(),
        "retained_event_size_bytes": retained.copy(),
        "retained_budget": {
            "status": "within_limit" if reduction_count else "unavailable",
            "declared_limit_bytes": 16_384 if reduction_count else None,
            "within_limit_count": reduction_count,
            "over_limit_count": 0,
        },
        "recurring": is_recurring,
        "remediation": (
            {
                "owner_role": "module owner",
                "owner_reference": "src.services.example",
                "remediation_reference": (
                    "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                    "and-remediate-recurring-callers"
                ),
            }
            if is_recurring
            else None
        ),
    }
    return {
        "schema_version": "1.0",
        "status": effective_status,
        "evidence_run_id": "r6-contract-fixture",
        "repository_commit_sha": _SHA,
        "availability_reason": None,
        "corpus": {
            "log_files_scanned": 1,
            "log_files_unreadable": 0,
            "structured_event_count": reduction_count,
            "malformed_structured_line_count": 0,
            "invalid_reduction_metadata_count": 0,
        },
        "time_window": {
            "log_file_dates": {
                "status": "observed",
                "start": "2026-10-10",
                "end": "2026-10-10",
            },
            "timestamp_utc": {
                "status": "observed",
                "start": "2026-10-10T12:00:00+00:00",
                "end": "2026-10-10T12:00:02+00:00",
            },
        },
        "build_identity": {
            "collector_commit_sha": _SHA,
            "producer_status": "observed",
            "producer_commit_shas": [_SHA],
            "producer_commit_sha_count": 1,
        },
        "reduction_count": reduction_count,
        "attempted_size_bytes": size.copy(),
        "retained_event_size_bytes": retained.copy(),
        "retained_budget": {
            "status": "within_limit" if reduction_count else "unavailable",
            "declared_limit_bytes": 16_384 if reduction_count else None,
            "within_limit_count": reduction_count,
            "over_limit_count": 0,
        },
        "recurring_threshold": {
            "minimum_reductions_per_module_event": 3,
            "basis": "same validated module/event pair in the scanned corpus",
        },
        "group_summary": _summary(effective_status, reduction_count),
        "groups": [group] if reduction_count else [],
        "automatic_remediation": False,
    }


def _replace(
    payload: dict[str, Any], path: tuple[str | int, ...], value: object
) -> object:
    if not path:
        return value
    parent: Any = payload
    for key in path[:-1]:
        parent = parent[key]
    final_key = path[-1]
    if value == _DELETE:
        del parent[final_key]
    else:
        parent[final_key] = value
    return payload


@pytest.mark.parametrize(
    ("base_status", "path", "value"),
    [
        ("available", (), None),
        ("available", ("unexpected",), 1),
        ("available", ("schema_version",), "9.0"),
        ("available", ("schema_version",), _DELETE),
        ("available", ("status",), "unknown"),
        ("available", ("evidence_run_id",), "x" * 129),
        ("available", ("availability_reason",), 7),
        ("available", ("repository_commit_sha",), "bad-sha"),
        ("available", ("automatic_remediation",), True),
        ("unavailable", ("reduction_count",), 0),
        ("available", ("reduction_count",), -1),
        ("available", ("reduction_count",), True),
        ("available", ("reduction_count",), 4),
        ("zero", ("reduction_count",), 1),
        ("available", ("reduction_count",), 0),
        ("available", ("groups",), None),
        ("unavailable", ("groups",), [{}]),
        ("unavailable", ("groups",), _valid_scorecard()["groups"]),
        ("available", ("group_summary",), None),
        ("available", ("group_summary", "status"), "bad"),
        ("available", ("group_summary", "maximum_included_groups"), 101),
        ("available", ("group_summary", "included_group_count"), -1),
        ("available", ("group_summary", "included_group_count"), 2),
        ("available", ("group_summary", "module_event_group_count"), 2),
        ("available", ("group_summary", "omitted_recurring_group_count"), 1),
        ("available", ("group_summary", "recurring_group_count"), 0),
        ("unavailable", ("group_summary", "module_event_group_count"), 0),
        ("available", ("group_summary", "omitted_recurring_group_count"), 1),
        ("available", ("group_summary", "omitted_group_count"), 1),
        ("available", ("group_summary", "module_event_group_count"), 2),
        ("available", ("group_summary", "recurring_group_count"), 2),
        ("available", ("group_summary", "overflow_remediation"), {"owner": "module"}),
        (
            "available",
            ("group_summary",),
            {
                "status": "partial",
                "module_event_group_count": 2,
                "recurring_group_count": 2,
                "included_group_count": 1,
                "omitted_group_count": 1,
                "omitted_recurring_group_count": 1,
                "maximum_included_groups": 100,
                "overflow_remediation": None,
            },
        ),
        ("available", ("attempted_size_bytes",), None),
        ("available", ("attempted_size_bytes", "sample_count"), -1),
        ("available", ("attempted_size_bytes", "status"), "bad"),
        ("unavailable", ("attempted_size_bytes", "status"), "available"),
        (
            "unavailable",
            ("attempted_size_bytes",),
            _percentiles(1, (100, 100, 100, 100, 100)),
        ),
        ("available", ("attempted_size_bytes", "p99"), -1),
        ("available", ("attempted_size_bytes", "p99"), 19_000),
        ("available", ("attempted_size_bytes", "sample_count"), 2),
        ("unavailable", ("attempted_size_bytes", "sample_count"), 1),
        ("available", ("retained_budget",), None),
        ("available", ("retained_budget", "status"), "unknown"),
        ("available", ("retained_budget", "within_limit_count"), -1),
        ("available", ("retained_budget", "status"), "over_limit"),
        ("available", ("corpus",), []),
        ("available", ("corpus", "structured_event_count"), -1),
        ("available", ("corpus", "log_files_unreadable"), 2),
        ("unavailable", ("corpus", "structured_event_count"), 0),
        ("available", ("time_window",), None),
        ("available", ("time_window", "timestamp_utc"), None),
        ("available", ("time_window", "timestamp_utc", "status"), "bad"),
        ("available", ("time_window", "timestamp_utc", "start"), None),
        ("available", ("time_window", "log_file_dates", "start"), "bad"),
        (
            "available",
            ("time_window", "timestamp_utc", "start"),
            "2026-10-10T12:00:00",
        ),
        ("available", ("time_window", "log_file_dates", "start"), "2026-10-11"),
        ("available", ("time_window", "log_file_dates", "status"), "unavailable"),
        ("available", ("build_identity",), None),
        ("available", ("build_identity", "collector_commit_sha"), "bad"),
        ("available", ("build_identity", "producer_commit_shas"), ["bad"]),
        ("available", ("build_identity", "producer_commit_shas"), [_SHA, _SHA]),
        ("available", ("build_identity", "producer_commit_sha_count"), 0),
        ("available", ("build_identity", "producer_status"), "bad"),
        ("available", ("build_identity", "producer_status"), "unavailable"),
        ("available", ("recurring_threshold",), None),
        (
            "available",
            ("recurring_threshold", "minimum_reductions_per_module_event"),
            4,
        ),
        ("available", ("groups", 0, "unexpected"), "bad"),
        ("available", ("groups", 0, "module"), None),
        ("available", ("groups", 0, "module"), "raw payload text"),
        ("available", ("groups", 0, "module"), "src." + ("a" * 158)),
        ("available", ("groups", 0, "identity_status"), "bad"),
        ("available", ("groups", 0, "reduction_count"), 0),
        ("available", ("groups", 0, "distinct_run_count"), -1),
        ("available", ("groups", 0, "distinct_run_count"), 4),
        ("available", ("groups", 0, "recurring"), False),
        ("available", ("groups", 0, "remediation"), None),
        ("normal", ("groups", 0, "remediation"), {"unexpected": "owner"}),
    ],
)
def test_contract_rejects_malformed_or_unsafe_persisted_scorecards(
    base_status: str,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    payload = _replace(_valid_scorecard(status=base_status), path, value)

    with pytest.raises(ValueError):
        validate_log_reduction_scorecard(payload)
