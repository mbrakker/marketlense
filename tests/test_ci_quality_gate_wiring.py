from __future__ import annotations

from pathlib import Path

from scripts.ci.run_quality_gate import quality_gate_commands

ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_policy_backed_structural_and_lint_gates() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python scripts/ci/check_ruff_lint.py" in ci
    assert "python scripts/ci/check_role_io_boundaries.py" in ci
    assert "python scripts/ci/check_service_boundary_map.py" in ci
    assert "python scripts/ci/check_refactor_movement_evidence.py" in ci
    assert "python scripts/ci/check_agent_policy.py" in ci


def test_dependency_lock_and_pyproject_are_present() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "[tool.ruff]" in pyproject
    assert "[tool.pytest.ini_options]" in pyproject
    assert "[tool.mypy]" in pyproject
    assert "openai==" in lockfile
    assert "streamlit==" in lockfile
    assert "python scripts/ci/check_dependency_consistency.py" in ci


def test_local_quality_gate_includes_github_structural_checks_in_ci_order() -> None:
    commands = quality_gate_commands()
    expected = (
        ("python", "scripts/ci/check_dependency_consistency.py"),
        ("python", "scripts/ci/check_formatting.py"),
        ("python", "scripts/ci/check_ruff_lint.py"),
        ("python", "scripts/ci/check_risk_policy.py"),
        ("python", "scripts/ci/check_split_symbol_links.py"),
        ("python", "scripts/ci/run_type_check.py"),
        ("python", "scripts/ci/check_architecture_imports.py"),
        ("python", "scripts/ci/check_agent_policy.py"),
        ("python", "scripts/ci/check_role_io_boundaries.py"),
        ("python", "scripts/ci/check_service_boundary_map.py"),
        ("python", "scripts/ci/check_refactor_movement_evidence.py"),
    )

    assert commands[: len(expected)] == expected
