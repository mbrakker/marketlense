from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BACKLOG = "CONSOLIDATED_TODO.md"
ARCHIVED_BACKLOG_DOCS = ("docs/quality/deep-analysis-x10-plan-2026-04-15.md",)
ACTIVE_BACKLOG_PATTERNS = (
    re.compile(r"^- \*\*Title:\*\* ", re.MULTILINE),
    re.compile(r"^\s*- \[ \] ", re.MULTILINE),
    re.compile(r"^\s*- Acceptance Criteria:", re.MULTILINE),
    re.compile(r"^## Priority Launch Plan$", re.MULTILINE),
)


@dataclass(frozen=True)
class BacklogSourceViolation:
    path: str
    reason: str


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def list_tracked_markdown() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return tuple(
        _normalize(path)
        for path in result.stdout.decode("utf-8").split("\0")
        if path.strip()
    )


def _is_ignored(path: str) -> bool:
    return (
        path in {CANONICAL_BACKLOG, "simplification.md"}
        or path.startswith("tools/")
        or path.startswith("docs/superpowers/plans/")
        or path.startswith("docs/superpowers/specs/")
    )


def validate_backlog_sources(
    paths: Iterable[str],
    *,
    root: Path,
) -> tuple[BacklogSourceViolation, ...]:
    violations: list[BacklogSourceViolation] = []
    canonical = root / CANONICAL_BACKLOG
    if not canonical.exists():
        violations.append(
            BacklogSourceViolation(
                path=CANONICAL_BACKLOG,
                reason="canonical backlog file is missing",
            )
        )
    readme = root / "README.md"
    if readme.exists() and CANONICAL_BACKLOG not in readme.read_text(encoding="utf-8"):
        violations.append(
            BacklogSourceViolation(
                path="README.md",
                reason="README does not point contributors to CONSOLIDATED_TODO.md",
            )
        )

    for archived_path in ARCHIVED_BACKLOG_DOCS:
        full_path = root / archived_path
        if not full_path.exists():
            violations.append(
                BacklogSourceViolation(
                    path=archived_path,
                    reason="archived backlog source is missing",
                )
            )
            continue
        header = "\n".join(full_path.read_text(encoding="utf-8").splitlines()[:12])
        if "consolidated into `CONSOLIDATED_TODO.md`" not in header:
            violations.append(
                BacklogSourceViolation(
                    path=archived_path,
                    reason="archived backlog source lacks consolidation notice",
                )
            )

    for raw_path in paths:
        path = _normalize(raw_path)
        if _is_ignored(path):
            continue
        full_path = root / path
        if not full_path.exists():
            continue
        text = full_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in ACTIVE_BACKLOG_PATTERNS:
            if pattern.search(text):
                violations.append(
                    BacklogSourceViolation(
                        path=path,
                        reason=(
                            f"active backlog pattern found outside {CANONICAL_BACKLOG}"
                        ),
                    )
                )
                break
    return tuple(violations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce CONSOLIDATED_TODO.md as the only active backlog source."
    )
    return parser.parse_args()


def main() -> int:
    _parse_args()
    try:
        violations = validate_backlog_sources(list_tracked_markdown(), root=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Backlog source gate failed to run: {exc}")
        return 2
    if not violations:
        print("Backlog source gate passed.")
        return 0
    print("Backlog source gate failed:")
    for item in violations:
        print(f"  - {item.path}: {item.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
