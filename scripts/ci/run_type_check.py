from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
MYPY_CONFIG = ROOT / "mypy.ini"


def _within_roots(rel_path: str, roots: Iterable[str]) -> bool:
    normalized = rel_path.replace("\\", "/").lstrip("./")
    for root in roots:
        prefix = root.replace("\\", "/").rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def _git_changed_python_files(roots: list[str]) -> list[str]:
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

    diff_output = ""
    commands = [["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"]]
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
            ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD~1..HEAD"],
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        ]
    )
    for command in commands:
        output = _run_git(command)
        if output:
            diff_output = output
            break

    lines = diff_output.splitlines() if diff_output else []
    untracked = _run_git(["git", "ls-files", "--others", "--exclude-standard"])
    if untracked:
        lines.extend(untracked.splitlines())
    if not lines:
        return []

    changed: list[str] = []
    for raw_line in lines:
        rel = raw_line.strip()
        if not rel.endswith(".py"):
            continue
        if not _within_roots(rel, roots):
            continue
        path = ROOT / rel
        if path.exists():
            changed.append(rel.replace("\\", "/"))
    return sorted(set(changed))


def main() -> int:
    configured_paths = os.getenv("TYPECHECK_PATHS", "").strip().split()
    targets = configured_paths or ["src", "tests", "scripts/ci"]
    changed_paths = _git_changed_python_files(targets) if not configured_paths else []

    if configured_paths:
        typecheck_targets = targets
    elif changed_paths:
        typecheck_targets = changed_paths
    else:
        print("Type gate: no changed Python files detected; skipping.")
        return 0

    print("Type gate files:")
    for path in typecheck_targets:
        print(f"  - {path}")

    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        str(MYPY_CONFIG),
        "--follow-imports=skip",
        *typecheck_targets,
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
