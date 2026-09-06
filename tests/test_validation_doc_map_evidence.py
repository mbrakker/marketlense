from __future__ import annotations

from src.generators.validation.evidence import collect_evidence_texts


def test_collect_evidence_texts_includes_doc_map_source_claims() -> None:
    texts, evidence_by_id = collect_evidence_texts(
        artifacts={},
        evidence_packs={
            "doc_map": {
                "summary": "Ad expenditure grew in the measured period.",
                "sections": [
                    {
                        "summary": "Growth slowed after the rebound.",
                        "key_points": ["Year-over-year growth was 16.0% in 2024."],
                    }
                ],
            }
        },
    )

    assert evidence_by_id == {}
    assert "Ad expenditure grew in the measured period." in texts
    assert "Growth slowed after the rebound." in texts
    assert "Year-over-year growth was 16.0% in 2024." in texts
