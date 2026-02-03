from pathlib import Path
import csv
import json
import sys
import importlib.util

# load calculate_durations from the project root by file path to avoid
# importing a same-named module in this scripts/ folder
ROOT_CALC = Path(__file__).resolve().parents[1] / "calculate_durations.py"
spec = importlib.util.spec_from_file_location("calculate_durations_root", str(ROOT_CALC))
calc_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc_mod)

parse_log_file = calc_mod.parse_log_file
calculate_durations = calc_mod.calculate_durations
LOG_FILE = getattr(calc_mod, "LOG_FILE", "logs/market_lense_2026-02-03.log")

THRESHOLD_SECONDS = 30
OUT_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / f"long_events_{THRESHOLD_SECONDS}s.csv"
JSON_PATH = OUT_DIR / f"long_events_{THRESHOLD_SECONDS}s.json"


def main(threshold=THRESHOLD_SECONDS, top_n=100):
    log_entries = parse_log_file(LOG_FILE)
    durations = calculate_durations(log_entries)

    # filter
    long_events = [d for d in durations if d.get("duration", 0) >= threshold]
    long_events_sorted = sorted(long_events, key=lambda x: -x.get("duration", 0))

    # save CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "event", "duration"])
        writer.writeheader()
        for row in long_events_sorted:
            writer.writerow(row)

    # save JSON
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(long_events_sorted, f, indent=2)

    # print a short summary
    print(f"Filtered {len(long_events_sorted)} events >= {threshold}s")
    for row in long_events_sorted[:top_n]:
        print(f"Task ID: {row['task_id']}, Event: {row['event']}, Duration: {row['duration']}s")


if __name__ == '__main__':
    thr = THRESHOLD_SECONDS
    n = 50
    if len(sys.argv) > 1:
        try:
            thr = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            n = int(sys.argv[2])
        except ValueError:
            pass
    main(thr, n)
