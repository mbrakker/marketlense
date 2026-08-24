"""Produce deterministic completion evidence from a MarketLense working-tree diff.

This development-only command selects existing checks.  It does not approve
work based on an LLM response and it does not recreate the CI quality sequence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
HIGH_RISK_PATHS = (
    ".github/",
    "AGENTS.md",
    "Wordpress/",
    "pyproject.toml",
    "requirements",
    "scripts/ci/",
    "src/config/",
    "src/orchestrators/",
    "src/prompts/",
    "src/services/",
    "docs/quality/architecture_policy.yaml",
)
ROLE_ROOTS = (
    "src/contracts/",
    "src/generators/",
    "src/orchestrators/",
    "src/services/",
)


@dataclass(frozen=True)
class ChangeClassification:
    subsystems: tuple[str, ...]
    risk: str
    full_gate_required: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CheckExecution:
    check: Check
    returncode: int
    elapsed_ms: int


def _check_payload(check: Check) -> dict[str, object]:
    return {
        "name": check.name,
        "command": list(check.command),
        "environment": dict(check.environment),
    }


def build_completion_report(
    *,
    changed_files: tuple[str, ...],
    classification: ChangeClassification,
    selected_checks: tuple[Check, ...],
    executions: tuple[CheckExecution, ...],
    working_tree_unchanged: bool,
) -> dict[str, object]:
    """Return a PASS only when deterministic requirements all completed cleanly."""
    failures: list[str] = []
    unverified: list[str] = []
    executed_by_name = {execution.check.name: execution for execution in executions}
    if not changed_files:
        failures.append("no changed files to verify")
    for check in selected_checks:
        execution = executed_by_name.get(check.name)
        if execution is None:
            unverified.append(f"required check was not run: {check.name}")
        elif execution.returncode != 0:
            failures.append(
                f"{check.name} failed with exit code {execution.returncode}"
            )
    if not working_tree_unchanged:
        failures.append("working tree changed while checks ran")
    result = "PASS" if not failures and not unverified else "FAIL"
    executions_payload = [
        {
            **_check_payload(execution.check),
            "returncode": execution.returncode,
            "elapsed_ms": execution.elapsed_ms,
        }
        for execution in executions
    ]
    tests_run = [item for item in executions_payload if "pytest" in item["command"]]
    return {
        "schema_version": "1.0",
        "result": result,
        "summary": (
            f"{result}: {len(changed_files)} changed file(s), "
            f"{len(executions)} required check(s) executed, "
            f"{len(failures)} failure(s), {len(unverified)} unverified requirement(s)."
        ),
        "changed_files": list(changed_files),
        "classification": {
            "subsystems": list(classification.subsystems),
            "risk": classification.risk,
            "reasons": list(classification.reasons),
        },
        "selected_checks": [_check_payload(check) for check in selected_checks],
        "tests_run": tests_run,
        "failures": failures,
        "unverified_requirements": unverified,
        "full_gate_required": classification.full_gate_required,
        "working_tree_unchanged": working_tree_unchanged,
    }


def _git_output(command: tuple[str, ...], *, root: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout


def discover_changed_files(*, root: Path, base: str) -> tuple[str, ...]:
    """Return diff and untracked paths without treating ignored state as code."""
    diff_paths = _git_output(
        ("git", "diff", "--name-only", "--diff-filter=ACMRUXB", base, "--"),
        root=root,
    ).splitlines()
    untracked_paths = _git_output(
        ("git", "ls-files", "--others", "--exclude-standard"), root=root
    ).splitlines()
    return tuple(
        sorted({path.replace("\\", "/") for path in (*diff_paths, *untracked_paths)})
    )


def _working_tree_signature(*, root: Path) -> str:
    return _git_output(("git", "status", "--porcelain=v1"), root=root)


def _execute_check(check: Check) -> CheckExecution:
    environment = os.environ.copy()
    environment.update(dict(check.environment))
    started = time.monotonic()
    completed = subprocess.run(
        check.command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return CheckExecution(
        check=check, returncode=completed.returncode, elapsed_ms=elapsed_ms
    )


def run_selected_checks(
    checks: tuple[Check, ...],
    *,
    execute: Callable[[Check], CheckExecution] = _execute_check,
) -> tuple[CheckExecution, ...]:
    """Run required checks in order and stop once PASS is impossible."""
    executions: list[CheckExecution] = []
    for check in checks:
        execution = execute(check)
        executions.append(execution)
        if execution.returncode != 0:
            break
    return tuple(executions)


def run_completion_gate(*, root: Path, base: str) -> dict[str, object]:
    before = _working_tree_signature(root=root)
    changed_files = discover_changed_files(root=root, base=base)
    classification = classify_changes(changed_files)
    checks = select_checks(classification, changed_files)
    executions = run_selected_checks(checks)
    after = _working_tree_signature(root=root)
    return build_completion_report(
        changed_files=changed_files,
        classification=classification,
        selected_checks=checks,
        executions=executions,
        working_tree_unchanged=before == after,
    )


def classify_changes(changed_files: tuple[str, ...]) -> ChangeClassification:
    """Classify changed paths using the repository's current ownership layout."""
    subsystems: set[str] = set()
    reasons: list[str] = []
    for path in changed_files:
        if path.startswith("docs/") or path.endswith(".md"):
            subsystems.add("documentation")
        if path.startswith("tests/"):
            subsystems.add("tests")
        if path.startswith("scripts/"):
            subsystems.add("development_tooling")
        if path.startswith("src/"):
            subsystems.add("application_code")
        if path.startswith("src/contracts/"):
            subsystems.add("contracts")
        if path.startswith("src/services/"):
            subsystems.add("service_boundary")
        if path.startswith("src/orchestrators/"):
            subsystems.add("workflow_orchestration")
        if path.startswith("src/generators/"):
            subsystems.add("generation")
        if path.startswith("src/prompts/"):
            subsystems.add("llm_prompt_pipeline")
        if path.startswith("src/config/"):
            subsystems.add("operator_configuration")
        if path.startswith("Wordpress/"):
            subsystems.add("wordpress_publication")
        if path.startswith("scripts/ci/"):
            subsystems.add("quality_gate")
        if path == "AGENTS.md" or path.startswith("docs/quality/architecture_policy"):
            subsystems.add("agent_policy")
        if any(path == marker or path.startswith(marker) for marker in HIGH_RISK_PATHS):
            reasons.append(f"high_risk_path:{path}")

    return ChangeClassification(
        subsystems=tuple(sorted(subsystems)),
        risk="high" if reasons else "focused",
        full_gate_required=bool(reasons),
        reasons=tuple(sorted(reasons)),
    )


