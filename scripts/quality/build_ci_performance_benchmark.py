"""Build a bounded CI benchmark without treating parallel work as workflow wall time."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MEASUREMENT_PROFILE_HASH = "ci:pytest-and-quality-gates:v2"
REQUIRED_QUALITY_STAGES = (
    "coverage",
    "mutation",
    "quality_non_regression",
    "pdf_candidate_benchmark",
    "pdf_crop_refine_benchmark",
    "pdf_benchmark_trends",
    "public_report_quality",
    "llm_routing_retained_benchmark",
    "workflow_queue_evidence",
    "prompt_fixture_regression",
)
_TEST_OUTCOMES = frozenset({"passed", "failed", "skipped"})
_RESOURCE_STATUSES = frozenset({"unavailable", "not_applicable", "observed"})


def build_benchmark(
    *, test_telemetry: dict[str, Any], command_telemetry: dict[str, Any]
) -> dict[str, Any]:
    """Combine pytest and quality telemetry, retaining validation diagnostics."""

    errors = validate_test_telemetry(test_telemetry)
    errors.extend(validate_command_telemetry(command_telemetry))
    tests = _objects(test_telemetry.get("tests"))
    stage_records = _objects(command_telemetry.get("stages"))
    test_duration = _non_negative_int(test_telemetry.get("total_run_duration_ms"))
    quality_stage_summaries = [
        _stage_summary(stage, index=index) for index, stage in enumerate(stage_records)
    ]
    quality_stage_summaries.sort(key=lambda stage: stage["stage"])

    test_summary = {
        "total": len(test_telemetry.get("tests", []))
        if isinstance(test_telemetry.get("tests"), list)
        else 0,
        "passed": sum(1 for test in tests if test.get("outcome") == "passed"),
        "failed": sum(1 for test in tests if test.get("outcome") == "failed"),
    }
    quality_command_duration = sum(
        stage["wall_time_ms"]
        for stage in quality_stage_summaries
        if isinstance(stage["wall_time_ms"], int)
        and not isinstance(stage["wall_time_ms"], bool)
    )
    aggregate_command_duration = (
        test_duration + quality_command_duration if test_duration is not None else None
    )
    quality_passed = (
        not errors
        and type(test_telemetry.get("pytest_exit_code")) is int
        and test_telemetry.get("pytest_exit_code") == 0
        and test_summary["failed"] == 0
        and all(
            stage.get("outcome") == "passed" and stage.get("exit_code") == 0
            for stage in quality_stage_summaries
        )
    )

    return {
        "schema_version": "1.0",
        "repository_commit_sha": _string_or_empty(
            test_telemetry.get("repository_commit_sha")
        ),
        "evidence_run_id": _string_or_empty(test_telemetry.get("evidence_run_id")),
        "measurement_profile_hash": MEASUREMENT_PROFILE_HASH,
        # Compatibility alias: this remains the pytest session duration only.
        "total_run_duration_ms": test_duration,
        "pytest_duration_ms": test_duration,
        "quality_command_duration_ms": quality_command_duration,
        "aggregate_command_duration_ms": aggregate_command_duration,
        # The release-evidence job cannot know these until the workflow completes.
        "workflow_elapsed_ms": None,
        "workflow_critical_path_ms": None,
        "workflow_timing_status": "pending_completed_github_actions_timestamps",
        "estimated_cost_usd": None,
        "quality_passed": quality_passed,
        "passed": quality_passed,
        "test_summary": test_summary,
        "quality_stage_summaries": quality_stage_summaries,
        "quality_validation_errors": errors,
    }


def validate_test_telemetry(payload: dict[str, Any]) -> list[str]:
    """Return bounded issue codes for incomplete or contradictory pytest evidence."""

    errors: list[str] = []
    _append_load_error(errors, payload, "test_telemetry")
    if payload.get("schema_version") != "1.0":
        errors.append("test_telemetry_schema_version_invalid")

    sha = payload.get("repository_commit_sha")
    if (
        not isinstance(sha, str)
        or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", sha) is None
    ):
        errors.append("repository_commit_sha_missing_or_invalid")
    run_id = payload.get("evidence_run_id")
    if not isinstance(run_id, str) or not run_id.strip() or run_id != run_id.strip():
        errors.append("evidence_run_id_missing_or_invalid")

    test_count = payload.get("test_count")
    tests = payload.get("tests")
    if _non_negative_int(test_count) is None:
        errors.append("test_count_missing_or_invalid")
    if not isinstance(tests, list):
        errors.append("test_records_missing_or_invalid")
        tests = []
    elif not tests:
        errors.append("test_records_empty")
    if _non_negative_int(test_count) is not None and test_count != len(tests):
        errors.append("test_count_mismatch")

    if _non_negative_int(payload.get("total_run_duration_ms")) is None:
        errors.append("pytest_duration_missing_or_invalid")
    exit_code = payload.get("pytest_exit_code")
    if type(exit_code) is not int:
        errors.append("pytest_exit_code_missing_or_invalid")

    failed_count = 0
    for index, record in enumerate(tests):
        if not isinstance(record, dict):
            errors.append(f"test_record_invalid:{index}")
            continue
        nodeid = record.get("nodeid")
        duration = record.get("duration_ms")
        outcome = record.get("outcome")
        resource_status = record.get("resource_status")
        if not isinstance(nodeid, str) or not nodeid.strip():
            errors.append(f"test_nodeid_invalid:{index}")
        if _non_negative_int(duration) is None:
            errors.append(f"test_duration_invalid:{index}")
        if not isinstance(outcome, str) or outcome not in _TEST_OUTCOMES:
            errors.append(f"test_outcome_invalid:{index}")
        elif outcome == "failed":
            failed_count += 1
        if (
            not isinstance(resource_status, str)
            or resource_status not in _RESOURCE_STATUSES
        ):
            errors.append(f"test_resource_status_invalid:{index}")
    if exit_code == 0 and failed_count:
        errors.append("pytest_exit_code_outcome_mismatch")
    if failed_count:
        errors.append(f"pytest_failed_tests:{failed_count}")
    if type(exit_code) is int and exit_code != 0:
        errors.append("pytest_exit_code_nonzero")
    return errors


def validate_command_telemetry(payload: dict[str, Any]) -> list[str]:
    """Validate command telemetry against the exact CI workflow producer inventory."""

    errors: list[str] = []
    _append_load_error(errors, payload, "command_telemetry")
    if payload.get("schema_version") != "1.0":
        errors.append("command_telemetry_schema_version_invalid")

    stage_count = payload.get("stage_count")
    stages = payload.get("stages")
    if not isinstance(stages, list):
        errors.append("quality_stages_missing_or_invalid")
        stages = []
    if _non_negative_int(stage_count) is None:
        errors.append("quality_stage_count_missing_or_invalid")
    elif stage_count != len(stages):
        errors.append("quality_stage_count_mismatch")

    seen: set[str] = set()
    for index, record in enumerate(stages):
        if not isinstance(record, dict):
            errors.append(f"quality_stage_invalid:{index}")
            continue
        stage_name = record.get("stage")
        if not isinstance(stage_name, str) or not stage_name.strip():
            errors.append(f"quality_stage_identity_invalid:{index}")
            stage_name = ""
        if stage_name not in REQUIRED_QUALITY_STAGES:
            errors.append(f"quality_stage_identity_unexpected:{index}")
        elif stage_name in seen:
            errors.append(f"quality_stage_identity_duplicate:{stage_name}")
        else:
            seen.add(stage_name)

        wall_time_ms = record.get("wall_time_ms")
        exit_code = record.get("exit_code")
        outcome = record.get("outcome")
        resource_status = record.get("resource_status")
        if _non_negative_int(wall_time_ms) is None:
            errors.append(f"quality_stage_duration_invalid:{index}")
        if type(exit_code) is not int:
            errors.append(f"quality_stage_exit_code_invalid:{index}")
        if not isinstance(outcome, str) or outcome not in {"passed", "failed"}:
            errors.append(f"quality_stage_outcome_invalid:{index}")
        elif type(exit_code) is int and (exit_code == 0) != (outcome == "passed"):
            errors.append(f"quality_stage_exit_code_outcome_mismatch:{index}")
        if outcome == "failed" or (type(exit_code) is int and exit_code != 0):
            errors.append(f"quality_stage_failed:{stage_name or index}")
        if (
            not isinstance(resource_status, str)
            or resource_status not in _RESOURCE_STATUSES
        ):
            errors.append(f"quality_stage_resource_status_invalid:{index}")

    for stage_name in REQUIRED_QUALITY_STAGES:
        if stage_name not in seen:
            errors.append(f"quality_stage_missing:{stage_name}")
    return errors


def benchmark_validation_errors(
    payload: dict[str, Any], *, test_telemetry: dict[str, Any] | None = None
) -> list[str]:
    """Check the passing benchmark contract consumed by release summary and review."""

    errors: list[str] = []
    if payload.get("schema_version") != "1.0":
        errors.append("benchmark_schema_version_invalid")
    if payload.get("measurement_profile_hash") != MEASUREMENT_PROFILE_HASH:
        errors.append("benchmark_measurement_profile_invalid")
    if payload.get("passed") is not True or payload.get("quality_passed") is not True:
        errors.append("benchmark_not_passed")
    validation_errors = payload.get("quality_validation_errors")
    if validation_errors != []:
        errors.append("benchmark_validation_errors_missing_or_nonempty")

    summaries = payload.get("quality_stage_summaries")
    if not isinstance(summaries, list):
        errors.append("benchmark_quality_stage_summaries_missing_or_invalid")
        summaries = []
    seen: set[str] = set()
    for index, stage in enumerate(summaries):
        if not isinstance(stage, dict):
            errors.append(f"benchmark_quality_stage_invalid:{index}")
            continue
        name = stage.get("stage")
        if not isinstance(name, str) or name not in REQUIRED_QUALITY_STAGES:
            errors.append(f"benchmark_quality_stage_identity_invalid:{index}")
            continue
        if name in seen:
            errors.append(f"benchmark_quality_stage_duplicate:{name}")
        seen.add(name)
        if _non_negative_int(stage.get("wall_time_ms")) is None:
            errors.append(f"benchmark_quality_stage_duration_invalid:{index}")
        if type(stage.get("exit_code")) is not int or stage.get("exit_code") != 0:
            errors.append(f"benchmark_quality_stage_exit_code_invalid:{index}")
        if stage.get("outcome") != "passed":
            errors.append(f"benchmark_quality_stage_outcome_invalid:{index}")
        resource_status = stage.get("resource_status")
        if (
            not isinstance(resource_status, str)
            or resource_status not in _RESOURCE_STATUSES
        ):
            errors.append(f"benchmark_quality_stage_resource_status_invalid:{index}")
    for name in REQUIRED_QUALITY_STAGES:
        if name not in seen:
            errors.append(f"benchmark_quality_stage_missing:{name}")

    test_summary = payload.get("test_summary")
    if not isinstance(test_summary, dict):
        errors.append("benchmark_test_summary_missing_or_invalid")
    else:
        total = _non_negative_int(test_summary.get("total"))
        passed = _non_negative_int(test_summary.get("passed"))
        failed = _non_negative_int(test_summary.get("failed"))
        if total is None or passed is None or failed is None:
            errors.append("benchmark_test_summary_counts_invalid")
        elif total == 0 or passed + failed > total:
            errors.append("benchmark_test_summary_counts_inconsistent")
        elif payload.get("quality_passed") is True and failed != 0:
            errors.append("benchmark_test_summary_failed_tests")
        if test_telemetry is not None:
            tests = test_telemetry.get("tests")
            if isinstance(tests, list):
                expected_summary = {
                    "total": len(tests),
                    "passed": sum(
                        1
                        for test in tests
                        if isinstance(test, dict) and test.get("outcome") == "passed"
                    ),
                    "failed": sum(
                        1
                        for test in tests
                        if isinstance(test, dict) and test.get("outcome") == "failed"
                    ),
                }
                if test_summary != expected_summary:
                    errors.append("benchmark_test_summary_mismatch")

    pytest_duration = _non_negative_int(payload.get("pytest_duration_ms"))
    if (
        pytest_duration is None
        or payload.get("total_run_duration_ms") != pytest_duration
    ):
        errors.append("benchmark_pytest_duration_invalid")
    if _non_negative_int(payload.get("quality_command_duration_ms")) is None:
        errors.append("benchmark_quality_command_duration_invalid")
    else:
        stage_duration = sum(
            stage["wall_time_ms"]
            for stage in summaries
            if isinstance(stage, dict)
            and _non_negative_int(stage.get("wall_time_ms")) is not None
        )
        if payload.get("quality_command_duration_ms") != stage_duration:
            errors.append("benchmark_quality_command_duration_mismatch")
    if _non_negative_int(payload.get("aggregate_command_duration_ms")) is None:
        errors.append("benchmark_aggregate_command_duration_invalid")
    elif (
        pytest_duration is not None
        and _non_negative_int(payload.get("quality_command_duration_ms")) is not None
    ):
        expected_aggregate = pytest_duration + int(
            payload["quality_command_duration_ms"]
        )
        if payload.get("aggregate_command_duration_ms") != expected_aggregate:
            errors.append("benchmark_aggregate_command_duration_mismatch")
    timing_values: list[int | None] = []
    for key in ("workflow_elapsed_ms", "workflow_critical_path_ms"):
        value = payload.get(key)
        if value is not None and _non_negative_int(value) is None:
            errors.append(f"benchmark_{key}_invalid")
        timing_values.append(_non_negative_int(value))
    workflow_elapsed, workflow_critical_path = timing_values
    timing_status = payload.get("workflow_timing_status")
    if workflow_elapsed is None and workflow_critical_path is None:
        if timing_status != "pending_completed_github_actions_timestamps":
            errors.append("benchmark_workflow_timing_status_invalid")
    elif workflow_elapsed is None or workflow_critical_path is None:
        errors.append("benchmark_workflow_timing_incomplete")
    elif timing_status != "completed_github_actions_timestamps":
        errors.append("benchmark_workflow_timing_status_invalid")
    elif workflow_critical_path > workflow_elapsed:
        errors.append("benchmark_critical_path_exceeds_workflow_elapsed")
    if payload.get("estimated_cost_usd") is not None:
        errors.append("benchmark_cost_must_be_unavailable")
    return errors


def _stage_summary(stage: dict[str, Any], *, index: int) -> dict[str, Any]:
    stage_name = stage.get("stage")
    return {
        "stage": stage_name
        if isinstance(stage_name, str) and stage_name.strip()
        else f"invalid_stage_{index}",
        "wall_time_ms": _non_negative_int(stage.get("wall_time_ms")),
        "exit_code": stage.get("exit_code")
        if type(stage.get("exit_code")) is int
        else None,
        "outcome": stage.get("outcome")
        if isinstance(stage.get("outcome"), str)
        else "invalid",
        "resource_status": stage.get("resource_status")
        if isinstance(stage.get("resource_status"), str)
        else "invalid",
    }


def _append_load_error(errors: list[str], payload: dict[str, Any], name: str) -> None:
    load_error = payload.get("_telemetry_load_error")
    if isinstance(load_error, str):
        errors.append(f"{name}_{load_error}")


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _string_or_empty(value: Any) -> str:
    return value if isinstance(value, str) else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a comparable CI performance benchmark artifact."
    )
    parser.add_argument("--test-telemetry", required=True)
    parser.add_argument("--command-telemetry", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    result = build_benchmark(
        test_telemetry=_load_json(Path(args.test_telemetry)),
        command_telemetry=_load_json(Path(args.command_telemetry)),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"_telemetry_load_error": "missing"}
    except OSError:
        return {"_telemetry_load_error": "unreadable"}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"_telemetry_load_error": "invalid_json"}
    if not isinstance(payload, dict):
        return {"_telemetry_load_error": "not_an_object"}
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
