import json
from copy import deepcopy
from dataclasses import replace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import ArtifactRegenerationRequest
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _unchanged_candidate_claim_issues,
)
from tests._test_report_analysis_generator._shared import (
    _artifacts_without_retained_claims,
    _deps,
    _payload,
    _runtime,
    _SemanticPassOpenAIClient,
    _set_interpretive_summary_provenance,
)
from tests.test_report_regeneration_generator import (
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakePromptClient,
    _settings,
)
from tests.test_verified_editorial_obligation_contract import _valid_artifact_pair
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _authority_artifacts,
    _fact,
    _packs_for_facts,
)


def _case():
    artifacts = _artifacts_without_retained_claims(
        summary={
            "tldr": "The same claim.",
            "executive_summary": "The same claim.",
            "card_tldr_compact": "Another claim.",
            "claim_evidence_map": [],
        }
    )
    _set_interpretive_summary_provenance(artifacts)
    claim = next(
        c
        for c in artifacts["soft_copy_claim_provenance"]["claims"]
        if c["text_hash"]
        != artifacts["soft_copy_claim_provenance"]["claims"][-1]["text_hash"]
    )
    claim["claim_id"] = "soft_copy:summary:one"
    claim["evidence_ids"] = ["f1"]
    artifacts["verified_facts"] = [
        {"id": "f1", "text": "original", "source_identity": "source-a"}
    ]
    return artifacts


def _issue(section):
    return ValidationIssue(
        schema_version="1.0",
        rule_id="grounding",
        severity="error",
        affected_section=section,
        entity_id="soft_copy:summary:one",
        evidence_ids=["f1"],
        violation_type="not_established",
        message="The denominator is not supported.",
    )


def test_duplicate_surface_findings_route_to_both_exact_claim_paths():
    artifacts = _case()
    issues = _unchanged_candidate_claim_issues(
        artifacts, deepcopy(artifacts), [_issue("tldr"), _issue("summary")]
    )
    assert {issue.affected_section for issue in issues} == {
        "summary.tldr",
        "summary.executive_summary",
    }
    assert all(issue.entity_id == "soft_copy:summary:one" for issue in issues)
    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
        verified_mode=True,
    )
    paths = {path for target in plan.targets for path in target.allowed_paths}
    assert paths == {
        "summary.tldr[claim_index=0]",
        "summary.executive_summary[claim_index=0]",
    }


def test_distinct_findings_share_repair_target_without_losing_reasoning():
    artifacts = _case()
    issues = _unchanged_candidate_claim_issues(
        artifacts,
        deepcopy(artifacts),
        [
            _issue("tldr"),
            replace(_issue("summary"), message="The base population is too broad."),
        ],
    )
    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
        verified_mode=True,
    )
    assert len(plan.targets) == 1
    assert len(plan.targets[0].allowed_paths) == 2
    assert {issue.message for issue in plan.targets[0].issues} == {
        "The denominator is not supported.",
        "The base population is too broad.",
    }


def test_missing_verified_facts_do_not_authorize_feedback():
    artifacts = _case()
    del artifacts["verified_facts"]
    assert (
        _unchanged_candidate_claim_issues(
            artifacts, deepcopy(artifacts), [_issue("summary")]
        )
        == []
    )


@pytest.mark.parametrize(
    "mutation", ["text", "one_surface", "binding", "duplicate", "fact", "source"]
)
def test_changed_or_ambiguous_claim_is_not_forwarded(mutation):
    artifacts = _case()
    artifacts["verified_facts"] = [
        {"id": "f1", "text": "original", "source_identity": "source-a"}
    ]
    candidate = deepcopy(artifacts)
    if mutation == "text":
        candidate["summary"]["tldr"] = "Changed claim."
        candidate["summary"]["executive_summary"] = "Changed claim."
    elif mutation == "one_surface":
        candidate["summary"]["executive_summary"] = "Changed claim."
    elif mutation == "binding":
        candidate["soft_copy_claim_provenance"]["claims"][0]["evidence_ids"] = ["f2"]
    elif mutation == "fact":
        candidate["verified_facts"][0]["text"] = "altered"
    elif mutation == "source":
        candidate["verified_facts"][0]["source_identity"] = "source-b"
    else:
        candidate["soft_copy_claim_provenance"]["claims"].append(
            deepcopy(candidate["soft_copy_claim_provenance"]["claims"][0])
        )
    assert (
        _unchanged_candidate_claim_issues(artifacts, candidate, [_issue("summary")])
        == []
    )


def test_feedback_reaches_real_regeneration_prompt(tmp_path):
    example = _case()
    artifacts = _current_artifacts()
    example["summary"]["claim_evidence_map"] = artifacts["summary"][
        "claim_evidence_map"
    ]
    artifacts["summary"] = example["summary"]
    artifacts["soft_copy_claim_provenance"] = example["soft_copy_claim_provenance"]
    artifacts["verified_facts"] = example["verified_facts"]
    issues = _unchanged_candidate_claim_issues(
        artifacts, deepcopy(artifacts), [_issue("summary")]
    )
    del artifacts["verified_facts"]
    plan = _build_regeneration_plan(
        issues=issues, artifacts=artifacts, broad_retry_available=False
    )
    evidence = _evidence_packs()
    prompt_client = _FakePromptClient()

    class Client:
        def openai_chat_json(self, request, ctx):
            payload = {
                "claim_repair_proposal": {
                    "schema_version": "1.0",
                    "action": "abstain",
                    "replacement_text": "",
                    "evidence_ids_used": [],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="test",
            )

    regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=plan,
            current_artifacts=artifacts,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=Client(),
        prompt_client=prompt_client,
    )
    failures = [
        json.loads(call["variables"]["failure_reasons_json"])
        for call in prompt_client.render_calls
        if "failure_reasons_json" in call["variables"]
    ]
    assert any(
        any(item["message"] == "The denominator is not supported." for item in group)
        for group in failures
    )


