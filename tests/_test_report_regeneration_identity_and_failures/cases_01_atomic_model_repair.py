# ruff: noqa: F401,F403,F405
from __future__ import annotations

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
from src.generators.artifact_normalization import artifact_evidence_span_index
from src.generators.report_regeneration_generator import (
    regenerate_artifacts,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
    _verified_deterministic_mutation_paths,
)
from src.utils.errors import AppError
from tests._test_report_regeneration_generator._shared import (
    _parse_fixture_variables,
)
from tests.test_report_regeneration_generator import (
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakePromptClient,
    _settings,
)

from ._shared import *  # noqa: F401,F403


class _RepairDecisionOpenAIClient:
    def __init__(self, decision: dict) -> None:
        self.decision = decision
        self.calls: list[object] = []

    def openai_chat_json(self, req, ctx):
        del ctx
        self.calls.append(req)
        envelope = {"repair_decision": self.decision}
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(envelope),
            parsed_json=envelope,
            request_id=f"req-repair-{len(self.calls)}",
        )

    def openai_respond_with_vector_store(self, req, ctx):
        return self.openai_chat_json(req, ctx)


def _atomic_insight_plan(*, quarantined: list[str] | None = None) -> RegenerationPlan:
    return RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="insights_bundle",
                regenerate_steps=["insights_final"],
                prompt_namespaces=["report_vs/artifacts/regenerate/insights_final"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="insights:insight-1.text",
                        message=(
                            "[grounding|unsupported_factual_claim] Repair one item."
                        ),
                        severity="error",
                        entity_id="insight:insight-1:text",
                        evidence_ids=["f1"],
                        excluded_evidence_ids=list(quarantined or []),
                    )
                ],
                repair_action="REGENERATE_ITEM",
                repair_strategy="current_evidence",
                allowed_paths=["insights_final[item=insight-1].text"],
                selected_evidence_ids=["f1"],
                quarantined_evidence_ids=list(quarantined or []),
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )


def _atomic_insight_decision(
    *,
    value: object = "Repaired final insight",
    path: str = "insights_final[item=insight-1].text",
    evidence_ids: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "repair_action": "REGENERATE_ITEM",
        "repair_strategy": "current_evidence",
        "evidence_ids_used": list(evidence_ids or ["f1"]),
        "changed_paths": [path],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value": value,
            }
        ],
    }


def test_model_repair_applies_one_validated_atomic_patch_in_one_call(tmp_path) -> None:
    current = _source_backed_artifacts()
    before = [dict(item) for item in current["insights_final"]]
    client = _RepairDecisionOpenAIClient(_atomic_insight_decision())

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=_atomic_insight_plan(),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    repaired = response.updated_artifacts["insights_final"]
    assert len(client.calls) == 1
    assert client.calls[0].structured_output_schema_identity == (
        "regeneration_repair_decision_v5"
    )
    prompt_variables = _parse_fixture_variables(client.calls[0].user_prompt)
    repair_context = json.loads(prompt_variables["repair_context_json"])
    assert repair_context["allowed_paths"] == ["insights_final[item=insight-1].text"]
    assert repair_context["allowed_evidence_ids"] == ["f1"]
    assert "required_protected_fields" not in repair_context
    assert repaired[0]["text"] == "Repaired final insight"
    assert repaired[0]["metric"] == before[0]["metric"]
    assert repaired[1:] == before[1:]
    assert response.repair_decisions[0].changed_paths == [
        "insights_final[item=insight-1].text"
    ]
    assert response.repair_decisions[0].diagnosed_failure_class == "grounding"


@pytest.mark.parametrize("replacement", ["", "Not available from text"])
def test_missing_required_insight_text_patch_preserves_original_candidate(
    tmp_path, replacement: str
) -> None:
    current = _source_backed_artifacts()
    original_text = current["insights_final"][0]["text"]
    client = _RepairDecisionOpenAIClient(_atomic_insight_decision(value=replacement))

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=_atomic_insight_plan(),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    candidate = response.updated_artifacts["insights_final"][0]
    assert candidate["text"] == original_text
    assert len(client.calls) == 1


