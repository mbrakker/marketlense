"""Aggregate bounded-log reduction metadata for read-only CTO review."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timezone

from src.contracts.log_reduction import (
    LogReductionScorecard,
    validate_log_reduction_scorecard,
)
from src.utils.gui_utils import (
    LOG_LINE_RE,
    parse_structured_log_line,
)

_MODULE_RE = re.compile(r"^(?:src|market_lense)(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_METADATA_INTEGER = (1 << 63) - 1
_MAX_EXPORTED_PRODUCER_SHAS = 25
_MAX_EXPORTED_GROUPS = 100
_RECURRING_REDUCTION_THRESHOLD = 3


def _safe_run_id(value: object) -> str | None:
    text = str(value or "")
    return text if _RUN_ID_RE.fullmatch(text) else None


def _utc_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def _percentiles(values: list[int]) -> dict[str, int | str | None]:
    if not values:
        return {
            "status": "unavailable",
            "sample_count": 0,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(values)

    def nearest_rank(percent: int) -> int:
        rank = (len(ordered) * percent + 99) // 100
        return ordered[max(0, rank - 1)]

    return {
        "status": "available",
        "sample_count": len(ordered),
        "p50": nearest_rank(50),
        "p90": nearest_rank(90),
        "p95": nearest_rank(95),
        "p99": nearest_rank(99),
        "max": ordered[-1],
    }


def _budget_summary(
    limits: list[int], within_count: int, over_count: int
) -> dict[str, int | str | None]:
    sample_count = within_count + over_count
    if not sample_count:
        status = "unavailable"
    elif over_count == 0:
        status = "within_limit"
    elif within_count == 0:
        status = "over_limit"
    else:
        status = "mixed"
    unique_limits = sorted(set(limits))
    return {
        "status": status,
        "declared_limit_bytes": unique_limits[0] if len(unique_limits) == 1 else None,
        "within_limit_count": within_count,
        "over_limit_count": over_count,
    }


class LogReductionAccumulator:
    """Bounded-metadata accumulator; caller retains only counts and byte sizes."""

    def __init__(
        self,
        *,
        evidence_run_id: str | None,
        repository_commit_sha: str | None,
        full_scan_available: bool = True,
    ) -> None:
        self._evidence_run_id = _safe_run_id(evidence_run_id)
        commit = str(repository_commit_sha or "").lower()
        self._repository_commit_sha = commit if _SHA_RE.fullmatch(commit) else None
        self._full_scan_available = full_scan_available
        self._structured_event_count = 0
        self._malformed_structured_line_count = 0
        self._invalid_reduction_metadata_count = 0
        self._dates: set[str] = set()
        self._timestamps: set[str] = set()
        self._producer_shas: set[str] = set()
        self._groups: dict[tuple[str, str], dict[str, object]] = defaultdict(
            lambda: {
                "identity_status": "available",
                "attempted": [],
                "retained": [],
                "limits": [],
                "within_limit_count": 0,
                "over_limit_count": 0,
                "run_ids": set(),
            }
        )

    def observe_file_date(self, value: str | None) -> None:
        """Retain only validated dates from canonical log filenames."""

        if not value:
            return
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return
        if parsed.isoformat() == value:
            self._dates.add(value)

    def observe_line(
        self, raw_line: str, *, log_date: str | None = None
    ) -> dict[str, object] | None:
        """Parse one retained log line and collect only safe reduction fields."""

        parsed = parse_structured_log_line(raw_line, log_date=log_date)
        self.observe_event(parsed, raw_line=raw_line, log_date=log_date)
        return parsed

    def observe_event(
        self,
        parsed: dict[str, object] | None,
        *,
        raw_line: str,
        log_date: str | None = None,
    ) -> None:
        """Observe a parser result from the shared CTO log scan."""

        self.observe_file_date(log_date)
        match = LOG_LINE_RE.match(raw_line.strip())
        if parsed is None:
            if match and str(match.group("message") or "").lstrip().startswith("{"):
                self._malformed_structured_line_count += 1
            return

        self._structured_event_count += 1
        timestamp = _utc_timestamp(parsed.get("timestamp_utc"))
        if timestamp:
            self._timestamps.add(timestamp)
        producer_sha = str(parsed.get("producer_commit_sha") or "").strip().lower()
        if _SHA_RE.fullmatch(producer_sha):
            self._producer_shas.add(producer_sha)

        fields = parsed.get("fields")
        if not isinstance(fields, dict) or "log_payload_reduced" not in fields:
            return
        reduction = fields.get("log_payload_reduced")
        attempted = (
            reduction.get("attempted_size_bytes")
            if isinstance(reduction, dict)
            else None
        )
        maximum = (
            reduction.get("maximum_size_bytes") if isinstance(reduction, dict) else None
        )
        if not (
            isinstance(attempted, int)
            and not isinstance(attempted, bool)
            and 0 < attempted <= _MAX_METADATA_INTEGER
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and 0 < maximum <= _MAX_METADATA_INTEGER
            and attempted > maximum
            and match is not None
        ):
            self._invalid_reduction_metadata_count += 1
            return

        module_value = parsed.get("module")
        event_value = parsed.get("event")
        module = str(module_value or "")
        event = str(event_value or "")
        identity_available = (
            len(module) <= 160
            and len(event) <= 96
            and _MODULE_RE.fullmatch(module) is not None
            and _EVENT_RE.fullmatch(event) is not None
        )
        key = (module, event) if identity_available else ("unavailable", "unavailable")
        group = self._groups[key]
        if not identity_available:
            group["identity_status"] = "unavailable"
        attempted_values = group["attempted"]
        retained_values = group["retained"]
        limits = group["limits"]
        assert isinstance(attempted_values, list)
        assert isinstance(retained_values, list)
        assert isinstance(limits, list)
        retained_bytes = len(str(match.group("message")).encode("utf-8"))
        attempted_values.append(attempted)
        retained_values.append(retained_bytes)
        limits.append(maximum)
        run_ids = group["run_ids"]
        assert isinstance(run_ids, set)
        run_id = _safe_run_id(parsed.get("run_id"))
        if run_id:
            run_ids.add(run_id)
        if retained_bytes <= maximum:
            group["within_limit_count"] = int(group["within_limit_count"]) + 1
        else:
            group["over_limit_count"] = int(group["over_limit_count"]) + 1

    def build(
        self,
        *,
        scanned_log_file_count: int,
        unreadable_log_file_count: int = 0,
    ) -> LogReductionScorecard:
        """Return deterministic JSON-ready metrics with explicit unavailable states."""

        scanned = max(0, int(scanned_log_file_count))
        unreadable = max(0, int(unreadable_log_file_count))
        readable_count = max(0, scanned - unreadable)
        unavailable_reason: str | None = None
        if not self._full_scan_available:
            unavailable_reason = "full_structured_event_scan_not_available"
        elif readable_count == 0:
            unavailable_reason = "no_readable_log_files"

        if unavailable_reason:
            status = "unavailable"
            reduction_count: int | None = None
            groups: list[dict[str, object]] = []
            attempted_summary = _percentiles([])
            retained_summary = _percentiles([])
            budget = _budget_summary([], 0, 0)
            structured_count: int | None = None
            malformed_count: int | None = None
            invalid_metadata_count: int | None = None
            group_summary = {
                "status": "unavailable",
                "module_event_group_count": None,
                "recurring_group_count": None,
                "included_group_count": 0,
                "omitted_group_count": 0,
                "omitted_recurring_group_count": None,
                "maximum_included_groups": _MAX_EXPORTED_GROUPS,
                "overflow_remediation": None,
            }
            time_window = {
                "log_file_dates": {"status": "unavailable", "start": None, "end": None},
                "timestamp_utc": {"status": "unavailable", "start": None, "end": None},
            }
            producer_shas: list[str] = []
            producer_sha_count = 0
        else:
            attempted_all: list[int] = []
            retained_all: list[int] = []
            all_limits: list[int] = []
            within_all = 0
            over_all = 0
            groups = []
            for (module, event), group in sorted(
                self._groups.items(),
                key=lambda item: (-len(item[1]["attempted"]), item[0][0], item[0][1]),
            ):
                attempted_values = list(group["attempted"])
                retained_values = list(group["retained"])
                limits = list(group["limits"])
                attempted_all.extend(attempted_values)
                retained_all.extend(retained_values)
                all_limits.extend(limits)
                within_count = int(group["within_limit_count"])
                over_count = int(group["over_limit_count"])
                within_all += within_count
                over_all += over_count
                run_ids = group["run_ids"]
                identity_status = str(group["identity_status"])
                count = len(attempted_values)
                recurring = (
                    count >= _RECURRING_REDUCTION_THRESHOLD
                    and identity_status == "available"
                )
                groups.append(
                    {
                        "module": module,
                        "event": event,
                        "identity_status": identity_status,
                        "reduction_count": count,
                        "distinct_run_count": len(run_ids),
                        "attempted_size_bytes": _percentiles(attempted_values),
                        "retained_event_size_bytes": _percentiles(retained_values),
                        "retained_budget": _budget_summary(
                            limits, within_count, over_count
                        ),
                        "recurring": recurring,
                        "remediation": {
                            "owner_role": "module owner",
                            "owner_reference": module,
                            "remediation_reference": (
                                "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                                "and-remediate-recurring-callers"
                            ),
                        }
                        if recurring
                        else None,
                    }
                )
            reduction_count = len(attempted_all)
            status = "available" if reduction_count else "zero"
            issues: list[str] = []
            if unreadable:
                issues.append("unreadable_log_files")
            if self._malformed_structured_line_count:
                issues.append("malformed_structured_lines")
            if self._invalid_reduction_metadata_count:
                issues.append("invalid_reduction_metadata")
            all_group_count = len(groups)
            all_recurring_group_count = sum(1 for group in groups if group["recurring"])
            omitted_groups = groups[_MAX_EXPORTED_GROUPS:]
            omitted_recurring_group_count = sum(
                1 for group in omitted_groups if group["recurring"]
            )
            if omitted_groups:
                issues.append("group_inventory_truncated")
            groups = groups[:_MAX_EXPORTED_GROUPS]
            if issues:
                status = "partial"
                unavailable_reason = ",".join(issues)
            attempted_summary = _percentiles(attempted_all)
            retained_summary = _percentiles(retained_all)
            budget = _budget_summary(all_limits, within_all, over_all)
            structured_count = self._structured_event_count
            malformed_count = self._malformed_structured_line_count
            invalid_metadata_count = self._invalid_reduction_metadata_count
            time_window = {
                "log_file_dates": {
                    "status": "observed" if self._dates else "unavailable",
                    "start": min(self._dates) if self._dates else None,
                    "end": max(self._dates) if self._dates else None,
                },
                "timestamp_utc": {
                    "status": "observed" if self._timestamps else "unavailable",
                    "start": min(
                        self._timestamps,
                        key=lambda value: datetime.fromisoformat(value),
                    )
                    if self._timestamps
                    else None,
                    "end": max(
                        self._timestamps,
                        key=lambda value: datetime.fromisoformat(value),
                    )
                    if self._timestamps
                    else None,
                },
            }
            producer_shas = sorted(self._producer_shas)[:_MAX_EXPORTED_PRODUCER_SHAS]
            producer_sha_count = len(self._producer_shas)
            group_summary = {
                "status": "partial" if issues else "available",
                "module_event_group_count": all_group_count,
                "recurring_group_count": all_recurring_group_count,
                "included_group_count": len(groups),
                "omitted_group_count": len(omitted_groups),
                "omitted_recurring_group_count": omitted_recurring_group_count,
                "maximum_included_groups": _MAX_EXPORTED_GROUPS,
                "overflow_remediation": {
                    "owner_role": "module owners",
                    "owner_reference": "omitted module/event groups",
                    "remediation_reference": (
                        "CONSOLIDATED_TODO.md#r6-review-bounded-log-reduction-telemetry-"
                        "and-remediate-recurring-callers"
                    ),
                }
                if omitted_recurring_group_count
                else None,
            }

        payload: LogReductionScorecard = {
            "schema_version": "1.0",
            "status": status,
            "evidence_run_id": self._evidence_run_id,
            "repository_commit_sha": self._repository_commit_sha,
            "availability_reason": unavailable_reason,
            "corpus": {
                "log_files_scanned": scanned,
                "log_files_unreadable": unreadable,
                "structured_event_count": structured_count,
                "malformed_structured_line_count": malformed_count,
                "invalid_reduction_metadata_count": invalid_metadata_count,
            },
            "time_window": time_window,
            "build_identity": {
                "collector_commit_sha": self._repository_commit_sha,
                "producer_status": "observed" if producer_sha_count else "unavailable",
                "producer_commit_shas": producer_shas,
                "producer_commit_sha_count": producer_sha_count,
            },
            "reduction_count": reduction_count,
            "attempted_size_bytes": attempted_summary,
            "retained_event_size_bytes": retained_summary,
            "retained_budget": budget,
            "recurring_threshold": {
                "minimum_reductions_per_module_event": _RECURRING_REDUCTION_THRESHOLD,
                "basis": "same validated module/event pair in the scanned corpus",
            },
            "group_summary": group_summary,
            "groups": groups,  # type: ignore[typeddict-item]
            "automatic_remediation": False,
        }
        return validate_log_reduction_scorecard(payload)
