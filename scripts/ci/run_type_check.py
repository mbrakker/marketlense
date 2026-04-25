from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MYPY_CONFIG = ROOT / "mypy.ini"
DEFAULT_BASELINE_PATH = ROOT / "docs" / "quality" / "mypy_baseline.json"
BASELINE_OWNER = "quality/type-safety"
BASELINE_EXPIRES_AT = "2026-06-30"
ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.*?)\s+\[(?P<code>[a-zA-Z0-9_-]+)\]$"
)


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


def _run_mypy(typecheck_targets: list[str]) -> tuple[int, str]:
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        str(MYPY_CONFIG),
        "--follow-imports=skip",
        "--no-pretty",
        *typecheck_targets,
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout or ""


def _parse_mypy_errors(output: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        match = ERROR_RE.match(raw_line.strip())
        if not match:
            continue
        path = match.group("path").replace("\\", "/")
        errors.append(
            {
                "path": path,
                "line": int(match.group("line")),
                "code": match.group("code"),
                "message": match.group("message").strip(),
            }
        )
    return errors


def _error_key(error: dict[str, Any]) -> str:
    return "|".join(
        [
            str(error.get("path") or ""),
            str(error.get("line") or ""),
            str(error.get("code") or ""),
            str(error.get("message") or ""),
        ]
    )


def _baseline_entries(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **error,
            "owner": BASELINE_OWNER,
            "expires_at": BASELINE_EXPIRES_AT,
        }
        for error in sorted(errors, key=_error_key)
    ]


def _load_baseline(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("errors") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"Invalid mypy baseline format: {path}")
    baseline: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            baseline.append(entry)
    return baseline


def _write_baseline(path: Path, errors: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "generated_by": "python scripts/ci/run_type_check.py --update-baseline",
        "owner": BASELINE_OWNER,
        "expires_at": BASELINE_EXPIRES_AT,
        "error_count": len(errors),
        "errors": _baseline_entries(errors),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_errors(title: str, errors: list[dict[str, Any]]) -> None:
    if not errors:
        return
    print(title)
    for error in errors[:50]:
        print(
            f"  - {error['path']}:{error['line']}: {error['message']} [{error['code']}]"
        )
    if len(errors) > 50:
        print(f"  ... {len(errors) - 50} more")


def _compare_to_baseline(
    *, current_errors: list[dict[str, Any]], baseline_errors: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_by_key = {_error_key(error): error for error in baseline_errors}
    current_by_key = {_error_key(error): error for error in current_errors}
    new_errors = [
        error for key, error in current_by_key.items() if key not in baseline_by_key
    ]
    stale_errors = [
        error for key, error in baseline_by_key.items() if key not in current_by_key
    ]
    return sorted(new_errors, key=_error_key), sorted(stale_errors, key=_error_key)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full-repo mypy with a checked-in baseline for existing debt."
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE_PATH.relative_to(ROOT)),
        help="Path to the mypy baseline JSON relative to the repository root.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match the current mypy error set.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    baseline_path = (ROOT / str(args.baseline)).resolve()
    configured_paths = os.getenv("TYPECHECK_PATHS", "").strip().split()
    changed_only = os.getenv("TYPECHECK_CHANGED_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    targets = configured_paths or ["src"]
    changed_paths = _git_changed_python_files(targets) if changed_only else []
    typecheck_targets = changed_paths if changed_paths else targets

    print("Type gate files:")
    for path in typecheck_targets:
        print(f"  - {path}")

    if changed_only and not changed_paths:
        print(
            "Type gate: no changed Python files detected; running full baseline gate."
        )
        typecheck_targets = targets

    mypy_returncode, output = _run_mypy(typecheck_targets)
    print(output, end="" if output.endswith("\n") or not output else "\n")
    current_errors = _parse_mypy_errors(output)

    if args.update_baseline:
        _write_baseline(baseline_path, current_errors)
        print(f"Type gate baseline updated: {baseline_path}")
        return 0

    baseline_errors = _load_baseline(baseline_path)
    new_errors, stale_errors = _compare_to_baseline(
        current_errors=current_errors,
        baseline_errors=baseline_errors,
    )
    if new_errors or stale_errors:
        _print_errors("Unbaselined mypy errors:", new_errors)
        _print_errors("Stale mypy baseline entries:", stale_errors)
        print(
            "Update the baseline only after triaging ownership and expiry: "
            "python scripts/ci/run_type_check.py --update-baseline"
        )
        return 1
    if mypy_returncode == 0 and current_errors:
        return 1
    print(
        "Type gate: full-repo mypy baseline matched "
        f"({len(current_errors)} tracked error(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
