from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS: tuple[tuple[str, Path], ...] = (
    ("generator", ROOT / "src" / "generators"),
    ("utility", ROOT / "src" / "utils"),
)

BANNED_NETWORK_IMPORT_PREFIXES: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "socket",
    "ftplib",
    "paramiko",
    "urllib.request",
    "urllib3",
)

BANNED_CALLS: set[str] = {
    "open",
    "os.listdir",
    "os.walk",
    "os.scandir",
    "os.mkdir",
    "os.makedirs",
    "os.remove",
    "os.unlink",
    "os.rename",
    "os.replace",
    "os.rmdir",
    "os.stat",
    "os.lstat",
    "os.path.exists",
    "os.path.isfile",
    "os.path.isdir",
    "os.path.getsize",
    "os.path.getmtime",
}

BANNED_CALL_PREFIXES: tuple[str, ...] = (
    "subprocess.",
    "shutil.",
    "tempfile.",
    "requests.",
    "httpx.",
    "aiohttp.",
    "socket.",
    "ftplib.",
    "paramiko.",
    "urllib.request.",
)

BANNED_PATH_METHODS: set[str] = {
    "open",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "rmdir",
    "touch",
    "glob",
    "rglob",
    "iterdir",
    "exists",
    "is_file",
    "is_dir",
    "stat",
}

PATH_ATTR_RETURNS_PATH: set[str] = {"parent"}


@dataclass(frozen=True)
class Violation:
    role: str
    path: Path
    line: int
    column: int
    message: str


def _iter_python_files(path: Path) -> Iterable[Path]:
    yield from sorted(path.rglob("*.py"))


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _extract_target_names(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for child in node.elts:
            names.extend(_extract_target_names(child))
        return names
    return []


def _is_forbidden_network_module(name: str) -> bool:
    module = str(name or "").strip()
    if not module:
        return False
    for prefix in BANNED_NETWORK_IMPORT_PREFIXES:
        if module == prefix or module.startswith(f"{prefix}."):
            return True
    return False


class _IoBoundaryScanner(ast.NodeVisitor):
    def __init__(self, *, role: str, path: Path) -> None:
        self.role = role
        self.path = path
        self.aliases: dict[str, str] = {}
        self.path_vars: set[str] = set()
        self.violations: list[Violation] = []

    def _add_violation(self, node: ast.AST, message: str) -> None:
        self.violations.append(
            Violation(
                role=self.role,
                path=self.path,
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0) + 1,
                message=message,
            )
        )

    def _resolve_name(self, raw_name: str) -> str:
        if not raw_name:
            return ""
        parts = raw_name.split(".")
        root = parts[0]
        resolved_root = self.aliases.get(root, root)
        resolved_parts = resolved_root.split(".")
        return ".".join(resolved_parts + parts[1:])

    def _looks_like_path_name(self, name: str) -> bool:
        token = str(name or "").strip().lower()
        if not token:
            return False
        return (
            "path" in token
            or token.endswith("_dir")
            or token.endswith("_file")
            or token == "root"
        )

    def _is_path_constructor_call(self, expr: ast.expr) -> bool:
        if not isinstance(expr, ast.Call):
            return False
        call_name = self._resolve_name(_call_name(expr.func))
        return call_name in {"pathlib.Path", "Path"}

    def _is_path_expr(self, expr: ast.expr) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self.path_vars or self._looks_like_path_name(expr.id)
        if isinstance(expr, ast.Call):
            return self._is_path_constructor_call(expr)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            return self._is_path_expr(expr.left) or self._is_path_expr(expr.right)
        if isinstance(expr, ast.Attribute):
            if expr.attr in PATH_ATTR_RETURNS_PATH:
                return self._is_path_expr(expr.value)
            return self._is_path_expr(expr.value) and self._looks_like_path_name(
                expr.attr
            )
        return False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.aliases[local_name] = alias.name
            if _is_forbidden_network_module(alias.name):
                self._add_violation(
                    node,
                    f"forbidden direct network import in {self.role}: {alias.name}",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = str(node.module or "").strip()
        for alias in node.names:
            local_name = alias.asname or alias.name
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.aliases[local_name] = full_name
            if _is_forbidden_network_module(full_name):
                self._add_violation(
                    node,
                    f"forbidden direct network import in {self.role}: {full_name}",
                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_path_expr(node.value):
            for target in node.targets:
                for name in _extract_target_names(target):
                    self.path_vars.add(name)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and self._is_path_expr(node.value):
            for name in _extract_target_names(node.target):
                self.path_vars.add(name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        raw_name = _call_name(node.func)
        resolved_name = self._resolve_name(raw_name)

        if raw_name == "open" or resolved_name == "open":
            self._add_violation(
                node,
                f"forbidden direct file I/O call in {self.role}: open(...)",
            )

        if resolved_name in BANNED_CALLS:
            self._add_violation(
                node,
                f"forbidden direct I/O call in {self.role}: {resolved_name}",
            )

        for prefix in BANNED_CALL_PREFIXES:
            if resolved_name.startswith(prefix):
                self._add_violation(
                    node,
                    f"forbidden direct I/O call in {self.role}: {resolved_name}",
                )
                break

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in BANNED_PATH_METHODS and self._is_path_expr(node.func.value):
                self._add_violation(
                    node,
                    f"forbidden pathlib I/O call in {self.role}: .{method}(...)",
                )

        self.generic_visit(node)


def _scan_role(role: str, directory: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(directory):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scanner = _IoBoundaryScanner(role=role, path=path)
        scanner.visit(tree)
        violations.extend(scanner.violations)
    return violations


def test_generators_and_utils_are_free_of_direct_io() -> None:
    violations: list[Violation] = []
    for role, directory in TARGET_DIRS:
        violations.extend(_scan_role(role, directory))

    if violations:
        details = "\n".join(
            f"{item.path.relative_to(ROOT).as_posix()}:{item.line}:{item.column} {item.message}"
            for item in sorted(
                violations,
                key=lambda item: (
                    item.role,
                    str(item.path),
                    item.line,
                    item.column,
                    item.message,
                ),
            )
        )
        raise AssertionError(f"Direct I/O boundary violations detected:\n{details}")
