# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators._artifact_generator.rendering import render_artifact_json_model

from ._shared import *  # noqa: F401,F403


def test_soft_copy_binding_gap_is_deferred_to_finalization(tmp_path) -> None:
    class SoftCopyRepairClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            claims = (
                [
                    {
                        "claim": "The first supported sentence.",
                        "classification": "interpretive",
                        "evidence_ids": [],
                    }
                ]
                if len(self.requests) == 1
                else [
                    {
                        "claim": "The first supported sentence.",
                        "classification": "interpretive",
                        "evidence_ids": [],
                    },
                    {
                        "claim": "The second supported sentence.",
                        "classification": "interpretive",
                        "evidence_ids": [],
                    },
                ]
            )
            payload = {
                "expert_comment": (
                    "The first supported sentence. The second supported sentence."
                ),
                "claim_provenance": claims,
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

    client = SoftCopyRepairClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/expert_comment",
        variables={"doc_map_json": "{}"},
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
    )

    assert [request.prompt_namespace for request in client.requests] == [
        "report_vs/artifacts/expert_comment"
    ]
    assert [binding["claim"] for binding in result["_soft_copy_claim_bindings"]] == [
        "The first supported sentence."
    ]


def test_linkedin_paragraph_bindings_remain_declared_until_finalization(
    tmp_path,
) -> None:
    class ParagraphClaimsClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            payload = {
                "linkedin_post": (
                    "First supported point. Second supported point.\n\n"
                    "Third supported point.\n\n#AI #MediaTrust"
                ),
                "claim_provenance": [
                    {
                        "claim": "First supported point. Second supported point.",
                        "classification": "factual",
                        "evidence_ids": [],
                    },
                    {
                        "claim": "Third supported point.",
                        "classification": "interpretive",
                        "evidence_ids": [],
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

    client = ParagraphClaimsClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/linkedin_post",
        variables={"doc_map_json": "{}"},
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
    )

    assert len(client.requests) == 1
    assert result["_soft_copy_claim_bindings"] == [
        {
            "claim": "First supported point. Second supported point.",
            "classification": "factual",
            "evidence_ids": [],
        },
        {
            "claim": "Third supported point.",
            "classification": "interpretive",
            "evidence_ids": [],
        },
    ]


def test_linkedin_binding_gap_is_deferred_without_model_retry(tmp_path) -> None:
    class PartialClaimsClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            payload = {
                "linkedin_post": (
                    "The first supported sentence. The trailing hashtag sentence."
                ),
                "claim_provenance": [
                    {
                        "claim": "The first supported sentence.",
                        "classification": "interpretive",
                        "evidence_ids": [],
                    }
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

    client = PartialClaimsClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/linkedin_post",
        variables={"doc_map_json": "{}"},
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
    )

    assert len(client.requests) == 1
    assert result["_soft_copy_claim_bindings"] == [
        {
            "claim": "The first supported sentence.",
            "classification": "interpretive",
            "evidence_ids": [],
        }
    ]


__all__ = [
    "test_soft_copy_binding_gap_is_deferred_to_finalization",
    "test_linkedin_paragraph_bindings_remain_declared_until_finalization",
    "test_linkedin_binding_gap_is_deferred_without_model_retry",
]
