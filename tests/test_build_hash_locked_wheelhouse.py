from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from scripts.dependencies.build_hash_locked_wheelhouse import (
    WheelhouseAuditRow,
    active_requirements,
    audit_existing_wheelhouse,
    locked_requirements,
    render_hash_locked_requirements,
    target_marker_environment,
)


def test_hash_lock_rendering_preserves_exact_pin_and_target_marker(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "requirements.lock"
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    linux_artifact = b"linux package wheel"
    (wheelhouse / "linux_package-1.2.3-py3-none-any.whl").write_bytes(linux_artifact)
    lock.write_text(
        "linux-package==1.2.3\nwindows-package==4.5.6; platform_system == 'Windows'\n",
        encoding="utf-8",
    )
    rows = (
        WheelhouseAuditRow(
            requirement="linux-package==1.2.3",
            package="linux-package",
            version="1.2.3",
            category="available_pypi_compatible_artifact",
            artifacts=("linux_package-1.2.3-py3-none-any.whl",),
            hashes=(hashlib.sha256(linux_artifact).hexdigest(),),
        ),
    )

    rendered = render_hash_locked_requirements(
        lock_path=lock,
        wheelhouse=wheelhouse,
        rows=rows,
        python_version="3.12",
    )

    assert rendered == (
        "linux-package==1.2.3 \\\n"
        f"    --hash=sha256:{hashlib.sha256(linux_artifact).hexdigest()}\n"
        "windows-package==4.5.6; platform_system == 'Windows'\n"
    )


def test_hash_lock_merge_preserves_linux_hashes_when_adding_windows_artifacts(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "shared-package==1.2.3 \\\n"
        f"    --hash=sha256:{'a' * 64}\n"
        "linux-package==2.0.0; sys_platform == 'linux' \\\n"
        f"    --hash=sha256:{'b' * 64}\n"
        "windows-package==4.5.6; platform_system == 'Windows'\n",
        encoding="utf-8",
    )
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    shared_artifact = b"shared Windows wheel"
    windows_artifact = b"Windows only wheel"
    (wheelhouse / "shared_package-1.2.3-py3-none-any.whl").write_bytes(shared_artifact)
    (wheelhouse / "windows_package-4.5.6-py3-none-any.whl").write_bytes(
        windows_artifact
    )
    rows = (
        WheelhouseAuditRow(
            requirement="shared-package==1.2.3",
            package="shared-package",
            version="1.2.3",
            category="available_pypi_compatible_artifact",
            artifacts=("shared_package-1.2.3-py3-none-any.whl",),
            hashes=(hashlib.sha256(shared_artifact).hexdigest(),),
        ),
        WheelhouseAuditRow(
            requirement="windows-package==4.5.6; platform_system == 'Windows'",
            package="windows-package",
            version="4.5.6",
            category="available_pypi_compatible_artifact",
            artifacts=("windows_package-4.5.6-py3-none-any.whl",),
            hashes=(hashlib.sha256(windows_artifact).hexdigest(),),
        ),
    )

    rendered = render_hash_locked_requirements(
        lock_path=lock,
        wheelhouse=wheelhouse,
        rows=rows,
        python_version="3.12",
        platform="win_amd64",
    )

    assert rendered == (
        "shared-package==1.2.3 \\\n"
        f"    --hash=sha256:{'a' * 64} \\\n"
        f"    --hash=sha256:{hashlib.sha256(shared_artifact).hexdigest()}\n"
        "linux-package==2.0.0; sys_platform == 'linux' \\\n"
        f"    --hash=sha256:{'b' * 64}\n"
        "windows-package==4.5.6; platform_system == 'Windows' \\\n"
        f"    --hash=sha256:{hashlib.sha256(windows_artifact).hexdigest()}\n"
    )


def test_target_marker_filters_windows_only_pin(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "linux-package==1.2.3; sys_platform == 'linux'\n"
        "windows-package==4.5.6; platform_system == 'Windows'\n"
        "cp312-package==7.8.9; python_version == '3.12'\n",
        encoding="utf-8",
    )

    requirements = locked_requirements(lock)
    linux_active = active_requirements(
        requirements,
        python_version="3.12",
        platform="manylinux2014_x86_64",
    )
    windows_active = active_requirements(
        requirements,
        python_version="3.12",
        platform="win_amd64",
    )

    assert [entry.requirement.name for entry in linux_active] == [
        "linux-package",
        "cp312-package",
    ]
    assert [entry.requirement.name for entry in windows_active] == [
        "windows-package",
        "cp312-package",
    ]
    environment = target_marker_environment(
        python_version="3.12.4", platform="win_amd64"
    )
    assert environment["platform_system"] == "Windows"
    assert environment["sys_platform"] == "win32"
    assert environment["python_full_version"] == "3.12.4"


@pytest.mark.parametrize(
    ("python_version", "platform"),
    (("3.13", "win_amd64"), ("3.12", "macosx_14_0_arm64")),
)
def test_target_rejects_unverified_python_or_platform(
    python_version: str, platform: str
) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        target_marker_environment(python_version=python_version, platform=platform)


def test_existing_wheelhouse_reports_missing_active_artifact(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    if sys.platform == "win32":
        platform = "win_amd64"
        active_package = "windows-package"
        lock_entry = "windows-package==4.5.6; platform_system == 'Windows'\n"
        incompatible_wheel = (
            "windows_package-4.5.6-cp312-cp312-manylinux_2_17_x86_64.whl"
        )
    else:
        platform = "manylinux2014_x86_64"
        active_package = "linux-package"
        lock_entry = "linux-package==1.2.3; sys_platform == 'linux'\n"
        incompatible_wheel = "linux_package-1.2.3-cp312-cp312-win_amd64.whl"
    (wheelhouse / incompatible_wheel).write_bytes(b"platform-incompatible artifact")
    lock.write_text(lock_entry, encoding="utf-8")

    rows = audit_existing_wheelhouse(
        lock_path=lock,
        wheelhouse=wheelhouse,
        python_version="3.12",
        platform=platform,
    )

    assert [(row.package, row.category) for row in rows] == [
        (active_package, "wheelhouse_missing_artifact")
    ]


def test_hash_lock_renderer_rejects_unverified_artifact_hash(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("example-package==1.2.3\n", encoding="utf-8")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    artifact_name = "example_package-1.2.3-py3-none-any.whl"
    (wheelhouse / artifact_name).write_bytes(b"wheel bytes whose digest does not match")
    rows = (
        WheelhouseAuditRow(
            requirement="example-package==1.2.3",
            package="example-package",
            version="1.2.3",
            category="available_pypi_compatible_artifact",
            artifacts=(artifact_name,),
            hashes=("f" * 64,),
        ),
    )

    with pytest.raises(ValueError, match="unverified target artifact"):
        render_hash_locked_requirements(
            lock_path=lock,
            wheelhouse=wheelhouse,
            rows=rows,
            python_version="3.12",
            platform="win_amd64",
        )
