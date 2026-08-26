"""Run pytest while retaining one bounded timing record for each test call."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass(eq=False)
class PytestTelemetryCollector:
    """Pytest plugin that keeps only scalar per-test execution facts."""

    _records: list[dict[str, int | str]] = field(default_factory=list)

    def record(self, *, nodeid: str, duration_seconds: float, outcome: str) -> None:
        self._records.append(
            {
                "nodeid": str(nodeid),
                "duration_ms": max(0, round(float(duration_seconds) * 1000)),
                "outcome": str(outcome),
                "resource_status": "unavailable",
            }
        )

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            self.record(
                nodeid=report.nodeid,
                duration_seconds=report.duration,
                outcome=report.outcome,
            )

    def payload(
        self,
        *,
        total_run_duration_ms: int | None = None,
        pytest_exit_code: int | None = None,
        repository_commit_sha: str | None = None,
        evidence_run_id: str | None = None,
    ) -> dict[str, object]:
        records = sorted(self._records, key=lambda item: str(item["nodeid"]))
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "test_count": len(records),
            "tests": records,
        }
        if total_run_duration_ms is not None:
            payload["total_run_duration_ms"] = max(0, int(total_run_duration_ms))
        if pytest_exit_code is not None:
            payload["pytest_exit_code"] = int(pytest_exit_code)
        if repository_commit_sha is not None:
            payload["repository_commit_sha"] = str(repository_commit_sha)
        if evidence_run_id is not None:
            payload["evidence_run_id"] = str(evidence_run_id)
        return payload


def parse_runner_args(argv: list[str] | None = None) -> tuple[str, str, str, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run pytest and retain scalar per-test timings."
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--repository-commit-sha", required=True)
    parser.add_argument("--evidence-run-id", required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    pytest_args = list(args.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    return (
        str(args.output_json),
        str(args.repository_commit_sha),
        str(args.evidence_run_id),
        pytest_args,
    )


def main(argv: list[str] | None = None) -> int:
    output_json, repository_commit_sha, evidence_run_id, pytest_args = (
        parse_runner_args(argv)
    )
    collector = PytestTelemetryCollector()
    started_ns = time.monotonic_ns()
    exit_code = pytest.main(pytest_args, plugins=[collector])
    total_run_duration_ms = max(
        0, round((time.monotonic_ns() - started_ns) / 1_000_000)
    )
    output = Path(output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            collector.payload(
                total_run_duration_ms=total_run_duration_ms,
                pytest_exit_code=exit_code,
                repository_commit_sha=repository_commit_sha,
                evidence_run_id=evidence_run_id,
            ),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
