from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.contracts.public_editorial_quality import PUBLIC_EDITORIAL_VALIDATOR_VERSION
from src.generators.public_editorial_quality_generator import (
    _public_text_items,
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
_TEMPORAL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "editorial_temporal"
_RELATIONSHIP_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "editorial_relationships"


def _retained_artifacts() -> dict:
    return json.loads(_GOLDEN_ARTIFACT.read_text(encoding="utf-8"))


def _temporal_fixture(name: str) -> dict:
    return json.loads((_TEMPORAL_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _relationship_fixture(name: str) -> dict:
    return json.loads((_RELATIONSHIP_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _rule_ids(report) -> set[str]:
    return {issue.rule_id for issue in report.issues}


def test_public_editorial_validator_version_invalidates_retained_v1_results() -> None:
    assert PUBLIC_EDITORIAL_VALIDATOR_VERSION == "public-editorial-quality:v3"


def _temporal_artifacts(*, text: str, evidence: str) -> dict:
    return {
        "insights_final": [
            {
                "id": "insight-temporal",
                "text": text,
                "evidence_id": "temporal-evidence",
                "evidence": evidence,
                "metric": {},
                "pages": [1],
                "so_what": "The comparison should inform the next reporting review.",
                "now_what": "Review the distinct source periods before acting.",
            }
        ]
    }


def _compact_tldr_artifacts(*, text: str, evidence: str) -> dict:
    return {
        "summary": {
            "tldr": "The retained Summary remains available.",
            "card_tldr_compact": text,
            "executive_summary": "The retained Summary remains available.",
            "claim_evidence_map": [
                {
                    "claim": text,
                    "evidence_id": "summary-evidence",
                    "evidence": evidence,
                    "pages": [1],
                }
            ],
        }
    }


def test_social_video_fixture_preserves_forecast_period_value_pairs() -> None:
    fixture = _relationship_fixture("social_video_ordered_metrics.json")

    valid = evaluate_public_editorial_quality(
        report_id="social-video",
        artifacts=_temporal_artifacts(
            text=fixture["valid_claim"], evidence=fixture["evidence"]
        ),
    )
    swapped_value = evaluate_public_editorial_quality(
        report_id="social-video",
        artifacts=_temporal_artifacts(
            text=fixture["swapped_value_claim"], evidence=fixture["evidence"]
        ),
    )
    swapped_period = evaluate_public_editorial_quality(
        report_id="social-video",
        artifacts=_temporal_artifacts(
            text=fixture["swapped_period_claim"], evidence=fixture["evidence"]
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" not in _rule_ids(valid)
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(
        swapped_value
    )
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(
        swapped_period
    )


def test_period_relationship_check_allows_an_implicit_shared_comparison_endpoint() -> None:
    evidence = (
        "Streaming viewing increased from 41% in 2022 to 70% in 2024, "
        "while traditional-TV viewing declined from 69% to 60%."
    )
    report = evaluate_public_editorial_quality(
        report_id="streaming-comparison",
        artifacts=_temporal_artifacts(
            text="Streaming reached 70% in 2024 while traditional TV remained 60% in 2024.",
            evidence=evidence,
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" not in _rule_ids(
        report
    )


def test_ordered_category_value_series_rejects_swapped_values_and_categories() -> None:
    evidence = "Platform preference: Alpha 43%; Beta 41%; Gamma 43%."

    valid = evaluate_public_editorial_quality(
        report_id="category-series",
        artifacts=_temporal_artifacts(
            text="Alpha has a 43% preference rate and Beta has 41%.",
            evidence=evidence,
        ),
    )
    swapped_value = evaluate_public_editorial_quality(
        report_id="category-series",
        artifacts=_temporal_artifacts(
            text="Beta has a 43% preference rate.", evidence=evidence
        ),
    )
    swapped_category = evaluate_public_editorial_quality(
        report_id="category-series",
        artifacts=_temporal_artifacts(
            text="Gamma has a 41% preference rate.", evidence=evidence
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" not in _rule_ids(valid)
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(
        swapped_value
    )
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(
        swapped_category
    )


def test_same_value_under_multiple_categories_requires_its_claimed_category() -> None:
    evidence = "Regional share: North 32%; South 32%; East 27%."
    report = evaluate_public_editorial_quality(
        report_id="category-series",
        artifacts=_temporal_artifacts(
            text="East accounts for 32% of regional share.", evidence=evidence
        ),
    )

    assert "public_editorial_quality.unsupported_numeric_claim" not in _rule_ids(report)
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(report)


def test_relationship_check_applies_to_summary_expert_linkedin_and_key_figures() -> None:
    evidence = "Average daily social-video time: 2023 0:48; 2024E 0:52; 2028E 0:57."
    artifacts = _temporal_artifacts(
        text="Average daily social-video time reaches 0:48 in 2024E.", evidence=evidence
    )
    artifacts["summary"] = {
        "tldr": "Average daily social-video time reaches 0:48 in 2024E.",
        "claim_evidence_map": [
            {"evidence_id": "temporal-evidence", "evidence": evidence}
        ],
    }
    artifacts["expert_comment"] = "Average daily social-video time reaches 0:48 in 2024E."
    artifacts["linkedin_post"] = "Average daily social-video time reaches 0:48 in 2024E."
    artifacts["key_figures"] = [
        {
            "label": "Average daily social-video time reaches 0:48 in 2024E.",
            "figure": "0:48 in 2024E",
            "why_it_matters": "Average daily social-video time reaches 0:48 in 2024E.",
            "evidence_id": "temporal-evidence",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="social-video", artifacts=artifacts
    )

    failed_fields = {
        issue.affected_field
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.metric_label_relationship"
    }
    assert {
        "insights:insight-temporal",
        "tldr",
        "expert_comment",
        "linkedin_post",
        "key_figures:1.label",
        "key_figures:1.figure",
        "key_figures:1.why_it_matters",
    } <= failed_fields


def test_relationship_failure_uses_existing_targeted_regeneration() -> None:
    evidence = "Average daily social-video time: 2023 0:48; 2024E 0:52; 2028E 0:57."
    artifacts = _temporal_artifacts(
        text="Average daily social-video time reaches 0:48 in 2024E.", evidence=evidence
    )
    report = evaluate_public_editorial_quality(
        report_id="social-video", artifacts=artifacts
    )

    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]


def test_public_text_items_includes_compact_summary_tldr_with_summary_evidence() -> None:
    artifacts = _compact_tldr_artifacts(
        text="U.S. internet advertising reached $258.6 billion in 2024.",
        evidence="U.S. internet advertising reached $258.6 billion in 2024.",
    )

    compact_item = next(
        item
        for item in _public_text_items(artifacts)
        if item["artifact"] == "summary" and item["field"] == "card_tldr_compact"
    )

    assert compact_item["evidence_ids"] == ["summary-evidence"]
    assert compact_item["evidence_text"] == (
        "U.S. internet advertising reached $258.6 billion in 2024."
    )
    assert compact_item["repair_target"] == "summary"


def test_compact_tldr_blocks_iab_truncated_currency_before_retained_decimal() -> None:
    report = evaluate_public_editorial_quality(
        report_id="iab-2024",
        artifacts=_compact_tldr_artifacts(
            text="U.S. internet advertising reached $258.",
            evidence="U.S. internet advertising reached $258.6 billion in 2024.",
        ),
    )

    issues = [
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.incomplete_numeric_expression"
    ]

    assert report.status == "fail"
    assert [(issue.affected_artifact, issue.affected_field) for issue in issues] == [
        ("summary", "card_tldr_compact")
    ]
    assert issues[0].evidence_ids == ["summary-evidence"]
    assert issues[0].repair_target == "summary"


def test_compact_tldr_blocks_collapsed_quarterly_comparison() -> None:
    report = evaluate_public_editorial_quality(
        report_id="iab-quarterly",
        artifacts=_compact_tldr_artifacts(
            text="Share fell from 43% in 2025 to 41% in 2025.",
            evidence="Share fell from 43% in Q1 2025 to 41% in Q2 2025.",
        ),
    )

    issues = [
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.temporal_integrity"
    ]

    assert report.status == "fail"
    assert [(issue.affected_artifact, issue.affected_field) for issue in issues] == [
        ("summary", "card_tldr_compact")
    ]
    assert issues[0].repair_target == "summary"


def test_compact_tldr_failure_routes_to_existing_summary_regeneration() -> None:
    artifacts = _compact_tldr_artifacts(
        text="U.S. internet advertising reached $258.",
        evidence="U.S. internet advertising reached $258.6 billion in 2024.",
    )
    report = evaluate_public_editorial_quality(
        report_id="iab-2024", artifacts=artifacts
    )

    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["summary"]
    assert [issue.affected_section for issue in plan.targets[0].issues] == [
        "card_tldr_compact"
    ]


def test_compact_tldr_accepts_complete_currency_and_time_qualifier() -> None:
    report = evaluate_public_editorial_quality(
        report_id="iab-2024",
        artifacts=_compact_tldr_artifacts(
            text="U.S. internet advertising reached $258.6 billion in 2024.",
            evidence="U.S. internet advertising reached $258.6 billion in 2024.",
        ),
    )

    assert report.status == "pass"
    assert not {
        "public_editorial_quality.incomplete_numeric_expression",
        "public_editorial_quality.temporal_integrity",
    } & _rule_ids(report)


@pytest.mark.parametrize(
    ("text", "evidence"),
    [
        (
            "Share fell from 43% in 2025 to 41% in 2025.",
            "Share fell from 43% in Q1 2025 to 41% in Q2 2025.",
        ),
        (
            "Demand moved from 15.7% in to 14.3% in.",
            "Demand moved from 15.7% in Q1 2025 to 14.3% in Q2 2025.",
        ),
        (
            "Quarterly growth moved from 15.7% in 2024 to 14.3% in 2024.",
            "Quarterly growth moved from 15.7% in Q1 to 14.3% in Q4.",
        ),
    ],
)
def test_temporal_integrity_blocks_lost_or_malformed_quarterly_comparison(
    text: str, evidence: str
) -> None:
    report = evaluate_public_editorial_quality(
        report_id="activate-iab-temporal", artifacts=_temporal_artifacts(text=text, evidence=evidence)
    )

    assert "public_editorial_quality.temporal_integrity" in _rule_ids(report)


@pytest.mark.parametrize(
    ("fixture_name", "text_key"),
    [
        ("activate_2026.json", "collapsed_comparison"),
        ("iab_pwc_quarterly.json", "collapsed_comparison"),
        ("iab_pwc_quarterly.json", "malformed_comparison"),
    ],
)
def test_temporal_integrity_blocks_named_regression_fixtures(
    fixture_name: str, text_key: str
) -> None:
    fixture = _temporal_fixture(fixture_name)
    report = evaluate_public_editorial_quality(
        report_id=fixture["report_id"],
        artifacts=_temporal_artifacts(
            text=fixture[text_key], evidence=fixture["source_comparison"]
        ),
    )

    assert "public_editorial_quality.temporal_integrity" in _rule_ids(report)


@pytest.mark.parametrize(
    "evidence",
    [
        "Conversion increased from 32% in H1 2025 to 35% in H2 2025.",
        "Conversion increased from 32% in January 2025 to 35% in March 2025.",
        "Conversion increased from 32% in FY 2024 to 35% in FY 2025.",
        "Conversion is forecast to increase from 32% in Q1 2025 to 35% in Q2 2025.",
    ],
)
def test_temporal_integrity_accepts_source_proven_distinct_comparisons(
    evidence: str,
) -> None:
    report = evaluate_public_editorial_quality(
        report_id="temporal-periods", artifacts=_temporal_artifacts(text=evidence, evidence=evidence)
    )

    assert "public_editorial_quality.temporal_integrity" not in _rule_ids(report)


@pytest.mark.parametrize("surface", ["summary", "expert_comment", "linkedin_post"])
def test_temporal_integrity_covers_downstream_editorial_surfaces(surface: str) -> None:
    source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."
    collapsed = "Share fell from 43% in 2025 to 41% in 2025."
    artifacts = _temporal_artifacts(text=source, evidence=source)
    if surface == "summary":
        artifacts["summary"] = {
            "tldr": collapsed,
            "executive_summary": "The source comparison remains material.",
            "claim_evidence_map": [
                {
                    "claim": collapsed,
                    "evidence": source,
                    "evidence_id": "temporal-evidence",
                }
            ],
        }
    else:
        artifacts[surface] = collapsed

    report = evaluate_public_editorial_quality(
        report_id="temporal-downstream", artifacts=artifacts
    )

    issues = [
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.temporal_integrity"
    ]
    assert any(issue.affected_artifact == surface for issue in issues)
    assert all(issue.repair_eligible for issue in issues)


def test_temporal_integrity_blocks_malformed_between_comparison() -> None:
    report = evaluate_public_editorial_quality(
        report_id="iab-quarterly",
        artifacts=_temporal_artifacts(
            text="Demand moved between and the two reported periods.",
            evidence="Demand moved from 15.7% in Q1 2025 to 14.3% in Q2 2025.",
        ),
    )

    assert "public_editorial_quality.temporal_integrity" in _rule_ids(report)


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
