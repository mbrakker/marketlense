from __future__ import annotations

from scripts.ci.run_quality_gate import quality_gate_commands
from scripts.ci.run_refactor_audit import refactor_audit_commands
from scripts.ci.check_refactor_movement_evidence import validate_movement_evidence
from scripts.ci.check_role_io_boundaries import scan_additional_role_io
from scripts.ci.check_service_boundary_map import scan_service_boundary_map


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
    assert any("scripts/count_long_files.py" in command for command in rendered)
    assert any("check_role_io_boundaries.py" in command for command in rendered)
    assert any("check_service_boundary_map.py" in command for command in rendered)
    assert any("check_refactor_movement_evidence.py" in command for command in rendered)


def test_role_io_gate_flags_environment_and_binary_media_imports(tmp_path) -> None:
    generator_root = tmp_path / "src" / "generators"
    utility_root = tmp_path / "src" / "utils"
    generator_root.mkdir(parents=True)
    utility_root.mkdir(parents=True)
    (generator_root / "bad.py").write_text(
        "import os\nfrom PIL import Image\nVALUE = os.getenv('TOKEN')\n",
        encoding="utf-8",
    )

    violations = scan_additional_role_io(tmp_path, allowlist_entries=[])

    assert {item.rule for item in violations} == {
        "binary_media_import",
        "environment_access",
    }


def test_service_boundary_gate_rejects_new_peer_provider_entrypoint(tmp_path) -> None:
    services = tmp_path / "src" / "services"
    services.mkdir(parents=True)
    (services / "openai_helper_service.py").write_text(
        "from openai import OpenAI\n",
        encoding="utf-8",
    )
    config = {
        "systems": {
            "openai": {
                "import_prefixes": ["openai"],
                "canonical_entrypoint": "src/services/llm_service.py",
                "private_roots": ["src/services/_llm_service/"],
            }
        }
    }

    violations = scan_service_boundary_map(tmp_path, config)

    assert len(violations) == 1
    assert violations[0].system == "openai"


def test_movement_evidence_requires_symbol_counts_and_facade_ownership() -> None:
    errors = validate_movement_evidence(
        {
            "schema_version": "1.0",
            "records": [
                {
                    "original_file": "src/example.py",
                    "baseline_ref": "HEAD:src/example.py",
                    "moved_symbol_count": 3,
                    "unchanged_moved_symbol_count": 3,
                    "changed_moved_symbol_count": 0,
                    "facade_owned_definitions": ["public_api"],
                }
            ],
        }
    )

    assert errors == []
