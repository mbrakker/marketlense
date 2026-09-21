# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators.validation.evidence import extract_quotes

from ._shared import *  # noqa: F401,F403


def test_validation_omits_legacy_quote_when_quote_family_abstained() -> None:
    request = ValidationRequest(
        schema_version="1.0",
        report_id="abstained-quote",
        report=_report(),
        artifacts={
            "quotes_final": [],
            "family_status": {"quotes": {"status": "abstained"}},
        },
        evidence_packs={},
    )

    assert extract_quotes(request, insights=[]) == []


def test_claim_support_accepts_numeric_claim_with_exact_retained_source_span(tmp_path):
    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="direct-doc-map-span",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": (
                        "The selected organizations had revenues from $100 million "
                        "to $5 billion."
                    ),
                    "card_tldr_compact": (
                        "Selected organizations ranged from $100 million to $5 "
                        "billion in revenue."
                    ),
                    "executive_summary": (
                        "The research sample included organizations with revenues "
                        "from $100 million to $5 billion."
                    ),
                    "claim_evidence_map": [
                        {
                            "claim": (
                                "The selected organizations had revenues from $100 "
                                "million to $5 billion."
                            ),
                            "evidence_id": "chapter-1",
                            "evidence_spans": [
                                {
                                    "evidence_id": "chapter-1",
                                    "source_pack": "doc_map",
                                    "text": (
                                        "Eligible organizations had revenues from "
                                        "$100 million to $5 billion."
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
            },
            evidence_packs={
                "doc_map": {
                    "sections": [
                        {
                            "id": "chapter-1",
                            "summary": "The chapter introduces the research context.",
                            "key_points": [
                                (
                                    "Eligible organizations had revenues from $100 "
                                    "million to $5 billion."
                                )
                            ],
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(issue.rule_id == "claim_support" for issue in result.issues)
