from __future__ import annotations

from pathlib import Path

from scripts.ci.check_dependency_consistency import (
    check_consistency,
    declared_exact_pins,
    diagnostics_for_supported_environments,
    hash_lock_diagnostics,
    locked_pins,
)

UNUSED_GPU_STACK_PACKAGES = frozenset(
    {
        "cuda-bindings",
        "cuda-pathfinder",
        "nvidia-cublas-cu12",
        "nvidia-cuda-cupti-cu12",
        "nvidia-cuda-nvrtc-cu12",
        "nvidia-cuda-runtime-cu12",
        "nvidia-cudnn-cu12",
        "nvidia-cufile-cu12",
        "nvidia-cufft-cu12",
        "nvidia-curand-cu12",
        "nvidia-cusolver-cu12",
        "nvidia-cusparse-cu12",
        "nvidia-cusparselt-cu12",
        "nvidia-nccl-cu12",
        "nvidia-nvjitlink-cu12",
        "nvidia-nvshmem-cu12",
        "nvidia-nvtx-cu12",
        "triton",
    }
)


def _write_repository(
    root: Path,
    *,
    runtime: str = "runtime-package==1.0.0\n",
    development: str = "dev-package==2.0.0\npydantic-settings==2.14.2\n",
    browser_dependencies: str = '"browser-package==3.0.0"',
    browser_dev_dependencies: str = '"pydantic-settings==2.14.2"',
    lock: str | None = None,
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


def test_matching_exact_pins_pass(tmp_path: Path) -> None:
    _write_repository(tmp_path)

    assert check_consistency(tmp_path) == ()


def test_unused_gpu_stack_is_not_in_the_canonical_lock() -> None:
    root = Path(__file__).resolve().parents[1]
    locked, diagnostics = locked_pins(root)
    declared = {package for package, _version, _source in declared_exact_pins(root)}
    unused_gpu_packages = UNUSED_GPU_STACK_PACKAGES | (
        {"torch"} if "torch" not in declared else set()
    )

    assert diagnostics == ()
    assert not (unused_gpu_packages & locked.keys())


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


def test_vendored_build_backend_pin_must_match_the_lock(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    browser_pyproject = tmp_path / "tools" / "browser-use" / "pyproject.toml"
    browser_pyproject.write_text(
        browser_pyproject.read_text(encoding="utf-8")
        + '\n[build-system]\nrequires = ["hatchling==1.32.4", "editables==0.6"]\n',
        encoding="utf-8",
    )

    assert check_consistency(tmp_path) == (
        "tools/browser-use/pyproject.toml: editables declared 0.6, locked missing",
        "tools/browser-use/pyproject.toml: hatchling declared 1.32.4, locked missing",
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


def test_hash_lock_diagnostics_require_the_active_platform_hash(tmp_path: Path) -> None:
    verified_hash = "a" * 64
    _write_repository(
        tmp_path,
        lock=(
            "runtime-package==1.0.0 \\\n"
            f"    --hash=sha256:{verified_hash}\n"
            "dev-package==2.0.0 \\\n"
            f"    --hash=sha256:{verified_hash}\n"
            "browser-package==3.0.0 \\\n"
            f"    --hash=sha256:{verified_hash}\n"
            "pydantic-settings==2.14.2 \\\n"
            f"    --hash=sha256:{verified_hash}\n"
            "linux-only==1.0.0; sys_platform == 'linux'\n"
            "windows-only==1.0.0; platform_system == 'Windows'\n"
        ),
    )

    assert hash_lock_diagnostics(
        tmp_path,
        environment={"platform_system": "Windows", "sys_platform": "win32"},
    ) == ("requirements.lock: windows-only has no SHA-256 hash",)
    assert hash_lock_diagnostics(
        tmp_path,
        environment={"platform_system": "Linux", "sys_platform": "linux"},
    ) == ("requirements.lock: linux-only has no SHA-256 hash",)


def test_supported_environment_diagnostics_require_windows_hashes() -> None:
    root = Path(__file__).resolve().parents[1]

    diagnostics = diagnostics_for_supported_environments(root)

    assert diagnostics == ()


def test_ci_installs_the_lock_with_hash_verification() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python -m pip install --require-hashes -r requirements.lock" in workflow


def test_ci_does_not_cache_pip_for_the_hash_locked_dependency_manifest() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    setup_python_steps = workflow.split("      - uses: actions/setup-python@v5")[1:]

    assert len(setup_python_steps) == 3
    assert all(
        "cache: pip" not in step.split("      - name:", maxsplit=1)[0]
        and "cache-dependency-path:" not in step.split("      - name:", maxsplit=1)[0]
        for step in setup_python_steps
    )
