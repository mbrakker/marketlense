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


def test_numeric_summary_claim_rebinds_unique_exact_direct_finding() -> None:
    claim_text = "Global gaming-app CPI rose 30% to $0.56 in 2025."
    summary = {
        "claim_evidence_map": [
            {
                "claim": claim_text,
                "evidence_id": "gaming-finding-keeping-users",
                "evidence": "Gaming app CPI (2025, Global) rose 30% to $0.56.",
            }
        ]
    }
    doc_map = {
        "sections": [
            {
                "id": "gaming-finding-keeping-users",
                "summary": "The section covers acquisition and retention.",
                "key_points": [
                    "Europe installs fell 7% while sessions rose 3%.",
                    "Gaming app CPI (2025, Global) rose 30% to $0.56.",
                ],
                "pages": [17, 18, 19, 20, 21, 22, 23, 24],
            }
        ]
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "gaming-cpi",
                    "text": claim_text,
                    "evidence": "The source labels this Gaming app CPI (2025, Global).",
                    "pages": [21],
                },
                {
                    "id": "gaming-retention",
                    "text": (
                        "Global gaming-app retention was 27% on day 1 and "
                        "5% on day 30."
                    ),
                    "pages": [21],
                },
            ]
        }
    }

    bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map=doc_map,
        evidence_packs=evidence_packs,
    )

    claim = summary["claim_evidence_map"][0]
    assert claim["evidence_id"] == "gaming-cpi"
    assert claim["pages"] == [21]
    assert claim["evidence_spans"] == [
        {
            "evidence_id": "gaming-cpi",
            "source_pack": "findings",
            "page": 21,
            "text": "The source labels this Gaming app CPI (2025, Global).",
        }
    ]


def test_numeric_summary_claim_does_not_choose_between_matching_findings() -> None:
    claim_text = "Global gaming-app CPI rose 30% to $0.56 in 2025."
    summary = {
        "claim_evidence_map": [
            {
                "claim": claim_text,
                "evidence_id": "gaming-finding-keeping-users",
            }
        ]
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {"id": "gaming-cpi-a", "text": claim_text, "pages": [21]},
                {"id": "gaming-cpi-b", "text": claim_text, "pages": [22]},
            ]
        }
    }

    bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={
            "sections": [
                {
                    "id": "gaming-finding-keeping-users",
                    "summary": "Gaming metrics.",
                    "pages": [17, 18, 19, 20, 21, 22],
                }
            ]
        },
        evidence_packs=evidence_packs,
    )

    assert summary["claim_evidence_map"][0]["evidence_id"] == (
        "gaming-finding-keeping-users"
    )


def test_numeric_summary_claim_rebinds_to_paired_metric_finding() -> None:
    summary = {
        "claim_evidence_map": [
            {
                "claim": "Global e-commerce app sessions increased 5% in 2025.",
                "evidence_id": "e-commerce-finding-keeping-users",
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
                    "id": "e-commerce-finding-keeping-users",
                    "summary": "The section covers e-commerce app performance.",
                    "pages": [27, 28, 29, 30, 31],
                }
            ]
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "ecommerce-growth",
                        "text": (
                            "Global e-commerce app installs fell 10% year over year "
                            "in 2025 while sessions increased 5%."
                        ),
                        "pages": [27],
                    }
                ]
            }
        },
    )

    claim = summary["claim_evidence_map"][0]
    assert claim["evidence_id"] == "ecommerce-growth"
    assert claim["pages"] == [27]
