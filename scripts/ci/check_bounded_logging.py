"""Reject direct dataclass serialization into standard structured log fields."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class BoundedLoggingViolation:
    path: str
    line: int
    reason: str


def _called_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def find_direct_asdict_log_fields(
    paths: Iterable[Path],
    *,
    root: Path,
) -> tuple[BoundedLoggingViolation, ...]:
    """Find `log_event(..., fields=asdict(contract))` in first-party code."""

    violations: list[BoundedLoggingViolation] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _called_name(node.func) != "log_event":
                continue
            fields = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "fields"),
                None,
            )
            direct_asdict = any(
                isinstance(value, ast.Call) and _called_name(value.func) == "asdict"
                for value in ast.walk(fields)
            )
            if not direct_asdict:
                continue
            violations.append(
                BoundedLoggingViolation(
                    path=path.relative_to(root).as_posix(),
                    line=fields.lineno,
                    reason=(
                        "direct fields=asdict(...) serializes a complete contract; "
                        "log an explicit bounded scalar summary instead"
                    ),
                )
            )
    return tuple(violations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject complete first-party contracts in standard structured logs."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root to scan (default: repository root).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    violations = find_direct_asdict_log_fields(
        root.joinpath("src").rglob("*.py"), root=root
    )
    if not violations:
        print("Bounded logging gate passed.")
        return 0
    print("Bounded logging gate failed:")
    for violation in violations:
        print(f"  - {violation.path}:{violation.line}: {violation.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
