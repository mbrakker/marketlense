from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence, cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.policy import (  # noqa: E402
    DEFAULT_POLICY_PATH,
    load_architecture_policy,
)


@dataclass(frozen=True)
class MutationTarget:
    module_path: Path
    test_paths: tuple[str, ...]
    max_mutants: int
    min_score: float
    report_module: str | None = None
    duration_weight_ms: int = 1


@dataclass(frozen=True)
class MutationCandidate:
    start: int
    end: int
    start_line: int
    end_line: int
    replacement: str
    description: str


@dataclass(frozen=True)
class MutationResult:
    target: MutationTarget
    total: int
    killed: int
    elapsed_ms: int

    @property
    def score(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.killed / self.total) * 100.0


@dataclass(frozen=True)
class MutationReport:
    schema_version: str
    min_score_default: float
    targets: list[dict[str, object]]
    metadata: dict[str, object] | None = None

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "min_score_default": self.min_score_default,
            "targets": self.targets,
        }
        if self.metadata is not None:
            payload.update(self.metadata)
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


class MutationExecutionError(RuntimeError):
    """A baseline or mutant test execution could not produce a valid verdict."""


def _threshold(env_name: str, default: float) -> float:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {env_name}: {raw}") from exc


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted mutation testing gate.")
    parser.add_argument(
        "--json-out",
        default="mutation_results.json",
        help="Path to write mutation summary JSON.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--target",
        action="append",
        default=[],
        help=(
            "Run only mutation targets whose module path or report module "
            "contains this text."
        ),
    )
    selection.add_argument(
        "--partition-index",
        type=int,
        help="Run one deterministic partition of the configured mutation targets.",
    )
    parser.add_argument("--partition-count", type=int)
    parser.add_argument("--repository-commit-sha")
    parser.add_argument("--evidence-run-id")
    args = parser.parse_args(argv)
    if args.partition_index is not None:
        if args.partition_count is None or args.partition_count < 1:
            parser.error("--partition-index requires a positive --partition-count")
        if not 0 <= args.partition_index < args.partition_count:
            parser.error("--partition-index must be within --partition-count")
        if not args.repository_commit_sha or not args.evidence_run_id:
            parser.error(
                "partitioned runs require --repository-commit-sha and --evidence-run-id"
            )
    elif args.partition_count is not None:
        parser.error("--partition-count requires --partition-index")
    return args


def _line_col_to_index(source: str, line: int, col: int) -> int:
    lines = source.splitlines(keepends=True)
    return sum(len(lines[idx]) for idx in range(line - 1)) + col


def _candidate_from_node(
    source: str, node: ast.AST, replacement: str, description: str
) -> MutationCandidate | None:
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    start_col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if not all(isinstance(v, int) for v in [start_line, end_line, start_col, end_col]):
        return None
    start_line_int = cast(int, start_line)
    end_line_int = cast(int, end_line)
    start_col_int = cast(int, start_col)
    end_col_int = cast(int, end_col)
    start = _line_col_to_index(source, start_line_int, start_col_int)
    end = _line_col_to_index(source, end_line_int, end_col_int)
    if start >= end:
        return None
    return MutationCandidate(
        start=start,
        end=end,
        start_line=start_line_int,
        end_line=end_line_int,
        replacement=replacement,
        description=description,
    )


