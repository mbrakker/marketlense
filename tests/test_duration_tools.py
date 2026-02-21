from __future__ import annotations

import csv
import json
from datetime import datetime

from scripts.duration_tools import (
    calculate_durations,
    filter_long_events,
    parse_log_file,
    write_long_event_reports,
)


def test_parse_log_file_reads_pipe_and_brace_lines(tmp_path) -> None:
    log_path = tmp_path / "events.log"
    log_path.write_text(
        "\n".join(
            [
                '12:00:00 | {"event":"ingest_start","task_id":"task-1"}',
                '12:00:04 source={"event":"ingest_complete","task_id":"task-1"}',
                "ignored line",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_log_file(log_path)

    assert len(rows) == 2
    assert rows[0]["event"] == "ingest_start"
    assert rows[1]["event"] == "ingest_complete"
    assert isinstance(rows[0]["timestamp"], datetime)


def test_calculate_durations_pairs_start_complete_events() -> None:
    rows = [
        {
            "event": "download_start",
            "task_id": "task-1",
            "timestamp": datetime(2026, 2, 21, 12, 0, 0),
        },
        {
            "event": "download_complete",
            "task_id": "task-1",
            "timestamp": datetime(2026, 2, 21, 12, 0, 5),
        },
        {
            "event": "ingest_complete",
            "task_id": "task-2",
            "timestamp": datetime(2026, 2, 21, 12, 1, 0),
        },
    ]

    durations = calculate_durations(rows)

    assert durations == [{"task_id": "task-1", "event": "download", "duration": 5.0}]


def test_filter_long_events_and_write_reports(tmp_path) -> None:
    durations = [
        {"task_id": "task-1", "event": "download", "duration": 12.0},
        {"task_id": "task-2", "event": "download", "duration": 48.0},
        {"task_id": "task-3", "event": "ingest", "duration": 31.0},
    ]

    long_events = filter_long_events(durations, threshold_seconds=30)

    assert [row["task_id"] for row in long_events] == ["task-2", "task-3"]

    csv_path, json_path = write_long_event_reports(
        long_events,
        threshold_seconds=30,
        out_dir=tmp_path,
    )

    assert csv_path == tmp_path / "long_events_30s.csv"
    assert json_path == tmp_path / "long_events_30s.json"

    with csv_path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        csv_rows = list(reader)
    assert csv_rows[0]["task_id"] == "task-2"
    assert csv_rows[1]["task_id"] == "task-3"

    with json_path.open("r", encoding="utf-8") as file:
        json_rows = json.load(file)
    assert [row["task_id"] for row in json_rows] == ["task-2", "task-3"]
