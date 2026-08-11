from src.generators.artifact_normalization import (
    fallback_artifact_insights_from_findings,
    normalize_artifact_insights,
    pad_artifact_insights,
)
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
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


def test_pad_artifact_insights_preserves_candidate_strategy_fields():
    padded = pad_artifact_insights(
        [],
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
    )

    assert padded[0]["coverage_role"] == "operating_implication"
    assert padded[0]["so_what"].startswith("Checkout teams")
    assert padded[0]["now_what"].startswith("Prioritize wallet")
    assert padded[0]["report_type_lens"] == "operations"
    assert padded[0]["decision_relevance_score"] == 0.95


def test_pad_artifact_insights_does_not_repeat_one_candidate_to_fill_the_bundle():
    padded = pad_artifact_insights(
        [],
        [
            {
                "id": "IC1",
                "text": "Podcast ad-supported audio share is 19%.",
                "evidence_id": "share_of_ear",
                "evidence": "19% daily share.",
            }
        ],
    )

    assert [item["text"] for item in padded if item["text"]] == [
        "Podcast ad-supported audio share is 19%."
    ]


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


def test_insights_family_abstains_when_fewer_than_five_distinct_claims_exist():
    insights = pad_artifact_insights(
        [],
        [
            {
                "id": f"IC{index}",
                "text": f"Distinct insight {index}.",
                "evidence_id": "share_of_ear",
                "evidence": "Grounded source evidence.",
            }
            for index in range(1, 5)
        ],
    )

    statuses = build_artifact_family_status(
        summary={},
        insights_candidates=insights[:4],
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


def test_pad_artifact_insights_repairs_candidate_cross_enum_strategy_fields():
    padded = pad_artifact_insights(
        [],
        [
            {
                "id": "i1",
                "text": "Technology adoption changes operating priorities.",
                "coverage_role": "technology_shift",
                "report_type_lens": "operating_implication",
            }
        ],
    )

    assert padded[0]["coverage_role"] == "market_context"
    assert padded[0]["report_type_lens"] == "operations"
