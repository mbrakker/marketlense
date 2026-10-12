from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ci.merge_mutation_partitions import (
    merge_partition_reports,
    record_parallel_mutation_stage,
)
from scripts.ci.run_mutation_gate import (
    MutationExecutionError,
    classify_pytest_result,
    configured_mutation_targets,
    partition_targets,
)

_SHA = "a" * 40
_RUN_ID = "38183085264-1"


def _write_junit(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_pytest_assertion_failure_is_the_only_mutant_kill(tmp_path: Path) -> None:
    report = _write_junit(
        tmp_path / "assertion.xml",
        '<testsuite tests="2" failures="1" errors="0" skipped="0">'
        '<testcase classname="tests.test_target" name="test_mutated_rule">'
        '<failure type="AssertionError" message="expected true">assert False</failure>'
        '</testcase><testcase classname="tests.test_target" name="test_other"/>'
        "</testsuite>",
    )

    assert classify_pytest_result(1, report, expected_test_count=2) == "killed"


def test_pytest_test_call_exception_is_a_legitimate_mutant_kill(tmp_path: Path) -> None:
    report = _write_junit(
        tmp_path / "test-call-exception.xml",
        '<testsuite tests="1" failures="1" errors="0">'
        '<testcase name="test_mutated_behavior"><failure type="ValueError">'
        "invalid value from mutated behavior</failure></testcase></testsuite>",
    )

    assert classify_pytest_result(1, report, expected_test_count=1) == "killed"


def test_pytest_success_is_a_surviving_mutant(tmp_path: Path) -> None:
    report = _write_junit(
        tmp_path / "passed.xml",
        '<testsuite tests="2" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.test_target" name="test_one"/>'
        '<testcase classname="tests.test_target" name="test_two"/>'
        "</testsuite>",
    )

    assert classify_pytest_result(0, report, expected_test_count=2) == "survived"


@pytest.mark.parametrize(
    ("exit_code", "xml", "expected_count"),
    [
        (
            1,
            '<testsuite tests="1" failures="0" errors="1"><testcase '
            'name="test_import"><error type="ImportError">broken import</error>'
            "</testcase></testsuite>",
            1,
        ),
        (2, '<testsuite tests="0" failures="0" errors="0"/>', 0),
        (5, '<testsuite tests="0" failures="0" errors="0"/>', 0),
        (0, '<testsuite tests="0" failures="0" errors="0"/>', 0),
        (
            0,
            '<testsuite tests="1" failures="0" errors="0" skipped="1">'
            '<testcase name="skipped"><skipped/></testcase></testsuite>',
            1,
        ),
        (
            0,
            '<testsuite tests="2" failures="0" errors="0">'
            '<testcase name="one"/></testsuite>',
            2,
        ),
    ],
)
def test_pytest_collection_execution_or_count_errors_fail_closed(
    tmp_path: Path, exit_code: int, xml: str, expected_count: int
) -> None:
    report = _write_junit(tmp_path / "invalid.xml", xml)

    with pytest.raises(MutationExecutionError):
        classify_pytest_result(exit_code, report, expected_test_count=expected_count)


def test_high_minimum_scores_follow_their_own_policy_keys() -> None:
    targets = {
        target.module_path.relative_to(Path.cwd()).as_posix(): target
        for target in configured_mutation_targets()
    }

    assert (
        targets["src/orchestrators/pipeline_preflight_orchestrator.py"].min_score
        == 90.0
    )
    assert (
        targets["src/orchestrators/retry_telemetry_orchestrator.py"].min_score == 90.0
    )
    assert (
        targets["src/orchestrators/workflow_control_orchestrator.py"].min_score == 90.0
    )


@pytest.mark.parametrize("partition_count", [2, 3, 4])
def test_target_partitions_are_deterministic_disjoint_and_balanced(
    partition_count: int,
) -> None:
    targets = configured_mutation_targets()
    first = partition_targets(targets, partition_count=partition_count)
    second = partition_targets(targets, partition_count=partition_count)
    target_ids = [
        target.module_path.relative_to(Path.cwd()).as_posix()
        for partition in first
        for target in partition
    ]
    weights = [sum(target.duration_weight_ms for target in part) for part in first]

    assert first == second
    assert all(first)
    assert len(target_ids) == len(set(target_ids)) == 17
    assert set(target_ids) == {
        target.module_path.relative_to(Path.cwd()).as_posix() for target in targets
    }
    assert max(weights) <= round(min(weights) * 1.15)


def _valid_partition_reports() -> tuple[list[dict[str, object]], list[list[object]]]:
    targets = configured_mutation_targets()
    partitions = partition_targets(targets, partition_count=4)
    reports: list[dict[str, object]] = []
    for partition_index, partition in enumerate(partitions):
        rows = []
        for target in partition:
            module = (
                target.report_module
                or target.module_path.relative_to(Path.cwd()).as_posix()
            )
            rows.append(
                {
                    "module": module,
                    "killed": 1,
                    "total": 1,
                    "score": 100.0,
                    "min_score": max(60.0, target.min_score),
                    "elapsed_ms": 10,
                }
            )
        reports.append(
            {
                "schema_version": "1.0",
                "min_score_default": 60.0,
                "partition_index": partition_index,
                "partition_count": 4,
                "repository_commit_sha": _SHA,
                "evidence_run_id": _RUN_ID,
                "worker_elapsed_ms": 20,
                "targets": rows,
            }
        )
    return reports, partitions


def test_partition_reports_merge_to_the_exact_authoritative_inventory() -> None:
    reports, _ = _valid_partition_reports()

    merged = merge_partition_reports(
        reports,
        targets=configured_mutation_targets(),
        partition_count=4,
        expected_sha=_SHA,
        expected_run_id=_RUN_ID,
        worker_conclusion="success",
    )

    assert merged["schema_version"] == "1.0"
    assert merged["repository_commit_sha"] == _SHA
    assert merged["evidence_run_id"] == _RUN_ID
    assert len(merged["targets"]) == 17
    assert len({row["module"] for row in merged["targets"]}) == 17
    assert {row["module"] for row in merged["targets"]} == {
        target.report_module or target.module_path.relative_to(Path.cwd()).as_posix()
        for target in configured_mutation_targets()
    }


@pytest.mark.parametrize("corruption", ["missing_partition", "duplicate_partition"])
def test_partition_merge_rejects_incomplete_or_duplicate_workers(
    corruption: str,
) -> None:
    reports, _ = _valid_partition_reports()
    if corruption == "missing_partition":
        reports.pop()
    else:
        reports[-1] = copy.deepcopy(reports[0])

    with pytest.raises(ValueError):
        merge_partition_reports(
            reports,
            targets=configured_mutation_targets(),
            partition_count=4,
            expected_sha=_SHA,
            expected_run_id=_RUN_ID,
            worker_conclusion="success",
        )


@pytest.mark.parametrize("field", ["repository_commit_sha", "evidence_run_id"])
def test_partition_merge_rejects_wrong_execution_identity(field: str) -> None:
    reports, _ = _valid_partition_reports()
    reports[0][field] = "wrong"

    with pytest.raises(ValueError):
        merge_partition_reports(
            reports,
            targets=configured_mutation_targets(),
            partition_count=4,
            expected_sha=_SHA,
            expected_run_id=_RUN_ID,
            worker_conclusion="success",
        )


@pytest.mark.parametrize(
    "corruption", ["missing_target", "duplicate_target", "zero_mutants", "wrong_score"]
)
def test_partition_merge_rejects_malformed_target_results(corruption: str) -> None:
    reports, partitions = _valid_partition_reports()
    first_report = reports[0]
    first_target = first_report["targets"][0]
    if corruption == "missing_target":
        first_report["targets"].pop()
    elif corruption == "duplicate_target":
        first_report["targets"].append(copy.deepcopy(first_target))
    elif corruption == "zero_mutants":
        first_target["killed"] = 0
        first_target["total"] = 0
        first_target["score"] = 0.0
    else:
        first_target["score"] = 99.0

    with pytest.raises(ValueError):
        merge_partition_reports(
            reports,
            targets=configured_mutation_targets(),
            partition_count=4,
            expected_sha=_SHA,
            expected_run_id=_RUN_ID,
            worker_conclusion="success",
        )


def test_partition_merge_rejects_failed_worker_even_with_all_reports() -> None:
    reports, _ = _valid_partition_reports()

    with pytest.raises(ValueError, match="worker"):
        merge_partition_reports(
            reports,
            targets=configured_mutation_targets(),
            partition_count=4,
            expected_sha=_SHA,
            expected_run_id=_RUN_ID,
            worker_conclusion="failure",
        )


def test_parallel_mutation_duration_is_added_to_existing_quality_telemetry(
    tmp_path: Path,
) -> None:
    telemetry_path = tmp_path / "quality.json"
    telemetry_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "stage_count": 1,
                "stages": [
                    {
                        "stage": "coverage",
                        "wall_time_ms": 270,
                        "exit_code": 0,
                        "outcome": "passed",
                        "resource_status": "unavailable",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    record_parallel_mutation_stage(telemetry_path, wall_time_ms=4321)

    payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert payload["stage_count"] == 2
    assert [stage["stage"] for stage in payload["stages"]] == [
        "coverage",
        "mutation",
    ]
    assert payload["stages"][1] == {
        "stage": "mutation",
        "wall_time_ms": 4321,
        "exit_code": 0,
        "outcome": "passed",
        "resource_status": "unavailable",
    }


def test_parallel_mutation_duration_refuses_duplicate_stage(tmp_path: Path) -> None:
    telemetry_path = tmp_path / "quality.json"
    telemetry_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "stage_count": 1,
                "stages": [{"stage": "mutation", "wall_time_ms": 100}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already contains"):
        record_parallel_mutation_stage(telemetry_path, wall_time_ms=4321)


def test_mutation_ci_workflow_overlaps_tests_with_two_isolated_workers() -> None:
    import yaml

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
    )
    jobs = workflow["jobs"]

    assert jobs["tests"]["needs"] == ["ci_start"]
    assert jobs["mutation"]["needs"] == ["ci_start"]
    assert jobs["mutation"]["strategy"]["matrix"]["partition"] == [0, 1]
    assert jobs["release_evidence"]["needs"] == [
        "ci_start",
        "tests",
        "mutation",
    ]
    assert jobs["release_evidence"]["if"] == "${{ always() }}"
    for job_name in ("tests", "mutation", "release_evidence"):
        steps = jobs[job_name]["steps"]
        install = next(
            step for step in steps if step.get("name") == "Install dependencies"
        )
        setup_python = next(
            step
            for step in steps
            if step.get("uses", "").startswith("actions/setup-python@")
        )
        assert "--require-hashes -r requirements.lock" in install["run"]
        assert setup_python["with"]["cache"] == "pip"
        assert setup_python["with"]["cache-dependency-path"] == "requirements.lock"

    test_steps = jobs["tests"]["steps"]
    pytest_step = next(
        step
        for step in test_steps
        if step.get("name")
        == "Run default pytest suite with coverage and timing telemetry"
    )
    assert "-n 8 --dist=worksteal" in pytest_step["run"]
    mutation_script = "\n".join(
        step.get("run", "") for step in jobs["mutation"]["steps"]
    )
    assert "--require-hashes -r requirements.lock" in mutation_script
    assert "python scripts/ci/check_risk_policy.py" in mutation_script
    assert "--partition-index" in mutation_script
    assert "--partition-count 2" in mutation_script
    merge_script = "\n".join(
        step.get("run", "") for step in jobs["release_evidence"]["steps"]
    )
    assert "--quality-command-telemetry" in merge_script
    assert "--partition-count 2" in merge_script
    release_step_names = {
        step.get("name") for step in jobs["release_evidence"]["steps"]
    }
    assert "Quality non-regression gate" in release_step_names
    assert "Build release evidence manifest" in release_step_names
    assert "Build release evidence review" in release_step_names
    assert "Upload release evidence bundle" in release_step_names
    assert "Write release evidence job summary" in release_step_names
