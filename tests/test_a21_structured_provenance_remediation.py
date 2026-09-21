from __future__ import annotations

import json

from src.contracts.openai import OpenAIResponseResult
from src.generators._artifact_generator.rendering import render_artifact_json_model
from src.generators.evidence_pack_generator import generate_evidence_packs
from tests._test_artifact_generator._shared import (
    CapturingPromptClient as ArtifactCapturingPromptClient,
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


def test_soft_copy_binding_coverage_uses_existing_structured_output_recovery(
    tmp_path,
) -> None:
    """An unbound model sentence uses the existing bounded recovery path."""

    class BainEquivalentRecoveryClient:
        def __init__(self, prompt_client) -> None:
            self.prompt_client = prompt_client
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            first_claim = "Born-tech companies created 52% of reported growth."
            second_claim = "Tech-led companies contributed another 20%."
            recovery_variables = self.prompt_client.variables_for_namespace(
                "report_vs/structured_output/regenerate"
            )
            complete = len(self.requests) == 3 and second_claim in str(
                recovery_variables.get("original_response") or ""
            )
            payload = {
                "linkedin_post": f"{first_claim} {second_claim}",
                "claim_provenance": [
                    {
                        "claim": first_claim,
                        "classification": "factual",
                        "evidence_ids": ["finding-1"],
                    },
                    *(
                        [
                            {
                                "claim": second_claim,
                                "classification": "factual",
                                "evidence_ids": ["finding-2"],
                            }
                        ]
                        if complete
                        else []
                    ),
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

    prompt_client = ArtifactCapturingPromptClient()
    client = BainEquivalentRecoveryClient(prompt_client)
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/linkedin_post",
        variables={"doc_map_json": "{}"},
        settings=artifact_settings(tmp_path),
        ctx=artifact_ctx(),
        openai_client=client,
        prompt_client=prompt_client,
        allow_vector_store=False,
        vector_store_id=None,
    )

    assert [request.prompt_namespace for request in client.requests] == [
        "report_vs/artifacts/linkedin_post",
        "report_vs/structured_output/repair",
        "report_vs/structured_output/regenerate",
    ]
    assert "Tech-led companies contributed another 20%." in str(
        prompt_client.variables_for_namespace(
            "report_vs/structured_output/regenerate"
        ).get("original_response")
    )
    assert result["linkedin_post"] == (
        "Born-tech companies created 52% of reported growth. "
        "Tech-led companies contributed another 20%."
    )
    assert [binding["claim"] for binding in result["_soft_copy_claim_bindings"]] == [
        "Born-tech companies created 52% of reported growth.",
        "Tech-led companies contributed another 20%.",
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
