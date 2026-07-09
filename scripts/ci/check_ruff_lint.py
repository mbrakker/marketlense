from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.policy import DEFAULT_POLICY_PATH, load_architecture_policy  # noqa: E402


def _policy_list(section: dict[str, object], key: str, default: list[str]) -> list[str]:
    raw = section.get(key)
    if not isinstance(raw, list):
        return default
    values = [str(item).strip() for item in raw if str(item).strip()]
    return values or default


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
    policy = load_architecture_policy(DEFAULT_POLICY_PATH)
    ruff_policy = policy.get("ruff")
    ruff_section = ruff_policy if isinstance(ruff_policy, dict) else {}
    configured_paths = os.getenv("RUFF_LINT_PATHS", "").strip().split()
    policy_paths = _policy_list(ruff_section, "paths", ["src", "tests", "scripts"])
    paths = configured_paths or (
        policy_paths
        if os.getenv("RUFF_LINT_ALL", "").strip().lower() in {"1", "true", "yes"}
        else _git_changed_python_files(policy_paths)
    )
    if not paths:
        print("Ruff lint gate: no changed Python files detected; skipping.")
        return 0
    selected_rules = _policy_list(ruff_section, "selected_rules", ["E", "F", "I"])
    initial_rules = _policy_list(ruff_section, "initial_enforced_rules", ["F"])
    rules = (
        selected_rules
        if os.getenv("RUFF_LINT_ALL", "").strip().lower() in {"1", "true", "yes"}
        else initial_rules
    )
    cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--select",
        ",".join(rules),
        *paths,
    ]
    print("Ruff lint gate:")
    print("  " + " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
