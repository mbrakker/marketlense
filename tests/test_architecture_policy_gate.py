from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from scripts.ci.check_architecture_imports import (
    ImportViolation,
    load_import_policy,
    scan_file,
)
from scripts.ci.check_service_boundary_map import load_service_boundary_config
from scripts.ci.policy import load_architecture_policy

ROOT = Path(__file__).resolve().parents[1]


def test_architecture_policy_encodes_required_enforcement_sections() -> None:
    policy = load_architecture_policy(
        ROOT / "docs" / "quality" / "architecture_policy.yaml"
    )

    assert policy["schema_version"] == "1.0"
    for section in (
        "roles",
        "allowed_imports_by_role",
        "allowed_io_by_role",
        "external_system_ownership",
        "forbidden_placeholders",
        "prompt_text_ownership",
        "test_patching_rules",
        "live_test_policy",
        "secret_policy",
        "policy_documents",
        "policy_validation",
        "waivers",
        "architecture_review_triggers",
        "decomposition_evidence_requirements",
    ):
        assert section in policy

    assert policy["test_patching_rules"]["monkeypatch"] == "forbidden"
    assert policy["policy_validation"]["agents_max_lines"] == 1000


def test_architecture_import_gate_reads_role_rules_from_policy(tmp_path: Path) -> None:
    policy_path = tmp_path / "architecture_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "roles": {"services": "services"},
                "allowed_imports_by_role": {"services": ["src.contracts", "src.utils"]},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    path = tmp_path / "src" / "services" / "bad_service.py"
    path.parent.mkdir(parents=True)
    path.write_text("from src.generators import publish_generator\n", encoding="utf-8")

    policy = load_import_policy(policy_path)
    violations = scan_file(path, policy=policy)

    assert violations == [
        ImportViolation(
            role="services",
            path=path,
            line=1,
            column=1,
            imported="src.generators",
            rule="services may only import src.contracts, src.utils",
        )
    ]


def test_service_boundary_policy_covers_required_external_systems() -> None:
    config = load_service_boundary_config(
        ROOT / "docs" / "quality" / "architecture_policy.yaml"
    )

    assert {
        "llm_providers",
        "google_drive",
        "wordpress",
        "filesystem",
        "sqlite",
        "browser_runtime",
        "pdf_ocr_stack",
        "email_imap",
        "http_network",
        "vector_store",
    } <= set(config["systems"])


def test_quality_gate_policy_sets_nonexpired_type_baseline_and_critical_thresholds() -> (
    None
):
    policy = load_architecture_policy(
        ROOT / "docs" / "quality" / "architecture_policy.yaml"
    )

    assert date.fromisoformat(policy["mypy_baseline"]["expires_at"]) >= date(2026, 7, 9)
    assert policy["coverage_thresholds"]["src/contracts"] >= 95.0
    assert policy["coverage_thresholds"]["src/generators"] >= 85.0
    assert policy["coverage_thresholds"]["src/orchestrators"] >= 80.0
    assert policy["coverage_thresholds"]["src/services"] >= 75.0
    assert policy["coverage_thresholds"]["src/control-plane"] >= 90.0
    assert policy["mutation"]["critical_min_score"] >= 85.0
