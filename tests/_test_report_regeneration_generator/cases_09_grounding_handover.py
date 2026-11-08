from __future__ import annotations

from types import SimpleNamespace

from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import _build_grounding_package
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _normalize_regeneration_issue,
)


def test_grounding_package_preserves_all_validator_fact_bindings_and_pages() -> None:
    artifacts = {
        "insights_final": [
            {
                "id": "insight-1",
                "evidence_id": "fact-1",
                "evidence_ids": ["fact-1", "fact-2"],
                "pages": [4, 5],
            },
            {"id": "insight-2", "evidence_id": "unrelated", "pages": [99]},
        ]
    }
    issue = ValidationIssue(
        rule_id="grounding",
        affected_section="insights:insight-1.text",
        message="The composite claim needs repair.",
        severity="error",
        repair_target="insights_bundle",
        entity_id="insight:insight-1:text",
        evidence_ids=["fact-1", "fact-2"],
    )

    normalized = _normalize_regeneration_issue(issue, artifacts)
    target = RegenerationTarget(
        target_section="insights_bundle",
        issues=[
            RegenerationIssue(
                rule_id=normalized.rule_id,
                affected_section=normalized.affected_section,
                message=normalized.message,
                severity=normalized.severity,
                evidence_ids=normalized.evidence_ids,
                pages=normalized.pages,
            )
        ],
    )
    package = _build_grounding_package(
        target=target,
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts=artifacts,
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "fact-1", "text": "First fact", "pages": [4]},
                    {"id": "fact-2", "text": "Second fact", "pages": [5]},
                    {"id": "unrelated", "text": "Other fact", "pages": [99]},
                ]
            }
        },
        doc_map={},
    )

    assert normalized.evidence_ids == ["fact-1", "fact-2"]
    assert normalized.pages == [4, 5]
    assert package["evidence_ids"] == ["fact-1", "fact-2"]
    assert package["pages"] == [4, 5]
    assert "unrelated" not in package["evidence_ids"]


def test_unidentified_insight_grounding_abstains_instead_of_collecting_all_items():
    normalized = _normalize_regeneration_issue(
        ValidationIssue(
            rule_id="grounding",
            affected_section="insights",
            message="An insight claim needs repair.",
            severity="error",
            repair_target="insights_bundle",
        ),
        {
            "insights_final": [
                {"id": "one", "evidence_id": "fact-1", "pages": [4]},
                {"id": "two", "evidence_id": "fact-2", "pages": [5]},
            ]
        },
    )

    assert normalized.evidence_ids == []
    assert normalized.pages == []
