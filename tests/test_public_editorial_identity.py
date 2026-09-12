from src.contracts.validation import ValidationIssue
from src.generators.public_editorial_quality_generator import (
    enumerate_public_editorial_items,
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)


def test_insight_entity_identity_is_stable_across_evidence_rebinding() -> None:
    artifacts = {
        "insights_final": [
            {
                "insight_id": "IC-001",
                "text": "The retained finding reports 99% adoption.",
                "evidence_id": "f1",
                "evidence": "The retained finding reports 70% adoption.",
                "metric": {},
            }
        ]
    }

    def issue_and_plan() -> tuple[object, object]:
        report = evaluate_public_editorial_quality(
            report_id="retained-report", artifacts=artifacts
        )
        return report, _build_regeneration_plan(
            issues=validation_issues_from_public_editorial_quality(report),
            artifacts=artifacts,
            broad_retry_available=True,
        )

    first_report, first_plan = issue_and_plan()
    artifacts["insights_final"][0]["evidence_id"] = "f2"
    second_report, second_plan = issue_and_plan()

    assert {item.item_id for item in enumerate_public_editorial_items(artifacts)} == {
        "insight:IC-001:text"
    }
    assert [issue.public_item_id for issue in first_report.issues] == [
        "insight:IC-001:text"
    ]
    assert [issue.public_item_id for issue in second_report.issues] == [
        "insight:IC-001:text"
    ]
    assert [issue.evidence_ids for issue in first_report.issues] == [["f1"]]
    assert [issue.evidence_ids for issue in second_report.issues] == [["f2"]]
    assert first_plan.targets[0].issues[0].entity_id == "insight:IC-001:text"
    assert second_plan.targets[0].issues[0].entity_id == "insight:IC-001:text"
    assert first_plan.targets[0].issues[0].evidence_ids == ["f1"]
    assert second_plan.targets[0].issues[0].evidence_ids == ["f2"]


def test_targeted_insight_repair_uses_public_item_identity_before_section() -> None:
    artifacts = {
        "insights_final": [
            {"id": "IC-001", "evidence_id": "f1", "pages": [1]},
            {"id": "IC-002", "evidence_id": "f2", "pages": [2]},
        ]
    }

    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                schema_version="1.0",
                message="[public_editorial_quality.unsupported_numeric_claim] bad",
                severity="error",
                affected_section="insights:IC-002",
                rule_id="public_editorial_quality.unsupported_numeric_claim",
                repair_target="insights_bundle",
                entity_id="insight:IC-001:text",
                evidence_ids=["f1"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert plan.targets[0].issues[0].entity_id == "insight:IC-001:text"
    assert plan.targets[0].issues[0].evidence_ids == ["f1"]
    assert plan.targets[0].issues[0].pages == [1]
