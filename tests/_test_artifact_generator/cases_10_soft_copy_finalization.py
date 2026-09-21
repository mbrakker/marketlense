# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace

from src.contracts.prompt_family_materialization import (
    PromptFamilyMaterializationRequest,
)
from src.services.prompt_family_materialization_service import materialize_prompt_family

from ._shared import *  # noqa: F401,F403


def test_fresh_and_cached_soft_copy_share_source_display_finalization(tmp_path) -> None:
    settings = _settings(tmp_path)
    fresh_client = FakeOpenAI(
        {
            "summary": {
                "summary": {
                    "tldr": "TLDR.",
                    "card_tldr_compact": "TLDR.",
                    "executive_summary": "Executive.",
                    "claim_evidence_map": [],
                }
            },
            "insights_candidates": {"insights_candidates": []},
            "quotes": {"quotes_final": []},
            "insights_final": {"insights_final": []},
            "cover_semantics": _cover_semantics_response(),
            "expert_comment": {
                "expert_comment": "Revenue 10% YoY.",
                "claim_provenance": [
                    {
                        "claim": "Revenue 10% YoY.",
                        "classification": "factual",
                        "evidence_ids": ["f1"],
                    }
                ],
            },
            "linkedin_post": {"linkedin_post": "Post."},
        }
    )
    first = generate_artifacts(
        report_id="persisted-family-reuse",
        report_name="Persisted Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=settings,
        md5="persisted-family-reuse-md5",
        ctx=replace(_ctx(), source_identity_id="source:persisted-family-reuse"),
        openai_client=fresh_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    family_outputs = first["_cache"]["family_outputs"]
    for family_id, output in family_outputs.items():
        identity = first["_cache"]["family_reuse"][family_id]
        materialize_prompt_family(
            PromptFamilyMaterializationRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                output_dir=settings.output_dir,
                report_id="persisted-family-reuse",
                report_slug="Persisted Family Reuse",
                source_id="source:persisted-family-reuse",
                family_id=family_id,
                family_schema_version=identity["family_schema_version"],
                processing_version=identity["processing_version"],
                output_payload=output,
                prompt_content_hash=identity["prompt_content_hash"],
                prompt_dependency_manifest=identity["prompt_dependency_manifest"],
                execution_identity=identity["execution_identity"],
                execution_identity_manifest=identity["execution_identity_manifest"],
                prompt_policy_version=identity["prompt_content_hash"],
                model_name=identity["model_name"],
                model_provider=identity["model_provider"],
                model_policy_namespace=identity["model_policy_namespace"],
                routing_policy_version=identity["routing_policy_version"],
                relevant_input_hash=identity["relevant_input_hash"],
                configuration_policy_hash=identity["configuration_policy_hash"],
                validator_version=identity["validator_version"],
                validation_status="pass",
            ),
            _ctx(),
        )

    replay_client = FakeOpenAI({})
    replay = generate_artifacts(
        report_id="persisted-family-reuse",
        report_name="Persisted Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=settings,
        md5="persisted-family-reuse-md5",
        ctx=replace(_ctx(), source_identity_id="source:persisted-family-reuse"),
        openai_client=replay_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert replay_client.requests == [], {
        "telemetry": replay["_cache"]["family_reuse_telemetry"],
        "first": first["_cache"]["family_reuse"],
        "replay": replay["_cache"]["family_reuse"],
    }
    assert replay["summary"] == first["summary"]
    assert replay["expert_comment"] == "Revenue +10% YoY."
    first_claim = next(
        claim
        for claim in first["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )
    replay_claim = next(
        claim
        for claim in replay["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )
    assert replay_claim["evidence_ids"] == ["f1"]
    assert replay_claim["source_spans"] == [
        {
            "evidence_id": "f1",
            "source_pack": "findings",
            "page": 2,
            "text": "Revenue +10% YoY",
        }
    ]
    assert (
        replay_claim["producing_prompt_identity"]
        == first_claim["producing_prompt_identity"]
    )


__all__ = ["test_fresh_and_cached_soft_copy_share_source_display_finalization"]
