from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.check_remediation_runbooks import validate_remediation_runbooks


def test_remediation_runbooks_validate_committed_registry() -> None:
    codes = validate_remediation_runbooks(Path("docs/ops/failure_remediation.yaml"))

    assert "pdf_text_unextractable" in codes
    assert "browser_download_timeout" in codes
    assert "claim_embedding_provider_count_mismatch" in codes


def test_remediation_runbooks_require_dry_run_hooks(tmp_path: Path) -> None:
    runbook_path = tmp_path / "runbook.md"
    runbook_path.write_text("runbook", encoding="utf-8")
    registry_path = tmp_path / "registry.yaml"
    runbook_yaml_path = runbook_path.as_posix()
    registry_path.write_text(
        f"""
schema_version: "1.0"
last_drill_date: "2026-04-25"
owner: "operations"
runbooks:
  - failure_code: "failure"
    owner: "ops"
    severity: "warning"
    runbook_path: "{runbook_yaml_path}"
    dashboard_link: "local://logs"
    alert_labels:
      stage: "stage"
    detector_log_events:
      - "event"
    remediation_hooks:
      - name: "unsafe"
        trigger: "automatic"
        dry_run: false
        command: "python -m src.cli ingest"
        safety: "none"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be dry_run"):
        validate_remediation_runbooks(registry_path)
