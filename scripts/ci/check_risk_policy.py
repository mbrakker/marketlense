from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RiskPolicy:
    name: str
    reason: str
    coverage_global_min: float
    coverage_orchestrators_min: float
    coverage_generators_min: float
    coverage_services_min: float
    mutation_min_score: float
    required_gates: tuple[str, ...]


@dataclass(frozen=True)
class RiskReport:
    changed_files: tuple[str, ...]
    policy: RiskPolicy


POLICIES: dict[str, RiskPolicy] = {
    "docs": RiskPolicy(
        name="docs",
        reason="documentation-only change",
        coverage_global_min=60.0,
        coverage_orchestrators_min=60.0,
        coverage_generators_min=60.0,
        coverage_services_min=44.0,
        mutation_min_score=50.0,
        required_gates=("format",),
    ),
    "standard": RiskPolicy(
        name="standard",
        reason="non-critical code or configuration change",
        coverage_global_min=60.0,
        coverage_orchestrators_min=60.0,
        coverage_generators_min=60.0,
        coverage_services_min=44.0,
        mutation_min_score=50.0,
        required_gates=("format", "type", "unit", "coverage"),
    ),
    "contract": RiskPolicy(
        name="contract",
        reason="contract or schema surface changed",
        coverage_global_min=62.0,
        coverage_orchestrators_min=60.0,
        coverage_generators_min=60.0,
        coverage_services_min=46.0,
        mutation_min_score=55.0,
        required_gates=(
            "format",
            "type",
            "unit",
            "contract-roundtrip",
            "contract-schema-snapshot",
            "coverage",
        ),
    ),
    "critical": RiskPolicy(
        name="critical",
        reason="critical service/generator/orchestrator path changed",
        coverage_global_min=63.0,
        coverage_orchestrators_min=63.0,
        coverage_generators_min=63.0,
        coverage_services_min=47.0,
        mutation_min_score=60.0,
        required_gates=(
            "format",
            "type",
            "unit",
            "architecture-imports",
            "coverage",
            "mutation",
            "quality-regression",
        ),
    ),
}


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def classify_changed_files(paths: Iterable[str]) -> RiskPolicy:
    normalized = tuple(sorted({_normalize(path) for path in paths if path.strip()}))
    if not normalized:
        return POLICIES["standard"]

    if any(
        path.startswith(("src/services/", "src/generators/", "src/orchestrators/"))
        for path in normalized
    ):
        return POLICIES["critical"]
    if any(path.startswith(("src/contracts/", "src/schemas/")) for path in normalized):
        return POLICIES["contract"]
    if all(
        path.startswith(("docs/", ".github/", "README.md"))
        or path.endswith((".md", ".txt"))
        for path in normalized
    ):
        return POLICIES["docs"]
    return POLICIES["standard"]


def build_report(paths: Iterable[str]) -> RiskReport:
    changed_files = tuple(sorted({_normalize(path) for path in paths if path.strip()}))
    return RiskReport(
        changed_files=changed_files,
        policy=classify_changed_files(changed_files),
    )


def _run_git(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""
    return result.stdout.strip()


def detect_changed_files() -> tuple[str, ...]:
    commands = []
    base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    if base_ref:
        commands.append(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMRTUXB",
                f"origin/{base_ref}...HEAD",
            ]
        )
    commands.extend(
        [
            ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"],
            ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD~1..HEAD"],
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        ]
    )
    for command in commands:
        output = _run_git(command)
        if output:
            return tuple(output.splitlines())
    return tuple()


def _write_github_env(policy: RiskPolicy) -> None:
    env_path = os.getenv("GITHUB_ENV", "").strip()
    if not env_path:
        return
    lines = [
        f"COVERAGE_GLOBAL_MIN={policy.coverage_global_min:.2f}",
        f"COVERAGE_ORCHESTRATORS_MIN={policy.coverage_orchestrators_min:.2f}",
        f"COVERAGE_GENERATORS_MIN={policy.coverage_generators_min:.2f}",
        f"COVERAGE_SERVICES_MIN={policy.coverage_services_min:.2f}",
        f"MUTATION_MIN_SCORE={policy.mutation_min_score:.2f}",
        f"MARKET_LENSE_RISK_POLICY={policy.name}",
    ]
    with Path(env_path).open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def main() -> int:
    raw_files = sys.argv[1:] or list(detect_changed_files())
    report = build_report(raw_files)
    policy = report.policy

    print(f"Risk policy: {policy.name} ({policy.reason})")
    print("Changed files:")
    for path in report.changed_files or ("<none detected>",):
        print(f"  - {path}")
    print("Required gates:")
    for gate in policy.required_gates:
        print(f"  - {gate}")
    print("Thresholds:")
    print(f"  - COVERAGE_GLOBAL_MIN={policy.coverage_global_min:.2f}")
    print(f"  - COVERAGE_ORCHESTRATORS_MIN={policy.coverage_orchestrators_min:.2f}")
    print(f"  - COVERAGE_GENERATORS_MIN={policy.coverage_generators_min:.2f}")
    print(f"  - COVERAGE_SERVICES_MIN={policy.coverage_services_min:.2f}")
    print(f"  - MUTATION_MIN_SCORE={policy.mutation_min_score:.2f}")
    _write_github_env(policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
