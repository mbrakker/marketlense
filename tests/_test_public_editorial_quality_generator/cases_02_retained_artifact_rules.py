# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_retained_public_artifact_has_no_editorial_blockers() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=_retained_artifacts()
    )

    assert report.status == "pass"
    assert not report.issues
    assert {item.rule_id for item in report.measurements} == {
        "public_editorial_quality.insight_role_diversity",
        "public_editorial_quality.repeated_syntax",
        "public_editorial_quality.excessive_verbosity",
        "public_editorial_quality.card_to_insight_linkage",
        "public_editorial_quality.figure_to_evidence_linkage",
        "public_editorial_quality.figure_to_insight_linkage",
        "public_editorial_quality.source_note_completeness",
        "public_editorial_quality.action_specificity",
    }


def test_public_chart_card_requires_retained_candidate_evidence_and_insight_chain() -> (
    None
):
    artifacts = _retained_artifacts()
    artifacts["chart_insight_cards"] = [
        {
            "status": "generated",
            "crop_qa_accepted": True,
            "title": "Demand shifts by channel",
            "caption": "Demand shifts by channel.",
            "evidence_id": "retained-70",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert report.status == "fail"
    assert "public_editorial_quality.figure_linkage_missing" in _rule_ids(report)


def test_linked_non_generic_public_chart_card_passes_figure_rules() -> None:
    artifacts = _retained_artifacts()
    artifacts["chart_insight_cards"] = [
        {
            "status": "generated",
            "crop_qa_accepted": True,
            "title": "Demand shifts by channel",
            "caption": "Demand shifts by channel.",
            "candidate_id": "candidate-1",
            "evidence_id": "retained-70",
            "source_page": 4,
            "insight_id": "insight-1",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert "public_editorial_quality.generic_figure_label" not in _rule_ids(report)
    assert "public_editorial_quality.figure_linkage_missing" not in _rule_ids(report)


def test_short_prose_and_legitimate_b2b_terminology_are_not_fragments() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update(
        {
            "text": "B2B marketers are adapting.",
            "evidence": "B2B marketers are adapting.",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert "public_editorial_quality.sentence_fragment" not in _rule_ids(report)
    assert "public_editorial_quality.ocr_fragment" not in _rule_ids(report)


def test_numeric_key_figure_display_is_not_treated_as_sentence_prose() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["key_figures"] = [
        {
            "label": "Retained adoption finding",
            "figure": "70 percent",
            "why_it_matters": "The retained adoption finding affects planning.",
            "evidence_id": "F1",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert "public_editorial_quality.sentence_fragment" not in _rule_ids(report)


def test_key_figure_numeric_display_does_not_repeat_comparative_periods() -> None:
    artifacts = deepcopy(_retained_artifacts())
    evidence = "Share fell from 43% in Q1 2024 to 41% in Q2 2025E."
    artifacts["insights_final"][0].update(
        {
            "text": evidence,
            "evidence": evidence,
            "evidence_id": "retained-comparison",
        }
    )
    artifacts["key_figures"] = [
        {
            "label": evidence,
            "figure": "43% to 41% share of Google searches resulting in clicks",
            "why_it_matters": evidence,
            "evidence_id": "retained-comparison",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert "public_editorial_quality.temporal_integrity" not in _rule_ids(report)


def test_selective_repair_targets_only_the_failed_insight_bundle() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update(
        {"text": "The retained finding reports 99% adoption."}
    )
    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]
    assert plan.targets[0].issues[0].evidence_ids
    assert plan.targets[0].issues[0].entity_id == "insight:IC-001:text"


def test_incomplete_currency_display_routes_to_existing_insight_repair() -> None:
    artifacts = _retained_artifacts()
    artifacts["insights_final"][0].update(
        {
            "text": "Revenue is projected to reach $1. next year.",
            "evidence": "Revenue is projected to reach $1.3T next year.",
            "evidence_id": "retained-revenue",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )
    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert "public_editorial_quality.incomplete_numeric_expression" in _rule_ids(report)
    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]


def test_currency_integer_truncated_before_source_decimal_routes_to_repair() -> None:
    artifacts = _retained_artifacts()
    artifacts["insights_final"][0].update(
        {
            "text": "Revenue is projected to grow from $2 next year.",
            "evidence": "Revenue is projected to grow from $2.7 trillion next year.",
            "evidence_id": "retained-revenue",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )
    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert "public_editorial_quality.incomplete_numeric_expression" in _rule_ids(report)
    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]


def test_truncated_key_figure_label_uses_linked_insight_for_repair() -> None:
    artifacts = _retained_artifacts()
    artifacts["insights_final"][0].update(
        {
            "id": "revenue-insight",
            "text": "Revenue is projected to grow from $2.7 trillion next year.",
            "evidence_id": "retained-revenue",
            "evidence": "Revenue is projected to grow from $2.7 trillion next year.",
        }
    )
    artifacts["key_figures"] = [
        {
            "label": "Revenue is projected to grow from $2",
            "figure": "$2.7 trillion projected revenue",
            "why_it_matters": "Revenue is projected to grow from $2",
            "evidence_id": "retained-revenue",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )
    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    affected_fields = {
        issue.affected_field
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.incomplete_numeric_expression"
    }
    assert "key_figures:1.label" in affected_fields
    assert "key_figures:1.why_it_matters" in affected_fields
    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["key_figures"]


@pytest.mark.parametrize("display", ["$1.3T", "€2.4bn", "12.5%"])
def test_complete_source_numeric_displays_remain_valid_editorial_copy(
    display: str,
) -> None:
    artifacts = _retained_artifacts()
    artifacts["insights_final"][0].update(
        {
            "text": f"The retained finding reports {display} in revenue.",
            "evidence": f"The retained finding reports {display} in revenue.",
            "evidence_id": "retained-metric",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert "public_editorial_quality.incomplete_numeric_expression" not in _rule_ids(
        report
    )


def test_missing_evidence_abstains_without_broad_regeneration() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update({"evidence_id": "", "evidence": ""})
    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    issues = validation_issues_from_public_editorial_quality(report)
    plan = _build_regeneration_plan(
        issues=issues, artifacts=artifacts, broad_retry_available=True
    )

    assert any(issue.repair_status == "abstained" for issue in report.issues)
    assert plan.mode == "skip"
    assert plan.targets == []


def test_public_quality_failure_propagates_exact_soft_claim_to_targeted_plan() -> None:
    sentences = ["Supported sibling.", "{{TODO}} unsupported claim.", "Final sibling."]
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:validator:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=({"page": index},),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    artifacts = {
        "expert_comment": " ".join(sentences),
        "insights_final": [
            {"evidence_id": f"f{index}", "evidence": f"Evidence {index}"}
            for index in range(1, 4)
        ],
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(claims),
    }

    report = evaluate_public_editorial_quality(
        report_id="claim-routing", artifacts=artifacts
    )
    issues = validation_issues_from_public_editorial_quality(report)
    plan = _build_regeneration_plan(
        issues=issues, artifacts=artifacts, broad_retry_available=True
    )

    issue = next(item for item in issues if item.entity_id == claims[1].claim_id)
    planned = plan.targets[0].issues[0]
    assert issue.affected_section == "expert_comment"
    assert planned.entity_id == claims[1].claim_id
    assert planned.evidence_ids == ["f2"]
    assert planned.pages == [2]


def test_rule_waiver_requires_a_nonempty_reason() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update(
        {"text": "Drive file ID: private-123 remains relevant."}
    )

    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=artifacts,
        disabled_rule_waivers={
            "public_editorial_quality.internal_identifier": "approved migration waiver",
            "public_editorial_quality.placeholder": "",
        },
    )

    assert "public_editorial_quality.internal_identifier" not in _rule_ids(report)
    assert report.disabled_rule_waivers == {
        "public_editorial_quality.internal_identifier": "approved migration waiver"
    }


def test_sentence_fragment_waiver_preserves_repairable_quality_status() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update({"text": "Across the market, and"})

    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=artifacts,
        disabled_rule_waivers={
            "public_editorial_quality.sentence_fragment": "controlled rollout"
        },
    )

    assert "public_editorial_quality.sentence_fragment" not in _rule_ids(report)
    assert report.hard_fail_count == 0
    assert report.status == "pass"


def test_config_keeps_only_explicit_public_editorial_rule_waivers() -> None:
    resolved = _resolve_validation_settings(
        {
            "public_editorial_quality": {
                "disabled_rule_waivers": {
                    "public_editorial_quality.placeholder": "approved rollout waiver",
                    "public_editorial_quality.ocr_fragment": "",
                }
            }
        }
    )

    assert resolved["public_editorial_quality_disabled_rule_waivers"] == {
        "public_editorial_quality.placeholder": "approved rollout waiver"
    }


def test_unsupported_public_factual_item_is_a_hard_publishability_failure() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["insights_final"][0].update(
        {
            "id": "activate-2021-spend",
            "text": "23% of users account for 77% of ecommerce spend.",
            "evidence": "22% of users account for 77% of ecommerce spend.",
            "evidence_id": "activate-2021-spend-evidence",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="activate-2021", artifacts=artifacts
    )

    hard_failure = next(
        issue
        for issue in report.issues
        if issue.affected_field == "insights:activate-2021-spend"
    )
    assert report.publishable is False
    assert hard_failure.hard_fail_class == "incorrect_numeric_value"
    assert hard_failure.public_item_id == "insight:activate-2021-spend:text"
