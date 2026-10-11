"""Versioned safe contract for retained structured-log reduction telemetry."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, TypedDict

LOG_REDUCTION_SCORECARD_SCHEMA_VERSION = "1.0"
_MODULE_RE = re.compile(r"^(?:src|market_lense)(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PercentileSummary(TypedDict):
    """Exact nearest-rank size percentiles, or explicit unavailable values."""

    status: Literal["available", "unavailable"]
    sample_count: int
    p50: int | None
    p90: int | None
    p95: int | None
    p99: int | None
    max: int | None


class LogReductionGroup(TypedDict):
    """Safe grouping and review locator for one module/event pair."""

    module: str
    event: str
    identity_status: Literal["available", "unavailable"]
    reduction_count: int
    distinct_run_count: int
    attempted_size_bytes: PercentileSummary
    retained_event_size_bytes: PercentileSummary
    retained_budget: dict[str, int | str | None]
    recurring: bool
    remediation: dict[str, str] | None


class LogReductionGroupSummary(TypedDict):
    """Bounded inventory counts; omitted identities remain explicit."""

    status: Literal["available", "partial", "unavailable"]
    module_event_group_count: int | None
    recurring_group_count: int | None
    included_group_count: int
    omitted_group_count: int
    omitted_recurring_group_count: int | None
    maximum_included_groups: int
    overflow_remediation: dict[str, str] | None


class LogReductionScorecard(TypedDict):
    """Persisted CTO scorecard; payload content is excluded by construction."""

    schema_version: Literal["1.0"]
    status: Literal["available", "zero", "partial", "unavailable"]
    evidence_run_id: str | None
    repository_commit_sha: str | None
    availability_reason: str | None
    corpus: dict[str, int | None]
    time_window: dict[str, dict[str, str | None]]
    build_identity: dict[str, object]
    reduction_count: int | None
    attempted_size_bytes: PercentileSummary
    retained_event_size_bytes: PercentileSummary
    retained_budget: dict[str, int | str | None]
    recurring_threshold: dict[str, int | str]
    group_summary: LogReductionGroupSummary
    groups: list[LogReductionGroup]
    automatic_remediation: Literal[False]


_SCORECARD_KEYS = {
    "schema_version",
    "status",
    "evidence_run_id",
    "repository_commit_sha",
    "availability_reason",
    "corpus",
    "time_window",
    "build_identity",
    "reduction_count",
    "attempted_size_bytes",
    "retained_event_size_bytes",
    "retained_budget",
    "recurring_threshold",
    "group_summary",
    "groups",
    "automatic_remediation",
}
_PERCENTILE_KEYS = {"status", "sample_count", "p50", "p90", "p95", "p99", "max"}
_GROUP_KEYS = {
    "module",
    "event",
    "identity_status",
    "reduction_count",
    "distinct_run_count",
    "attempted_size_bytes",
    "retained_event_size_bytes",
    "retained_budget",
    "recurring",
    "remediation",
}


def validate_log_reduction_scorecard(payload: object) -> LogReductionScorecard:
    """Reject unsupported fields or invalid states before persisting the contract."""

    if not isinstance(payload, dict) or set(payload) != _SCORECARD_KEYS:
        raise ValueError("log reduction scorecard fields are invalid")
    if payload.get("schema_version") != LOG_REDUCTION_SCORECARD_SCHEMA_VERSION:
        raise ValueError("log reduction scorecard schema_version is unsupported")
    if payload.get("status") not in {"available", "zero", "partial", "unavailable"}:
        raise ValueError("log reduction scorecard status is invalid")
    for name in ("evidence_run_id", "availability_reason"):
        value = payload.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 128):
            raise ValueError(f"log reduction scorecard {name} is invalid")
    repository_sha = payload.get("repository_commit_sha")
    if repository_sha is not None and (
        not isinstance(repository_sha, str)
        or not _COMMIT_SHA_RE.fullmatch(repository_sha)
    ):
        raise ValueError("log reduction scorecard repository commit is invalid")
    if payload.get("automatic_remediation") is not False:
        raise ValueError("log reduction scorecard cannot enable automatic remediation")

    count = payload.get("reduction_count")
    if payload["status"] == "unavailable":
        if count is not None:
            raise ValueError("unavailable scorecards cannot report a reduction count")
    elif isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("available scorecards require a nonnegative reduction count")
    if payload["status"] == "zero" and count != 0:
        raise ValueError("zero scorecards must report zero reductions")
    if payload["status"] == "available" and not count:
        raise ValueError("available scorecards require at least one reduction")

    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValueError("log reduction scorecard groups must be a list")
    for group in groups:
        _validate_group(group)
    if payload["status"] == "unavailable" and groups:
        raise ValueError("unavailable scorecards cannot report caller groups")
    _validate_group_summary(payload.get("group_summary"), groups)
    if count is not None:
        included_reductions = sum(group["reduction_count"] for group in groups)
        omitted_groups = payload["group_summary"]["omitted_group_count"]
        if included_reductions > count or (
            omitted_groups == 0 and included_reductions != count
        ):
            raise ValueError("log reduction group counts do not reconcile")

    for name in ("attempted_size_bytes", "retained_event_size_bytes"):
        _validate_percentiles(payload.get(name))
    _validate_budget(payload.get("retained_budget"))
    if count is not None and (
        payload["attempted_size_bytes"]["sample_count"] != count
        or payload["retained_event_size_bytes"]["sample_count"] != count
    ):
        raise ValueError("log reduction size samples do not reconcile")
    if payload["status"] == "unavailable" and any(
        payload[name]["status"] != "unavailable"
        for name in ("attempted_size_bytes", "retained_event_size_bytes")
    ):
        raise ValueError("unavailable scorecards cannot report size percentiles")

    corpus = payload.get("corpus")
    expected_corpus = {
        "log_files_scanned",
        "log_files_unreadable",
        "structured_event_count",
        "malformed_structured_line_count",
        "invalid_reduction_metadata_count",
    }
    if not isinstance(corpus, dict) or set(corpus) != expected_corpus:
        raise ValueError("log reduction scorecard corpus fields are invalid")
    for name, value in corpus.items():
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"log reduction scorecard corpus {name} is invalid")
    if int(corpus["log_files_scanned"] or 0) < int(corpus["log_files_unreadable"] or 0):
        raise ValueError("unreadable log count exceeds the scanned corpus")
    if (
        payload["status"] == "unavailable"
        and corpus["structured_event_count"] is not None
    ):
        raise ValueError("unavailable scorecards cannot report parsed event counts")

    time_window = payload.get("time_window")
    if not isinstance(time_window, dict) or set(time_window) != {
        "log_file_dates",
        "timestamp_utc",
    }:
        raise ValueError("log reduction scorecard time window is invalid")
    for name in ("log_file_dates", "timestamp_utc"):
        window = time_window[name]
        if not isinstance(window, dict) or set(window) != {"status", "start", "end"}:
            raise ValueError(f"log reduction scorecard {name} window is invalid")
        if window["status"] not in {"observed", "unavailable"}:
            raise ValueError(f"log reduction scorecard {name} state is invalid")
        if window["status"] == "observed":
            if not all(isinstance(window[key], str) for key in ("start", "end")):
                raise ValueError(f"log reduction scorecard {name} bounds are invalid")
            try:
                if name == "log_file_dates":
                    start_bound = date.fromisoformat(window["start"])
                    end_bound = date.fromisoformat(window["end"])
                else:
                    start_bound = datetime.fromisoformat(
                        window["start"].replace("Z", "+00:00")
                    )
                    end_bound = datetime.fromisoformat(
                        window["end"].replace("Z", "+00:00")
                    )
                    if start_bound.tzinfo is None or end_bound.tzinfo is None:
                        raise ValueError
            except ValueError as exc:
                raise ValueError(
                    f"log reduction scorecard {name} bounds are invalid"
                ) from exc
            if start_bound > end_bound:
                raise ValueError(f"log reduction scorecard {name} bounds are reversed")
        elif window["start"] is not None or window["end"] is not None:
            raise ValueError(f"unavailable {name} bounds must be null")

    build = payload.get("build_identity")
    if not isinstance(build, dict) or set(build) != {
        "collector_commit_sha",
        "producer_status",
        "producer_commit_shas",
        "producer_commit_sha_count",
    }:
        raise ValueError("log reduction scorecard build identity is invalid")
    collector_sha = build["collector_commit_sha"]
    if collector_sha is not None and (
        not isinstance(collector_sha, str)
        or not _COMMIT_SHA_RE.fullmatch(collector_sha)
    ):
        raise ValueError("log reduction scorecard collector SHA is invalid")
    producer_shas = build["producer_commit_shas"]
    producer_count = build["producer_commit_sha_count"]
    if (
        not isinstance(producer_shas, list)
        or len(producer_shas) > 25
        or any(
            not isinstance(sha, str) or not _COMMIT_SHA_RE.fullmatch(sha)
            for sha in producer_shas
        )
        or producer_shas != sorted(set(producer_shas))
        or isinstance(producer_count, bool)
        or not isinstance(producer_count, int)
        or producer_count < len(producer_shas)
    ):
        raise ValueError("log reduction scorecard producer SHAs are invalid")
    if build["producer_status"] not in {"observed", "unavailable"}:
        raise ValueError("log reduction scorecard producer status is invalid")
    if (build["producer_status"] == "observed") != (producer_count > 0):
        raise ValueError("log reduction producer status does not match its count")

    threshold = payload.get("recurring_threshold")
    if not isinstance(threshold, dict) or set(threshold) != {
        "minimum_reductions_per_module_event",
        "basis",
    }:
        raise ValueError("log reduction scorecard threshold is invalid")
    if (
        threshold["minimum_reductions_per_module_event"] != 3
        or threshold["basis"]
        != "same validated module/event pair in the scanned corpus"
    ):
        raise ValueError("log reduction scorecard threshold is unsupported")

    return payload  # type: ignore[return-value]


def _validate_percentiles(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _PERCENTILE_KEYS:
        raise ValueError("log reduction percentile fields are invalid")
    sample_count = value.get("sample_count")
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count < 0
    ):
        raise ValueError("log reduction percentile sample count is invalid")
    status = value.get("status")
    if status not in {"available", "unavailable"}:
        raise ValueError("log reduction percentile status is invalid")
    values = [value.get(name) for name in ("p50", "p90", "p95", "p99", "max")]
    if status == "unavailable":
        if sample_count != 0 or any(item is not None for item in values):
            raise ValueError("unavailable percentiles must have no values")
    else:
        if sample_count == 0 or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in values
        ):
            raise ValueError("available percentiles must have nonnegative values")
        numeric_values = [
            item
            for item in values
            if isinstance(item, int) and not isinstance(item, bool)
        ]
        if numeric_values != sorted(numeric_values):
            raise ValueError("log reduction percentiles must be nondecreasing")


def _validate_budget(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "declared_limit_bytes",
        "within_limit_count",
        "over_limit_count",
    }:
        raise ValueError("log reduction budget fields are invalid")
    if value.get("status") not in {
        "within_limit",
        "over_limit",
        "mixed",
        "unavailable",
    }:
        raise ValueError("log reduction budget status is invalid")
    for name in ("declared_limit_bytes", "within_limit_count", "over_limit_count"):
        item = value.get(name)
        if item is not None and (
            isinstance(item, bool) or not isinstance(item, int) or item < 0
        ):
            raise ValueError(f"log reduction budget {name} is invalid")
    within = value["within_limit_count"]
    over = value["over_limit_count"]
    status = value["status"]
    expected_status = (
        "unavailable"
        if not within and not over
        else "within_limit"
        if not over
        else "over_limit"
        if not within
        else "mixed"
    )
    if status != expected_status:
        raise ValueError("log reduction budget status does not match its counts")


def _validate_group(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _GROUP_KEYS:
        raise ValueError("log reduction group fields are invalid")
    module = value.get("module")
    event = value.get("event")
    if not isinstance(module, str) or not isinstance(event, str):
        raise ValueError("log reduction group identity is invalid")
    if value.get("identity_status") == "available":
        if (
            len(module) > 160
            or not _MODULE_RE.fullmatch(module)
            or not _EVENT_RE.fullmatch(event)
        ):
            raise ValueError("log reduction group identity is unsafe")
    elif value.get("identity_status") != "unavailable" or (
        module != "unavailable" or event != "unavailable"
    ):
        raise ValueError("unavailable log reduction group identity is invalid")
    count = value.get("reduction_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("log reduction group count is invalid")
    run_count = value.get("distinct_run_count")
    if isinstance(run_count, bool) or not isinstance(run_count, int) or run_count < 0:
        raise ValueError("log reduction group run count is invalid")
    if run_count > count:
        raise ValueError("log reduction group run count exceeds its events")
    for name in ("attempted_size_bytes", "retained_event_size_bytes"):
        _validate_percentiles(value.get(name))
    _validate_budget(value.get("retained_budget"))
    recurring = count >= 3 and value.get("identity_status") == "available"
    if value.get("recurring") is not recurring:
        raise ValueError("log reduction recurrence flag is inconsistent")
    remediation = value.get("remediation")
    if recurring:
        if remediation != {
            "owner_role": "module owner",
            "owner_reference": module,
            "remediation_reference": (
                "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                "and-remediate-recurring-callers"
            ),
        }:
            raise ValueError("recurring log reduction remediation is incomplete")
    elif remediation is not None:
        raise ValueError("nonrecurring groups cannot carry remediation work")


def _validate_group_summary(value: object, groups: list[object]) -> None:
    expected = {
        "status",
        "module_event_group_count",
        "recurring_group_count",
        "included_group_count",
        "omitted_group_count",
        "omitted_recurring_group_count",
        "maximum_included_groups",
        "overflow_remediation",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("log reduction group summary fields are invalid")
    if value["status"] not in {"available", "partial", "unavailable"}:
        raise ValueError("log reduction group summary status is invalid")
    if value["maximum_included_groups"] != 100 or len(groups) > 100:
        raise ValueError("log reduction group output exceeds its bound")
    for name in (
        "module_event_group_count",
        "recurring_group_count",
        "included_group_count",
        "omitted_group_count",
        "omitted_recurring_group_count",
    ):
        count = value[name]
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            raise ValueError(f"log reduction group summary {name} is invalid")
    if value["included_group_count"] != len(groups):
        raise ValueError("included log reduction group count does not reconcile")
    if value["module_event_group_count"] is not None and (
        value["module_event_group_count"]
        != value["included_group_count"] + value["omitted_group_count"]
    ):
        raise ValueError("module/event group count does not reconcile")
    included_recurring = sum(
        1
        for group in groups
        if isinstance(group, dict) and group.get("recurring") is True
    )
    omitted_recurring = value["omitted_recurring_group_count"]
    if (
        omitted_recurring is not None
        and omitted_recurring > value["omitted_group_count"]
    ):
        raise ValueError("omitted recurring group count exceeds omitted groups")
    if value["recurring_group_count"] is not None and (
        value["recurring_group_count"] != included_recurring + (omitted_recurring or 0)
    ):
        raise ValueError("recurring group count does not reconcile")
    if value["status"] == "unavailable" and any(
        value[name] is not None
        for name in (
            "module_event_group_count",
            "recurring_group_count",
            "omitted_recurring_group_count",
        )
    ):
        raise ValueError("unavailable group summaries cannot report counts")
    overflow = value["overflow_remediation"]
    if value["omitted_recurring_group_count"]:
        if overflow != {
            "owner_role": "module owners",
            "owner_reference": "omitted module/event groups",
            "remediation_reference": (
                "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                "and-remediate-recurring-callers"
            ),
        }:
            raise ValueError("omitted recurring callers lack a review reference")
    elif overflow is not None:
        raise ValueError("group summary has an unnecessary overflow reference")
