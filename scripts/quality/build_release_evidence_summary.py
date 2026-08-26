"""Build a bounded release-evidence executive summary from machine evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_release_evidence_summary(
    *,
    release_id: str,
    repository_commit_sha: str,
    test_telemetry: dict[str, Any],
    ci_performance_benchmark: dict[str, Any],
) -> dict[str, Any]:
    """Derive release claims without accepting operator-provided metrics."""

    for name, payload in (
        ("test telemetry", test_telemetry),
        ("CI performance benchmark", ci_performance_benchmark),
    ):
        if payload.get("schema_version") != "1.0":
            raise ValueError(f"{name} schema_version must be 1.0")
        if payload.get("repository_commit_sha") != repository_commit_sha:
            raise ValueError(f"{name} commit SHA does not match the release")
        if payload.get("evidence_run_id") != release_id:
            raise ValueError(f"{name} run ID does not match the release")
    tests = test_telemetry.get("tests")
    if not isinstance(tests, list):
        raise ValueError("test telemetry tests must be a list")
    failed_test_count = sum(
        1
        for test in tests
        if isinstance(test, dict) and test.get("outcome") == "failed"
    )
    claims = {
        "pytest_exit_code": test_telemetry.get("pytest_exit_code"),
        "failed_test_count": failed_test_count,
        "performance_passed": ci_performance_benchmark.get("passed"),
        "performance_quality_passed": ci_performance_benchmark.get("quality_passed"),
    }
    return {
        "schema_version": "1.0",
        "repository_commit_sha": repository_commit_sha,
        "evidence_run_id": release_id,
        "release_id": release_id,
        "passed": (
            claims["pytest_exit_code"] == 0
            and failed_test_count == 0
            and claims["performance_passed"] is True
            and claims["performance_quality_passed"] is True
        ),
        "claims": claims,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a machine-derived release-evidence executive summary."
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--repository-commit-sha", required=True)
    parser.add_argument("--test-telemetry", required=True)
    parser.add_argument("--ci-performance-benchmark", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    summary = build_release_evidence_summary(
        release_id=str(args.release_id),
        repository_commit_sha=str(args.repository_commit_sha),
        test_telemetry=_read_json(Path(args.test_telemetry)),
        ci_performance_benchmark=_read_json(Path(args.ci_performance_benchmark)),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
