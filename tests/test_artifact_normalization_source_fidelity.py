from src.generators.artifact_normalization import (
    constrain_summary_to_source_backed_claims,
    preserve_public_source_displays,
    select_artifact_insights,
)


def test_preservation_replaces_an_unsupported_insight_number_and_clears_metric() -> (
    None
):
    summary = {"claim_evidence_map": []}
    evidence = "Private-label expansion is one of the trends expected through 2026."
    insights = [
        {
            "id": "private-label",
            "text": "Private labels contributed +3.6% to global value growth.",
            "evidence_id": "trend-1",
            "evidence": evidence,
            "metric": {
                "label": "Private-label contribution",
                "value": "+3.6%",
                "unit": "percent",
                "timeframe": "MAT",
                "trend": "growth",
            },
        }
    ]

    preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="",
        linkedin_post="",
    )

    assert insights[0]["text"] == evidence
    assert insights[0]["metric"]["value"] == ""
    assert insights[0]["metric"]["label"] == ""
    assert insights[0]["metric"]["timeframe"] == ""


def test_summary_constraint_replaces_weakly_bound_summary_copy_with_direct_claims() -> (
    None
):
    summary = {
        "tldr": "Forecast growth will be led by unsupported drivers.",
        "card_tldr_compact": "Unsupported drivers lead the forecast.",
        "executive_summary": "Unsupported drivers lead the forecast.",
        "claim_evidence_map": [
            {
                "claim": "The report forecasts almost $375B in global growth dollars.",
                "evidence_id": "quote-1",
                "evidence_spans": [
                    {
                        "evidence_id": "quote-1",
                        "source_pack": "quote_candidates",
                        "text": "The report forecasts almost $375B in global growth dollars.",
                    }
                ],
            },
            {
                "claim": "Advertising will rely on multiple identity approaches.",
                "evidence_id": "identity-section",
                "evidence_spans": [
                    {
                        "evidence_id": "identity-section",
                        "source_pack": "doc_map",
                        "text": "The section examines identity approaches.",
                    }
                ],
            },
        ],
    }

    changed = constrain_summary_to_source_backed_claims(summary)

    assert changed is True
    assert (
        summary["tldr"] == "The report forecasts almost $375B in global growth dollars."
    )
    assert summary["card_tldr_compact"] == summary["tldr"]
    assert summary["executive_summary"] == summary["tldr"]
    assert [claim["evidence_id"] for claim in summary["claim_evidence_map"]] == [
        "quote-1"
    ]


def test_select_artifact_insights_preserves_chosen_candidate_factual_fields():
    """Candidate→final selection must not carry final-stage factual drift.

    This is the DHL/SimilarWeb mutation shape: the final model rewrote the
    same-stable-ID insight with a drifted metric display. Selection keeps the
    final editorial wording but deterministically restores the chosen
    candidate's protected factual fields.
    """
    plan = {
        "report_thesis": "The report supports grounded decisions.",
        "themes": [
            {"theme": "Margin", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Retention", "priority": 2, "evidence_ids": ["f2"]},
            {"theme": "Reach", "priority": 3, "evidence_ids": ["f3"]},
        ],
    }
    candidate_metric = {
        "label": "Europe margin",
        "value": "46%",
        "unit": "%",
        "trend": "",
        "timeframe": "2025",
        "geography": "Europe",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    drifted_metric = {
        "label": "Drifted label",
        "value": "99%",
        "unit": "%",
        "trend": "",
        "timeframe": "2024",
        "geography": "Global",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    candidate_insights = [
        {
            "id": "insight-1",
            "text": "Margin reached 46% in Europe during 2025.",
            "evidence_id": "f1",
            "metric": dict(candidate_metric),
            "pages": [3],
        },
        {
            "id": "insight-2",
            "text": "Retention held at 88%.",
            "evidence_id": "f2",
        },
    ]
    final_insights = [
        {
            # Same stable ID, drifted editorial wording AND drifted facts.
            "id": "insight-1",
            "text": "Margin improved to 46% in Europe in 2025.",
            "evidence_id": "f1",
            "metric": dict(drifted_metric),
            "pages": [3],
        },
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    repaired = next(item for item in selected if item["id"] == "insight-1")
    assert repaired["text"] == "Margin improved to 46% in Europe in 2025."
    for field_name, value in candidate_metric.items():
        assert repaired["metric"][field_name] == value
    # A stable-ID insight without a matching candidate keeps its own facts.
    untouched = next(item for item in selected if item["id"] == "insight-2")
    assert untouched["text"] == "Retention held at 88%."
