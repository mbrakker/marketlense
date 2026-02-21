from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MutationTarget:
    module_path: Path
    test_paths: tuple[str, ...]
    max_mutants: int


@dataclass(frozen=True)
class MutationCandidate:
    start: int
    end: int
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


def _threshold(env_name: str, default: float) -> float:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {env_name}: {raw}") from exc


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
    start = _line_col_to_index(source, start_line, start_col)  # type: ignore[arg-type]
    end = _line_col_to_index(source, end_line, end_col)  # type: ignore[arg-type]
    if start >= end:
        return None
    return MutationCandidate(
        start=start, end=end, replacement=replacement, description=description
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


def _run_target(target: MutationTarget) -> MutationResult:
    source = target.module_path.read_text(encoding="utf-8")
    candidates = _collect_candidates(source)[: target.max_mutants]
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
                f"[{candidate.description}] => {status}"
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
        ),
        MutationTarget(
            module_path=ROOT / "src" / "generators" / "taxonomy_generator.py",
            test_paths=("tests/test_taxonomy_generator.py",),
            max_mutants=4,
        ),
    ]


def main() -> int:
    min_score = _threshold("MUTATION_MIN_SCORE", 50.0)
    print(f"Mutation gate: min score {min_score:.2f}%")
    results = [_run_target(target) for target in _targets()]

    failed = []
    print("Mutation summary:")
    for result in results:
        rel = result.target.module_path.relative_to(ROOT).as_posix()
        print(f"  - {rel}: {result.killed}/{result.total} killed ({result.score:.2f}%)")
        if result.total <= 0:
            failed.append(f"{rel}: no mutation candidates generated")
            continue
        if result.score < min_score:
            failed.append(f"{rel}: score {result.score:.2f}% < {min_score:.2f}%")

    if failed:
        print("\nMutation gate failed:")
        for issue in failed:
            print(f"  - {issue}")
        return 1

    print("\nMutation gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
