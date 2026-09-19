from __future__ import annotations

import json

from src.contracts.openai import OpenAIResponseResult
from src.generators._artifact_generator.rendering import render_artifact_json_model
from src.generators.evidence_pack_generator import generate_evidence_packs
from tests._test_artifact_generator._shared import (
    FakePromptClient as ArtifactPromptClient,
)
from tests._test_artifact_generator._shared import _ctx as artifact_ctx
from tests._test_artifact_generator._shared import _settings as artifact_settings
from tests._test_evidence_pack_generator._shared import (
    FakeAnalysisStore,
    FakePromptClient as EvidencePromptClient,
    RoutedOpenAIClient,
    _ctx as evidence_ctx,
    _settings as evidence_settings,
    substantive_doc_map,
)


def test_soft_copy_display_normalization_rebinds_through_bounded_recovery(
    tmp_path,
) -> None:
    """A final public-display correction must be bound before it is retained."""

    class DisplayRepairClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            sentence = (
                "The source-backed index reached 3.0%."
                if len(self.requests) == 1
                else "The source-backed index reached 2.0%."
            )
            payload = {
                "linkedin_post": sentence,
                "claim_provenance": [
                    {
                        "claim": sentence,
                        "classification": "factual",
                        "evidence_ids": ["finding-1"],
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

    def preserve_source_display(payload: dict) -> None:
        payload["linkedin_post"] = str(payload["linkedin_post"]).replace("3.0%", "2.0%")

    client = DisplayRepairClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/linkedin_post",
        variables={"doc_map_json": "{}"},
        settings=artifact_settings(tmp_path),
        ctx=artifact_ctx(),
        openai_client=client,
        prompt_client=ArtifactPromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
        public_output_normalizer=preserve_source_display,
    )

    assert len(client.requests) == 2
    assert result["linkedin_post"] == "The source-backed index reached 2.0%."
    assert result["_soft_copy_claim_bindings"] == [
        {
            "claim": "The source-backed index reached 2.0%.",
            "classification": "factual",
            "evidence_ids": ["finding-1"],
        }
    ]


def test_empty_limitations_is_canonical_optional_pack_abstention(tmp_path) -> None:
    """An evidence-free optional limitations result is formal abstention, not bad JSON."""
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=evidence_settings(
            tmp_path, evidence_pack_registry=["doc_map", "limitations"]
        ),
        ctx=evidence_ctx(),
        openai_client=RoutedOpenAIClient(
            {"doc_map": substantive_doc_map(), "limitations": {"limitations": []}}
        ),
        prompt_client=EvidencePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["limitations"]["limitations"] == []
    assert packs["limitations"]["not_found_reason"] == "limitations_not_found"
    assert packs["limitations"]["family_status"]["status"] == "abstained"
