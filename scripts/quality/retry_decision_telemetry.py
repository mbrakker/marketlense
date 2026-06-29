from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.orchestrators.retry_telemetry_orchestrator import (
    build_retry_decision_telemetry,
)


def _event_payloads(lines: Iterable[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build retry-decision telemetry from structured JSON logs."
    )
    parser.add_argument("log_path", help="Structured JSON log path.")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--max-exhaustion-rate", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payloads = _event_payloads(
        Path(args.log_path).read_text(encoding="utf-8").splitlines()
    )
    report = build_retry_decision_telemetry(payloads)
    encoded = report.to_json()
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded, encoding="utf-8")
    print(encoded)
    if (
        args.max_exhaustion_rate is not None
        and report.retry_exhaustion_rate > args.max_exhaustion_rate
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
