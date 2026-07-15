from __future__ import annotations

from pathlib import Path

from scripts.ci.check_dependency_consistency import (
    check_consistency,
    hash_lock_diagnostics,
)


def _write_repository(
    root: Path,
    *,
    runtime: str = "runtime-package==1.0.0\n",
    development: str = "dev-package==2.0.0\npydantic-settings==2.14.2\n",
    browser_dependencies: str = '"browser-package==3.0.0"',
    browser_dev_dependencies: str = '"pydantic-settings==2.14.2"',
    lock: str | None = None,
    readme_pin: str = "pydantic-settings 2.14.2",
) -> None:
    (root / "tools" / "browser-use").mkdir(parents=True)
    (root / "requirements.txt").write_text(runtime, encoding="utf-8")
    (root / "requirements-dev.txt").write_text(development, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\ndependencies = []\n", encoding="utf-8"
    )
    (root / "tools" / "browser-use" / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                f"dependencies = [{browser_dependencies}]",
                "[tool.uv]",
                f"dev-dependencies = [{browser_dev_dependencies}]",
                "",
            )
        ),
        encoding="utf-8",
    )
    (root / "requirements.lock").write_text(
        lock
        or "\n".join(
            (
                "runtime-package==1.0.0",
                "dev-package==2.0.0",
                "browser-package==3.0.0",
                "pydantic-settings==2.14.2",
                "",
            )
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"Dependency security baseline: `{readme_pin}`\n", encoding="utf-8"
    )


def test_matching_exact_pins_pass(tmp_path: Path) -> None:
    _write_repository(tmp_path)

    assert check_consistency(tmp_path) == ()


def test_declared_pin_missing_from_lock_identifies_manifest_and_package(
    tmp_path: Path,
) -> None:
    _write_repository(
        tmp_path,
        lock="dev-package==2.0.0\nbrowser-package==3.0.0\npydantic-settings==2.14.2\n",
    )

    assert check_consistency(tmp_path) == (
        "requirements.txt: runtime-package declared 1.0.0, locked missing",
    )


def test_conflicting_versions_across_manifests_fail(tmp_path: Path) -> None:
    _write_repository(
        tmp_path,
        development="dev-package==2.0.0\npydantic-settings==2.13.1\n",
    )

    assert check_consistency(tmp_path) == (
        "conflicting exact declarations for pydantic-settings: "
        "requirements-dev.txt declares 2.13.1; "
        "tools/browser-use/pyproject.toml declares 2.14.2",
    )


def test_inactive_environment_marker_does_not_require_a_lock_pin(
    tmp_path: Path,
) -> None:
    _write_repository(
        tmp_path,
        browser_dependencies=(
            '"browser-package==3.0.0", "darwin-only==1.0.0; sys_platform == \'darwin\'"'
        ),
    )

    assert check_consistency(tmp_path, environment={"sys_platform": "win32"}) == ()


def test_documented_security_pin_mismatch_identifies_readme(tmp_path: Path) -> None:
    _write_repository(tmp_path, readme_pin="pydantic-settings 2.13.1")

    assert check_consistency(tmp_path) == (
        "README.md: pydantic-settings declared 2.13.1, locked 2.14.2",
    )


def test_hash_lock_diagnostics_require_active_linux_hashes(tmp_path: Path) -> None:
    _write_repository(
        tmp_path,
        lock=(
            "runtime-package==1.0.0 \\\n"
            f"    --hash=sha256:{'a' * 64}\n"
            "linux-unverified==2.0.0\n"
            "windows-only==3.0.0; platform_system == 'Windows'\n"
        ),
    )

    assert hash_lock_diagnostics(
        tmp_path,
        environment={"platform_system": "Linux", "sys_platform": "linux"},
    ) == ("requirements.lock: linux-unverified has no SHA-256 hash",)


def test_ci_installs_the_lock_with_hash_verification() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python -m pip install --require-hashes -r requirements.lock" in workflow
