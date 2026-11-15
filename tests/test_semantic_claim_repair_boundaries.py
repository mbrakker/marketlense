import json
from copy import deepcopy
from dataclasses import replace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
    soft_copy_claim_provenance_to_payload,
    soft_copy_public_text,
)
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
)
from src.utils.errors import AppError
from tests._test_report_regeneration_generator._split_support_test_report_regeneration_generator import (  # noqa: E501
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakeOpenAIClient,
    _FakePromptClient,
    _settings,
)


def _case(tmp_path, *, duplicate=False):
    current = _current_artifacts()
    first = "For 2018E, U.S. Pay TV revenue was estimated at $98.1 billion."
    sibling = "A separate sentence remains unchanged."
    current["linkedin_post"] = first + "  \n" + sibling
    claims = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post",
        text=current["linkedin_post"],
        declared_claims=[
            {"claim": s, "classification": "factual", "evidence_ids": ["f1"]}
            for s in (first, sibling)
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    others = [
        c
        for c in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if c.artifact_family != "linkedin_post"
    ]
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        others + claims
    )
    if duplicate:
        current["soft_copy_claim_provenance"]["claims"].append(
            deepcopy(current["soft_copy_claim_provenance"]["claims"][-2])
        )
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="linkedin_post",
        message="Unsupported claim",
        severity="error",
        entity_id=claims[0].claim_id,
        evidence_ids=["f1"],
    )
    paths = _allowed_paths("linkedin_post", [issue], current, "REMOVE_CLAIM")
    evidence = _evidence_packs()
    request = ArtifactRegenerationRequest(
        report_id="report-1",
        report_name="report-1",
        attempt_index=1,
        plan=RegenerationPlan(
            mode="targeted",
            targets=[
                RegenerationTarget(
                    target_section="linkedin_post",
                    repair_action="REMOVE_CLAIM",
                    repair_strategy="safe_removal",
                    allowed_paths=paths,
                    issues=[issue],
                )
            ],
            unmappable_issues=[],
            broad_retry_allowed=False,
        ),
        current_artifacts=current,
        doc_map=evidence["doc_map"],
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        source_status=current["source_status"],
        categories=["Category"],
        vector_store_id=None,
        md5="md5",
    )
    return request, paths, sibling


def test_scoped_removal_preserves_declared_initialism_and_sibling(tmp_path):
    request, paths, sibling = _case(tmp_path)
    assert paths == ["linkedin_post[claim_index=0]"]
    client = _FakeOpenAIClient()
    result = regenerate_artifacts(
        request, openai_client=client, prompt_client=_FakePromptClient()
    )
    assert result.updated_artifacts["linkedin_post"] == sibling
    assert client.calls == []


def test_duplicate_claim_identity_cannot_be_selected(tmp_path):
    _, paths, _ = _case(tmp_path, duplicate=True)
    assert paths == []


def test_uncovered_text_cannot_be_selected(tmp_path):
    request, _, _ = _case(tmp_path)
    current = request.current_artifacts
    current["linkedin_post"] += " Unbound addition."
    issue = request.plan.targets[0].issues[0]
    assert _allowed_paths("linkedin_post", [issue], current, "REMOVE_CLAIM") == []


def test_scoped_model_proposal_repairs_declared_claim(tmp_path):
    request, _, sibling = _case(tmp_path)
    request.plan.targets[0] = replace(
        request.plan.targets[0],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
    )

    class LocalProposal:
        def openai_chat_json(self, req, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": "U.S. revenue was estimated at $98.1 billion.",
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
        request, openai_client=LocalProposal(), prompt_client=_FakePromptClient()
    )
    assert (
        result.updated_artifacts["linkedin_post"]
        == "U.S. revenue was estimated at $98.1 billion.  \n" + sibling
    )


