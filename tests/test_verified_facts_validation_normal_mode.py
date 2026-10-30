from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)


def test_normal_mode_numeric_quality_rule_remains_active():
    report = evaluate_public_editorial_quality(
        report_id="normal-mode",
        artifacts={
            "insights_final": [
                {
                    "id": "normal-1",
                    "text": "Adoption reached 99%.",
                    "evidence_id": "finding-1",
                    "evidence": "Adoption reached 42%.",
                    "metric": {},
                }
            ]
        },
    )

    assert "public_editorial_quality.unsupported_numeric_claim" in {
        issue.rule_id for issue in report.issues
    }
