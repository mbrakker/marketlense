import json
from datetime import datetime
from collections import defaultdict

# Define a function to parse timestamps
def parse_timestamp(timestamp):
    return datetime.strptime(timestamp, "%H:%M:%S")

# Define a function to calculate durations
def calculate_durations(log_entries):
    task_events = defaultdict(dict)
    durations = []

    for entry in log_entries:
        event_data = json.loads(entry)
        task_id = event_data["task_id"]
        event = event_data["event"]
        timestamp = parse_timestamp(event_data["timestamp"])

        if event.endswith("start"):
            task_events[task_id]["start"] = timestamp
        elif event.endswith("complete"):
            task_events[task_id]["complete"] = timestamp

    for task_id, events in task_events.items():
        if "start" in events and "complete" in events:
            duration = (events["complete"] - events["start"]).total_seconds()
            durations.append({"task_id": task_id, "duration": duration})

    return durations

# Sample log entries (replace with actual log data)
log_entries = [
    '{"task_id": "ingest_db_access", "event": "state_db_access_start", "timestamp": "22:03:32"}',
    '{"task_id": "ingest_db_access", "event": "state_db_access_complete", "timestamp": "22:03:33"}',
    '{"task_id": "cli_ingest", "event": "ingest_start", "timestamp": "22:03:32"}',
    '{"task_id": "cli_ingest", "event": "ingest_complete", "timestamp": "22:03:40"}'
]

# Calculate durations
durations = calculate_durations(log_entries)

# Print results
for duration in durations:
    print(f"Task ID: {duration['task_id']}, Duration: {duration['duration']} seconds")