def test_linkedin_claim_repair_can_see_unchanged_sibling_context(tmp_path):
    request, _, sibling = _case(tmp_path)
    request.plan.targets[0] = replace(
        request.plan.targets[0],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
    )

    class ContextSensitiveProposal:
        def openai_chat_json(self, req, ctx):
            variables = json.loads(req.user_prompt.split("|", 1)[1])
            scope = json.loads(variables["claim_repair_scope_json"])
            replacement = (
                "U.S. revenue was estimated at $98.1 billion."
                if sibling in scope.get("public_context", "")
                else "A separate sentence remains unchanged."
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
    assert result.updated_artifacts["linkedin_post"] == (
        "U.S. revenue was estimated at $98.1 billion.  \n" + sibling
    )


def test_later_linkedin_claim_repair_receives_earlier_replacement(tmp_path):
    request, _, sibling = _case(tmp_path)
    first_target = replace(
        request.plan.targets[0],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
    )
    claims = soft_copy_claim_provenance_from_payload(
        request.current_artifacts["soft_copy_claim_provenance"]
    )
    second_claim = next(
        claim
        for claim in claims
        if claim.artifact_family == "linkedin_post"
        and claim.text_hash
        != next(
            c.text_hash
            for c in claims
            if c.claim_id == first_target.issues[0].entity_id
        )
    )
    second_issue = replace(first_target.issues[0], entity_id=second_claim.claim_id)
    request.plan.targets[:] = [
        replace(
            first_target,
            issues=[*first_target.issues, second_issue],
            allowed_paths=[
                "linkedin_post[claim_index=0]",
                "linkedin_post[claim_index=1]",
            ],
        )
    ]

    class ContextSensitiveProposal:
        def openai_chat_json(self, req, ctx):
            variables = json.loads(req.user_prompt.split("|", 1)[1])
            scope = json.loads(variables["claim_repair_scope_json"])
            if scope["failed_claim"] == sibling:
                replacement = (
                    "The distinct implication remains."
                    if "Revenue was $98.1 billion." in scope.get("public_context", "")
                    else "Revenue was $98.1 billion."
                )
            else:
                replacement = "Revenue was $98.1 billion."
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
    assert result.updated_artifacts["linkedin_post"] == (
        "Revenue was $98.1 billion.  \nThe distinct implication remains."
    )


def test_linkedin_model_can_declare_a_merged_replacement(tmp_path):
    request, _, sibling = _case(tmp_path)
    request.plan.targets[0] = replace(
        request.plan.targets[0],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
    )

    class LocalProposal:
        def openai_chat_json(self, req, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": "U.S. revenue grew. Costs fell.",
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
        request, openai_client=LocalProposal(), prompt_client=_FakePromptClient()
    )
    assert result.updated_artifacts["linkedin_post"] == (
        "U.S. revenue grew. Costs fell.  \n" + sibling
    )


@pytest.mark.parametrize(
    ("parts", "failed", "expected"),
    [
        (
            ("First stable claim.", "U.S. revenue rose. More context follows."),
            1,
            "First stable claim.",
        ),
        (("Demand rose", "while costs fell."), 1, "Demand rose"),
    ],
)
def test_removal_respects_declared_merge_or_split(tmp_path, parts, failed, expected):
    request, _, _ = _case(tmp_path)
    current = request.current_artifacts
    current["linkedin_post"] = " ".join(parts)
    claims = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post",
        text=current["linkedin_post"],
        declared_claims=[
            {"claim": s, "classification": "factual", "evidence_ids": ["f1"]}
            for s in parts
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    others = [
        c
        for c in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if c.artifact_family != "linkedin_post"
    ]
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        others + claims
    )
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="linkedin_post",
        message="Unsupported claim",
        severity="error",
        entity_id=claims[failed].claim_id,
        evidence_ids=["f1"],
    )
    target = replace(
        request.plan.targets[0],
        issues=[issue],
        allowed_paths=_allowed_paths("linkedin_post", [issue], current, "REMOVE_CLAIM"),
    )
    request.plan.targets[0] = target
    assert target.allowed_paths == [f"linkedin_post[claim_index={failed}]"]
    result = regenerate_artifacts(
        request, openai_client=_FakeOpenAIClient(), prompt_client=_FakePromptClient()
    )
    assert result.updated_artifacts["linkedin_post"] == expected


def _summary_case(tmp_path, parts, failed, action="REMOVE_CLAIM"):
    request, _, _ = _case(tmp_path)
    current = request.current_artifacts
    summary = current["summary"]
    summary.update(
        tldr="Lead claim.",
        card_tldr_compact="Card claim.",
        executive_summary=" ".join(parts),
        claim_evidence_map=[
            {
                "claim": text,
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "pages": [1],
            }
            for text in ("Lead claim.", "Card claim.", *parts)
        ],
    )
    declared = ["Lead claim.", "Card claim.", *parts]
    claims = build_soft_copy_claim_provenance(
        artifact_family="summary",
        text=soft_copy_public_text("summary", summary),
        declared_claims=[
            {"claim": text, "classification": "factual", "evidence_ids": ["f1"]}
            for text in declared
        ],
        evidence_span_index={},
        producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    others = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "summary"
    ]
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        others + claims
    )
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="summary.executive_summary",
        message="Unsupported claim",
        severity="error",
        entity_id=claims[2 + failed].claim_id,
        evidence_ids=["f1"],
    )
    paths = _allowed_paths("summary", [issue], current, action)
    target = RegenerationTarget(
        target_section="summary",
        repair_action=action,
        repair_strategy="safe_removal"
        if action == "REMOVE_CLAIM"
        else "current_evidence",
        allowed_paths=paths,
        issues=[issue],
    )
    request.plan.targets[0] = target
    return request, claims, paths


