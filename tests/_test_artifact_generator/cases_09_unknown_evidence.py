# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_generate_artifacts_does_not_fabricate_insights_after_unknown_evidence(
    tmp_path,
) -> None:
    client = FakeOpenAI(
        [
            {
                "summary": {
                    "tldr": "Grounded TLDR.",
                    "card_tldr_compact": "Grounded TLDR.",
                    "executive_summary": "Executive summary.",
                    "claim_evidence_map": [],
                }
            },
            {
                "insights_candidates": [
                    {
                        "id": "candidate-1",
                        "text": "Candidate insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                        "score": 0.9,
                    },
                    {
                        "id": "candidate-2",
                        "text": "Second candidate insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "candidate-3",
                        "text": "Third candidate insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "candidate-4",
                        "text": "Fourth candidate insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                ]
            },
            {
                "quotes_final": [
                    {
                        "text": "We are expanding rapidly",
                        "speaker": "CEO",
                        "citation": "Earnings call",
                        "page": 3,
                        "evidence_id": "q1",
                    }
                ]
            },
            {
                "insights_final": [
                    {
                        "id": "insight-1",
                        "text": "Final insight.",
                        "evidence_id": "unknown-reference",
                        "evidence": "Unsupported source.",
                        "metric": {},
                        "pages": [2],
                    }
                ]
            },
            {
                "insights_final": [
                    {
                        "id": "insight-1",
                        "text": "Final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "insight-2",
                        "text": "Second final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "insight-3",
                        "text": "Third final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "insight-4",
                        "text": "Fourth final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                    {
                        "id": "insight-5",
                        "text": "Fifth final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    },
                ]
            },
            _cover_semantics_response(),
            {"expert_comment": "Grounded comment."},
            {"linkedin_post": "Grounded post."},
        ]
    )

    payload = generate_artifacts(
        report_id="reference-repair",
        report_name="reference-repair",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert [request[2] for request in client.requests].count("insights_final") == 1
    assert payload["insights_final"]
    assert "unknown-reference" not in {
        item["evidence_id"] for item in payload["insights_final"]
    }


__all__ = ["test_generate_artifacts_does_not_fabricate_insights_after_unknown_evidence"]
