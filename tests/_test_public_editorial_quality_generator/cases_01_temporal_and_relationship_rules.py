# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_public_editorial_validator_version_invalidates_retained_v1_results() -> None:
    assert PUBLIC_EDITORIAL_VALIDATOR_VERSION == "public-editorial-quality:v6"


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


def test_period_relationship_check_allows_an_implicit_shared_comparison_endpoint() -> (
    None
):
    evidence = (
        "Streaming viewing increased from 41% in 2022 to 70% in 2024, "
        "while traditional-TV viewing declined from 69% to 60%."
    )
    report = evaluate_public_editorial_quality(
        report_id="streaming-comparison",
        artifacts=_temporal_artifacts(
            text=(
                "Streaming reached 70% in 2024 while traditional TV remained 60% "
                "in 2024."
            ),
            evidence=evidence,
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" not in _rule_ids(report)


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


def test_doubleverify_emea_engagement_retained_relationship_and_mismatches() -> None:
    fixture = _relationship_fixture("doubleverify_emea_engagement.json")
    evidence = fixture["evidence"]
    valid_text = fixture["public_text"]

    assert _period_value_pairs(evidence) == set()
    assert _structured_category_value_pairs(evidence)
    assert _subject_value_relationships(evidence) == set()
    assert (
        "emea",
        "engagement",
        "116",
    ) in _ordered_category_row_value_pairs(evidence)
    assert _metric_label_relationship_explanation(valid_text, evidence) == ""
    valid_report = evaluate_public_editorial_quality(
        report_id="doubleverify-emea",
        artifacts=_temporal_artifacts(text=valid_text, evidence=evidence),
    )
    assert "public_editorial_quality.metric_label_relationship" not in _rule_ids(
        valid_report
    )

    claims = {
        "wrong_region": valid_text.replace("EMEA's", "APAC's"),
        "wrong_category": valid_text.replace("Engagement Index", "Exposure Index"),
        "wrong_value": valid_text.replace("at 116", "at 117"),
    }
    for claim in claims.values():
        report = evaluate_public_editorial_quality(
            report_id="doubleverify-emea",
            artifacts=_temporal_artifacts(text=claim, evidence=evidence),
        )
        assert "public_editorial_quality.metric_label_relationship" in _rule_ids(report)

    wrong_value = evaluate_public_editorial_quality(
        report_id="doubleverify-emea-numeric",
        artifacts=_temporal_artifacts(
            text=valid_text.replace("at 116", "at 117"), evidence=evidence
        ),
    )
    assert "public_editorial_quality.unsupported_numeric_claim" in _rule_ids(
        wrong_value
    )

    wrong_period = evaluate_public_editorial_quality(
        report_id="doubleverify-emea-period",
        artifacts=_temporal_artifacts(
            text="EMEA Engagement Index: 116 in Q2 2026.",
            evidence="EMEA Engagement Index: 116 in Q1 2026.",
        ),
    )
    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(
        wrong_period
    )


def test_doubleverify_ordered_row_does_not_authorize_adjacent_values() -> None:
    fixture = _relationship_fixture("doubleverify_emea_engagement.json")
    evidence = (
        fixture["evidence"].replace("EMEA: 110, 104, 116", "EMEA: 110, 104, 115")
        + " The adjacent technology table reports Technology Engagement Index 116."
    )
    report = evaluate_public_editorial_quality(
        report_id="doubleverify-emea",
        artifacts=_temporal_artifacts(
            text=fixture["public_text"],
            evidence=evidence,
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(report)


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


def test_relationship_check_rejects_wrong_cohort_and_denominator() -> None:
    """Catch the cohort/value swap that token-presence checks would accept."""
    evidence = (
        "Super Users are 23% of users and account for 59% of total eCommerce spend. "
        "All other users are 77% of users and account for 41% of total eCommerce spend."
    )
    report = evaluate_public_editorial_quality(
        report_id="activate-2021",
        artifacts=_temporal_artifacts(
            text="Super Users account for 77% of total eCommerce spend.",
            evidence=evidence,
        ),
    )

    assert "public_editorial_quality.metric_label_relationship" in _rule_ids(report)


def test_relationship_check_applies_to_summary_expert_linkedin_and_key_figures() -> (
    None
):
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
    artifacts["expert_comment"] = (
        "Average daily social-video time reaches 0:48 in 2024E."
    )
    artifacts["linkedin_post"] = (
        "Average daily social-video time reaches 0:48 in 2024E."
    )
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


def test_expert_relationship_failure_retains_only_the_rejected_evidence_id() -> None:
    artifacts = {
        "insights_final": [
            {
                "id": "growth",
                "text": (
                    "Revenue is forecast to rise from $1.4T in 2020E to $1.6T in 2024E."
                ),
                "evidence_id": "growth-evidence",
                "evidence": "Revenue is forecast at $1.4T in 2020E and $1.6T in 2024E.",
            },
            {
                "id": "subscriptions",
                "text": (
                    "The average U.S. paid video streaming subscription owner had 4.1 "
                    "subscriptions in 2020; the source forecasts 5.7 by 2024."
                ),
                "evidence_id": "subscription-evidence",
                "evidence": (
                    "The chart reports 4.1 average paid video streaming subscriptions "
                    "owned per subscriber in 2020 and states that Activate forecasts "
                    "5.7 by 2024."
                ),
            },
        ],
        "expert_comment": (
            "Average paid video streaming subscriptions per subscriber are forecast to "
            "rise from 4.1 to 5.7 in 2020-2024."
        ),
    }
    claim_text = artifacts["expert_comment"]
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family="expert_comment",
                claim_id="soft_copy:expert_comment:relationship-failure",
                text_hash=hashlib.sha256(claim_text.encode()).hexdigest(),
                classification="interpretive",
                evidence_ids=("subscription-evidence",),
                source_spans=(),
                producing_prompt_identity={
                    "namespace": "report_vs/artifacts/expert_comment"
                },
                generation_attempt=1,
                regeneration_attempt=0,
            )
        ]
    )

    report = evaluate_public_editorial_quality(
        report_id="mixed-status", artifacts=artifacts
    )
    issues = [
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.metric_label_relationship"
        and issue.affected_field == "expert_comment"
    ]

    assert len(issues) == 1
    assert issues[0].evidence_ids == ["subscription-evidence"]

    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert plan.targets[0].issues[0].excluded_evidence_ids == ["subscription-evidence"]
    assert plan.targets[0].allowed_paths == ["expert_comment[claim_index=0]"]


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


def test_key_figure_relationship_failure_regenerates_only_key_figure_selection() -> (
    None
):
    evidence = "Average daily social-video time: 2023 0:48; 2024E 0:52; 2028E 0:57."
    artifacts = _temporal_artifacts(
        text="Average daily social-video time reaches 0:52 in 2024E.", evidence=evidence
    )
    artifacts["key_figures"] = [
        {
            "label": "Average daily social-video time",
            "figure": "0:48 in 2024E",
            "why_it_matters": "Average daily social-video time reaches 0:48 in 2024E.",
            "evidence_id": "temporal-evidence",
        }
    ]

    report = evaluate_public_editorial_quality(
        report_id="social-video", artifacts=artifacts
    )
    plan = _build_regeneration_plan(
        issues=validation_issues_from_public_editorial_quality(report),
        artifacts=artifacts,
        broad_retry_available=True,
    )

    assert [target.target_section for target in plan.targets] == ["key_figures"]
    assert plan.targets[0].regenerate_steps == ["key_figures"]


def test_public_text_items_includes_compact_summary_tldr_with_summary_evidence() -> (
    None
):
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
        report_id="activate-iab-temporal",
        artifacts=_temporal_artifacts(text=text, evidence=evidence),
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
        report_id="temporal-periods",
        artifacts=_temporal_artifacts(text=evidence, evidence=evidence),
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
