import json
import logging
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from src.contracts.regeneration import (
    ArtifactRegenerationResponse,
    RepairDecision,
    RepairPatchOperation,
)
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.generators.claim_validation_generator import materialize_retained_claim_package
from src.generators.validation_generator import validate_report
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_regeneration_loop,
)
from src.utils.cache_utils import sha256_json
from src.utils.verified_facts import build_verified_authority_context
from tests._test_report_analysis_generator._shared import (
    _deps,
    _payload,
    _runtime,
    _SemanticPassOpenAIClient,
    _set_interpretive_summary_provenance,
)
from tests._test_validation_generator._shared import FakePromptClient
from tests.test_unchanged_candidate_claim_feedback import _case
from tests.test_verified_editorial_obligation_contract import _valid_artifact_pair
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _authority_artifacts,
    _fact,
    _packs_for_facts,
)


def test_verified_first_repair_revalidates_changed_context_and_promotes(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="market_lense.validation_generator")
    original = _case()
    authority_artifacts = _authority_artifacts()
    facts = [deepcopy(_fact()) for _ in range(5)]
    for index, fact in enumerate(facts, start=1):
        fact["fact_id"] = f"f{index}"
        fact["statement"] = f"Verified observation number {index}."
    digest = sha256_json({"source_identity": SOURCE_IDENTITY, "verified_facts": facts})
    authority_artifacts["verified_facts"] = facts
    authority_artifacts["_cache"]["visual_authority_canary"].update(
        verified_facts=deepcopy(facts),
        digest=digest,
        verified_fact_digest=digest,
        verified_evidence_packs=_packs_for_facts(facts),
    )
    original["verified_facts"] = deepcopy(facts)
    original["_cache"] = deepcopy(authority_artifacts["_cache"])
    original["insights_final"] = []
    for index, fact in enumerate(facts, start=1):
        insight = deepcopy(authority_artifacts["insights_final"][0])
        insight["id"] = f"c{index}"
        insight["text"] = fact["statement"]
        insight["evidence_id"] = f"verified-fact:{fact['fact_id']}"
        insight["evidence_spans"][0]["evidence_id"] = insight["evidence_id"]
        original["insights_final"].append(insight)
    original["insights_candidates"] = deepcopy(original["insights_final"])
    editorial, _ = _valid_artifact_pair()
    original["editorial_plan"] = deepcopy(editorial["editorial_plan"])
    cache = original["_cache"]["visual_authority_canary"]
    cache["audit"] = deepcopy(editorial["_cache"]["visual_authority_canary"]["audit"])
    cache["admitted_candidates"] = deepcopy(original["insights_candidates"])
    _set_interpretive_summary_provenance(original)
    candidate = deepcopy(original)
    candidate["summary"]["card_tldr_compact"] = "A clearer summary."
    _set_interpretive_summary_provenance(candidate)

    runtime = _runtime(tmp_path)
    runtime = replace(
        runtime,
        settings=replace(runtime.settings, validation_regeneration_max_attempts=1),
        ctx=replace(runtime.ctx, configuration_hash="config", policy_hash="policy"),
    )
    authority = build_verified_authority_context(
        original, expected_source_identity=SOURCE_IDENTITY
    )
    evidence = authority.evidence_packs

    class RecordingClient(_SemanticPassOpenAIClient):
        def __init__(self):
            self.grounding_prompts = []

        def openai_chat_json(self, request, ctx):
            if request.artifact_family == "validation_grounding":
                self.grounding_prompts.append(request.user_prompt)
            response = super().openai_chat_json(request, ctx)
            if request.artifact_family == "public_editorial_quality":
                payload = dict(response.parsed_json)
                payload["original_essential_obligation_assessments"] = [
                    {
                        "theme": theme,
                        "status": "covered",
                        "explanation": (
                            "The source-backed insight covers this obligation."
                        ),
                        "evidence_ids": [f"verified-fact:f{index}"],
                        "supporting_insight_ids": [f"insight:c{index}"],
                    }
                    for index, theme in enumerate(
                        ("Essential signal", "Supporting signal"), start=1
                    )
                ]
                return replace(response, parsed_json=payload, text=json.dumps(payload))
            return response

    client = RecordingClient()

    def validate(request, settings, ctx, **kwargs):
        return validate_report(
            request, settings, ctx, prompt_client=FakePromptClient(), **kwargs
        )

    baseline_request = ValidationRequest(
        schema_version="1.1",
        report_id=runtime.file.file_id,
        report=_payload(),
        artifacts=original,
        evidence_packs=evidence,
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    baseline_validation = validate(
        baseline_request,
        runtime.settings,
        runtime.ctx,
        pack_name="validation",
        report_name=runtime.report_name,
        md5=runtime.md5,
        openai_client=client,
    )
    baseline_calls = len(client.grounding_prompts)
    assert baseline_calls
    baseline_package = json.loads(
        Path(baseline_validation.source_path)
        .with_name("validation_retained_claim_validation_candidate.json")
        .read_text(encoding="utf-8")
    )
    old_claim = next(
        result
        for result in baseline_package["results"]
        if result["candidate"]["claim_id"] == "insight:c1:text"
    )
    assert old_claim["status"] == "supported"
    assert old_claim["semantic_validator_used"] is True
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="summary.card_tldr_compact",
        message="The compact summary needs clearer wording.",
        repair_target="summary",
    )

    def regenerate(request):
        decision = RepairDecision(
            diagnosed_failure_class="grounding",
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            evidence_ids_used=[],
            protected_fields=[],
            changed_paths=["summary.card_tldr_compact"],
            minimal_patch=[
                RepairPatchOperation(
                    op="replace",
                    path="summary.card_tldr_compact",
                    value="A clearer summary.",
                )
            ],
        )
        return ArtifactRegenerationResponse(
            updated_artifacts=deepcopy(candidate),
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(tmp_path / "candidate.json"),
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            repair_decisions=[decision],
        )

    promoted, validation, attempts, _, paths, _ = _run_validation_regeneration_loop(
        runtime=runtime,
        mode_ctx=runtime.ctx,
        base_payload=_payload(),
        current_artifacts=original,
        current_validation_report=ValidationReport(
            schema_version="1.1", status="fail", severity="error", issues=[issue]
        ),
        evidence_packs=evidence,
        source_status=original["source_status"],
        category_labels=["Category"],
        vector_store_id=None,
        dependencies=_deps(regenerate_artifacts=regenerate, run_validation=validate),
        validation_openai_client=client,
        source_identity=SOURCE_IDENTITY,
        verified_source_identity=SOURCE_IDENTITY,
        verified_fact_digest=authority.verified_fact_digest,
        verified_authority_context=authority,
    )
    assert [attempt.promotion_outcome for attempt in attempts] == ["promoted"]
    assert validation.status == "pass"
    assert promoted["summary"]["card_tldr_compact"] == "A clearer summary."
    assert len(client.grounding_prompts) > baseline_calls
    baseline_items = [
        item
        for prompt in client.grounding_prompts[:baseline_calls]
        for item in json.loads(prompt.removeprefix("user "))[
            "retained_claims_to_ground"
        ]
    ]
    candidate_items = [
        item
        for prompt in client.grounding_prompts[baseline_calls:]
        for item in json.loads(prompt.removeprefix("user "))[
            "retained_claims_to_ground"
        ]
    ]
    assert any(
        item["text"] == "Verified observation number 1." for item in baseline_items
    )
    assert any(
        item["text"] == "Verified observation number 1." for item in candidate_items
    )
    assert any(
        "current_artifact_identity_changed" in record.message
        for record in caplog.records
        if "validation_claim_reuse_decided" in record.message
    )
    package = json.loads(
        Path(paths["validation_retained_claim_validation_candidate"]).read_text(
            encoding="utf-8"
        )
    )
    final, error = materialize_retained_claim_package(
        package,
        report_id=runtime.file.file_id,
        artifacts=promoted,
        evidence_packs=evidence,
        final_html="<html></html>",
        source_id=SOURCE_IDENTITY,
        source_md5=runtime.md5,
        configuration_hash="config",
        policy_hash="policy",
        verified_facts_only=True,
    )
    assert error == ""
    assert final["readiness_status"] == "awaiting_review"
    assert final["unresolved_factual_count"] == 0
    assert final["unsupported_factual_count"] == 0
    final_claim = next(
        result
        for result in final["results"]
        if result["candidate"]["claim_id"] == "insight:c1:text"
    )
    assert final_claim["status"] == "supported"
    assert final_claim["semantic_validator_used"] is True
