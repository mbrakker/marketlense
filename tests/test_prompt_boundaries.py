from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PROMPT_SERVICE_PATH = SRC_ROOT / "services" / "prompt_service.py"
PROMPT_NAMES = {"system_prompt", "user_prompt"}
REQUEST_PROMPT_ATTRS = {"request.system_prompt", "request.user_prompt"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    column: int
    message: str


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if path == PROMPT_SERVICE_PATH:
            continue
        yield path


def _attribute_name(node: ast.Attribute) -> str:
    parts: list[str] = [node.attr]
    value = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _references_prompt_symbol(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in PROMPT_NAMES:
            return True
        if isinstance(child, ast.Attribute):
            if _attribute_name(child) in REQUEST_PROMPT_ATTRS:
                return True
    return False


def _is_prompt_mutation_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return _references_prompt_symbol(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _references_prompt_symbol(node)
    return False


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for child in node.elts:
            names.extend(_target_names(child))
        return names
    return []


class _PromptMutationScanner(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []

    def _add(self, node: ast.AST, message: str) -> None:
        self.violations.append(
            Violation(
                path=self.path,
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0) + 1,
                message=message,
            )
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        target_names: list[str] = []
        for target in node.targets:
            target_names.extend(_target_names(target))
        if any(
            name in PROMPT_NAMES for name in target_names
        ) and _is_prompt_mutation_expr(node.value):
            self._add(
                node,
                "prompt text concatenation/mutation is forbidden outside src/services/prompt_service.py",
            )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target_names = _target_names(node.target)
        if (
            node.value is not None
            and any(name in PROMPT_NAMES for name in target_names)
            and _is_prompt_mutation_expr(node.value)
        ):
            self._add(
                node,
                "prompt text concatenation/mutation is forbidden outside src/services/prompt_service.py",
            )
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        target_names = _target_names(node.target)
        if any(name in PROMPT_NAMES for name in target_names):
            self._add(
                node,
                "prompt text concatenation/mutation is forbidden outside src/services/prompt_service.py",
            )
        self.generic_visit(node)


def test_prompt_text_is_not_mutated_outside_prompt_service() -> None:
    violations: list[Violation] = []
    for path in _iter_python_files(SRC_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scanner = _PromptMutationScanner(path)
        scanner.visit(tree)
        violations.extend(scanner.violations)

    if violations:
        details = "\n".join(
            f"{item.path.relative_to(ROOT).as_posix()}:{item.line}:{item.column} {item.message}"
            for item in violations
        )
        raise AssertionError(f"Prompt boundary violations detected:\n{details}")
