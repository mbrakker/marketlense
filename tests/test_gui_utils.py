from __future__ import annotations

from dataclasses import dataclass

from src.utils.gui_utils import (
    coerce_editor_records,
    compute_task_duration_rollups,
    extract_log_date_from_filename,
    filter_log_events,
    mapping_from_editor_records,
    normalize_text_lines,
    parse_structured_log_line,
    pricing_from_editor_records,
    row_dicts,
    safe_json_loads,
    status_chip_level,
)


@dataclass(frozen=True)
class _RowDataclass:
    file_id: str


class _RowObject:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


def test_status_chip_level_maps_known_states() -> None:
    assert status_chip_level("processed") == "success"
    assert status_chip_level("warning") == "warn"
    assert status_chip_level("error") == "error"
    assert status_chip_level("unknown") == "info"


def test_extract_log_date_from_filename() -> None:
    assert (
        extract_log_date_from_filename("logs/market_lense_2026-02-09.log")
        == "2026-02-09"
    )
    assert extract_log_date_from_filename("logs/other.log") is None


def test_parse_structured_log_line_with_payload() -> None:
    line = '12:01:02 | INFO | market_lense.test | {"run_id":"r1","task_id":"t1","span_id":"s1","event":"ingest_start","role":"orchestrator","module":"m","fields":{}}'
    parsed = parse_structured_log_line(line, log_date="2026-02-09")
    assert parsed is not None
    assert parsed["run_id"] == "r1"
    assert parsed["event"] == "ingest_start"
    assert parsed["timestamp_utc"].startswith("2026-02-09T12:01:02")


def test_parse_structured_log_line_preserves_payload_timestamp() -> None:
    line = '12:01:02 | INFO | market_lense.test | {"run_id":"r1","task_id":"t1","span_id":"s1","timestamp_utc":"2026-02-09T12:01:02+00:00","event":"ingest_start","role":"orchestrator","module":"m","fields":{}}'
    parsed = parse_structured_log_line(line, log_date="2026-02-10")
    assert parsed is not None
    assert parsed["timestamp_utc"] == "2026-02-09T12:01:02+00:00"


def test_filter_log_events_by_dimensions() -> None:
    rows = [
        {
            "run_id": "r1",
            "task_id": "t1",
            "span_id": "s1",
            "event": "ingest_start",
            "role": "orchestrator",
            "module": "a",
        },
        {
            "run_id": "r2",
            "task_id": "t2",
            "span_id": "s2",
            "event": "publish_start",
            "role": "orchestrator",
            "module": "b",
        },
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


def test_row_dicts_serializes_dataclasses_and_dicts() -> None:
    rows = row_dicts([_RowDataclass(file_id="a"), {"file_id": "b"}])
    assert rows == [{"file_id": "a"}, {"file_id": "b"}]


def test_row_dicts_optionally_includes_object_attrs() -> None:
    assert row_dicts([_RowObject("a")]) == []
    assert row_dicts([_RowObject("a")], include_object_attrs=True) == [{"file_id": "a"}]


def test_normalize_text_lines_deduplicates_and_trims() -> None:
    lines = normalize_text_lines("  one\n\nTWO\n two \nthree")
    assert lines == ["one", "TWO", "three"]


def test_coerce_editor_records_supports_list_of_dicts() -> None:
    rows = coerce_editor_records([{"a": 1}, {"b": 2}, "skip"])
    assert rows == [{"a": 1}, {"b": 2}]


def test_mapping_from_editor_records_builds_clean_map() -> None:
    rows = [
        {"namespace": " a ", "model": " gpt-5-mini "},
        {"namespace": "", "model": "skip"},
    ]
    mapped = mapping_from_editor_records(
        rows, key_field="namespace", value_field="model"
    )
    assert mapped == {"a": "gpt-5-mini"}


def test_pricing_from_editor_records_parses_and_reports_errors() -> None:
    rows = [
        {
            "model": "gpt-5-mini",
            "input_tokens_per_1k_usd": 0.00025,
            "output_tokens_per_1k_usd": 0.002,
            "tool_call_usd": 0.0025,
        },
        {
            "model": "broken",
            "input_tokens_per_1k_usd": "x",
            "output_tokens_per_1k_usd": 0.1,
            "tool_call_usd": 0.1,
        },
    ]
    pricing, errors = pricing_from_editor_records(rows)
    assert pricing["gpt-5-mini"]["input_tokens_per_1k_usd"] == 0.00025
    assert len(errors) == 1
