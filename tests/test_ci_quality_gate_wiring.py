from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_policy_backed_structural_and_lint_gates() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python scripts/ci/check_ruff_lint.py" in ci
    assert "python scripts/ci/check_role_io_boundaries.py" in ci
    assert "python scripts/ci/check_service_boundary_map.py" in ci
    assert "python scripts/ci/check_refactor_movement_evidence.py" in ci


def test_dependency_lock_and_pyproject_are_present() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (ROOT / "requirements.lock").read_text(encoding="utf-8")

    assert "[tool.ruff]" in pyproject
    assert "[tool.pytest.ini_options]" in pyproject
    assert "[tool.mypy]" in pyproject
    assert "openai==" in lockfile
    assert "streamlit==" in lockfile
