from __future__ import annotations

from src.generators.artifact_normalization import bind_artifact_evidence_spans


def test_multi_fact_insight_binding_retains_each_source_span_and_page() -> None:
    insight = {
        "id": "regional-comparison",
        "text": "North America and APAC report different attention indices.",
        "evidence_id": "fact-na",
        "evidence_ids": ["fact-na", "fact-apac"],
        "pages": [8, 9],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "fact-na",
                        "text": "North America lists 128.",
                        "evidence": "North America lists 128.",
                        "pages": [8],
                    },
                    {
                        "id": "fact-apac",
                        "text": "APAC lists 131.",
                        "evidence": "APAC lists 131.",
                        "pages": [9],
                    },
                ]
            }
        },
    )

    assert insight["pages"] == [8, 9]
    assert [span["evidence_id"] for span in insight["evidence_spans"]] == [
        "fact-na",
        "fact-apac",
    ]


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
                        "Global gaming-app retention was 27% on day 1 and 5% on day 30."
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
                        "evidence": (
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


def test_normal_insight_binding_keeps_provisional_doc_map_locator_unchanged() -> None:
    insight = {
        "id": "ai-search-platform-relationships",
        "text": "Publishers forecast search traffic to decline.",
        "evidence_id": "answer-engines-and-traffic",
        "evidence": "The section summary is navigation context.",
        "pages": [10],
        "metric": {"value": "40%", "direction": "decline"},
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={
            "sections": [
                {
                    "id": "answer-engines-and-traffic",
                    "summary": "Navigation context for changing search traffic.",
                    "pages": [10],
                }
            ]
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "search-traffic-forecast",
                        "section_id": "answer-engines-and-traffic",
                        "text": (
                            "Publishers forecast that search-engine traffic will "
                            "decline by more than 40% over the next three years."
                        ),
                        "evidence": "The forecast is a publisher expectation.",
                        "pages": [3, 4, 10],
                    }
                ]
            }
        },
    )

    assert insight["evidence_id"] == "answer-engines-and-traffic"
    assert insight["pages"] == [10]
    assert insight["metric"] == {"value": "40%", "direction": "decline"}
    assert insight["evidence"] == "The section summary is navigation context."
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"
    assert insight["text"] == "Publishers forecast search traffic to decline."


def test_doc_map_insight_does_not_choose_between_ambiguous_section_findings() -> None:
    insight = {
        "id": "ambiguous-insight",
        "text": "The section has an important commercial implication.",
        "evidence_id": "shared-section",
        "pages": [8],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={
            "sections": [{"id": "shared-section", "summary": "Context", "pages": [8]}]
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "finding-a",
                        "section_id": "shared-section",
                        "text": "One distinct source proposition.",
                        "evidence": "Evidence A.",
                        "pages": [8],
                    },
                    {
                        "id": "finding-b",
                        "section_id": "shared-section",
                        "text": "Another distinct source proposition.",
                        "evidence": "Evidence B.",
                        "pages": [9],
                    },
                ]
            }
        },
    )

    assert insight["evidence_id"] == "shared-section"
    assert insight["pages"] == [8]
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"


def test_doc_map_insight_does_not_promote_unsupported_finding() -> None:
    insight = {
        "id": "unsupported-insight",
        "text": "Publishers forecast search traffic to decline.",
        "evidence_id": "shared-section",
        "pages": [8],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={
            "sections": [{"id": "shared-section", "summary": "Context", "pages": [8]}]
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "unsupported-finding",
                        "section_id": "shared-section",
                        "text": "Publishers forecast search traffic to decline.",
                        "evidence": "Evidence.",
                        "pages": [8],
                    }
                ]
            },
            "evidence_fidelity": {
                "results": [
                    {
                        "status": "unsupported",
                        "candidate": {
                            "claim_id": "evidence:findings:unsupported-finding"
                        },
                    }
                ]
            },
        },
    )

    assert insight["evidence_id"] == "shared-section"
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"


def test_doc_map_insight_does_not_promote_without_explicit_fidelity_support() -> None:
    insight = {
        "id": "missing-fidelity",
        "text": "Publishers forecast search traffic to decline.",
        "evidence_id": "shared-section",
        "pages": [8],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={"sections": [{"id": "shared-section", "pages": [8]}]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "matching-finding",
                        "section_id": "shared-section",
                        "text": "Publishers forecast search traffic to decline.",
                        "evidence": "The forecast is a publisher expectation.",
                        "pages": [8],
                    }
                ]
            }
        },
    )

    assert insight["evidence_id"] == "shared-section"
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"


def test_doc_map_insight_does_not_match_reversed_proposition_by_token_overlap() -> None:
    insight = {
        "id": "reversed-trend",
        "text": "Publishers forecast search traffic to rise.",
        "evidence_id": "shared-section",
        "pages": [8],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={"sections": [{"id": "shared-section", "pages": [8]}]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "falling-finding",
                        "section_id": "shared-section",
                        "text": "Publishers forecast search traffic to decline.",
                        "evidence": "The forecast is a publisher expectation.",
                        "pages": [8],
                    }
                ]
            }
        },
    )

    assert insight["evidence_id"] == "shared-section"
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"


def test_doc_map_insight_does_not_match_same_value_for_a_different_metric() -> None:
    insight = {
        "id": "metric-scope",
        "text": "Revenue growth reached 10% in 2025.",
        "evidence_id": "shared-section",
        "pages": [8],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={"sections": [{"id": "shared-section", "pages": [8]}]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "user-growth",
                        "section_id": "shared-section",
                        "text": "User growth reached 10% in 2025.",
                        "evidence": "The user metric is reported on the page.",
                        "pages": [8],
                    }
                ]
            }
        },
    )

    assert insight["evidence_id"] == "shared-section"
    assert insight["evidence_spans"][0]["source_pack"] == "doc_map"


def test_already_canonical_insight_binding_remains_source_bound() -> None:
    insight = {
        "id": "canonical-insight",
        "text": "The source-supported proposition.",
        "evidence_id": "verified-finding",
        "evidence": "Stale artifact text.",
        "pages": [1],
    }

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[insight],
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "verified-finding",
                        "text": "The source-supported proposition.",
                        "evidence": "Authoritative source excerpt.",
                        "pages": [7],
                    }
                ]
            }
        },
    )

    assert insight["evidence_id"] == "verified-finding"
    assert insight["pages"] == [7]
    assert insight["evidence"] == "Authoritative source excerpt."
    assert insight["evidence_spans"][0]["source_pack"] == "findings"
