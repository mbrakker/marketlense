from __future__ import annotations

from scripts.ci.check_risk_policy import build_report, classify_changed_files


def test_risk_policy_marks_critical_layer_changes() -> None:
    policy = classify_changed_files(["src/services/openai_service.py"])

    assert policy.name == "critical"
    assert policy.coverage_services_min > 44.0
    assert "mutation" in policy.required_gates


def test_risk_policy_marks_contract_changes() -> None:
    report = build_report(["src/contracts/report_assets.py", "README.md"])

    assert report.policy.name == "contract"
    assert "contract-schema-snapshot" in report.policy.required_gates


def test_risk_policy_marks_docs_only_changes() -> None:
    policy = classify_changed_files(["docs/quality/example.md", "README.md"])

    assert policy.name == "docs"
    assert policy.required_gates == ("format",)
