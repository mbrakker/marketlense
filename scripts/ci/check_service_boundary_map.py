from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.policy import DEFAULT_POLICY_PATH, load_architecture_policy  # noqa: E402

MAP_PATH = ROOT / "docs" / "quality" / "service_boundary_map.json"


@dataclass(frozen=True)
class ServiceBoundaryViolation:
    path: str
    line: int
    system: str
    imported: str


def load_service_boundary_config(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        policy = load_architecture_policy(path)
        systems = policy.get("external_system_ownership")
        return {"systems": systems if isinstance(systems, dict) else {}}
    return json.loads(path.read_text(encoding="utf-8"))


def scan_service_boundary_map(
    root: Path,
    config: dict[str, Any],
) -> list[ServiceBoundaryViolation]:
    violations: list[ServiceBoundaryViolation] = []
    systems = config.get("systems")
    if not isinstance(systems, dict):
        return violations
    services_root = root / "src" / "services"
    for path in sorted(services_root.rglob("*.py")):
        relative_path = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported, line in _imports(tree):
            for system, raw_spec in systems.items():
                spec = raw_spec if isinstance(raw_spec, dict) else {}
                prefixes = spec.get("import_prefixes")
                if not isinstance(prefixes, list) or not any(
                    imported == prefix or imported.startswith(f"{prefix}.")
                    for prefix in prefixes
                ):
                    continue
                canonical = str(spec.get("canonical_entrypoint") or "")
                private_roots = spec.get("private_roots")
                allowed_private = isinstance(private_roots, list) and any(
                    relative_path.startswith(str(item)) for item in private_roots
                )
                if relative_path != canonical and not allowed_private:
                    violations.append(
                        ServiceBoundaryViolation(
                            relative_path,
                            line,
                            str(system),
                            imported,
                        )
                    )
    return violations


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))
    return imports


def main() -> int:
    config = load_service_boundary_config(DEFAULT_POLICY_PATH)
    violations = scan_service_boundary_map(ROOT, config)
    if violations:
        print("Service boundary map gate failed:")
        for item in violations:
            print(
                f"  - {item.path}:{item.line} imports {item.imported}; "
                f"{item.system} must use its canonical boundary"
            )
        return 1
    print("Service boundary map gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
