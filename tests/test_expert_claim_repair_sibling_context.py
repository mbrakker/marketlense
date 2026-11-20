import json
from dataclasses import replace

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import RegenerationIssue, RegenerationTarget
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
)
from src.services import prompt_service
from tests._test_report_regeneration_generator._split_support_test_report_regeneration_generator import (  # noqa: E501
    _FakePromptClient,
)
from tests.test_semantic_claim_repair_boundaries import _case


def _expert_case(tmp_path):
    request, _, _ = _case(tmp_path)
    first = "The audio audience accounted for 64% of listening."
    sibling = "The sports audience accounted for 61% of viewing."
    request.current_artifacts["expert_comment"] = first + " " + sibling
    claims = build_soft_copy_claim_provenance(
        artifact_family="expert_comment",
        text=request.current_artifacts["expert_comment"],
        declared_claims=[
            {"claim": text, "classification": "factual", "evidence_ids": ["f1"]}
            for text in (first, sibling)
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    other = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            request.current_artifacts["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "expert_comment"
    ]
    request.current_artifacts["soft_copy_claim_provenance"] = (
        soft_copy_claim_provenance_to_payload(other + claims)
    )
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="expert_comment",
        message="Unsupported claim",
        severity="error",
        entity_id=claims[0].claim_id,
        evidence_ids=["f1"],
    )
    request.plan.targets[:] = [
        RegenerationTarget(
            target_section="expert_comment",
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
            allowed_paths=_allowed_paths(
                "expert_comment", [issue], request.current_artifacts, "REGENERATE_ITEM"
            ),
            issues=[issue],
        )
    ]
    return request, first, sibling, claims


def test_expert_claim_repair_uses_retained_sibling_as_editorial_context(tmp_path):
    request, _, sibling, _ = _expert_case(tmp_path)

    class ContextSensitiveProposal:
        def openai_chat_json(self, req, ctx):
            variables = json.loads(req.user_prompt.split("|", 1)[1])
            scope = json.loads(variables["claim_repair_scope_json"])
            grounding = json.loads(variables["grounding_package_json"])
            replacement = (
                "The audio audience accounted for 47% of spending."
                if sibling in scope.get("public_context", "")
                and sibling not in json.dumps(grounding.get("relevant_evidence"))
                else sibling
            )
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": replacement,
                    "evidence_ids_used": ["f1"],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="local",
            )

    result = regenerate_artifacts(
        request,
        openai_client=ContextSensitiveProposal(),
        prompt_client=_FakePromptClient(),
    )
    assert result.updated_artifacts["expert_comment"] == (
        "The audio audience accounted for 47% of spending. " + sibling
    )


def test_later_expert_repair_sees_the_first_accepted_replacement(tmp_path):
    request, _, sibling, claims = _expert_case(tmp_path)
    target = request.plan.targets[0]
    second_issue = replace(target.issues[0], entity_id=claims[1].claim_id)
    request.plan.targets[:] = [
        replace(
            target,
            issues=[target.issues[0], second_issue],
            allowed_paths=[
                "expert_comment[claim_index=0]",
                "expert_comment[claim_index=1]",
            ],
        )
    ]

    class ContextSensitiveProposal:
        def openai_chat_json(self, req, ctx):
            variables = json.loads(req.user_prompt.split("|", 1)[1])
            scope = json.loads(variables["claim_repair_scope_json"])
            first_replacement = "The audio audience accounted for 47% of spending."
            if scope["failed_claim"] == sibling:
                replacement = (
                    "The sports audience accounted for 27% of users."
                    if first_replacement in scope.get("public_context", "")
                    else first_replacement
                )
            else:
                replacement = first_replacement
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": replacement,
                    "evidence_ids_used": ["f1"],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="local",
            )

    result = regenerate_artifacts(
        request,
        openai_client=ContextSensitiveProposal(),
        prompt_client=_FakePromptClient(),
    )
    assert result.updated_artifacts["expert_comment"] == (
        "The audio audience accounted for 47% of spending. "
        "The sports audience accounted for 27% of users."
    )


def test_rendered_expert_prompt_treats_sibling_context_as_non_evidence(tmp_path):
    request, _, sibling, _ = _expert_case(tmp_path)

    class ContextSensitiveProposal:
        def openai_chat_json(self, req, ctx):
            replacement = (
                "The audio audience accounted for 47% of spending."
                if sibling in req.user_prompt and "never as evidence" in req.user_prompt
                else sibling
            )
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": replacement,
                    "evidence_ids_used": ["f1"],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="local",
            )

    result = regenerate_artifacts(
        request, openai_client=ContextSensitiveProposal(), prompt_client=prompt_service
    )
    assert result.updated_artifacts["expert_comment"] == (
        "The audio audience accounted for 47% of spending. " + sibling
    )
