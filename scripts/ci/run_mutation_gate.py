from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence, cast


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MutationTarget:
    module_path: Path
    test_paths: tuple[str, ...]
    max_mutants: int
    min_score: float
    report_module: str | None = None


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

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "min_score_default": self.min_score_default,
                "targets": self.targets,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def _threshold(env_name: str, default: float) -> float:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {env_name}: {raw}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted mutation testing gate.")
    parser.add_argument(
        "--json-out",
        default="mutation_results.json",
        help="Path to write mutation summary JSON.",
    )
    return parser.parse_args()


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


def _run_tests(test_paths: Sequence[str]) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-m", "not integration", "-q", *test_paths]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode != 0


def _target_module_coverage_lines(target: MutationTarget) -> set[int]:
    module_rel = target.module_path.relative_to(ROOT).as_posix().lower()
    with TemporaryDirectory(prefix="mutation_cov_", dir=ROOT) as tmp_dir:
        tmp_path = Path(tmp_dir)
        data_path = tmp_path / ".coverage"
        json_path = tmp_path / "coverage.json"
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
        if run_result.returncode != 0:
            print(
                f"  - warning: coverage probe failed for {module_rel}; "
                "using unfiltered mutation candidates"
            )
            return set()
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
            print(
                f"  - warning: coverage json export failed for {module_rel}; "
                "using unfiltered mutation candidates"
            )
            return set()
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
    files = payload.get("files", {})
    if not isinstance(files, dict):
        return set()
    for file_path, details in files.items():
        normalized_file = str(file_path).replace("\\", "/").lower()
        if not normalized_file.endswith(module_rel):
            continue
        if not isinstance(details, dict):
            return set()
        executed = details.get("executed_lines")
        if not isinstance(executed, list):
            return set()
        return {int(line) for line in executed if isinstance(line, int)}
    return set()


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
    source = target.module_path.read_text(encoding="utf-8")
    candidates = _collect_candidates(source)
    covered_lines = _target_module_coverage_lines(target)
    candidates = _filter_candidates_by_coverage(candidates, covered_lines)
    candidates = candidates[: target.max_mutants]
    if not candidates:
        return MutationResult(target=target, total=0, killed=0)

    killed = 0
    try:
        for index, candidate in enumerate(candidates, start=1):
            mutated = (
                source[: candidate.start]
                + candidate.replacement
                + source[candidate.end :]
            )
            target.module_path.write_text(mutated, encoding="utf-8")
            is_killed = _run_tests(target.test_paths)
            status = "killed" if is_killed else "survived"
            print(
                f"  - {target.module_path.as_posix()} mutant {index}/{len(candidates)} "
                f"[{candidate.description} @L{candidate.start_line}-L{candidate.end_line}] => {status}"
            )
            if is_killed:
                killed += 1
    finally:
        target.module_path.write_text(source, encoding="utf-8")

    return MutationResult(target=target, total=len(candidates), killed=killed)


def _targets() -> Iterable[MutationTarget]:
    return [
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "publish_queue_orchestrator.py",
            test_paths=("tests/test_publish_queue_orchestrator.py",),
            max_mutants=4,
            min_score=50.0,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "taxonomy_generator.py",
            test_paths=("tests/test_taxonomy_generator.py",),
            max_mutants=4,
            min_score=75.0,
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "evidence_pack_generator.py",
            test_paths=("tests/test_evidence_pack_generator.py",),
            max_mutants=3,
            min_score=60.0,
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
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "validation_generator.py",
            test_paths=("tests/test_validation_generator.py",),
            max_mutants=3,
            min_score=60.0,
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "services"
            / "_openai_service"
            / "vector_store.py",
            test_paths=("tests/test_openai_vector_store.py",),
            max_mutants=3,
            min_score=60.0,
            report_module="src/services/openai_service.py",
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
        ),
        MutationTarget(
            module_path=ROOT
            / "src"
            / "orchestrators"
            / "report_pipeline_orchestrator.py",
            test_paths=("tests/test_report_pipeline_orchestrator.py",),
            max_mutants=3,
            min_score=60.0,
        ),
    ]


def main() -> int:
    args = _parse_args()
    min_score = _threshold("MUTATION_MIN_SCORE", 50.0)
    print(f"Mutation gate: min score {min_score:.2f}%")
    targets = list(_targets())
    results = [_run_target(target) for target in targets]

    failed = []
    report_targets: list[dict[str, object]] = []
    print("Mutation summary:")
    for result in results:
        rel = (
            result.target.report_module
            or result.target.module_path.relative_to(ROOT).as_posix()
        )
        print(f"  - {rel}: {result.killed}/{result.total} killed ({result.score:.2f}%)")
        required_score = max(min_score, result.target.min_score)
        report_targets.append(
            {
                "module": rel,
                "killed": result.killed,
                "total": result.total,
                "score": round(result.score, 4),
                "min_score": required_score,
            }
        )
        if result.total <= 0:
            failed.append(f"{rel}: no mutation candidates generated")
            continue
        if result.score < required_score:
            failed.append(f"{rel}: score {result.score:.2f}% < {required_score:.2f}%")

    report = MutationReport(
        schema_version="1.0",
        min_score_default=min_score,
        targets=report_targets,
    )
    Path(args.json_out).write_text(report.to_json(), encoding="utf-8")
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
