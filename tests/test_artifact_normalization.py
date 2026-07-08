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
