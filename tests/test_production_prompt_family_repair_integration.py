import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from src.contracts.openai import OpenAIResponseResult
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators.report_regeneration_generator import regenerate_artifacts
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


def test_production_summary_repair_prompt_promotes_verified_candidate(tmp_path):
    artifacts = _case()
    authority_fixture = _authority_artifacts()
    facts = [deepcopy(_fact()) for _ in range(5)]
    for index, fact in enumerate(facts, 1):
        fact["fact_id"] = f"f{index}"
    digest = sha256_json({"source_identity": SOURCE_IDENTITY, "verified_facts": facts})
    authority_fixture["_cache"]["visual_authority_canary"].update(
        verified_facts=deepcopy(facts),
        digest=digest,
        verified_fact_digest=digest,
        verified_evidence_packs=_packs_for_facts(facts),
    )
    artifacts["verified_facts"] = deepcopy(facts)
    artifacts["_cache"] = deepcopy(authority_fixture["_cache"])
    artifacts["insights_final"] = []
    for index, fact in enumerate(facts, 1):
        insight = deepcopy(authority_fixture["insights_final"][0])
        insight.update(
            id=f"c{index}",
            text=fact["statement"],
            evidence_id=f"verified-fact:{fact['fact_id']}",
            metric_public_copy=fact["statement"],
        )
        insight["evidence_spans"][0]["evidence_id"] = insight["evidence_id"]
        artifacts["insights_final"].append(insight)
    artifacts["insights_candidates"] = deepcopy(artifacts["insights_final"])
    artifacts["summary"]["claim_evidence_map"] = [
        {
            "claim": facts[0]["statement"],
            "evidence_id": "verified-fact:f1",
            "evidence": facts[0]["statement"],
            "pages": [4],
            "evidence_spans": deepcopy(
                artifacts["insights_final"][0]["evidence_spans"]
            ),
        }
    ]
    editorial, _ = _valid_artifact_pair()
    artifacts["editorial_plan"] = deepcopy(editorial["editorial_plan"])
    cache = artifacts["_cache"]["visual_authority_canary"]
    cache["audit"] = deepcopy(editorial["_cache"]["visual_authority_canary"]["audit"])
    cache["admitted_candidates"] = deepcopy(artifacts["insights_candidates"])
    _set_interpretive_summary_provenance(artifacts)
    compact_hash = hashlib.sha256(
        artifacts["summary"]["card_tldr_compact"].encode()
    ).hexdigest()
    compact_claim = next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["text_hash"] == compact_hash
    )
    compact_claim["evidence_ids"] = ["verified-fact:f1"]
    compact_claim["source_spans"] = deepcopy(
        artifacts["insights_final"][0]["evidence_spans"]
    )
    artifacts["family_status"] = build_artifact_family_status(
        summary=artifacts["summary"],
        insights_candidates=artifacts["insights_candidates"],
        insights_final=artifacts["insights_final"],
        quotes_final=artifacts["quotes_final"],
        expert_comment=artifacts["expert_comment"],
        linkedin_post=artifacts["linkedin_post"],
    )
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=SOURCE_IDENTITY
    )
    runtime = _runtime(tmp_path)
    runtime = replace(
        runtime,
        settings=replace(runtime.settings, validation_regeneration_max_attempts=1),
        ctx=replace(runtime.ctx, configuration_hash="config", policy_hash="policy"),
    )

    class Provider(_SemanticPassOpenAIClient):
        def __init__(self):
            self.repairs = []

        def openai_chat_json(self, request, ctx):
            identity = request.structured_output_schema_identity or ""
            if "regeneration_" in identity:
                self.repairs.append(request)
                if "claim_repair_proposal" in identity:
                    payload = {
                        "claim_repair_proposal": {
                            "schema_version": "1.0",
                            "action": "replace",
                            "replacement_text": "A clearer summary.",
                            "evidence_ids_used": ["verified-fact:f1"],
                        }
                    }
                else:
                    payload = {
                        "repair_decision": {
                            "schema_version": "1.0",
                            "repair_action": "REGENERATE_ITEM",
                            "repair_strategy": "current_evidence",
                            "evidence_ids_used": ["verified-fact:f1"],
                            "changed_paths": [
                                "summary.card_tldr_compact[claim_index=0]"
                            ],
                            "minimal_patch": [
                                {
                                    "op": "replace",
                                    "path": "summary.card_tldr_compact[claim_index=0]",
                                    "value": "A clearer summary.",
                                }
                            ],
                        }
                    }
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="repair",
                )
            response = super().openai_chat_json(request, ctx)
            if request.artifact_family == "public_editorial_quality":
                payload = dict(response.parsed_json)
                payload["original_essential_obligation_assessments"] = [
                    {
                        "theme": theme,
                        "status": "covered",
                        "explanation": "Supported.",
                        "evidence_ids": [f"verified-fact:f{index}"],
                        "supporting_insight_ids": [f"insight:c{index}"],
                    }
                    for index, theme in enumerate(
                        ("Essential signal", "Supporting signal"), 1
                    )
                ]
                return replace(response, parsed_json=payload, text=json.dumps(payload))
            return response

    client = Provider()

    def validate(request, settings, ctx, **kwargs):
        return validate_report(
            request, settings, ctx, prompt_client=FakePromptClient(), **kwargs
        )

    issue = ValidationIssue(
        rule_id="clarity",
        severity="error",
        affected_section="summary.card_tldr_compact",
        message="The compact summary needs clearer wording.",
        repair_target="summary",
        evidence_ids=["verified-fact:f1"],
        entity_id=compact_claim["claim_id"],
    )
    promoted, validation, attempts, _, paths, _ = _run_validation_regeneration_loop(
        runtime=runtime,
        mode_ctx=runtime.ctx,
        base_payload=_payload(),
        current_artifacts=artifacts,
        current_validation_report=ValidationReport(
            schema_version="1.1", status="fail", severity="error", issues=[issue]
        ),
        evidence_packs=authority.evidence_packs,
        source_status=artifacts["source_status"],
        category_labels=["Category"],
        vector_store_id=None,
        dependencies=_deps(
            regenerate_artifacts=regenerate_artifacts, run_validation=validate
        ),
        regeneration_openai_client=client,
        validation_openai_client=client,
        source_identity=SOURCE_IDENTITY,
        verified_source_identity=SOURCE_IDENTITY,
        verified_fact_digest=authority.verified_fact_digest,
        verified_authority_context=authority,
    )
    assert len(client.repairs) == 1
    assert "Repair the named summary" in client.repairs[0].user_prompt
    assert "verified-fact:f1" in client.repairs[0].user_prompt
    assert (
        "regeneration_claim_repair_proposal"
        in client.repairs[0].structured_output_schema_identity
    )
    assert [attempt.promotion_outcome for attempt in attempts] == ["promoted"]
    assert validation.status == "pass"
    assert promoted["summary"]["card_tldr_compact"] == "A clearer summary."
    assert promoted["summary"]["tldr"] == artifacts["summary"]["tldr"]
    assert promoted["insights_final"] == artifacts["insights_final"]
    assert (
        build_verified_authority_context(
            promoted, expected_source_identity=SOURCE_IDENTITY
        ).verified_fact_digest
        == digest
    )
    assert Path(paths["validation_retained_claim_validation_candidate"]).is_file()
    analysis_dir = tmp_path / "out" / runtime.report_name / "report_analysis"
    persisted = json.loads(
        (analysis_dir / "artifacts_regen_candidate_1.json").read_text(encoding="utf-8")
    )
    assert (
        persisted["summary"]["card_tldr_compact"]
        == promoted["summary"]["card_tldr_compact"]
    )
    audit = json.loads(
        (analysis_dir / "regeneration_candidate_audit_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["repair_action"] == "REGENERATE_ITEM"
    assert audit["repair_decisions"][0]["evidence_ids_used"] == ["verified-fact:f1"]
