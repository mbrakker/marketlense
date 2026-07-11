from src.generators.artifact_normalization import (
    normalize_artifact_insights,
    pad_artifact_insights,
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
                "so_what": "Checkout teams need to treat wallets as core infrastructure.",
                "now_what": "Prioritize wallet coverage in payment orchestration roadmaps.",
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
                "so_what": "Checkout teams need to treat wallets as core infrastructure.",
                "now_what": "Prioritize wallet coverage in payment orchestration roadmaps.",
                "report_type_lens": "operations",
            }
        ],
    )

    assert padded[0]["coverage_role"] == "operating_implication"
    assert padded[0]["so_what"].startswith("Checkout teams")
    assert padded[0]["now_what"].startswith("Prioritize wallet")
    assert padded[0]["report_type_lens"] == "operations"
    assert padded[0]["decision_relevance_score"] == 0.95


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


def test_normalize_artifact_insights_keeps_unknown_strategy_fields_invalid():
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

    assert insights[0]["coverage_role"] == "not_a_role"
    assert insights[0]["report_type_lens"] == "not_a_lens"


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
