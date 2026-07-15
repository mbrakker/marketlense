from __future__ import annotations

from pathlib import Path

from scripts.dependencies.build_hash_locked_wheelhouse import (
    WheelhouseAuditRow,
    active_requirements,
    audit_existing_wheelhouse,
    locked_requirements,
    render_hash_locked_requirements,
)


def test_hash_lock_rendering_preserves_exact_pin_and_target_marker(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "requirements.lock"
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
            hashes=("a" * 64,),
        ),
    )

    rendered = render_hash_locked_requirements(
        lock_path=lock, rows=rows, python_version="3.12"
    )

    assert rendered == (
        "linux-package==1.2.3 \\\n"
        f"    --hash=sha256:{'a' * 64}\n"
        "windows-package==4.5.6; platform_system == 'Windows'\n"
    )


def test_target_marker_filters_windows_only_pin(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "linux-package==1.2.3\nwindows-package==4.5.6; platform_system == 'Windows'\n",
        encoding="utf-8",
    )

    active = active_requirements(locked_requirements(lock), python_version="3.12")

    assert [entry.requirement.name for entry in active] == ["linux-package"]


def test_existing_wheelhouse_reports_missing_active_artifact(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("linux-package==1.2.3\n", encoding="utf-8")

    rows = audit_existing_wheelhouse(
        lock_path=lock, wheelhouse=tmp_path / "wheelhouse", python_version="3.12"
    )

    assert rows[0].category == "wheelhouse_missing_artifact"
