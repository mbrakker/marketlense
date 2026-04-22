from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"

ROLE_DIRS: dict[str, str] = {
    "contracts": "contracts",
    "services": "services",
    "generators": "generators",
    "orchestrators": "orchestrators",
    "utils": "utils",
}

FORBIDDEN_BY_ROLE: dict[str, tuple[str, ...]] = {
    "contracts": ("src.services", "src.generators", "src.orchestrators", "src.ui"),
    "utils": ("src.services", "src.generators", "src.orchestrators", "src.ui"),
    "services": ("src.generators", "src.orchestrators", "src.ui"),
    "generators": ("src.orchestrators", "src.ui"),
    "orchestrators": ("src.ui",),
}


@dataclass(frozen=True)
class ImportViolation:
    role: str
    path: Path
    line: int
    column: int
    imported: str
    rule: str


def _role_for_path(path: Path) -> str | None:
    try:
        relative = path.relative_to(SRC_ROOT)
    except ValueError:
        parts = path.parts
        if "src" not in parts:
            return None
        src_index = parts.index("src")
        first = parts[src_index + 1] if len(parts) > src_index + 1 else ""
    else:
        first = relative.parts[0] if relative.parts else ""
    for role, dirname in ROLE_DIRS.items():
        if first == dirname:
            return role
    return None


def _iter_python_files() -> Iterable[Path]:
    for dirname in ROLE_DIRS.values():
        directory = SRC_ROOT / dirname
        if directory.exists():
            yield from sorted(directory.rglob("*.py"))


def _imported_modules(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name, node.lineno, node.col_offset + 1
    elif isinstance(node, ast.ImportFrom):
        if not node.module:
            return
        yield node.module, node.lineno, node.col_offset + 1


def _violates(imported: str, forbidden_prefixes: tuple[str, ...]) -> str | None:
    for prefix in forbidden_prefixes:
        if imported == prefix or imported.startswith(prefix + "."):
            return prefix
    return None


def scan_file(path: Path) -> list[ImportViolation]:
    role = _role_for_path(path)
    if role is None:
        return []
    forbidden = FORBIDDEN_BY_ROLE.get(role, ())
    if not forbidden:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[ImportViolation] = []
    for node in ast.walk(tree):
        for imported, line, column in _imported_modules(node):
            rule = _violates(imported, forbidden)
            if rule is None:
                continue
            violations.append(
                ImportViolation(
                    role=role,
                    path=path,
                    line=line,
                    column=column,
                    imported=imported,
                    rule=f"{role} must not import {rule}",
                )
            )
    return violations


def scan_repository() -> list[ImportViolation]:
    violations: list[ImportViolation] = []
    for path in _iter_python_files():
        violations.extend(scan_file(path))
    return violations


def main() -> int:
    violations = scan_repository()
    if not violations:
        print("Architecture import gate passed.")
        return 0

    print("Architecture import gate failed:")
    for item in sorted(violations, key=lambda x: (str(x.path), x.line, x.column)):
        rel = item.path.relative_to(ROOT).as_posix()
        print(
            f"  - {rel}:{item.line}:{item.column} imports {item.imported}; {item.rule}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
