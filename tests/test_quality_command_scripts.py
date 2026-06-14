from __future__ import annotations

from scripts.ci.run_quality_gate import quality_gate_commands
from scripts.ci.run_refactor_audit import refactor_audit_commands


def test_quality_gate_covers_canonical_ci_checks_in_order() -> None:
    commands = quality_gate_commands()
    rendered = [" ".join(command) for command in commands]

    assert rendered[0].endswith("scripts/ci/check_formatting.py")
    assert any("run_type_check.py" in command for command in rendered)
    assert any("check_architecture_imports.py" in command for command in rendered)
    assert any("check_forbidden_patching.py" in command for command in rendered)
    assert any("check_contract_schemas.py" in command for command in rendered)
    assert any("check_wordpress_subproject.py" in command for command in rendered)
    assert any("-m pytest --cov=src" in command for command in rendered)
    assert any("run_mutation_gate.py" in command for command in rendered)
    assert rendered[-1].startswith(
        "python scripts/ci/check_prompt_fixture_regression.py"
    )


def test_refactor_audit_reuses_existing_structural_gates() -> None:
    rendered = [" ".join(command) for command in refactor_audit_commands()]

    assert any("check_split_symbol_links.py" in command for command in rendered)
    assert any("check_architecture_imports.py" in command for command in rendered)
    assert any("tests/test_io_boundaries.py" in command for command in rendered)
    assert any("scripts/count_long_files.py" in command for command in rendered)