@pytest.mark.parametrize(
    ("parts", "failed", "expected"),
    [
        (("Demand rose", "while costs fell."), 1, "Demand rose"),
        (
            ("Stable sibling.", "U.S. revenue rose. More context follows."),
            1,
            "Stable sibling.",
        ),
    ],
)
def test_summary_scoped_removal_respects_declared_boundary(
    tmp_path, parts, failed, expected
):
    request, claims, paths = _summary_case(tmp_path, parts, failed)
    assert paths == [f"summary.executive_summary[claim_index={failed}]"]
    before = deepcopy(request.current_artifacts["summary"])
    client = _FakeOpenAIClient()
    result = regenerate_artifacts(
        request, openai_client=client, prompt_client=_FakePromptClient()
    )
    summary = result.updated_artifacts["summary"]
    assert summary["executive_summary"] == expected
    assert summary["tldr"] == before["tldr"]
    assert summary["card_tldr_compact"] == before["card_tldr_compact"]
    remaining = soft_copy_claim_provenance_from_payload(
        result.updated_artifacts["soft_copy_claim_provenance"]
    )
    assert claims[2 + failed].claim_id not in {c.claim_id for c in remaining}
    assert claims[2].claim_id in {c.claim_id for c in remaining}
    assert client.calls == []


def test_summary_scoped_model_repair_preserves_sibling(tmp_path):
    request, claims, paths = _summary_case(
        tmp_path, ("Demand rose", "while costs fell."), 1, "REGENERATE_ITEM"
    )
    assert paths == ["summary.executive_summary[claim_index=1]"]

    class LocalProposal:
        def openai_chat_json(self, req, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": "and costs declined.",
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
        request, openai_client=LocalProposal(), prompt_client=_FakePromptClient()
    )
    assert (
        result.updated_artifacts["summary"]["executive_summary"]
        == "Demand rose and costs declined."
    )
    remaining = soft_copy_claim_provenance_from_payload(
        result.updated_artifacts["soft_copy_claim_provenance"]
    )
    assert claims[2].claim_id in {c.claim_id for c in remaining}
    assert claims[3].claim_id not in {c.claim_id for c in remaining}


def test_summary_model_proposal_can_declare_a_merged_claim(tmp_path):
    request, _, _ = _summary_case(
        tmp_path, ("Stable sibling.", "U.S. revenue rose."), 1, "REGENERATE_ITEM"
    )

    class LocalProposal:
        def openai_chat_json(self, req, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "replace",
                    "replacement_text": "U.S. revenue grew. Costs fell.",
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
        request, openai_client=LocalProposal(), prompt_client=_FakePromptClient()
    )
    assert (
        result.updated_artifacts["summary"]["executive_summary"]
        == "Stable sibling. U.S. revenue grew. Costs fell."
    )


@pytest.mark.parametrize("ambiguity", ["duplicate", "uncovered"])
def test_summary_ambiguous_or_uncovered_claim_is_not_planned(tmp_path, ambiguity):
    request, _, _ = _summary_case(tmp_path, ("Demand rose", "while costs fell."), 1)
    artifacts = request.current_artifacts
    if ambiguity == "duplicate":
        claims = artifacts["soft_copy_claim_provenance"]["claims"]
        claims.append(deepcopy(claims[-1]))
    else:
        artifacts["summary"]["executive_summary"] += " Unbound addition."
    issue = request.plan.targets[0].issues[0]
    assert _allowed_paths("summary", [issue], artifacts, "REMOVE_CLAIM") == []


def test_summary_repair_rejects_wrong_claim_scope(tmp_path):
    request, _, _ = _summary_case(tmp_path, ("Demand rose", "while costs fell."), 1)
    request.plan.targets[0] = replace(
        request.plan.targets[0],
        allowed_paths=["summary.executive_summary[claim_index=0]"],
    )
    with pytest.raises(AppError):
        regenerate_artifacts(
            request,
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )
