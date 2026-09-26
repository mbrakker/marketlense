# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.generators.report_regeneration_generator import (
    _decode_repair_patch_value_json,
    regenerate_artifacts,
)
from src.utils.errors import AppError
from tests.test_report_regeneration_generator import (
    _ctx,
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
                        message="[grounding|unsupported_factual_claim] Repair one item.",
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
    value: str = "Repaired final insight",
    value_json: str | None = None,
    path: str = "insights_final[item=insight-1].text",
    evidence_ids: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "repair_action": "REGENERATE_ITEM",
        "repair_strategy": "current_evidence",
        "evidence_ids_used": list(evidence_ids or ["f1"]),
        "protected_fields": [
            "insights_final[item=insight-1].id",
            "insights_final[item=insight-1].evidence_id",
            "insights_final[item=insight-1].evidence",
            "insights_final[item=insight-1].metric",
            "insights_final[item=insight-1].pages",
        ],
        "changed_paths": [path],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value_json": (
                    value_json
                    if value_json is not None
                    else json.dumps(value, ensure_ascii=False)
                ),
            }
        ],
        "claim_provenance": [],
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
        "regeneration_repair_decision_v3"
    )
    assert repaired[0]["text"] == "Repaired final insight"
    assert repaired[0]["metric"] == before[0]["metric"]
    assert repaired[1:] == before[1:]
    assert response.repair_decisions[0].changed_paths == [
        "insights_final[item=insight-1].text"
    ]
    assert response.repair_decisions[0].diagnosed_failure_class == "grounding"


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
            "value_json": json.dumps("Changed sibling"),
        }
    )
    client = _RepairDecisionOpenAIClient(decision)

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

    assert error.value.code == "regeneration_repair_decision_invalid"
    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


def test_model_repair_rejects_invalid_json_patch_value_before_candidate_write(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(_atomic_insight_decision(value_json="{"))

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

    assert error.value.code == "regeneration_repair_decision_invalid"
    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


@pytest.mark.parametrize(
    "value",
    ["text", 0, False, None, ["a", 1], {"value": ["a", 1]}],
)
def test_repair_value_json_round_trip_preserves_json_types(value) -> None:
    assert _decode_repair_patch_value_json(json.dumps(value)) == value


def test_model_repair_rejects_quarantined_evidence_before_candidate_write(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(_atomic_insight_decision(evidence_ids=["f1"]))

    with pytest.raises(AppError) as error:
        regenerate_artifacts(
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

    assert error.value.code == "regeneration_repair_decision_invalid"
    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


def test_model_repair_rejects_evidence_missing_from_retained_package(
    tmp_path,
) -> None:
    current = _source_backed_artifacts()
    client = _RepairDecisionOpenAIClient(
        _atomic_insight_decision(evidence_ids=["not-retained"])
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

    assert error.value.code == "regeneration_repair_decision_invalid"
    assert len(client.calls) == 1
    assert not list((tmp_path / "out").rglob("artifacts_regen_candidate_1.json"))


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
    "test_model_repair_applies_one_validated_atomic_patch_in_one_call",
    "test_model_repair_rejects_illegal_sibling_patch_before_candidate_write",
    "test_model_repair_rejects_invalid_json_patch_value_before_candidate_write",
    "test_repair_value_json_round_trip_preserves_json_types",
    "test_model_repair_rejects_quarantined_evidence_before_candidate_write",
    "test_model_repair_rejects_evidence_missing_from_retained_package",
    "test_invalid_repair_contract_does_not_trigger_a_second_provider_call",
]
