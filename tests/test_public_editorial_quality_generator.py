from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.services._config_service.validation import _resolve_validation_settings

_GOLDEN_ARTIFACT = next(
    (Path(__file__).parent / "fixtures" / "docpacks" / "golden").glob(
        "*/report_analysis/artifacts.json"
    )
)


def _retained_artifacts() -> dict:
    return json.loads(_GOLDEN_ARTIFACT.read_text(encoding="utf-8"))


def _rule_ids(report) -> set[str]:
    return {issue.rule_id for issue in report.issues}


def _set_near_duplicate(payload: dict) -> None:
    payload["insights_final"][0].update(
        {
            "text": "A 70% rate is reported for retail buyers in 2026.",
            "evidence": "A 70% rate is reported for retail buyers in 2026.",
            "evidence_id": "retained-70",
        }
    )
    payload["insights_final"][1].update(
        {
            "text": "In 2026, retail buyers are reported at a 70% rate.",
            "evidence": "A 70% rate is reported for retail buyers in 2026.",
            "evidence_id": "retained-70",
        }
    )


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


def test_public_html_blocks_operational_source_and_editorial_scaffolding() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            '<a href="https://drive.google.com/file/d/private">Source</a>'
            "<p>Observation: the source says demand rose...</p>"
        ),
    )

    assert report.status == "fail"
    assert {
        "public_editorial_quality.private_operational_reference",
        "public_editorial_quality.mechanical_editorial_scaffold",
        "public_editorial_quality.literal_truncation",
    } <= _rule_ids(report)


def test_public_html_ignores_non_visible_text_in_spaced_script_tags() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<script >Drive file ID: private-123</script >",
    )

    assert report.status == "pass"
    assert "public_editorial_quality.internal_identifier" not in _rule_ids(report)


def test_public_html_allows_pipe_separated_public_taxonomy_labels() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<small>luxury | premium | midscale, Global, announced 2026</small>",
    )

    assert "public_editorial_quality.malformed_extraction_fragment" not in _rule_ids(
        report
    )


def test_public_html_allows_ellipsis_that_closes_a_quoted_prompt() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<p>Use the prompt “We are doing this because we believe…” to surface assumptions.</p>",
    )

    assert "public_editorial_quality.literal_truncation" not in _rule_ids(report)


def test_public_html_source_section_requires_a_public_original_source_link() -> None:
    missing = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html='<section id="source"><p>Source details</p></section>',
    )
    linked = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            '<section id="source">'
            '<a href="https://publisher.example/report" rel="noopener">'
            "Open original source</a></section>"
        ),
    )
    unavailable = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html='<section id="source"><p>Source URL: Not available</p></section>',
    )

    assert "public_editorial_quality.public_source_provenance_missing" in _rule_ids(
        missing
    )
    assert "public_editorial_quality.public_source_provenance_missing" not in _rule_ids(
        linked
    )
    assert "public_editorial_quality.public_source_provenance_missing" not in _rule_ids(
        unavailable
    )


@pytest.mark.parametrize(
    ("rule_id", "mutate"),
    [
        (
            "public_editorial_quality.unsupported_numeric_claim",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The retained finding reports 99% adoption."}
            ),
        ),
        (
            "public_editorial_quality.material_claim_evidence_missing",
            lambda payload: payload["insights_final"][0].update(
                {"evidence_id": "", "evidence": ""}
            ),
        ),
        (
            "public_editorial_quality.internal_identifier",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Drive file ID: private-123 remains relevant."}
            ),
        ),
        (
            "public_editorial_quality.placeholder",
            lambda payload: payload["insights_final"][0].update(
                {"text": "{{ replace with source-backed insight }}"}
            ),
        ),
        (
            "public_editorial_quality.malformed_extraction_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The platfor | ms are changing."}
            ),
        ),
        (
            "public_editorial_quality.text_corruption",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Consumer demand rose by 12â€% in the survey."}
            ),
        ),
        (
            "public_editorial_quality.duplicate_insight",
            _set_near_duplicate,
        ),
        (
            "public_editorial_quality.sentence_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Across the market, and"}
            ),
        ),
        (
            "public_editorial_quality.ocr_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The consum3rjourney is changing."}
            ),
        ),
        (
            "public_editorial_quality.generic_figure_label",
            lambda payload: payload.update(
                {
                    "chart_insight_cards": [
                        {
                            "status": "generated",
                            "crop_qa_accepted": True,
                            "title": "Figure 1",
                            "caption": "Retail demand moves across channels.",
                            "evidence_id": "retained-figure",
                        }
                    ]
                }
            ),
        ),
        (
            "public_editorial_quality.fallback_boilerplate",
            lambda payload: payload["insights_final"][0].update(
                {
                    "text": "Decision relevance: source-backed finding.",
                    "evidence": "Decision relevance: source-backed finding.",
                }
            ),
        ),
        (
            "public_editorial_quality.unsupported_certainty",
            lambda payload: payload["insights_final"][0].update(
                {
                    "text": "The evidence will certainly determine the market.",
                    "evidence_status": "limited",
                }
            ),
        ),
        (
            "public_editorial_quality.nonspecific_decision_implication",
            lambda payload: payload["insights_final"][0].update(
                {"now_what": "Review the finding."}
            ),
        ),
    ],
)
def test_public_editorial_blockers_detect_mutations_of_retained_artifact(
    rule_id: str, mutate
) -> None:
    artifacts = deepcopy(_retained_artifacts())
    mutate(artifacts)

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert report.status == "fail"
    assert rule_id in _rule_ids(report)


def test_public_editorial_html_missing_asset_is_a_blocker(tmp_path: Path) -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<img src='missing-chart.png'>",
        html_path=str(tmp_path / "report.html"),
    )

    assert "public_editorial_quality.missing_asset" in _rule_ids(report)


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

    assert "public_editorial_quality.incomplete_numeric_expression" in _rule_ids(
        report
    )
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
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]


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