def test_safe_removal_replacement_id_does_not_overwrite_sibling_evidence_identity(
    tmp_path,
) -> None:
    current = _current_artifacts()
    failed, sibling, other, extra_one, extra_two = deepcopy(current["insights_final"])
    failed.update({"id": "failed-insight", "evidence_id": "f1"})
    sibling.update(
        {
            "id": "sibling-insight",
            "text": "Retain the original sibling insight.",
            "evidence_id": "replacement-id",
        }
    )
    other.update(
        {
            "id": "other-insight",
            "text": "Retain the other original insight.",
            "evidence_id": "f1",
        }
    )
    extra_one.update(
        {
            "id": "extra-insight-one",
            "text": "Retain the first additional insight.",
            "evidence_id": "f1",
        }
    )
    extra_two.update(
        {
            "id": "extra-insight-two",
            "text": "Retain the second additional insight.",
            "evidence_id": "f2",
        }
    )
    current["insights_final"] = [failed, sibling, other, extra_one, extra_two]
    current["insights_candidates"] = [
        {
            "id": "replacement-id",
            "text": "Evidence text 2",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [],
            "metric": deepcopy(sibling["metric"]),
            "score": 10,
        }
    ]
    current["editorial_plan"] = {
        "report_thesis": "Retain distinct supported insight identities.",
        "themes": [
            {"theme": "Second source", "priority": 1, "evidence_ids": ["f2"]},
            {"theme": "First source", "priority": 2, "evidence_ids": ["f1"]},
            {"theme": "Second source detail", "priority": 3, "evidence_ids": ["f2"]},
            {"theme": "First source detail", "priority": 4, "evidence_ids": ["f1"]},
            {"theme": "Second source context", "priority": 5, "evidence_ids": ["f2"]},
        ],
    }
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="insights:failed-insight.text",
        message="The failed insight cannot be grounded.",
        severity="error",
        entity_id="insight:failed-insight:text",
        evidence_ids=["f1"],
    )
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        regenerate_steps=["insights_candidates", "insights_final"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/insights_candidates",
                            "report_vs/artifacts/regenerate/insights_final",
                        ],
                        issues=[issue],
                        repair_action="REMOVE_CLAIM",
                        repair_strategy="safe_removal",
                        allowed_paths=[
                            "insights_candidates[item=failed-insight]",
                            "insights_final[item=failed-insight]",
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=None,
        prompt_client=_FakePromptClient(),
    )

    final_by_id = {
        item["id"]: item for item in response.updated_artifacts["insights_final"]
    }
    assert "failed-insight" not in final_by_id
    assert final_by_id["sibling-insight"] == sibling
    assert final_by_id["other-insight"] == other
    assert final_by_id["extra-insight-one"] == extra_one
    assert final_by_id["extra-insight-two"] == extra_two
    assert final_by_id["replacement-id"]["evidence_id"] == "f2"
    assert len(final_by_id) == 5


