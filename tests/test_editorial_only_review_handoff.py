"""Reviewer disposition handoff through the real public-quality boundary."""

import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.generators.public_editorial_quality_generator import (
    public_editorial_semantic_review_items,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.orchestrators._report_analysis_orchestrator.validation import (
    _evaluate_and_store_public_editorial_quality,
)
from tests._test_report_analysis_generator._shared import _artifacts, _runtime
from tests.test_public_editorial_review_reuse import _SemanticPassClient


class ReviewClient(_SemanticPassClient):
    def __init__(self, items, *, mode, rule):
        super().__init__(items)
        self.mode = mode
        self.rule = rule

    def openai_chat_json(self, request, ctx):
        response = super().openai_chat_json(request, ctx)
        payload = response.parsed_json
        item = next(
            value
            for value in self.items
            if value.get("artifact") == "insights_final"
            and value.get("field") == "insights:insight-1.so_what"
        )
        verdict = next(
            value
            for value in payload["verdicts"]
            if value["item_id"] == item["public_item_id"]
        )
        if self.mode in {"report_only", "report_legacy", "report_unresolved"}:
            report = payload["report_verdict"]
            report.update(
                status="fail",
                severity="error",
                rule_id=self.rule,
                hard_fail_class=(
                    "editorial_only"
                    if self.mode in {"report_only", "report_unresolved"}
                    else "report_editorial_acceptance"
                ),
                reason="The report's analysis lacks a distinct implication.",
                evidence_ids=[],
                repair_target="",
                affected_item_id="",
            )
            report["dimensions"]["analytical_depth"] = {
                "status": "unresolved" if self.mode == "report_unresolved" else "fail",
                "reason": "The report needs more specific analysis.",
            }
        elif self.mode in {"nomination", "mixed_dimensions", "failed_nomination"}:
            verdict["classification"] = "analyst_interpretation"
            if self.mode == "failed_nomination":
                verdict.update(
                    status="fail",
                    severity="error",
                    rule_id="public_editorial_quality.semantic_decision_value",
                    hard_fail_class="editorial_only",
                    reason="This implication lacks decision value.",
                    repair_target=item["repair_target"],
                )
            report = payload["report_verdict"]
            report.update(
                status="fail",
                severity="error",
                rule_id=self.rule,
                hard_fail_class="editorial_only",
                reason="The report needs a distinct implication.",
                repair_items=[
                    {
                        "item_id": item["public_item_id"],
                        "reason": "Make the implication distinct.",
                        "evidence_ids": list(item["evidence_ids"]),
                        "repair_target": item["repair_target"],
                    }
                ],
            )
            report["dimensions"]["analytical_depth"] = {
                "status": "fail",
                "reason": "The implication is generic.",
            }
            if self.mode == "mixed_dimensions":
                report["dimensions"]["limitations"] = {
                    "status": "fail",
                    "reason": "A material limitation is omitted.",
                }
        else:
            verdict.update(
                status="fail",
                severity="error",
                rule_id=self.rule,
                classification="factual_claim"
                if self.mode == "factual"
                else "analyst_interpretation",
                hard_fail_class="editorial_quality"
                if self.mode == "legacy"
                else "editorial_only",
                reason="The insight needs a more specific implication.",
                repair_target=item["repair_target"],
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            model=request.model,
        )


def _review(tmp_path, *, mode, rule):
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    artifacts["insights_final"][0]["so_what"] = "The implication is generic."
    items = public_editorial_semantic_review_items(artifacts)
    report, _ = _evaluate_and_store_public_editorial_quality(
        runtime=runtime,
        dependencies=ReportAnalysisDependencies.default(),
        artifacts=artifacts,
        pack_name="public_editorial_quality_test",
        ctx=runtime.ctx,
        openai_client=ReviewClient(items, mode=mode, rule=rule),
    )
    return report


@pytest.mark.parametrize(
    "rule",
    [
        "public_editorial_quality.semantic_analytical_depth",
        "public_editorial_quality.semantic_unexpected_but_editorial",
    ],
)
def test_item_editorial_only_survives_handoff_independent_of_rule_id(tmp_path, rule):
    report = _review(tmp_path, mode="item", rule=rule)
    issue = next(issue for issue in report.issues if issue.rule_id == rule)
    assert issue.violation_type == "editorial_only"
    assert issue.classification == "analyst_interpretation"
    assert issue.repair_target == "insights_bundle"


def test_collective_editorial_only_disposition_reaches_nomination(tmp_path):
    report = _review(
        tmp_path,
        mode="nomination",
        rule="public_editorial_quality.semantic_unexpected_but_editorial",
    )
    issue = next(
        (
            issue
            for issue in report.issues
            if issue.rule_id
            == "public_editorial_quality.semantic_collective_editorial_repair"
        ),
        None,
    )
    assert issue is not None, "Valid editorial-only nomination was rejected"
    assert issue.violation_type == "editorial_only"
    assert issue.entity_id == "insight:insight-1:so_what"
    assert issue.evidence_ids == ["f1"]


def test_failed_editorial_only_item_can_be_collectively_nominated(tmp_path):
    report = _review(
        tmp_path,
        mode="failed_nomination",
        rule="public_editorial_quality.semantic_distinctness",
    )
    nominated = next(
        (
            issue
            for issue in report.issues
            if issue.rule_id
            == "public_editorial_quality.semantic_collective_editorial_repair"
        ),
        None,
    )
    assert nominated is not None, "Failed editorial-only item nomination was rejected"
    assert nominated.entity_id == "insight:insight-1:so_what"
    assert nominated.violation_type == "editorial_only"
    assert nominated.evidence_ids == ["f1"]


def test_unresolved_editorial_dimension_cannot_authorize_editorial_only(tmp_path):
    rule = "public_editorial_quality.semantic_analytical_depth"
    report = _review(tmp_path, mode="report_unresolved", rule=rule)
    assert not any(
        issue.rule_id == rule and issue.violation_type == "editorial_only"
        for issue in report.issues
    ), "An unresolved report dimension was accepted as editorial-only"
    assert report.status == "fail"


def test_factual_claim_cannot_be_labeled_editorial_only(tmp_path):
    report = _review(
        tmp_path,
        mode="factual",
        rule="public_editorial_quality.semantic_unexpected_but_editorial",
    )
    assert not any(
        issue.violation_type == "editorial_only"
        and issue.classification == "factual_claim"
        for issue in report.issues
    ), "Contradictory factual classification was accepted as editorial-only"
    assert report.status == "fail"


def test_report_with_source_limitation_failure_cannot_be_editorial_only(tmp_path):
    report = _review(
        tmp_path,
        mode="mixed_dimensions",
        rule="public_editorial_quality.semantic_unexpected_but_editorial",
    )
    assert not any(
        issue.rule_id == "public_editorial_quality.semantic_collective_editorial_repair"
        and issue.violation_type == "editorial_only"
        for issue in report.issues
    )
    assert report.status == "fail"


def test_legacy_editorial_quality_is_not_upgraded_to_editorial_only(tmp_path):
    report = _review(
        tmp_path,
        mode="legacy",
        rule="public_editorial_quality.semantic_analytical_depth",
    )
    issue = next(
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.semantic_analytical_depth"
    )
    assert issue.violation_type == "editorial_quality"
    assert issue.violation_type != "editorial_only"


@pytest.mark.parametrize(
    "rule",
    [
        "public_editorial_quality.semantic_decision_value",
        "public_editorial_quality.semantic_distinct_commercial_analysis",
    ],
)
def test_evidence_free_editorial_only_report_accepts_arbitrary_diagnostic_rule(
    tmp_path, rule
):
    report = _review(tmp_path, mode="report_only", rule=rule)
    issue = next((issue for issue in report.issues if issue.rule_id == rule), None)
    assert issue is not None, "Valid evidence-free editorial report was rejected"
    assert issue.violation_type == "editorial_only"
    assert issue.evidence_ids == []
    assert issue.repair_target == ""
    assert report.status == "fail"


def test_evidence_free_legacy_report_acceptance_keeps_existing_prefix_rule(tmp_path):
    report = _review(
        tmp_path,
        mode="report_legacy",
        rule="public_editorial_quality.report_editorial_acceptance",
    )
    issue = next(
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.report_editorial_acceptance"
    )
    assert issue.violation_type == "report_editorial_acceptance"
    assert issue.evidence_ids == []


def test_evidence_free_legacy_semantic_rule_remains_unresolved(tmp_path):
    rule = "public_editorial_quality.semantic_decision_value"
    report = _review(tmp_path, mode="report_legacy", rule=rule)
    assert not any(issue.rule_id == rule for issue in report.issues)
    assert report.status == "fail"
