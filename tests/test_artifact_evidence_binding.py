from __future__ import annotations

from src.generators.artifact_normalization import bind_artifact_evidence_spans


def test_doc_map_binding_retains_summary_and_key_points_for_numeric_claims() -> None:
    summary = {
        "claim_evidence_map": [
            {
                "claim": (
                    "The selected organizations had revenues from $100 million "
                    "to $5 billion."
                ),
                "evidence_id": "chapter-1",
            }
        ]
    }

    bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={
            "sections": [
                {
                    "id": "chapter-1",
                    "summary": "The chapter introduces the research context.",
                    "key_points": [
                        (
                            "Eligible organizations had revenues from $100 million "
                            "to $5 billion."
                        )
                    ],
                }
            ]
        },
        evidence_packs={},
    )

    span = summary["claim_evidence_map"][0]["evidence_spans"][0]
    assert span["text"] == (
        "The chapter introduces the research context. Eligible organizations had "
        "revenues from $100 million to $5 billion."
    )
