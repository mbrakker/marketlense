"""Fail when declared exact dependency pins drift from requirements.lock."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    Path("requirements.txt"),
    Path("requirements-dev.txt"),
    Path("pyproject.toml"),
    Path("tools/browser-use/pyproject.toml"),
)
LOCK_FILE = Path("requirements.lock")
README_FILE = Path("README.md")
VENDORED_SECURITY_DEV_PACKAGES = frozenset({"pydantic-settings"})
_LOCK_HASH_PATTERN = re.compile(r"\s+--hash=sha256:[0-9a-fA-F]{64}")
_LOCK_HASH_VALUE_PATTERN = re.compile(r"--hash=sha256:[0-9a-fA-F]{64}")


def _marker_environment(
    environment: Mapping[str, str] | None,
) -> dict[str, str]:
    resolved = {key: str(value) for key, value in default_environment().items()}
    if environment is not None:
        resolved.update(environment)
    return resolved


def _active_exact_requirement(
    raw_requirement: str,
    *,
    environment: Mapping[str, str],
) -> tuple[str, str] | None:
    requirement = Requirement(raw_requirement)
    if requirement.marker is not None and not requirement.marker.evaluate(environment):
        return None
    exact_versions = [
        specifier.version
        for specifier in requirement.specifier
        if specifier.operator == "=="
    ]
    if len(exact_versions) != 1 or len(requirement.specifier) != 1:
        return None
    return canonicalize_name(requirement.name), exact_versions[0]


def _requirements_from_file(
    path: Path,
    *,
    environment: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    requirements: list[tuple[str, str]] = []
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith(("-r", "--requirement", "-c", "--constraint")):
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        logical_line = (pending + line).strip()
        pending = ""
        parsed = _active_exact_requirement(
            _LOCK_HASH_PATTERN.sub("", logical_line).strip(),
            environment=environment,
        )
        if parsed is not None:
            requirements.append(parsed)
    if pending:
        raise ValueError(f"{path}: unfinished line continuation")
    return tuple(requirements)


def _requirements_from_pyproject(
    path: Path,
    *,
    environment: Mapping[str, str],
    include_dev_packages: frozenset[str] = frozenset(),
) -> tuple[tuple[str, str], ...]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    tool = payload.get("tool", {})
    uv = tool.get("uv", {}) if isinstance(tool, dict) else {}
    raw_requirements = project.get("dependencies", [])
    raw_requirements.extend(
        requirement
        for requirement in uv.get("dev-dependencies", [])
        if canonicalize_name(Requirement(str(requirement)).name) in include_dev_packages
    )
    parsed_requirements: list[tuple[str, str]] = []
    for raw_requirement in raw_requirements:
        parsed = _active_exact_requirement(
            str(raw_requirement), environment=environment
        )
        if parsed is not None:
            parsed_requirements.append(parsed)
    return tuple(parsed_requirements)


def declared_exact_pins(
    root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    """Return active exact pins as (package, version, source_manifest)."""
    marker_environment = _marker_environment(environment)

    declared: list[tuple[str, str, str]] = []
    for relative_path in SOURCE_FILES:
        path = root / relative_path
        source = relative_path.as_posix()
        if path.suffix == ".toml":
            include_dev_packages = (
                VENDORED_SECURITY_DEV_PACKAGES
                if relative_path == Path("tools/browser-use/pyproject.toml")
                else frozenset()
            )
            pins = _requirements_from_pyproject(
                path,
                environment=marker_environment,
                include_dev_packages=include_dev_packages,
            )
        else:
            pins = _requirements_from_file(path, environment=marker_environment)
        declared.extend((package, version, source) for package, version in pins)
    return tuple(declared)


def locked_pins(
    root: Path, *, environment: Mapping[str, str] | None = None
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return active lock pins and duplicate-lock diagnostics."""
    marker_environment = _marker_environment(environment)

    pins: dict[str, str] = {}
    errors: list[str] = []
    for package, version in _requirements_from_file(
        root / LOCK_FILE, environment=marker_environment
    ):
        existing = pins.get(package)
        if existing is not None and existing != version:
            errors.append(
                f"requirements.lock: conflicting locked declarations for {package}: "
                f"{existing} and {version}"
            )
            continue
        pins[package] = version
    return pins, tuple(errors)