def test_rebound_insight_uses_canonical_evidence_pages_and_spans(tmp_path) -> None:
    current = _source_backed_artifacts()
    item = current["insights_final"][0]
    item.update(
        {
            "now_what": "Use the currently retained source.",
            "evidence_id": "f1",
            "evidence": "Old source text.",
            "pages": [77],
            "evidence_spans": [
                {
                    "evidence_id": "f1",
                    "source_pack": "doc_map",
                    "section_id": "f1",
                    "page": 77,
                    "text": "Old source text.",
                }
            ],
        }
    )
    evidence_packs = _evidence_packs()
    source_sections = [
        {
            "id": f"f{index}",
            "title": f"Source {index}",
            "summary": (
                "The supported replacement evidence explains the recommendation."
                if index == 2
                else f"Canonical source text for f{index}."
            ),
            "pages": [index],
        }
        for index in range(1, 6)
    ]
    evidence_packs["doc_map"]["sections"] = source_sections
    evidence_packs["findings"]["findings"] = [
        {
            "id": f"f{index}",
            "text": (
                "The supported replacement evidence explains the recommendation."
                if index == 2
                else f"Canonical source text for f{index}."
            ),
            "evidence": (
                "The supported replacement evidence explains the recommendation."
                if index == 2
                else f"Canonical source text for f{index}."
            ),
            "pages": [index],
        }
        for index in range(1, 6)
    ]
    item_path = "insights_final[item=insight-1]"
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="insights_bundle",
                regenerate_steps=["insights_final"],
                prompt_namespaces=["report_vs/artifacts/regenerate/insights_final"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="insights:insight-1.now_what",
                        message="The recommendation needs an alternative source.",
                        severity="error",
                        entity_id="insight:insight-1:now_what",
                        evidence_ids=["f2"],
                    )
                ],
                repair_action="REBIND_EVIDENCE",
                repair_strategy="current_evidence",
                allowed_paths=[
                    f"{item_path}.evidence_id",
                    f"{item_path}.now_what",
                ],
                # The planner carries the evidence attached to the failed
                # claim; the model repair selects the canonical alternative.
                selected_evidence_ids=["f1"],
                quarantined_evidence_ids=[],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    decision = {
        "schema_version": "1.0",
        "repair_action": "REBIND_EVIDENCE",
        "repair_strategy": "current_evidence",
        "evidence_ids_used": ["f2"],
        "changed_paths": [f"{item_path}.evidence_id", f"{item_path}.now_what"],
        "minimal_patch": [
            {
                "op": "replace",
                "path": f"{item_path}.evidence_id",
                "value": "f2",
            },
            {
                "op": "replace",
                "path": f"{item_path}.now_what",
                "value": "Use the supported replacement evidence.",
            },
        ],
    }
    client = _RepairDecisionOpenAIClient(decision)

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    rebound = response.updated_artifacts["insights_final"][0]
    assert rebound["evidence_id"] == "f2"
    assert rebound["evidence"] == (
        "The supported replacement evidence explains the recommendation."
    )
    assert rebound["pages"] == [2]
    expected_spans = [
        span
        for span in artifact_evidence_span_index(
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
        )["f2"]
        if span.get("source_pack") in {"findings", "quote_candidates"}
    ]
    assert rebound["evidence_spans"] == expected_spans
    assert response.deterministic_mutation_paths == [
        f"{item_path}.evidence",
        f"{item_path}.evidence_spans",
        f"{item_path}.pages",
    ]
    verified = _verified_deterministic_mutation_paths(
        paths=response.deterministic_mutation_paths,
        before=current,
        after=response.updated_artifacts,
        plan=plan,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
        repair_decisions=response.repair_decisions,
    )
    assert verified == set(response.deterministic_mutation_paths)

    scoped_before = {"insights_final": [deepcopy(item)]}
    scoped_after = {
        "insights_final": [deepcopy(rebound)],
    }
    scope = _scope_validation_report(
        before=scoped_before,
        after=scoped_after,
        plan=plan,
        deterministic_mutation_paths=response.deterministic_mutation_paths,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
        repair_decisions=response.repair_decisions,
    )
    assert scope.status == "pass", [
        (issue.affected_section, issue.rule_id) for issue in scope.issues
    ]

    unselected_scope = _scope_validation_report(
        before=scoped_before,
        after=scoped_after,
        plan=plan,
        deterministic_mutation_paths=response.deterministic_mutation_paths,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )
    assert unselected_scope.status == "fail"

    unrelated_selection = replace(
        response.repair_decisions[0],
        changed_paths=["insights_final[item=insight-2].text"],
    )
    assert not _verified_deterministic_mutation_paths(
        paths=response.deterministic_mutation_paths,
        before=current,
        after=response.updated_artifacts,
        plan=plan,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
        repair_decisions=[unrelated_selection],
    )
    mismatched_selection = replace(
        response.repair_decisions[0], evidence_ids_used=["f3"]
    )
    assert not _verified_deterministic_mutation_paths(
        paths=response.deterministic_mutation_paths,
        before=current,
        after=response.updated_artifacts,
        plan=plan,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
        repair_decisions=[mismatched_selection],
    )

    tampered = deepcopy(response.updated_artifacts)
    tampered["insights_final"][0]["pages"] = [77]
    assert not _verified_deterministic_mutation_paths(
        paths=response.deterministic_mutation_paths,
        before=current,
        after=tampered,
        plan=plan,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )
    tampered_scope = _scope_validation_report(
        before=scoped_before,
        after={"insights_final": [tampered["insights_final"][0]]},
        plan=plan,
        deterministic_mutation_paths=response.deterministic_mutation_paths,
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
        repair_decisions=response.repair_decisions,
    )
    assert tampered_scope.status == "fail"


