"""Per-leaf evidence isolation for grouped editorial nominations."""

import json
from copy import deepcopy

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import ArtifactRegenerationRequest
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from tests._test_report_regeneration_identity_and_failures._shared import (
    _source_backed_artifacts,
)
from tests.test_report_regeneration_generator import _ctx, _evidence_packs, _settings


def _run_grouped_repair(
    tmp_path, *, nominations, used, leaves, return_response=False, non_collective=()
):
    artifacts = _source_backed_artifacts()
    insight = artifacts["insights_final"][0]
    insight["so_what"] = "Original implication."
    insight["now_what"] = "Original action."
    insight["evidence_ids"] = ["f1", "f2"]
    before = deepcopy(artifacts)
    issues = [
        ValidationIssue(
            schema_version="1.0",
            severity="error",
            rule_id=(
                "public_editorial_quality.semantic_generic_copy"
                if leaf in non_collective
                else "public_editorial_quality.semantic_collective_editorial_repair"
            ),
            message="Make the nominated leaf distinct.",
            affected_section=f"insights:insight-1.{leaf}",
            entity_id=f"insight:insight-1:{leaf}",
            repair_target="insights_bundle",
            evidence_ids=[evidence_id],
        )
        for leaf, evidence_id in nominations
    ]
    plan = _build_regeneration_plan(
        issues=issues, artifacts=artifacts, broad_retry_available=False
    )
    assert len(plan.targets) == 1
    if non_collective:
        assert {issue.rule_id for issue in plan.targets[0].issues} == {
            "public_editorial_quality.semantic_collective_editorial_repair",
            "public_editorial_quality.semantic_generic_copy",
        }
    assert set(plan.targets[0].allowed_paths) == {
        "insights_final[item=insight-1].so_what",
        "insights_final[item=insight-1].now_what",
    }

    class CrossLeafProvider:
        def openai_chat_json(self, request, ctx):
            del request, ctx
            payload = {
                "repair_decision": {
                    "schema_version": "1.0",
                    "repair_action": "REGENERATE_ITEM",
                    "repair_strategy": "current_evidence",
                    "evidence_ids_used": used,
                    "changed_paths": [
                        f"insights_final[item=insight-1].{leaf}" for leaf in leaves
                    ],
                    "minimal_patch": [
                        {
                            "op": "replace",
                            "path": f"insights_final[item=insight-1].{leaf}",
                            "value": f"Repaired {leaf}.",
                        }
                        for leaf in leaves
                    ],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="local",
            )

    evidence = _evidence_packs()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=artifacts,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=CrossLeafProvider(),
    )
    assert artifacts == before
    if return_response:
        return response
    return response.updated_artifacts["insights_final"][0]


def test_grouped_nominations_cannot_authorize_other_leafs_evidence(tmp_path):
    result = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f2")],
        used=["f2"],
        leaves=["so_what"],
    )
    assert result["so_what"] == "Original implication."


def test_grouped_nomination_abstains_on_empty_evidence_for_patched_leaf(tmp_path):
    response = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f2")],
        used=[],
        leaves=["so_what"],
        return_response=True,
    )
    assert response.updated_artifacts["insights_final"][0]["so_what"] == (
        "Original implication."
    )
    assert response.repair_decisions[0].repair_action == "ABSTAIN"


def test_mixed_issue_cannot_authorize_other_leafs_evidence(tmp_path):
    response = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f2")],
        non_collective=("now_what",),
        used=["f2"],
        leaves=["so_what"],
        return_response=True,
    )
    assert response.updated_artifacts["insights_final"][0]["so_what"] == (
        "Original implication."
    )
    assert response.repair_decisions[0].repair_action == "ABSTAIN"


@pytest.mark.parametrize(
    ("leaf", "evidence", "other", "original"),
    [
        ("so_what", "f1", "now_what", "Original action."),
        ("now_what", "f2", "so_what", "Original implication."),
    ],
)
def test_grouped_nomination_accepts_own_leaf_evidence(
    tmp_path, leaf, evidence, other, original
):
    result = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f2")],
        used=[evidence],
        leaves=[leaf],
    )
    assert result[leaf] == f"Repaired {leaf}."
    assert result[other] == original


def test_disjoint_leaf_nominations_reject_flat_multi_leaf_evidence(tmp_path):
    result = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f2")],
        used=["f1", "f2"],
        leaves=["so_what", "now_what"],
    )
    assert result["so_what"] == "Original implication."
    assert result["now_what"] == "Original action."


def test_shared_leaf_evidence_accepts_flat_multi_leaf_repair(tmp_path):
    result = _run_grouped_repair(
        tmp_path,
        nominations=[("so_what", "f1"), ("now_what", "f1")],
        used=["f1"],
        leaves=["so_what", "now_what"],
    )
    assert result["so_what"] == "Repaired so_what."
    assert result["now_what"] == "Repaired now_what."
