from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.policy import DEFAULT_POLICY_PATH, load_architecture_policy  # noqa: E402

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
class ImportPolicy:
    role_dirs: dict[str, str]
    allowed_by_role: dict[str, tuple[str, ...]]


def load_import_policy(path: Path = DEFAULT_POLICY_PATH) -> ImportPolicy:
    payload = load_architecture_policy(path)
    roles_raw = payload.get("roles")
    allowed_raw = payload.get("allowed_imports_by_role")
    if not isinstance(roles_raw, dict) or not isinstance(allowed_raw, dict):
        return ImportPolicy(role_dirs=ROLE_DIRS, allowed_by_role={})
    role_dirs: dict[str, str] = {}
    for role, raw_path in roles_raw.items():
        parts = str(raw_path).replace("\\", "/").strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "src":
            role_dirs[str(role)] = parts[1]
    allowed_by_role: dict[str, tuple[str, ...]] = {}
    for role, raw_prefixes in allowed_raw.items():
        if isinstance(raw_prefixes, list):
            allowed_by_role[str(role)] = tuple(str(item) for item in raw_prefixes)
    return ImportPolicy(role_dirs=role_dirs, allowed_by_role=allowed_by_role)


@dataclass(frozen=True)
class ImportViolation:
    role: str
    path: Path
    line: int
    column: int
    imported: str
    rule: str


@dataclass(frozen=True)
class ImportCycle:
    modules: tuple[str, ...]


def _role_for_path(path: Path, role_dirs: dict[str, str] | None = None) -> str | None:
    dirs = role_dirs or ROLE_DIRS
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
    for role, dirname in dirs.items():
        if first == dirname:
            return role
    return None


def _iter_python_files() -> Iterable[Path]:
    for dirname in ROLE_DIRS.values():
        directory = SRC_ROOT / dirname
        if directory.exists():
            yield from sorted(directory.rglob("*.py"))


def _iter_first_party_python_files(src_root: Path = SRC_ROOT) -> Iterable[Path]:
    if src_root.exists():
        yield from sorted(src_root.rglob("*.py"))


def _module_name_for_path(path: Path, src_root: Path = SRC_ROOT) -> str:
    relative = path.relative_to(src_root).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("src", *parts))


def _imported_modules(node: ast.AST) -> Iterable[tuple[str, int, int]]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name, node.lineno, node.col_offset + 1
    elif isinstance(node, ast.ImportFrom):
        if not node.module:
            return
        yield node.module, node.lineno, node.col_offset + 1


def _static_imported_module_names(tree: ast.AST) -> Iterable[str]:
    class StaticImportVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.imports: list[str] = []

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                self.imports.append(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module:
                self.imports.append(node.module)

    visitor = StaticImportVisitor()
    visitor.visit(tree)
    return visitor.imports


def _resolve_first_party_import(
    imported: str, known_modules: set[str], known_packages: set[str]
) -> str | None:
    if imported == "src":
        return None
    if not imported.startswith("src."):
        return None
    parts = imported.split(".")
    for length in range(len(parts), 1, -1):
        candidate = ".".join(parts[:length])
        if candidate in known_modules:
            return candidate
        if candidate in known_packages:
            return candidate
    return None


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    open_cycle = cycle[:-1]
    min_index = min(range(len(open_cycle)), key=lambda index: open_cycle[index])
    rotated = open_cycle[min_index:] + open_cycle[:min_index]
    return tuple((*rotated, rotated[0]))


def _find_cycles(graph: dict[str, set[str]]) -> list[ImportCycle]:
    cycles: set[tuple[str, ...]] = set()
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(module: str) -> None:
        if module in visiting:
            if module in stack:
                cycle = stack[stack.index(module) :] + [module]
                cycles.add(_canonical_cycle(cycle))
            return
        if module in visited:
            return
        visiting.add(module)
        stack.append(module)
        for dependency in sorted(graph.get(module, ())):
            visit(dependency)
        stack.pop()
        visiting.remove(module)
        visited.add(module)

    for module in sorted(graph):
        visit(module)
    return [ImportCycle(modules=cycle) for cycle in sorted(cycles)]


def scan_first_party_import_cycles(src_root: Path = SRC_ROOT) -> list[ImportCycle]:
    paths = list(_iter_first_party_python_files(src_root))
    module_by_path = {
        path: _module_name_for_path(path, src_root)
        for path in paths
        if path.name != "__init__.py"
    }
    known_modules = set(module_by_path.values())
    known_packages = {
        _module_name_for_path(path, src_root)
        for path in paths
        if path.name == "__init__.py"
    }
    graph: dict[str, set[str]] = {module: set() for module in known_modules}
    for path, module in module_by_path.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in _static_imported_module_names(tree):
            dependency = _resolve_first_party_import(
                imported, known_modules, known_packages
            )
            if dependency is None or dependency == module:
                continue
            graph[module].add(dependency)
    return _find_cycles(graph)


def _violates(imported: str, forbidden_prefixes: tuple[str, ...]) -> str | None:
    for prefix in forbidden_prefixes:
        if imported == prefix or imported.startswith(prefix + "."):
            return prefix
    return None


def _violates_policy(imported: str, allowed_prefixes: tuple[str, ...]) -> bool:
    if not imported.startswith("src."):
        return False
    if not allowed_prefixes:
        return True
    return not any(
        imported == prefix or imported.startswith(prefix + ".")
        for prefix in allowed_prefixes
    )


def scan_file(
    path: Path, *, policy: ImportPolicy | None = None
) -> list[ImportViolation]:
    import_policy = policy or load_import_policy()
    role = _role_for_path(path, import_policy.role_dirs)
    if role is None:
        return []
    allowed = import_policy.allowed_by_role.get(role)
    if allowed is None:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[ImportViolation] = []
    for node in ast.walk(tree):
        for imported, line, column in _imported_modules(node):
            if not _violates_policy(imported, allowed):
                continue
            allowed_text = ", ".join(allowed) if allowed else "no src role imports"
            violations.append(
                ImportViolation(
                    role=role,
                    path=path,
                    line=line,
                    column=column,
                    imported=imported,
                    rule=f"{role} may only import {allowed_text}",
                )
            )
    return violations


def scan_repository() -> list[ImportViolation]:
    policy = load_import_policy()
    violations: list[ImportViolation] = []
    for path in _iter_python_files():
        violations.extend(scan_file(path, policy=policy))
    return violations


def main() -> int:
    violations = scan_repository()
    cycles = scan_first_party_import_cycles()
    if not violations and not cycles:
        print("Architecture import gate passed.")
        return 0

    print("Architecture import gate failed:")
    for item in sorted(violations, key=lambda x: (str(x.path), x.line, x.column)):
        rel = item.path.relative_to(ROOT).as_posix()
        print(
            f"  - {rel}:{item.line}:{item.column} imports {item.imported}; {item.rule}"
        )
    for cycle in cycles:
        print(f"  - first-party import cycle: {' -> '.join(cycle.modules)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