def test_model_repair_rejects_illegal_sibling_patch_before_candidate_write(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    decision = _atomic_insight_decision()
    sibling_path = "insights_final[item=insight-2].text"
    decision["changed_paths"].append(sibling_path)
    decision["minimal_patch"].append(
        {
            "op": "replace",
            "path": sibling_path,
            "value": "Changed sibling",
        }
    )
    client = _RepairDecisionOpenAIClient(decision)

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_atomic_insight_plan(),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    assert response.repair_decisions[-1].repair_action == "ABSTAIN"
    assert (
        response.repair_decisions[-1].repair_strategy
        == "current_evidence:provider_rejected:changed_path_outside_allowed_paths"
    )
    assert response.updated_artifacts["insights_final"] == current["insights_final"]
    assert len(client.calls) == 1


def test_model_repair_rejects_non_string_patch_value_before_candidate_write(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(
        _atomic_insight_decision(value={"text": "over-broad"})
    )

    with pytest.raises(AppError) as error:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=_atomic_insight_plan(),
                current_artifacts=current,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=client,
            prompt_client=_FakePromptClient(),
        )

    assert error.value.code == "artifact_structured_output_invalid"
    assert error.value.context["error_class"] == "schema_type_mismatch"
    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


def test_model_repair_rejects_quarantined_evidence_before_candidate_write(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(_atomic_insight_decision(evidence_ids=["f1"]))

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_atomic_insight_plan(quarantined=["f1"]),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    assert response.repair_decisions[-1].repair_action == "ABSTAIN"
    assert (
        response.repair_decisions[-1].repair_strategy
        == "current_evidence:provider_rejected:evidence_not_retained_or_quarantined"
    )
    assert len(client.calls) == 1
    prompt_variables = _parse_fixture_variables(client.calls[0].user_prompt)
    repair_context = json.loads(prompt_variables["repair_context_json"])
    assert "f1" not in repair_context["allowed_evidence_ids"]
    assert response.updated_artifacts["insights_final"] == current["insights_final"]


def test_model_repair_rejects_evidence_missing_from_retained_package(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(
        _atomic_insight_decision(evidence_ids=["not-retained"])
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_atomic_insight_plan(),
            current_artifacts=current,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=client,
        prompt_client=_FakePromptClient(),
    )

    assert response.repair_decisions[-1].repair_action == "ABSTAIN"
    assert (
        response.repair_decisions[-1].repair_strategy
        == "current_evidence:provider_rejected:evidence_not_retained_or_quarantined"
    )
    assert len(client.calls) == 1
    assert response.updated_artifacts["insights_final"] == current["insights_final"]


def test_invalid_repair_contract_does_not_trigger_a_second_provider_call(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    decision = _atomic_insight_decision()
    del decision["evidence_ids_used"]
    client = _RepairDecisionOpenAIClient(decision)

    with pytest.raises(AppError):
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=_atomic_insight_plan(),
                current_artifacts=current,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=client,
            prompt_client=_FakePromptClient(),
        )

    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


__all__ = [
    "test_missing_required_insight_text_patch_preserves_original_candidate",
    "test_safe_removal_replacement_id_does_not_overwrite_sibling_evidence_identity",
    "test_rebound_insight_uses_canonical_evidence_pages_and_spans",
    "test_model_repair_applies_one_validated_atomic_patch_in_one_call",
    "test_model_repair_rejects_illegal_sibling_patch_before_candidate_write",
    "test_model_repair_rejects_non_string_patch_value_before_candidate_write",
    "test_model_repair_rejects_quarantined_evidence_before_candidate_write",
    "test_model_repair_rejects_evidence_missing_from_retained_package",
    "test_invalid_repair_contract_does_not_trigger_a_second_provider_call",
]
