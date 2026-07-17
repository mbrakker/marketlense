from pathlib import Path

from scripts.quality.generate_remediation_coverage import (
    load_remediation_coverage,
    render_remediation_coverage,
)


def test_generated_remediation_coverage_inventory_is_complete_and_explicit() -> None:
    workflows = load_remediation_coverage(
        Path("docs/ops/remediation_workflow_coverage.yaml")
    )
    report = render_remediation_coverage(workflows)

    names = {item["workflow"] for item in workflows}
    assert {
        "ingest",
        "ingest_file",
        "candidate_extraction",
        "claim_embedding",
        "cross_report_analysis",
        "publisher_inventory_discovery",
        "wordpress_intelligence_projection",
        "report_card_date_remediation",
        "signal_candidate_extraction",
        "signal_post",
    } <= names
    assert all(item["coverage"] in {"covered", "exempt"} for item in workflows)
    assert all(
        item[field]
        for item in workflows
        for field in (
            "workflow_name",
            "entrypoint",
            "failure_boundary",
            "checkpoint_source",
            "idempotency_source",
            "budget_context_available",
            "current_remediation_status",
            "required_change",
            "test_reference",
        )
    )
    assert "Failure boundary" in report
    assert "31 production workflows" in report
