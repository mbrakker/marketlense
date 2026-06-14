from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = ROOT / "docs" / "quality" / "role_io_boundary_allowlist.json"
ROLE_ROOTS = {
    "generator": Path("src/generators"),
    "utility": Path("src/utils"),
}


@dataclass(frozen=True)
class RoleIoViolation:
    path: str
    line: int
    role: str
    rule: str
    detail: str


def scan_additional_role_io(
    root: Path,
    *,
    allowlist_entries: list[dict[str, Any]],
) -> list[RoleIoViolation]:
    violations: list[RoleIoViolation] = []
    for role, relative_root in ROLE_ROOTS.items():
        directory = root / relative_root
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_path = path.relative_to(root).as_posix()
            for node in ast.walk(tree):
                violation = _node_violation(node, relative_path, role)
                if violation is None:
                    continue
                if _allowlisted(violation, allowlist_entries):
                    continue
                violations.append(violation)
    return violations


def validate_allowlist(entries: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, entry in enumerate(entries):
        for field in ("path", "rule", "owner", "expires"):
            if not str(entry.get(field) or "").strip():
                errors.append(f"entry {index} missing {field}")
        expires = str(entry.get("expires") or "")
        try:
            expiry = date.fromisoformat(expires)
        except ValueError:
            errors.append(f"entry {index} has invalid expires date")
            continue
        if expiry < date.today():
            errors.append(f"entry {index} expired on {expires}")
    return errors


def _node_violation(
    node: ast.AST,
    path: str,
    role: str,
) -> RoleIoViolation | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "PIL" or alias.name.startswith("PIL."):
                return RoleIoViolation(
                    path, node.lineno, role, "binary_media_import", alias.name
                )
    if isinstance(node, ast.ImportFrom):
        module = str(node.module or "")
        if module == "PIL" or module.startswith("PIL."):
            return RoleIoViolation(
                path, node.lineno, role, "binary_media_import", module
            )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "getenv"
        ):
            return RoleIoViolation(
                path, node.lineno, role, "environment_access", "os.getenv"
            )
    if isinstance(node, ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        ):
            return RoleIoViolation(
                path, node.lineno, role, "environment_access", "os.environ"
            )
    return None


def _allowlisted(
    violation: RoleIoViolation,
    entries: list[dict[str, Any]],
) -> bool:
    return any(
        str(entry.get("path") or "") == violation.path
        and str(entry.get("rule") or "") == violation.rule
        for entry in entries
    )


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_io_boundaries.py", "-q"],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        return completed.returncode
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        print("Role I/O allowlist must contain an entries list.")
        return 1
    errors = validate_allowlist(entries)
    violations = scan_additional_role_io(ROOT, allowlist_entries=entries)
    if errors or violations:
        print("Role I/O boundary gate failed:")
        for error in errors:
            print(f"  - allowlist: {error}")
        for item in violations:
            print(f"  - {item.path}:{item.line} {item.role} {item.rule}: {item.detail}")
        return 1
    print("Role I/O boundary gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
