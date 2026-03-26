from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Iterable


LOG_LINE_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2})\s+\|\s+(?P<level>[^|]+)\s+\|\s+(?P<logger>[^|]+)\s+\|\s+(?P<message>.*)$"
)
LOG_DATE_RE = re.compile(r"market_lense_(?P<date>\d{4}-\d{2}-\d{2})\.log$")


def status_chip_level(status: str | None) -> str:
    value = str(status or "").strip().lower()
    if value in {"processed", "published", "generated", "pass", "success", "ready", "complete", "indexed"}:
        return "success"
    if value in {"skipped", "warn", "warning", "missing", "partial"}:
        return "warn"
    if value in {"error", "failed", "fail", "blocked", "conflict"}:
        return "error"
    return "info"


def extract_log_date_from_filename(path: str) -> str | None:
    match = LOG_DATE_RE.search(path.replace("\\", "/"))
    if not match:
        return None
    return match.group("date")


def parse_structured_log_line(line: str, *, log_date: str | None = None) -> dict[str, Any] | None:
    match = LOG_LINE_RE.match(line.strip())
    if not match:
        return None
    message = str(match.group("message") or "").strip()
    if not message.startswith("{"):
        return None
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    timestamp_utc = None
    if log_date:
        try:
            parsed = datetime.fromisoformat(f"{log_date}T{match.group('time')}")
            timestamp_utc = parsed.isoformat()
        except ValueError:
            timestamp_utc = None

    event = dict(payload)
    event["level"] = str(match.group("level") or "").strip()
    event["logger_name"] = str(match.group("logger") or "").strip()
    event["timestamp_hms"] = str(match.group("time") or "").strip()
    if timestamp_utc:
        event["timestamp_utc"] = timestamp_utc
    return event


def filter_log_events(
    events: list[dict[str, Any]],
    *,
    run_id: str = "",
    task_id: str = "",
    span_id: str = "",
    event: str = "",
    role: str = "",
    module: str = "",
) -> list[dict[str, Any]]:
    run_id_q = run_id.strip()
    task_id_q = task_id.strip()
    span_id_q = span_id.strip()
    event_q = event.strip().lower()
    role_q = role.strip().lower()
    module_q = module.strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in events:
        if run_id_q and str(row.get("run_id") or "") != run_id_q:
            continue
        if task_id_q and str(row.get("task_id") or "") != task_id_q:
            continue
        if span_id_q and str(row.get("span_id") or "") != span_id_q:
            continue
        if event_q and event_q not in str(row.get("event") or "").lower():
            continue
        if role_q and role_q != str(row.get("role") or "").lower():
            continue
        if module_q and module_q not in str(row.get("module") or "").lower():
            continue
        filtered.append(row)
    return filtered


def compute_task_duration_rollups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in events:
        run_id = str(row.get("run_id") or "").strip()
        task_id = str(row.get("task_id") or "").strip()
        timestamp_raw = str(row.get("timestamp_utc") or "").strip()
        if not run_id or not task_id or not timestamp_raw:
            continue
        try:
            ts = datetime.fromisoformat(timestamp_raw)
        except ValueError:
            continue
        key = (run_id, task_id)
        acc = grouped.get(key)
        if acc is None:
            grouped[key] = {
                "run_id": run_id,
                "task_id": task_id,
                "started_at": ts,
                "ended_at": ts,
                "event_count": 1,
            }
            continue
        if ts < acc["started_at"]:
            acc["started_at"] = ts
        if ts > acc["ended_at"]:
            acc["ended_at"] = ts
        acc["event_count"] += 1

    rows: list[dict[str, Any]] = []
    for acc in grouped.values():
        duration_s = int((acc["ended_at"] - acc["started_at"]).total_seconds())
        rows.append({
            "run_id": acc["run_id"],
            "task_id": acc["task_id"],
            "started_at": acc["started_at"].isoformat(),
            "ended_at": acc["ended_at"].isoformat(),
            "duration_seconds": duration_s,
            "event_count": acc["event_count"],
        })
    rows.sort(key=lambda item: (-item["duration_seconds"], item["run_id"], item["task_id"]))
    return rows


def safe_json_loads(value: str) -> dict[str, Any] | list[Any] | None:
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def row_dicts(
    items: Iterable[Any],
    *,
    include_object_attrs: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if is_dataclass(item) and not isinstance(item, type):
            rows.append(asdict(item))
            continue
        if isinstance(item, dict):
            rows.append(item)
            continue
        if include_object_attrs and hasattr(item, "__dict__"):
            rows.append(dict(item.__dict__))
    return rows


def normalize_text_lines(value: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value.splitlines():
        token = str(raw).strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(token)
    return normalized


def coerce_editor_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if hasattr(value, "to_dict"):
        try:
            rows = value.to_dict(orient="records")
        except Exception:
            return []
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def mapping_from_editor_records(value: Any, *, key_field: str, value_field: str) -> dict[str, str]:
    rows = coerce_editor_records(value)
    mapped: dict[str, str] = {}
    for row in rows:
        key = str(row.get(key_field) or "").strip()
        mapped_value = str(row.get(value_field) or "").strip()
        if not key or not mapped_value:
            continue
        mapped[key] = mapped_value
    return mapped


def pricing_from_editor_records(value: Any) -> tuple[dict[str, dict[str, float]], list[str]]:
    rows = coerce_editor_records(value)
    pricing: dict[str, dict[str, float]] = {}
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        model = str(row.get("model") or "").strip()
        if not model:
            continue
        try:
            input_cost = float(row.get("input_tokens_per_1k_usd"))
            output_cost = float(row.get("output_tokens_per_1k_usd"))
            tool_cost = float(row.get("tool_call_usd"))
        except (TypeError, ValueError):
            errors.append(f"Row {idx} ({model}) has invalid numeric pricing values.")
            continue
        pricing[model] = {
            "input_tokens_per_1k_usd": input_cost,
            "output_tokens_per_1k_usd": output_cost,
            "tool_call_usd": tool_cost,
        }
    return pricing, errors
