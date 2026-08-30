from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
    normalize_artifact_insights,
    normalize_artifact_summary,
    select_artifact_insights,
)


def test_normalize_artifact_insights_preserves_scoring_and_strategy_fields():
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Wallet adoption changes checkout planning.",
                "evidence_id": "f1",
                "evidence": "Wallet adoption is rising.",
                "metric": {"value": "42", "unit": "percent"},
                "pages": [4],
                "score": 0.91,
                "decision_relevance_score": 0.95,
                "metric_strength_score": 0.8,
                "novelty_score": 0.7,
                "coverage_role": "operating_implication",
                "so_what": (
                    "Checkout teams need to treat wallets as core infrastructure."
                ),
                "now_what": (
                    "Prioritize wallet coverage in payment orchestration roadmaps."
                ),
                "report_type_lens": "operations",
            }
        ],
        prefix="insight",
    )

    assert insights == [
        {
            "id": "i1",
            "text": "Wallet adoption changes checkout planning.",
            "evidence_id": "f1",
            "evidence": "Wallet adoption is rising.",
            "evidence_spans": [],
            "metric": {
                "value": "42",
                "unit": "percent",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [4],
            "coverage_role": "operating_implication",
            "so_what": "Checkout teams need to treat wallets as core infrastructure.",
            "now_what": "Prioritize wallet coverage in payment orchestration roadmaps.",
            "report_type_lens": "operations",
            "score": 0.91,
            "decision_relevance_score": 0.95,
            "metric_strength_score": 0.8,
            "novelty_score": 0.7,
        }
    ]


def test_normalize_artifact_summary_removes_editorial_scaffold_labels() -> None:
    summary = normalize_artifact_summary(
        {
            "executive_summary": (
                "Answer: Brand tracking joins survey design and activation. "
                "Scale: The service covers 50 markets. "
                "Implication: Teams can compare markets."
            )
        }
    )

    assert summary["executive_summary"] == (
        "Brand tracking joins survey design and activation. "
        "The service covers 50 markets. Teams can compare markets."
    )


def test_initial_artifact_normalization_preserves_distinct_quarterly_periods() -> None:
    source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."

    summary = normalize_artifact_summary(
        {
            "tldr": source,
            "card_tldr_compact": source,
            "executive_summary": source,
            "claim_evidence_map": [
                {"claim": source, "evidence": source, "evidence_id": "activate-43-41"}
            ],
        }
    )
    insights = normalize_artifact_insights(
        [{"id": "candidate-1", "text": source, "evidence": source}],
        prefix="candidate",
    )

    assert summary["tldr"] == source
    assert summary["claim_evidence_map"][0]["evidence"] == source
    assert insights[0]["text"] == source


def test_fallback_artifact_insights_uses_distinct_grounded_findings_only():
    findings = {
        "findings": [
            {
                "id": "finding_1",
                "text": "Brand tracking identifies funnel drop-offs.",
                "evidence": "The report identifies where audiences drop off.",
                "pages": [4],
            },
            {
                "id": "finding_2",
                "text": "Harmonized data supports cross-market comparison.",
                "evidence": "The report covers more than 50 markets.",
                "pages": [7],
            },
            {
                "id": "finding_1",
                "text": "Brand tracking identifies funnel drop-offs.",
                "evidence": "Duplicate claim with a different locator.",
                "pages": [8],
            },
            {
                "id": "",
                "text": "An unaddressable finding must not be used.",
                "evidence": "No evidence id.",
            },
        ]
    }

    fallback = fallback_artifact_insights_from_findings(findings)

    assert fallback == [
        {
            "id": "finding_1",
            "text": "Brand tracking identifies funnel drop-offs.",
            "evidence_id": "finding_1",
            "evidence": "The report identifies where audiences drop off.",
            "evidence_spans": [],
            "metric": {
                "value": "",
                "unit": "",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [4],
        },
        {
            "id": "finding_2",
            "text": "Harmonized data supports cross-market comparison.",
            "evidence_id": "finding_2",
            "evidence": "The report covers more than 50 markets.",
            "evidence_spans": [],
            "metric": {
                "value": "",
                "unit": "",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [7],
        },
    ]


def test_insights_family_abstains_when_fewer_than_two_grounded_claims_exist():
    insights = normalize_artifact_insights(
        [
            {
                "id": "IC1",
                "text": "One supported report theme remains.",
                "evidence_id": "share_of_ear",
                "evidence": "Grounded source evidence.",
            }
        ],
        prefix="insight",
    )

    statuses = build_artifact_family_status(
        summary={},
        insights_candidates=insights,
        insights_final=insights,
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert statuses["insights_bundle"]["status"] == "abstained"
    assert statuses["insights_bundle"]["reason"] == "insights_missing_required_count"


def test_normalize_artifact_insights_repairs_cross_enum_strategy_fields():
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Rules changes create implementation risk.",
                "coverage_role": "risk_regulation",
                "report_type_lens": "strategic_risk",
            },
            {
                "id": "i2",
                "text": "Consumer preference shifts affect payment adoption.",
                "coverage_role": "consumer_behavior",
                "report_type_lens": "behavior_shift",
            },
        ],
        prefix="insight",
    )

    assert insights[0]["coverage_role"] == "strategic_risk"
    assert insights[0]["report_type_lens"] == "risk_regulation"
    assert insights[1]["coverage_role"] == "behavior_shift"
    assert insights[1]["report_type_lens"] == "consumer_behavior"


def test_normalize_artifact_insights_drops_unknown_optional_strategy_fields():
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Unexpected vocabulary should still reach schema validation.",
                "coverage_role": "not_a_role",
                "report_type_lens": "not_a_lens",
            }
        ],
        prefix="insight",
    )

    assert "coverage_role" not in insights[0]
    assert "report_type_lens" not in insights[0]


def test_select_artifact_insights_fills_required_report_slots_after_theme_coverage():
    """A four-theme plan must not truncate an otherwise grounded five-insight report."""
    plan = {
        "report_thesis": "The report supports five distinct grounded decisions.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [f"e{index}"],
            }
            for index in range(1, 5)
        ],
    }
    final_insights = [
        {
            "id": f"final-{index}",
            "text": f"Final insight {index}.",
            "evidence_id": f"e{index}",
            "score": 0.9,
        }
        for index in range(1, 5)
    ]
    candidate_insights = [
        {
            "id": "candidate-5",
            "text": "Fifth grounded insight.",
            "evidence_id": "e5",
            "score": 0.8,
        }
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    assert [item["evidence_id"] for item in selected] == ["e1", "e2", "e3", "e4", "e5"]


def test_normalize_artifact_insights_omits_composite_public_metric_fields() -> None:
    insight = normalize_artifact_insights(
        [
            {
                "id": "iab-composite",
                "text": "The insight keeps all supporting figures in its public prose.",
                "evidence_id": "iab-evidence-1",
                "evidence": "19.2%, $62.1 billion, and $102.9 billion are source-backed.",
                "metric": {
                    "value": "19.2%; $62.1; $102.9; 39.8% growth",
                    "unit": "$ billion; $ billion; share",
                },
            }
        ],
        prefix="insight",
    )[0]

    assert insight["metric"]["value"] == ""
    assert insight["metric"]["unit"] == ""
    assert (
        insight["text"]
        == "The insight keeps all supporting figures in its public prose."
    )
    assert insight["evidence_id"] == "iab-evidence-1"