def hash_lock_diagnostics(
    root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Require SHA-256 evidence for every active exact lock pin."""
    marker_environment = _marker_environment(environment)
    diagnostics: list[str] = []
    pending = ""
    for raw_line in (root / LOCK_FILE).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        logical_line = (pending + line).strip()
        pending = ""
        if logical_line.startswith(("-r", "--requirement", "-c", "--constraint")):
            continue
        requirement = Requirement(_LOCK_HASH_PATTERN.sub("", logical_line).strip())
        if requirement.marker is not None and not requirement.marker.evaluate(
            marker_environment
        ):
            continue
        exact_versions = [
            specifier.version
            for specifier in requirement.specifier
            if specifier.operator == "=="
        ]
        if len(exact_versions) != 1 or len(requirement.specifier) != 1:
            continue
        if not _LOCK_HASH_VALUE_PATTERN.findall(logical_line):
            diagnostics.append(
                f"requirements.lock: {requirement.name} has no SHA-256 hash"
            )
    if pending:
        diagnostics.append("requirements.lock: unfinished line continuation")
    return tuple(diagnostics)


def readme_security_pins(root: Path) -> tuple[tuple[str, str], ...]:
    """Read explicitly documented pins from the README security-baseline sentence."""
    for line in (root / README_FILE).read_text(encoding="utf-8").splitlines():
        if "Dependency security baseline:" not in line:
            continue
        values: list[tuple[str, str]] = []
        for fragment in line.split("`")[1::2]:
            parts = fragment.split()
            if len(parts) == 2:
                values.append((canonicalize_name(parts[0]), parts[1]))
        return tuple(values)
    return ()


def check_consistency(
    root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return deterministic diagnostics for source, lock, and README pin drift."""
    declarations = declared_exact_pins(root, environment=environment)
    lock, errors = locked_pins(root, environment=environment)
    diagnostics = list(errors)

    versions_by_package: dict[str, dict[str, list[str]]] = {}
    for package, version, source in declarations:
        versions_by_package.setdefault(package, {}).setdefault(version, []).append(
            source
        )

    for package in sorted(versions_by_package):
        declared_versions = versions_by_package[package]
        if len(declared_versions) > 1:
            details = "; ".join(
                f"{source} declares {version}"
                for version in sorted(declared_versions)
                for source in sorted(declared_versions[version])
            )
            diagnostics.append(
                f"conflicting exact declarations for {package}: {details}"
            )
            continue
        declared_version = next(iter(declared_versions))
        locked_version = lock.get(package)
        for source in sorted(declared_versions[declared_version]):
            if locked_version != declared_version:
                rendered_locked = (
                    locked_version if locked_version is not None else "missing"
                )
                diagnostics.append(
                    f"{source}: {package} declared {declared_version}, "
                    f"locked {rendered_locked}"
                )

    for package, documented_version in readme_security_pins(root):
        locked_version = lock.get(package)
        if locked_version != documented_version:
            rendered_locked = (
                locked_version if locked_version is not None else "missing"
            )
            diagnostics.append(
                f"README.md: {package} declared {documented_version}, "
                f"locked {rendered_locked}"
            )
    return tuple(diagnostics)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify exact dependency declarations agree with requirements.lock."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> int:
    root = _parse_args().root
    diagnostics = check_consistency(root) + hash_lock_diagnostics(
        root,
        environment={
            "implementation_name": "cpython",
            "platform_machine": "x86_64",
            "platform_system": "Linux",
            "python_version": "3.12",
            "sys_platform": "linux",
        },
    )
    if diagnostics:
        print("Dependency manifest consistency check failed:")
        for diagnostic in diagnostics:
            print(f"  - {diagnostic}")
        return 1
    print("Dependency manifest consistency check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
