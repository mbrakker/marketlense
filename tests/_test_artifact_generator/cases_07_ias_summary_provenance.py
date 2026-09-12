# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

from src.contracts.openai import OpenAIResponseResult
from src.generators._artifact_generator.rendering import render_artifact_json_model

from ._shared import *  # noqa: F401,F403


def test_ias_summary_with_uk_provenance_is_accepted_on_primary_response(
    tmp_path,
) -> None:
    """Reproduce the failed IAS Summary shape without a provider call."""

    class IasSummaryClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            payload = {
                "summary": {
                    "tldr": "U.K. media experts prioritise digital video and display over the next 12 months.",
                    "card_tldr_compact": "U.K. experts prioritise digital video and display.",
                    "executive_summary": "U.K. media experts prioritise digital video and display over the next 12 months.",
                    "claim_evidence_map": [
                        {
                            "claim": "U.K. media experts prioritise digital video and display over the next 12 months.",
                            "evidence_id": "finding-2",
                            "evidence": "Digital video and display lead the stated priorities.",
                            "evidence_spans": [],
                            "pages": [6],
                        }
                    ],
                },
                "claim_provenance": [
                    {
                        "claim": "U.K. media experts prioritise digital video and display over the next 12 months.",
                        "classification": "factual",
                        "evidence_ids": ["finding-2"],
                    },
                    {
                        "claim": "U.K. experts prioritise digital video and display.",
                        "classification": "factual",
                        "evidence_ids": ["finding-2"],
                    },
                ],
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                model=request.model,
            )

    client = IasSummaryClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/summary",
        variables={"doc_map_json": "{}", "evidence_json": "{}"},
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
    )

    assert len(client.requests) == 1
    assert result["summary"]["tldr"].startswith("U.K.")
    assert len(result["_soft_copy_claim_bindings"]) == 2


__all__ = ["test_ias_summary_with_uk_provenance_is_accepted_on_primary_response"]