def _targeted_test_paths(changed_files: tuple[str, ...]) -> tuple[str, ...]:
    candidates: set[str] = {
        path
        for path in changed_files
        if path.startswith("tests/") and path.endswith(".py")
    }
    for path in changed_files:
        if not path.startswith("src/") or not path.endswith(".py"):
            continue
        candidate = f"tests/test_{Path(path).stem}.py"
        if (ROOT / candidate).is_file():
            candidates.add(candidate)
    return tuple(sorted(candidates))


def select_checks(
    classification: ChangeClassification, changed_files: tuple[str, ...]
) -> tuple[Check, ...]:
    """Select existing checks at the lowest credible scope for the diff."""
    selected: list[Check] = []
    changed_python = any(path.endswith(".py") for path in changed_files)
    changed_docs = any(
        path.startswith("docs/") or path.endswith(".md") for path in changed_files
    )
    changed_roles = any(path.startswith(ROLE_ROOTS) for path in changed_files)
    test_paths = _targeted_test_paths(changed_files)

    if changed_python:
        selected.append(Check("ruff", ("python", "scripts/ci/check_ruff_lint.py")))
    if any(path.startswith("src/") and path.endswith(".py") for path in changed_files):
        selected.append(
            Check(
                "type_check_changed_source",
                ("python", "scripts/ci/run_type_check.py"),
                (("TYPECHECK_CHANGED_ONLY", "1"),),
            )
        )
    if changed_roles:
        selected.append(
            Check(
                "architecture_imports",
                ("python", "scripts/ci/check_architecture_imports.py"),
            )
        )
        selected.append(
            Check(
                "role_io_boundaries",
                ("python", "scripts/ci/check_role_io_boundaries.py"),
            )
        )
    if "service_boundary" in classification.subsystems:
        selected.append(
            Check(
                "service_boundary_map",
                ("python", "scripts/ci/check_service_boundary_map.py"),
            )
        )
    if "contracts" in classification.subsystems:
        selected.append(
            Check(
                "contract_schemas",
                (
                    "python",
                    "scripts/ci/check_contract_schemas.py",
                    "--snapshot",
                    "docs/quality/contract_schemas.json",
                ),
            )
        )
    if "llm_prompt_pipeline" in classification.subsystems:
        selected.append(
            Check(
                "prompt_fixture_regression",
                (
                    "python",
                    "scripts/ci/check_prompt_fixture_regression.py",
                    "--baseline",
                    "docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json",
                    "--config",
                    "src/config/app.yaml",
                    "--iterations",
                    "3",
                ),
            )
        )
    if changed_docs:
        selected.append(
            Check(
                "documentation",
                ("python", "scripts/ci/check_documentation.py", "--check-generated"),
            )
        )
    if test_paths:
        selected.append(
            Check("focused_pytest", ("python", "-m", "pytest", "-q", *test_paths))
        )
    elif changed_python:
        selected.append(Check("default_pytest", ("python", "-m", "pytest", "-q")))
    if classification.full_gate_required:
        selected.append(
            Check(
                "canonical_quality_gate", ("python", "scripts/ci/run_quality_gate.py")
            )
        )
    return tuple(selected)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="HEAD",
        help="Git revision used as the completion-gate diff base (default: HEAD).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = run_completion_gate(root=ROOT, base=args.base)
    except RuntimeError as error:
        report = {
            "schema_version": "1.0",
            "result": "FAIL",
            "summary": "FAIL: completion gate could not inspect the working tree.",
            "changed_files": [],
            "selected_checks": [],
            "tests_run": [],
            "failures": [str(error)],
            "unverified_requirements": ["working-tree inspection"],
            "full_gate_required": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