def _collect_candidates(source: str) -> list[MutationCandidate]:
    tree = ast.parse(source)
    candidates: list[MutationCandidate] = []

    compare_map = {
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.Gt: ast.LtE,
        ast.GtE: ast.Lt,
        ast.Lt: ast.GtE,
        ast.LtE: ast.Gt,
        ast.In: ast.NotIn,
        ast.NotIn: ast.In,
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and node.ops:
            first_op = type(node.ops[0])
            mapped = compare_map.get(first_op)
            if mapped:
                compare_clone: ast.Compare = copy.deepcopy(node)
                compare_clone.ops[0] = mapped()
                candidate = _candidate_from_node(
                    source=source,
                    node=node,
                    replacement=ast.unparse(compare_clone),
                    description=f"{first_op.__name__}->{mapped.__name__}",
                )
                if candidate:
                    candidates.append(candidate)
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                bool_and_clone: ast.BoolOp = copy.deepcopy(node)
                bool_and_clone.op = ast.Or()
                candidate = _candidate_from_node(
                    source, node, ast.unparse(bool_and_clone), "And->Or"
                )
                if candidate:
                    candidates.append(candidate)
            elif isinstance(node.op, ast.Or):
                bool_or_clone: ast.BoolOp = copy.deepcopy(node)
                bool_or_clone.op = ast.And()
                candidate = _candidate_from_node(
                    source, node, ast.unparse(bool_or_clone), "Or->And"
                )
                if candidate:
                    candidates.append(candidate)
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            replacement = "False" if node.value is True else "True"
            candidate = _candidate_from_node(source, node, replacement, "BoolFlip")
            if candidate:
                candidates.append(candidate)

    unique: dict[tuple[int, int, str], MutationCandidate] = {}
    for candidate in candidates:
        unique[(candidate.start, candidate.end, candidate.replacement)] = candidate
    return list(unique.values())


def _junit_test_count(path: Path) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise MutationExecutionError(
            f"pytest produced invalid JUnit XML: {path}"
        ) from exc
    return sum(
        1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "testcase"
    )


def classify_pytest_result(
    exit_code: int,
    junit_xml_path: Path,
    *,
    expected_test_count: int | None = None,
) -> str:
    """Classify complete test-call failures as kills and execution errors as invalid."""

    try:
        root = ET.parse(junit_xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise MutationExecutionError(
            f"pytest produced invalid JUnit XML: {junit_xml_path}"
        ) from exc
    test_count = sum(
        1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "testcase"
    )
    if test_count <= 0:
        raise MutationExecutionError("pytest collected no target tests")
    skipped_count = sum(
        1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "skipped"
    )
    if skipped_count >= test_count:
        raise MutationExecutionError("pytest executed no target tests")
    if expected_test_count is not None and test_count != expected_test_count:
        raise MutationExecutionError(
            f"pytest collected {test_count} tests; expected {expected_test_count}"
        )

    failures = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "failure"
    ]
    errors = [
        element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "error"
    ]
    if exit_code == 0:
        if failures or errors:
            raise MutationExecutionError(
                "pytest exited successfully but JUnit XML contains failures or errors"
            )
        return "survived"
    if exit_code != 1 or errors or not failures:
        raise MutationExecutionError(
            f"pytest exited {exit_code} without a failure-only test report"
        )
    return "killed"


def _run_tests(
    test_paths: Sequence[str], junit_xml_path: Path, expected_test_count: int
) -> str:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not integration",
        "-q",
        f"--junitxml={junit_xml_path}",
        *test_paths,
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return classify_pytest_result(
        result.returncode,
        junit_xml_path,
        expected_test_count=expected_test_count,
    )


def _target_module_coverage_lines(target: MutationTarget) -> tuple[set[int], int]:
    module_rel = target.module_path.relative_to(ROOT).as_posix().lower()
    with TemporaryDirectory(prefix="mutation_cov_", dir=ROOT) as tmp_dir:
        tmp_path = Path(tmp_dir)
        data_path = tmp_path / ".coverage"
        json_path = tmp_path / "coverage.json"
        junit_path = tmp_path / "baseline.xml"
        run_cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--data-file",
            str(data_path),
            "--source",
            "src",
            "-m",
            "pytest",
            "-m",
            "not integration",
            "-q",
            f"--junitxml={junit_path}",
            *target.test_paths,
        ]
        run_result = subprocess.run(
            run_cmd,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            baseline_status = classify_pytest_result(run_result.returncode, junit_path)
        except MutationExecutionError as exc:
            raise MutationExecutionError(
                f"unmutated target suite failed for {module_rel}: {exc}"
            ) from exc
        if baseline_status != "survived":
            raise MutationExecutionError(
                f"unmutated target suite did not pass for {module_rel}"
            )
        expected_test_count = _junit_test_count(junit_path)
        json_cmd = [
            sys.executable,
            "-m",
            "coverage",
            "json",
            "--data-file",
            str(data_path),
            "-o",
            str(json_path),
        ]
        json_result = subprocess.run(
            json_cmd,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if json_result.returncode != 0 or not json_path.exists():
            raise MutationExecutionError(
                "coverage JSON export failed for "
                f"{module_rel}: {json_result.stdout[-2000:]}"
            )
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MutationExecutionError(
                f"coverage JSON is malformed for {module_rel}"
            ) from exc
    files = payload.get("files", {})
    if not isinstance(files, dict):
        raise MutationExecutionError(
            f"coverage JSON has no files mapping for {module_rel}"
        )
    for file_path, details in files.items():
        normalized_file = str(file_path).replace("\\", "/").lower()
        if not normalized_file.endswith(module_rel):
            continue
        if not isinstance(details, dict):
            raise MutationExecutionError(
                f"coverage entry is malformed for {module_rel}"
            )
        executed = details.get("executed_lines")
        if not isinstance(executed, list):
            raise MutationExecutionError(
                f"coverage lines are malformed for {module_rel}"
            )
        return (
            {int(line) for line in executed if isinstance(line, int)},
            expected_test_count,
        )
    return set(), expected_test_count


def _filter_candidates_by_coverage(
    candidates: list[MutationCandidate], covered_lines: set[int]
) -> list[MutationCandidate]:
    if not covered_lines:
        return candidates
    filtered = [
        candidate
        for candidate in candidates
        if any(
            line_no in covered_lines
            for line_no in range(candidate.start_line, candidate.end_line + 1)
        )
    ]
    return filtered or candidates


def _run_target(target: MutationTarget) -> MutationResult:
    started_ns = time.perf_counter_ns()
    source = target.module_path.read_text(encoding="utf-8")
    candidates = _collect_candidates(source)
    covered_lines, expected_test_count = _target_module_coverage_lines(target)
    candidates = _filter_candidates_by_coverage(candidates, covered_lines)
    candidates = candidates[: target.max_mutants]
    if not candidates:
        return MutationResult(
            target=target,
            total=0,
            killed=0,
            elapsed_ms=round((time.perf_counter_ns() - started_ns) / 1_000_000),
        )

    killed = 0
    try:
        with TemporaryDirectory(prefix="mutation_run_", dir=ROOT) as tmp_dir:
            junit_dir = Path(tmp_dir)
            for index, candidate in enumerate(candidates, start=1):
                mutated = (
                    source[: candidate.start]
                    + candidate.replacement
                    + source[candidate.end :]
                )
                target.module_path.write_text(mutated, encoding="utf-8")
                status = _run_tests(
                    target.test_paths,
                    junit_dir / f"mutant-{index}.xml",
                    expected_test_count,
                )
                print(
                    f"  - {target.module_path.as_posix()} "
                    f"mutant {index}/{len(candidates)} "
                    f"[{candidate.description} @L{candidate.start_line}-"
                    f"L{candidate.end_line}] => {status}",
                    flush=True,
                )
                if status == "killed":
                    killed += 1
    finally:
        target.module_path.write_text(source, encoding="utf-8")

    return MutationResult(
        target=target,
        total=len(candidates),
        killed=killed,
        elapsed_ms=round((time.perf_counter_ns() - started_ns) / 1_000_000),
    )


def _mutation_policy() -> dict[str, object]:
    policy = load_architecture_policy(DEFAULT_POLICY_PATH)
    raw_policy = policy.get("mutation")
    return raw_policy if isinstance(raw_policy, dict) else {}


def _target_min_score(path: str, default: float) -> float:
    policy = _mutation_policy()
    raw_scores = policy.get("target_min_scores")
    scores = raw_scores if isinstance(raw_scores, dict) else {}
    raw = scores.get(path, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def configured_mutation_targets() -> tuple[MutationTarget, ...]:
    """Return the canonical mutation inventory and measured partition weights."""

    # Seed weights are per-target timings from Ubuntu 24.04/CPython 3.12.15,
    # measured in run 38211776311 at SHA 29fb1fb9f401f9a914b4c3298558f59a5ee6f872.
    return (
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "publish_queue_orchestrator.py",
            test_paths=("tests/test_publish_queue_orchestrator.py",),
            max_mutants=4,
            min_score=50.0,
            duration_weight_ms=12_377,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "taxonomy_generator.py",
            test_paths=("tests/test_taxonomy_generator.py",),
            max_mutants=4,
            min_score=75.0,
            duration_weight_ms=28_526,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "evidence_pack_generator.py",
            test_paths=("tests/test_evidence_pack_generator.py",),
            max_mutants=3,
            min_score=60.0,
            duration_weight_ms=29_142,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "generators"
            / "_artifact_generator"
            / "generation.py",
            test_paths=("tests/test_artifact_generator.py",),
            max_mutants=3,
            min_score=60.0,
            report_module="src/generators/artifact_generator.py",
            duration_weight_ms=58_409,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "validation_generator.py",
            test_paths=("tests/test_validation_generator.py",),
            max_mutants=3,
            min_score=60.0,
            duration_weight_ms=44_052,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "report_card_projection.py",
            test_paths=(
                "tests/test_report_card_projection.py",
                "tests/test_cover_geometry_selection.py",
            ),
            max_mutants=6,
            min_score=80.0,
            duration_weight_ms=27_744,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "cover_image_generator.py",
            test_paths=("tests/test_cover_image_generator.py",),
            max_mutants=4,
            min_score=75.0,
            duration_weight_ms=23_237,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "report_render_generator.py",
            test_paths=(
                "tests/test_report_render_generator.py",
                "tests/test_report_render_generator_metadata_governance.py",
            ),
            max_mutants=4,
            min_score=75.0,
            duration_weight_ms=48_912,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "publish_generator.py",
            test_paths=("tests/test_publish_generator.py",),
            max_mutants=4,
            min_score=_target_min_score("src/generators/publish_generator.py", 85.0),
            duration_weight_ms=36_434,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "services" / "_llm_service" / "vector_store.py",
            test_paths=("tests/test_openai_vector_store.py",),
            max_mutants=3,
            min_score=60.0,
            report_module="src/services/llm_service.py",
            duration_weight_ms=28_905,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "services"
            / "_drive_service"
            / "client_cache.py",
            test_paths=("tests/test_drive_service_threading.py",),
            max_mutants=3,
            min_score=60.0,
            report_module="src/services/drive_service.py",
            duration_weight_ms=26_106,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "services"
            / "_wordpress_service"
            / "transport.py",
            test_paths=("tests/test_wordpress_service.py",),
            max_mutants=3,
            min_score=60.0,
            report_module="src/services/wordpress_service.py",
            duration_weight_ms=15_081,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "report_pipeline_orchestrator.py",
            test_paths=(
                "tests/test_report_pipeline_orchestrator.py",
                "tests/test_publish_readiness_refresh.py",
            ),
            max_mutants=3,
            min_score=60.0,
            duration_weight_ms=45_571,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "orchestrators" / "retry_orchestrator.py",
            test_paths=(
                "tests/test_retry_decision_contract.py",
                "tests/test_orchestrator_retry.py",
            ),
            max_mutants=6,
            min_score=80.0,
            duration_weight_ms=71_190,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "pipeline_preflight_orchestrator.py",
            test_paths=(
                "tests/test_pipeline_preflight_orchestrator.py",
                "tests/test_report_pipeline_orchestrator.py",
            ),
            max_mutants=6,
            min_score=_target_min_score(
                "src/orchestrators/pipeline_preflight_orchestrator.py", 90.0
            ),
            duration_weight_ms=80_316,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "retry_telemetry_orchestrator.py",
            test_paths=(
                "tests/test_retry_decision_telemetry.py",
                "tests/test_run_health_scorecard.py",
            ),
            max_mutants=6,
            min_score=_target_min_score(
                "src/orchestrators/retry_telemetry_orchestrator.py", 90.0
            ),
            duration_weight_ms=27_248,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "workflow_control_orchestrator.py",
            test_paths=(
                "tests/test_workflow_control_orchestrator.py",
                "tests/test_report_pipeline_orchestrator.py",
            ),
            max_mutants=6,
            min_score=_target_min_score(
                "src/orchestrators/workflow_control_orchestrator.py", 90.0
            ),
            duration_weight_ms=80_209,
        ),
    )


def _targets() -> list[MutationTarget]:
    """Keep the original mutation inventory helper for existing callers."""

    return list(configured_mutation_targets())


def partition_targets(
    targets: Sequence[MutationTarget], *, partition_count: int
) -> tuple[tuple[MutationTarget, ...], ...]:
    """Balance targets deterministically using observed whole-target runtimes."""

    if partition_count <= 0 or partition_count > len(targets):
        raise ValueError("partition_count must be between one and the target count")
    target_ids = [target.module_path.relative_to(ROOT).as_posix() for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("mutation target inventory contains duplicate modules")
    if any(
        isinstance(target.duration_weight_ms, bool) or target.duration_weight_ms <= 0
        for target in targets
    ):
        raise ValueError("mutation target duration weights must be positive integers")

    groups: list[list[MutationTarget]] = [[] for _ in range(partition_count)]
    group_weights = [0] * partition_count
    ordered = sorted(
        targets,
        key=lambda target: (
            -target.duration_weight_ms,
            target.module_path.relative_to(ROOT).as_posix(),
        ),
    )
    for target in ordered:
        index = min(
            range(partition_count), key=lambda part: (group_weights[part], part)
        )
        groups[index].append(target)
        group_weights[index] += target.duration_weight_ms
    return tuple(tuple(group) for group in groups)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    raw_default = _mutation_policy().get("default_min_score", 60.0)
    try:
        default_min_score = float(raw_default)
    except (TypeError, ValueError):
        default_min_score = 60.0
    min_score = _threshold("MUTATION_MIN_SCORE", default_min_score)
    print(f"Mutation gate: min score {min_score:.2f}%")
    targets = list(configured_mutation_targets())
    metadata: dict[str, object] | None = None
    if args.partition_index is not None:
        partitions = partition_targets(
            targets, partition_count=int(args.partition_count)
        )
        targets = list(partitions[args.partition_index])
        metadata = {
            "partition_index": args.partition_index,
            "partition_count": args.partition_count,
            "repository_commit_sha": args.repository_commit_sha,
            "evidence_run_id": args.evidence_run_id,
        }
    if args.target:
        filters = tuple(str(item) for item in args.target)
        targets = [
            target
            for target in targets
            if any(
                item in target.module_path.as_posix()
                or (target.report_module is not None and item in target.report_module)
                for item in filters
            )
        ]
        if not targets:
            raise SystemExit(
                "No mutation targets matched filters: " + ", ".join(filters)
            )
    worker_started_ns = time.perf_counter_ns()
    try:
        results = [_run_target(target) for target in targets]
    except MutationExecutionError as exc:
        print(f"Mutation execution failed: {exc}", file=sys.stderr)
        return 2
    worker_elapsed_ms = round((time.perf_counter_ns() - worker_started_ns) / 1_000_000)

    failed = []
    report_targets: list[dict[str, object]] = []
    print("Mutation summary:")
    for result in results:
        rel = (
            result.target.report_module
            or result.target.module_path.relative_to(ROOT).as_posix()
        )
        print(
            f"  - {rel}: {result.killed}/{result.total} killed "
            f"({result.score:.2f}%, {result.elapsed_ms} ms)"
        )
        required_score = max(min_score, result.target.min_score)
        report_targets.append(
            {
                "module": rel,
                "killed": result.killed,
                "total": result.total,
                "score": round(result.score, 4),
                "min_score": required_score,
                "elapsed_ms": result.elapsed_ms,
            }
        )
        if result.total <= 0:
            failed.append(f"{rel}: no mutation candidates generated")
            continue
        if result.score < required_score:
            failed.append(f"{rel}: score {result.score:.2f}% < {required_score:.2f}%")

    if metadata is not None:
        metadata["worker_elapsed_ms"] = worker_elapsed_ms
    report = MutationReport(
        schema_version="1.0",
        min_score_default=min_score,
        targets=report_targets,
        metadata=metadata,
    )
    output_path = Path(args.json_out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json() + "\n", encoding="utf-8")
    print(f"Mutation report written: {args.json_out}")

    if failed:
        print("\nMutation gate failed:")
        for issue in failed:
            print(f"  - {issue}")
        return 1

    print("\nMutation gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
