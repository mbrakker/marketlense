"""Audit pinned requirements and build a hash-verified target wheelhouse.

This operational tool deliberately asks pip for one already-pinned requirement
at a time.  It never resolves or upgrades the dependency graph: the lock is
the input contract and the downloaded wheel hashes are the output evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform as runtime_platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import Tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

_HASH_PATTERN = re.compile(r"\s+--hash=sha256:[0-9a-fA-F]{64}")
_HASH_VALUE_PATTERN = re.compile(r"--hash=sha256:([0-9a-fA-F]{64})")
_HASH_ARGUMENT_PATTERN = re.compile(r"--hash=\S+")
_SUPPORTED_PYTHON_RELEASE = (3, 12)
_SUPPORTED_TARGETS = {
    "manylinux2014_x86_64": {
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_system": "Linux",
        "sys_platform": "linux",
    },
    "manylinux_2_17_x86_64": {
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_system": "Linux",
        "sys_platform": "linux",
    },
    "win_amd64": {
        "os_name": "nt",
        "platform_machine": "AMD64",
        "platform_python_implementation": "CPython",
        "platform_system": "Windows",
        "sys_platform": "win32",
    },
}


@dataclass(frozen=True)
class LockedRequirement:
    """One logical pinned requirement read from the canonical lock."""

    raw: str
    requirement: Requirement
    hashes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WheelhouseAuditRow:
    """One target-platform audit result, with no dependency re-resolution."""

    requirement: str
    package: str
    version: str
    category: str
    artifacts: tuple[str, ...] = field(default_factory=tuple)
    hashes: tuple[str, ...] = field(default_factory=tuple)
    pip_error: str = ""


def logical_requirement_lines(text: str) -> tuple[str, ...]:
    """Return comments-stripped logical requirement lines, including hashes."""
    lines: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        lines.append((pending + line).strip())
        pending = ""
    if pending:
        raise ValueError("requirements lock ends with an unfinished continuation")
    return tuple(lines)


def locked_requirements(path: Path) -> tuple[LockedRequirement, ...]:
    """Read installable, exact pins from a requirements lock."""
    entries: list[LockedRequirement] = []
    for line in logical_requirement_lines(path.read_text(encoding="utf-8")):
        if line.startswith(("-r", "--requirement", "-c", "--constraint")):
            continue
        hash_arguments = _HASH_ARGUMENT_PATTERN.findall(line)
        hashes = tuple(_HASH_VALUE_PATTERN.findall(line))
        if len(hash_arguments) != len(hashes):
            raise ValueError(f"lock entry contains an invalid hash: {line}")
        without_hashes = _HASH_PATTERN.sub("", line).strip()
        requirement = Requirement(without_hashes)
        exact = [
            item.version for item in requirement.specifier if item.operator == "=="
        ]
        if len(exact) != 1 or len(requirement.specifier) != 1:
            raise ValueError(f"lock entry is not one exact pin: {without_hashes}")
        entries.append(
            LockedRequirement(
                raw=without_hashes, requirement=requirement, hashes=hashes
            )
        )
    return tuple(entries)


def target_marker_environment(
    *, python_version: str, platform: str = "manylinux2014_x86_64"
) -> dict[str, str]:
    """Return a marker environment for one supported CPython 3.12 x64 target."""
    target = _SUPPORTED_TARGETS.get(platform)
    if target is None:
        raise ValueError(f"unsupported wheelhouse platform target: {platform}")
    try:
        version = Version(python_version)
    except Exception as error:
        raise ValueError(
            f"unsupported Python target version: {python_version}"
        ) from error
    if (
        version.release[:2] != _SUPPORTED_PYTHON_RELEASE
        or version.is_prerelease
        or version.is_devrelease
        or version.is_postrelease
        or version.local is not None
    ):
        raise ValueError(f"unsupported Python target version: {python_version}")
    full_version = ".".join(str(part) for part in version.release)
    if len(version.release) == 2:
        full_version += ".0"

    environment = {key: str(value) for key, value in default_environment().items()}
    environment.update(
        {
            "implementation_name": "cpython",
            "implementation_version": full_version,
            **target,
            "python_full_version": full_version,
            "python_version": ".".join(str(part) for part in version.release[:2]),
        }
    )
    return environment


def active_requirements(
    requirements: Iterable[LockedRequirement],
    *,
    python_version: str,
    platform: str = "manylinux2014_x86_64",
) -> tuple[LockedRequirement, ...]:
    """Return requirements active for the target CI environment."""
    environment = target_marker_environment(
        python_version=python_version, platform=platform
    )
    return tuple(
        entry
        for entry in requirements
        if entry.requirement.marker is None
        or entry.requirement.marker.evaluate(environment)
    )


def _exact_version(requirement: Requirement) -> str:
    return next(item.version for item in requirement.specifier if item.operator == "==")


def _pypi_version_exists(*, package: str, version: str) -> bool:
    """Check the approved PyPI JSON endpoint without accepting another index."""
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def _artifact_paths_for_requirement(
    *,
    wheelhouse: Path,
    requirement: Requirement,
    compatible_tags: frozenset[Tag] | None = None,
) -> tuple[Path, ...]:
    expected_name = canonicalize_name(requirement.name)
    expected_version = _exact_version(requirement)
    artifacts: list[Path] = []
    for path in wheelhouse.glob("*.whl"):
        try:
            name, version, _build, tags = parse_wheel_filename(path.name)
        except Exception:
            continue
        if (
            canonicalize_name(name) == expected_name
            and str(version) == expected_version
            and (compatible_tags is None or not tags.isdisjoint(compatible_tags))
        ):
            artifacts.append(path)
    return tuple(sorted(artifacts))


def _native_wheel_tags(*, platform: str) -> frozenset[Tag]:
    """Reject an existing wheelhouse selected on a different OS or architecture."""
    machine = runtime_platform.machine().lower()
    if platform == "win_amd64":
        is_target = sys.platform == "win32" and machine in {"amd64", "x86_64"}
    else:
        is_target = (
            platform in {"manylinux2014_x86_64", "manylinux_2_17_x86_64"}
            and sys.platform == "linux"
            and machine == "x86_64"
        )
    if not is_target:
        raise ValueError(
            f"existing wheelhouse target {platform} does not match the native host"
        )
    return frozenset(sys_tags())


def _native_target_python_version(*, python_version: str, platform: str) -> str:
    """Use the actual interpreter patch version for a native wheelhouse audit."""
    target_marker_environment(
        python_version=python_version,
        platform=platform,
    )
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise ValueError("native wheelhouse audit requires CPython 3.12")
    actual = Version(runtime_platform.python_version())
    requested = Version(python_version)
    if len(requested.release) > 2 and requested.release != actual.release:
        raise ValueError(
            f"requested Python target {python_version} does not match "
            f"native interpreter {actual}"
        )
    return str(actual)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_wheelhouse(
    *,
    lock_path: Path,
    wheelhouse: Path,
    index_url: str,
    platform: str,
    python_version: str,
    abi: str,
) -> tuple[WheelhouseAuditRow, ...]:
    """Download exact active pins and classify source/platform failures."""
    if abi != "cp312":
        raise ValueError(f"unsupported CPython ABI target: {abi}")
    wheelhouse.mkdir(parents=True, exist_ok=True)
    rows: list[WheelhouseAuditRow] = []
    for entry in active_requirements(
        locked_requirements(lock_path),
        python_version=python_version,
        platform=platform,
    ):
        requirement = entry.requirement
        version = _exact_version(requirement)
        if requirement.url:
            rows.append(
                WheelhouseAuditRow(
                    requirement=entry.raw,
                    package=requirement.name,
                    version=version,
                    category="genuinely_private_or_direct_reference",
                )
            )
            continue
        with tempfile.TemporaryDirectory(prefix="marketlense-wheel-audit-") as temp_dir:
            command = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--disable-pip-version-check",
                "--index-url",
                index_url,
                "--only-binary=:all:",
                "--no-deps",
                "--platform",
                platform,
                "--implementation",
                "cp",
                "--python-version",
                python_version,
                "--abi",
                abi,
                "--dest",
                temp_dir,
                f"{requirement.name}=={version}",
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            artifacts = _artifact_paths_for_requirement(
                wheelhouse=Path(temp_dir), requirement=requirement
            )
            if completed.returncode == 0 and artifacts:
                artifact_names = tuple(path.name for path in artifacts)
                hashes = tuple(_sha256(path) for path in artifacts)
                for path in artifacts:
                    shutil.copy2(path, wheelhouse / path.name)
        if completed.returncode == 0 and artifacts:
            rows.append(
                WheelhouseAuditRow(
                    requirement=entry.raw,
                    package=requirement.name,
                    version=version,
                    category="available_pypi_compatible_artifact",
                    artifacts=artifact_names,
                    hashes=hashes,
                )
            )
            continue
        exists = _pypi_version_exists(package=requirement.name, version=version)
        rows.append(
            WheelhouseAuditRow(
                requirement=entry.raw,
                package=requirement.name,
                version=version,
                category=(
                    "available_pypi_missing_required_platform_artifact"
                    if exists
                    else "invalid_or_stale_lock_entry"
                ),
                pip_error=(completed.stderr or completed.stdout).strip(),
            )
        )
    return tuple(rows)


def audit_existing_wheelhouse(
    *,
    lock_path: Path,
    wheelhouse: Path,
    python_version: str,
    platform: str = "manylinux2014_x86_64",
) -> tuple[WheelhouseAuditRow, ...]:
    """Hash exact artifacts already selected by a native target environment.

    Use this after `pip download` runs in the real CI platform.  Unlike the
    synthetic `--platform` mode, native pip evaluates its complete compatible
    tag set (including older and newer manylinux aliases).
    """
    python_version = _native_target_python_version(
        python_version=python_version,
        platform=platform,
    )
    rows: list[WheelhouseAuditRow] = []
    compatible_tags = _native_wheel_tags(platform=platform)
    for entry in active_requirements(
        locked_requirements(lock_path),
        python_version=python_version,
        platform=platform,
    ):
        requirement = entry.requirement
        version = _exact_version(requirement)
        if requirement.url:
            rows.append(
                WheelhouseAuditRow(
                    requirement=entry.raw,
                    package=requirement.name,
                    version=version,
                    category="genuinely_private_or_direct_reference",
                )
            )
            continue
        artifacts = _artifact_paths_for_requirement(
            wheelhouse=wheelhouse,
            requirement=requirement,
            compatible_tags=compatible_tags,
        )
        if artifacts:
            rows.append(
                WheelhouseAuditRow(
                    requirement=entry.raw,
                    package=requirement.name,
                    version=version,
                    category="available_pypi_compatible_artifact",
                    artifacts=tuple(path.name for path in artifacts),
                    hashes=tuple(_sha256(path) for path in artifacts),
                )
            )
            continue
        rows.append(
            WheelhouseAuditRow(
                requirement=entry.raw,
                package=requirement.name,
                version=version,
                category="wheelhouse_missing_artifact",
            )
        )
    return tuple(rows)


def render_hash_locked_requirements(
    *,
    lock_path: Path,
    wheelhouse: Path,
    rows: Iterable[WheelhouseAuditRow],
    python_version: str,
    platform: str = "manylinux2014_x86_64",
) -> str:
    """Merge verified target wheel hashes without discarding other-platform hashes."""
    by_requirement = {row.requirement: row for row in rows}
    rendered: list[str] = []
    for entry in locked_requirements(lock_path):
        active = entry in active_requirements(
            (entry,), python_version=python_version, platform=platform
        )
        row = by_requirement.get(entry.raw)
        hashes = entry.hashes
        if active:
            if row is None or row.category != "available_pypi_compatible_artifact":
                raise ValueError(f"cannot hash-lock unresolved target pin: {entry.raw}")
            if not row.artifacts or len(row.artifacts) != len(row.hashes):
                raise ValueError(
                    f"cannot hash-lock unverified target artifacts: {entry.raw}"
                )
            if any(
                not re.fullmatch(r"[0-9a-fA-F]{64}", digest) for digest in row.hashes
            ):
                raise ValueError(
                    f"cannot hash-lock unverified artifact hash: {entry.raw}"
                )
            for artifact, digest in zip(row.artifacts, row.hashes, strict=True):
                artifact_path = wheelhouse / artifact
                if (
                    not artifact_path.is_file()
                    or _sha256(artifact_path) != digest.lower()
                ):
                    raise ValueError(
                        f"cannot hash-lock unverified target artifact: {artifact}"
                    )
            hashes = tuple(
                dict.fromkeys((*hashes, *(digest.lower() for digest in row.hashes)))
            )
        if not hashes:
            rendered.append(entry.raw)
            continue
        rendered.append(entry.raw + " \\")
        rendered.extend(f"    --hash=sha256:{digest} \\" for digest in hashes[:-1])
        rendered.append(f"    --hash=sha256:{hashes[-1]}")
    return "\n".join(rendered) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("requirements.lock"))
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--index-url", default="https://pypi.org/simple")
    parser.add_argument("--platform", default="manylinux2014_x86_64")
    parser.add_argument(
        "--python-version",
        default=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
    parser.add_argument("--abi", default="cp312")
    parser.add_argument(
        "--from-existing-wheelhouse",
        action="store_true",
        help="Hash an already-native-selected wheelhouse without requesting an index.",
    )
    parser.add_argument("--write-lock", type=Path)
    args = parser.parse_args()
    if args.abi != "cp312":
        raise SystemExit(f"unsupported CPython ABI target: {args.abi}")
    if args.from_existing_wheelhouse:
        args.python_version = _native_target_python_version(
            python_version=args.python_version,
            platform=args.platform,
        )
    rows = (
        audit_existing_wheelhouse(
            lock_path=args.lock,
            wheelhouse=args.wheelhouse,
            python_version=args.python_version,
            platform=args.platform,
        )
        if args.from_existing_wheelhouse
        else audit_wheelhouse(
            lock_path=args.lock,
            wheelhouse=args.wheelhouse,
            index_url=args.index_url,
            platform=args.platform,
            python_version=args.python_version,
            abi=args.abi,
        )
    )
    payload = {
        "schema_version": "1.0",
        "platform": args.platform,
        "python_version": args.python_version,
        "abi": args.abi,
        "rows": [asdict(row) for row in rows],
    }
    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unresolved = [
        row for row in rows if row.category != "available_pypi_compatible_artifact"
    ]
    if args.write_lock:
        if unresolved:
            raise SystemExit(
                "wheelhouse audit incomplete; canonical lock was not changed"
            )
        args.write_lock.write_text(
            render_hash_locked_requirements(
                lock_path=args.lock,
                wheelhouse=args.wheelhouse,
                rows=rows,
                python_version=args.python_version,
                platform=args.platform,
            ),
            encoding="utf-8",
        )
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
