from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

LOG_FILE = "logs/market_lense_2026-02-03.log"
THRESHOLD_SECONDS = 30
OUT_DIR = Path("logs")

_TIMESTAMP_PATTERN = re.compile(r"^(\d{2}:\d{2}:\d{2})")


def parse_log_file(file_path: str | Path) -> list[dict[str, Any]]:
    """Parse log lines and attach parsed timestamps to each JSON event payload."""
    path = Path(file_path)
    log_entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                match = _TIMESTAMP_PATTERN.match(line)
                if not match:
                    continue
                timestamp = datetime.strptime(match.group(1), "%H:%M:%S")

                if "|" in line:
                    json_part = line.rsplit("|", 1)[-1].strip()
                else:
                    start_idx = line.find("{")
                    if start_idx == -1:
                        continue
                    json_part = line[start_idx:]

                log_entry = json.loads(json_part)
                if not isinstance(log_entry, dict):
                    continue
                log_entry["timestamp"] = timestamp
                log_entries.append(log_entry)
            except (ValueError, json.JSONDecodeError):
                continue
    print(f"Parsed {len(log_entries)} log entries from {path}")
    return log_entries


def calculate_durations(log_entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate duration in seconds for *_start and *_complete event pairs."""
    events: dict[tuple[str, str], datetime] = {}
    durations: list[dict[str, Any]] = []
    unmatched_events: list[dict[str, Any]] = []

    for entry in log_entries:
        event = entry.get("event")
        task_id = entry.get("task_id")
        timestamp = entry.get("timestamp")
        if not (
            isinstance(event, str)
            and isinstance(task_id, str)
            and isinstance(timestamp, datetime)
        ):
            continue

        if event.endswith("_start"):
            events[(task_id, event)] = timestamp
        elif event.endswith("_complete"):
            start_event = event.replace("_complete", "_start")
            start_time = events.pop((task_id, start_event), None)
            if start_time is None:
                unmatched_events.append(
                    {"task_id": task_id, "event": event, "timestamp": timestamp}
                )
                continue
            durations.append(
                {
                    "task_id": task_id,
                    "event": event.replace("_complete", ""),
                    "duration": (timestamp - start_time).total_seconds(),
                }
            )

    if unmatched_events:
        print("Unmatched events:")
        for unmatched in unmatched_events:
            print(unmatched)

    return durations


def filter_long_events(
    durations: Iterable[dict[str, Any]], threshold_seconds: int
) -> list[dict[str, Any]]:
    """Keep and sort events where duration is at least the provided threshold."""
    long_events = [
        row
        for row in durations
        if float(row.get("duration", 0) or 0) >= threshold_seconds
    ]
    return sorted(long_events, key=lambda row: -float(row.get("duration", 0) or 0))


def write_long_event_reports(
    long_events: list[dict[str, Any]],
    *,
    threshold_seconds: int,
    out_dir: Path = OUT_DIR,
) -> tuple[Path, Path]:
    """Persist filtered duration rows as CSV and JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"long_events_{threshold_seconds}s.csv"
    json_path = out_dir / f"long_events_{threshold_seconds}s.json"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["task_id", "event", "duration"])
        writer.writeheader()
        for row in long_events:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(long_events, file, indent=2)

    return csv_path, json_path


def main_calculate(log_file: str | Path = LOG_FILE) -> None:
    log_entries = parse_log_file(log_file)
    durations = calculate_durations(log_entries)

    print("Task Durations:")
    for duration in durations:
        print(
            f"Task ID: {duration['task_id']}, Event: {duration['event']}, "
            f"Duration: {duration['duration']} seconds"
        )


def main_filter(
    threshold_seconds: int = THRESHOLD_SECONDS,
    top_n: int = 100,
    log_file: str | Path = LOG_FILE,
    out_dir: Path = OUT_DIR,
) -> None:
    log_entries = parse_log_file(log_file)
    durations = calculate_durations(log_entries)
    long_events_sorted = filter_long_events(durations, threshold_seconds)
    write_long_event_reports(
        long_events_sorted,
        threshold_seconds=threshold_seconds,
        out_dir=out_dir,
    )

    print(f"Filtered {len(long_events_sorted)} events >= {threshold_seconds}s")
    for row in long_events_sorted[:top_n]:
        print(
            f"Task ID: {row['task_id']}, Event: {row['event']}, "
            f"Duration: {row['duration']}s"
        )
