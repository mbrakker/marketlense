from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    column: int
    message: str


def _iter_test_files() -> Iterable[Path]:
    yield from sorted(TESTS_DIR.rglob("test_*.py"))
    conftest = TESTS_DIR / "conftest.py"
    if conftest.exists():
        yield conftest


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_private_attr(name: str | None) -> bool:
    return bool(name and name.startswith("_"))


def _is_contract_constructor_target(path: str) -> bool:
    if not path.startswith("src.contracts."):
        return False
    target = path.rsplit(".", 1)[-1]
    return bool(target and target[0].isupper())


def _check_call(path: Path, node: ast.Call) -> list[Violation]:
    violations: list[Violation] = []
    call_name = _call_name(node.func)

    if call_name.endswith("monkeypatch.setattr"):
        attr_name: str | None = None
        if len(node.args) >= 2:
            attr_name = _constant_str(node.args[1])
            if attr_name is None:
                target_expr = _constant_str(node.args[0])
                if target_expr and "." in target_expr:
                    attr_name = target_expr.rsplit(".", 1)[-1]
        if _is_private_attr(attr_name):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"forbidden private monkeypatch target: {attr_name}",
                )
            )
        return violations

    is_patch_call = call_name.endswith("patch")
    is_patch_object_call = call_name.endswith("patch.object")
    if not is_patch_call and not is_patch_object_call:
        return violations

    if is_patch_call and node.args:
        target = _constant_str(node.args[0])
        if target:
            attr_name = target.rsplit(".", 1)[-1]
            if _is_private_attr(attr_name):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        column=node.col_offset + 1,
                        message=f"forbidden private patch target: {target}",
                    )
                )
            if _is_contract_constructor_target(target):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        column=node.col_offset + 1,
                        message=f"forbidden dataclass constructor patch target: {target}",
                    )
                )

    if is_patch_object_call and len(node.args) >= 2:
        attr_name = _constant_str(node.args[1])
        if _is_private_attr(attr_name):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    column=node.col_offset + 1,
                    message=f"forbidden private patch.object target: {attr_name}",
                )
            )

    return violations


def _scan_file(path: Path) -> list[Violation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            violations.extend(_check_call(path, node))
    return violations


def main() -> int:
    violations: list[Violation] = []
    for path in _iter_test_files():
        violations.extend(_scan_file(path))

    if not violations:
        print("Forbidden patching gate passed.")
        return 0

    print("Forbidden patching gate failed:")
    for item in sorted(violations, key=lambda x: (str(x.path), x.line, x.column)):
        relative = item.path.relative_to(ROOT).as_posix()
        print(f"  - {relative}:{item.line}:{item.column} {item.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
