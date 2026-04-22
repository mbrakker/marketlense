from __future__ import annotations

from scripts.ci.check_contract_schemas import build_contract_schema_snapshot


def test_contract_schema_snapshot_contains_schema_versions_and_required_fields() -> (
    None
):
    snapshot = build_contract_schema_snapshot()

    assert snapshot["schema_version"] == "1.0"
    run_context = snapshot["contracts"]["src.contracts.run_context.RunContext"]
    assert "schema_version" in run_context["properties"]
    assert run_context["required"] == ["schema_version", "run_id", "task_id", "span_id"]
