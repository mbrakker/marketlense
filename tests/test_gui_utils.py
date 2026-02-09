from __future__ import annotations

from src.utils.gui_utils import (
    compute_task_duration_rollups,
    extract_log_date_from_filename,
    filter_log_events,
    parse_structured_log_line,
    safe_json_loads,
    status_chip_level,
)


def test_status_chip_level_maps_known_states() -> None:
    assert status_chip_level("processed") == "success"
    assert status_chip_level("warning") == "warn"
    assert status_chip_level("error") == "error"
    assert status_chip_level("unknown") == "info"


def test_extract_log_date_from_filename() -> None:
    assert extract_log_date_from_filename("logs/market_lense_2026-02-09.log") == "2026-02-09"
    assert extract_log_date_from_filename("logs/other.log") is None


def test_parse_structured_log_line_with_payload() -> None:
    line = '12:01:02 | INFO | market_lense.test | {"run_id":"r1","task_id":"t1","span_id":"s1","event":"ingest_start","role":"orchestrator","module":"m","fields":{}}'
    parsed = parse_structured_log_line(line, log_date="2026-02-09")
    assert parsed is not None
    assert parsed["run_id"] == "r1"
    assert parsed["event"] == "ingest_start"
    assert parsed["timestamp_utc"].startswith("2026-02-09T12:01:02")


def test_filter_log_events_by_dimensions() -> None:
    rows = [
        {"run_id": "r1", "task_id": "t1", "span_id": "s1", "event": "ingest_start", "role": "orchestrator", "module": "a"},
        {"run_id": "r2", "task_id": "t2", "span_id": "s2", "event": "publish_start", "role": "orchestrator", "module": "b"},
    ]
    filtered = filter_log_events(rows, run_id="r2")
    assert len(filtered) == 1
    assert filtered[0]["event"] == "publish_start"


def test_compute_task_duration_rollups_groups_rows() -> None:
    rows = [
        {"run_id": "r1", "task_id": "t1", "timestamp_utc": "2026-02-09T10:00:00"},
        {"run_id": "r1", "task_id": "t1", "timestamp_utc": "2026-02-09T10:00:05"},
        {"run_id": "r2", "task_id": "t2", "timestamp_utc": "2026-02-09T11:00:00"},
        {"run_id": "r2", "task_id": "t2", "timestamp_utc": "2026-02-09T11:00:02"},
    ]
    rollups = compute_task_duration_rollups(rows)
    assert len(rollups) == 2
    assert rollups[0]["duration_seconds"] == 5
    assert rollups[0]["event_count"] == 2


def test_safe_json_loads_returns_none_on_invalid_input() -> None:
    assert safe_json_loads("{") is None
    assert safe_json_loads('{"ok":1}') == {"ok": 1}
