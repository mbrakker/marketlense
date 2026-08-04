from __future__ import annotations

from scripts.quality.autonomous_happy_path_smoke import (
    run_autonomous_happy_path_smoke,
)
from scripts.ci.run_quality_gate import quality_gate_commands
from scripts.ci.run_refactor_audit import refactor_audit_commands
from scripts.quality.capability_maps import build_capability_maps, diff_capability_maps
from scripts.ci.check_refactor_movement_evidence import validate_movement_evidence
from scripts.ci.check_role_io_boundaries import scan_additional_role_io
from scripts.ci.check_service_boundary_map import scan_service_boundary_map


def test_quality_gate_covers_canonical_ci_checks_in_order() -> None:
    commands = quality_gate_commands()
    rendered = [" ".join(command) for command in commands]

    expected_pre_test_gates = [
        "python scripts/ci/check_dependency_consistency.py",
        "python scripts/ci/check_formatting.py",
        "python scripts/ci/check_ruff_lint.py",
        "python scripts/ci/check_risk_policy.py",
        "python scripts/ci/check_split_symbol_links.py",
        "python scripts/ci/run_type_check.py",
        "python scripts/ci/check_architecture_imports.py",
        "python scripts/ci/check_agent_policy.py",
        "python scripts/ci/check_role_io_boundaries.py",
        "python scripts/ci/check_service_boundary_map.py",
        "python scripts/ci/check_refactor_movement_evidence.py",
    ]

    assert rendered[: len(expected_pre_test_gates)] == expected_pre_test_gates
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


def test_capability_maps_include_side_effect_idempotency_and_failure_runbooks() -> None:
    maps = build_capability_maps()

    assert maps["schema_version"] == "1.0"
    assert (
        maps["external_systems"]["openai"]["canonical_service"]
        == "src/services/llm_service.py"
    )
    assert (
        maps["workflows"]["mail_acquisition"]["orchestrator"]
        == "src/orchestrators/mail_report_acquisition_orchestrator.py"
    )
    assert maps["side_effects"]["wordpress_posts"]["idempotency_scope"]
    assert maps["side_effects"]["mail_delivery_requests"]["idempotency_scope"]
    assert maps["side_effects"]["mailbox_candidate_rejections"]["idempotency_scope"]
    assert "mail_report_not_arrived_yet" in maps["failure_codes"]
    assert "autonomous_happy_path" in maps["smoke_suites"]

    stale = dict(maps)
    stale["side_effects"] = dict(maps["side_effects"])
    stale["side_effects"].pop("wordpress_posts")

    assert diff_capability_maps(expected=maps, actual=stale) == [
        "side_effects.wordpress_posts missing"
    ]


def test_autonomous_happy_path_smoke_runs_mailbox_workflow_and_route_memory(
    tmp_path,
) -> None:
    payload = run_autonomous_happy_path_smoke(tmp_path)

    assert payload["status"] == "passed"
    assert payload["processed_count"] == 1
    assert payload["succeeded_count"] == 1
    assert payload["route_memory_promoted"] is True
    assert payload["route_kind"] == "email_delivery"
    assert payload["route_outcome"] == "downloaded"
    assert payload["downloaded_file_size_bytes"] > 0

    replay_payload = run_autonomous_happy_path_smoke(tmp_path)

    assert replay_payload["status"] == "passed"
    assert replay_payload["processed_count"] == 0
    assert replay_payload["succeeded_count"] == 0
    assert replay_payload["route_memory_promoted"] is True
    assert replay_payload["idempotent_replay_confirmed"] is True
