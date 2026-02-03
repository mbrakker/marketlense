import json
import re
from datetime import datetime

# Path to the log file
LOG_FILE = "logs/market_lense_2026-02-03.log"

def parse_log_file(file_path):
    """Parse the log file and return a list of log entries with extracted timestamps."""
    log_entries = []
    timestamp_pattern = re.compile(r"^(\d{2}:\d{2}:\d{2})")

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            try:
                # Extract timestamp using regex
                match = timestamp_pattern.match(line)
                if not match:
                    continue

                timestamp_str = match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%H:%M:%S")

                # Parse the JSON part of the log entry by taking text after the last '|'
                if '|' in line:
                    json_part = line.rsplit('|', 1)[-1].strip()
                else:
                    # fallback: find first '{'
                    idx = line.find('{')
                    if idx == -1:
                        continue
                    json_part = line[idx:]

                log_entry = json.loads(json_part)
                log_entry["timestamp"] = timestamp
                log_entries.append(log_entry)
            except (ValueError, json.JSONDecodeError):
                continue
    # debug: show how many entries were parsed
    print(f"Parsed {len(log_entries)} log entries from {file_path}")
    return log_entries

def calculate_durations(log_entries):
    """Calculate durations between start and complete events."""
    events = {}
    durations = []
    unmatched_events = []

    for entry in log_entries:
        event = entry.get("event")
        task_id = entry.get("task_id")
        timestamp = entry.get("timestamp")

        if not (event and task_id and timestamp):
            continue

        if event.endswith("_start"):
            events[(task_id, event)] = timestamp
        elif event.endswith("_complete"):
            start_event = event.replace("_complete", "_start")
            start_time = events.pop((task_id, start_event), None)

            if start_time:
                duration = (timestamp - start_time).total_seconds()
                durations.append({
                    "task_id": task_id,
                    "event": event.replace("_complete", ""),
                    "duration": duration
                })
            else:
                unmatched_events.append({"task_id": task_id, "event": event, "timestamp": timestamp})

    if unmatched_events:
        print("Unmatched events:")
        for unmatched in unmatched_events:
            print(unmatched)

    return durations

def main():
    log_entries = parse_log_file(LOG_FILE)
    durations = calculate_durations(log_entries)

    print("Task Durations:")
    for duration in durations:
        print(f"Task ID: {duration['task_id']}, Event: {duration['event']}, Duration: {duration['duration']} seconds")

if __name__ == "__main__":
    main()