def test_verified_loop_routes_rolled_back_findings_from_promoted_artifacts(tmp_path):
    from src.contracts.regeneration import ArtifactRegenerationResponse
    from src.contracts.validation import ValidationReport
    from src.orchestrators._report_analysis_orchestrator.validation import (
        _run_validation_regeneration_loop,
    )
    from src.utils.cache_utils import sha256_json
    from src.utils.verified_facts import build_verified_authority_context

    original = _case()
    authority = _authority_artifacts()
    facts = [deepcopy(_fact()) for _ in range(5)]
    for index, fact in enumerate(facts, start=1):
        fact["fact_id"] = f"f{index}"
        fact["statement"] = f"Verified observation number {index}."
    digest = sha256_json({"source_identity": SOURCE_IDENTITY, "verified_facts": facts})
    authority["verified_facts"] = facts
    authority["_cache"]["visual_authority_canary"].update(
        {
            "verified_facts": deepcopy(facts),
            "digest": digest,
            "verified_fact_digest": digest,
            "verified_evidence_packs": _packs_for_facts(facts),
        }
    )
    original["verified_facts"] = deepcopy(authority["verified_facts"])
    original["_cache"] = deepcopy(authority["_cache"])
    original["insights_final"] = []
    for index, fact in enumerate(facts, start=1):
        item = deepcopy(authority["insights_final"][0])
        item["id"] = f"c{index}"
        item["text"] = fact["statement"]
        item["evidence_id"] = f"verified-fact:{fact['fact_id']}"
        item["evidence_spans"][0]["evidence_id"] = item["evidence_id"]
        original["insights_final"].append(item)
    original["insights_candidates"] = deepcopy(original["insights_final"])
    editorial, _ = _valid_artifact_pair()
    original["editorial_plan"] = deepcopy(editorial["editorial_plan"])
    cache = original["_cache"]["visual_authority_canary"]
    cache["audit"] = deepcopy(editorial["_cache"]["visual_authority_canary"]["audit"])
    cache["admitted_candidates"] = deepcopy(original["insights_candidates"])
    claim = original["soft_copy_claim_provenance"]["claims"][0]
    claim["evidence_ids"] = ["verified-fact:f1"]
    baseline = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="summary.card_tldr_compact",
        entity_id=original["soft_copy_claim_provenance"]["claims"][1]["claim_id"],
        message="The compact claim needs repair.",
        violation_type="not_established",
    )
    findings = [
        replace(_issue("tldr"), evidence_ids=["verified-fact:f1"]),
        replace(
            _issue("summary"),
            evidence_ids=["verified-fact:f1"],
            message="The base population is too broad.",
        ),
    ]
    runtime = replace(
        _runtime(tmp_path),
        settings=replace(
            _runtime(tmp_path).settings, validation_regeneration_max_attempts=2
        ),
    )
    requests = []
    validations = []

    def regenerate(request):
        requests.append(request)
        return ArtifactRegenerationResponse(
            updated_artifacts=deepcopy(request.current_artifacts),
            regenerated_sections=["summary"],
            prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
            candidate_artifacts_path=str(tmp_path / "candidate.json"),
            repair_action="REGENERATE_ITEM",
            repair_strategy="current_evidence",
        )

    def validate(req, settings, ctx, *, pack_name, report_name, md5):
        validations.append(pack_name)
        return ValidationReport(
            schema_version="1.1", status="fail", severity="error", issues=findings
        )

    evidence = _packs_for_facts(facts)
    evidence["doc_map"] = {"sections": []}
    authority_context = build_verified_authority_context(
        original, expected_source_identity=SOURCE_IDENTITY
    )
    (
        promoted,
        promoted_validation,
        attempts,
        _loop_state,
        _evidence_paths,
        _overrides,
    ) = _run_validation_regeneration_loop(
        runtime=runtime,
        mode_ctx=runtime.ctx,
        base_payload=_payload(),
        current_artifacts=original,
        current_validation_report=ValidationReport(
            schema_version="1.1", status="fail", severity="error", issues=[baseline]
        ),
        evidence_packs=evidence,
        source_status=original["source_status"],
        category_labels=["Category"],
        vector_store_id=None,
        dependencies=_deps(regenerate_artifacts=regenerate, run_validation=validate),
        validation_openai_client=_SemanticPassOpenAIClient(),
        source_identity=SOURCE_IDENTITY,
        verified_source_identity=SOURCE_IDENTITY,
        verified_fact_digest=authority_context.verified_fact_digest,
        verified_authority_context=authority_context,
    )
    assert validations == [
        "validation_regen_candidate_1",
        "validation_regen_candidate_2",
    ]
    assert [attempt.promotion_outcome for attempt in attempts] == [
        "rolled_back",
        "rolled_back",
    ]
    assert promoted == original
    assert promoted_validation.issues == [baseline]
    assert requests[1].current_artifacts == original
    targeted = [
        t
        for t in requests[1].plan.targets
        if any(i.entity_id == "soft_copy:summary:one" for i in t.issues)
    ]
    assert len(targeted) == 1
    assert set(targeted[0].allowed_paths) == {
        "summary.tldr[claim_index=0]",
        "summary.executive_summary[claim_index=0]",
    }
    assert {i.message for i in targeted[0].issues} == {
        "The denominator is not supported.",
        "The base population is too broad.",
    }
