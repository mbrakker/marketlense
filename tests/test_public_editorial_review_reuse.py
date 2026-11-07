from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.report_analysis import AnalysisPackPathResponse
from src.generators.public_editorial_quality_generator import (
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _evaluate_and_store_public_editorial_quality,
    _public_editorial_review_input_identity,
    _public_editorial_semantic_review,
)
from tests._test_report_analysis_generator._shared import (
    _artifacts,
    _deps,
    _runtime,
)


class _SemanticPassClient:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.calls = 0
        self.requests = []

    def openai_chat_json(self, request, _ctx):
        self.calls += 1
        self.requests.append(request)
        verdicts = [
            {
                "item_id": str(item["public_item_id"]),
                "status": "pass",
                "classification": (
                    "factual_claim"
                    if item.get("evidence_ids") or item.get("verified_facts")
                    else "prescriptive_recommendation"
                ),
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The item remains supported by the retained evidence.",
                "evidence_ids": list(item.get("evidence_ids") or []),
                "repair_target": "",
            }
            for item in self.items
        ]
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for verdict in verdicts
                for evidence_id in verdict["evidence_ids"]
            )
        )
        payload = {
            "verdicts": verdicts,
            "report_verdict": {
                "status": "pass",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The report remains coherent and source-grounded.",
                "evidence_ids": evidence_ids,
                "repair_target": "",
                "affected_item_id": "",
                "dimensions": {
                    dimension: {
                        "status": "pass",
                        "reason": "The report satisfies this dimension.",
                    }
                    for dimension in (
                        "material_coverage",
                        "analytical_depth",
                        "distinctness",
                        "limitations",
                    )
                },
            },
        }
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            model=request.model,
        )


def test_public_editorial_review_declares_allowed_repair_targets_to_model(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    client = _SemanticPassClient(items)
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: AnalysisPackPathResponse(
            schema_version="1.0", output_path=request.pack_name
        )
    )

    _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_before",
    )

    assert client.requests
    prompt = client.requests[0].user_prompt
    marker = '"public_items"'
    marker_index = prompt.find(marker)
    assert marker_index >= 0
    object_start = prompt.rfind("{", 0, marker_index)
    review_input, _ = json.JSONDecoder().raw_decode(prompt[object_start:])
    sent_items = review_input["public_items"]
    sent_by_id = {str(item["item_id"]): item for item in sent_items}
    for item in items:
        sent = sent_by_id[str(item["public_item_id"])]
        assert sent["allowed_repair_target"] == str(item.get("repair_target") or "")


def test_localized_report_failure_carries_independent_item_classification(tmp_path):
    runtime = _runtime(tmp_path)
    artifacts = _artifacts(
        summary={"tldr": "", "executive_summary": "", "claim_evidence_map": []},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
    )
    items = public_editorial_semantic_review_items(artifacts)
    target = next(item for item in items if item["artifact"] == "expert_comment")

    class _LocalizedFailureClient:
        def openai_chat_json(self, request, _ctx):
            verdicts = []
            for item in items:
                item_id = str(item["public_item_id"])
                evidence_ids = list(item.get("evidence_ids") or [])
                if item_id == target["public_item_id"]:
                    verdicts.append(
                        {
                            "item_id": item_id,
                            "status": "fail",
                            "classification": "analyst_interpretation",
                            "severity": "error",
                            "rule_id": "public_editorial_quality.semantic_generic_copy",
                            "hard_fail_class": "editorial_quality",
                            "reason": (
                                "The Expert View repeats the finding without a "
                                "specific commercial implication."
                            ),
                            "evidence_ids": [],
                            "repair_target": "expert_comment",
                        }
                    )
                else:
                    verdicts.append(
                        {
                            "item_id": item_id,
                            "status": "pass",
                            "classification": (
                                "factual_claim"
                                if evidence_ids
                                else "prescriptive_recommendation"
                            ),
                            "severity": "info",
                            "rule_id": "",
                            "hard_fail_class": "",
                            "reason": (
                                "The item remains valid within its retained scope."
                            ),
                            "evidence_ids": evidence_ids,
                            "repair_target": "",
                        }
                    )
            payload = {
                "verdicts": verdicts,
                "report_verdict": {
                    "status": "fail",
                    "severity": "error",
                    "rule_id": "public_editorial_quality.report_acceptance",
                    "hard_fail_class": "report_editorial_acceptance",
                    "reason": "The report needs more analytical depth.",
                    "evidence_ids": [],
                    "repair_target": "expert_comment",
                    "affected_item_id": target["public_item_id"],
                    "dimensions": {
                        "material_coverage": {
                            "status": "pass",
                            "reason": "Material findings remain represented.",
                        },
                        "analytical_depth": {
                            "status": "fail",
                            "reason": (
                                "The report repeats the finding without analysis."
                            ),
                        },
                        "distinctness": {
                            "status": "pass",
                            "reason": "The selected items remain distinct.",
                        },
                        "limitations": {
                            "status": "pass",
                            "reason": "The report retains its limitations.",
                        },
                    },
                },
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                model=request.model,
            )

    issues = _public_editorial_semantic_review(
        runtime=runtime,
        artifacts=artifacts,
        ctx=runtime.ctx,
        openai_client=_LocalizedFailureClient(),
    )

    item_issue = next(
        issue for issue in issues if issue.public_item_id == target["public_item_id"]
    )
    report_issue = next(
        issue
        for issue in issues
        if issue.rule_id == "public_editorial_quality.report_acceptance"
    )
    assert item_issue.classification == "analyst_interpretation"
    assert report_issue.classification == "analyst_interpretation"
    assert report_issue.repair_eligible is True
    assert report_issue.repair_target == "expert_comment"


class _SemanticInvalidClient:
    def __init__(self) -> None:
        self.calls = 0

    def openai_chat_json(self, request, _ctx):
        self.calls += 1
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json={},
            model=request.model,
        )


def _run_quality_review(
    *,
    runtime,
    dependencies,
    artifacts: dict,
    client,
    pack_name: str,
    capture=None,
    reuse=None,
):
    return _evaluate_and_store_public_editorial_quality(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=artifacts,
        pack_name=pack_name,
        ctx=runtime.ctx,
        openai_client=client,
        semantic_review_capture=capture,
        semantic_review_reuse=reuse,
    )


def test_public_editorial_review_reuses_terminal_pass_and_materializes_both_packs(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    client = _SemanticPassClient(public_editorial_semantic_review_items(artifacts))
    stored = []

    def store(request, _ctx):
        stored.append(request)
        return AnalysisPackPathResponse(
            schema_version="1.0", output_path=request.pack_name
        )

    dependencies = _deps(analysis_store_pack=store)
    capture: list[Any] = []

    first, first_path = _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_before",
        capture=capture,
    )
    second, second_path = _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_after",
        reuse=capture[0],
    )

    assert first is not None and second is not None
    assert first.status == second.status
    assert first.issues == second.issues
    assert first_path == "public_editorial_quality_before"
    assert second_path == "public_editorial_quality_after"
    assert client.calls == 1
    assert [request.pack_name for request in stored] == [
        "public_editorial_quality_before",
        "public_editorial_quality_after",
    ]


def test_public_editorial_review_reuses_terminal_failure_without_reopening_it(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    client = _SemanticInvalidClient()
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: AnalysisPackPathResponse(
            schema_version="1.0", output_path=request.pack_name
        )
    )
    capture: list[Any] = []

    first, _ = _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_before",
        capture=capture,
    )
    calls_after_first = client.calls
    second, _ = _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_after",
        reuse=capture[0],
    )

    assert first is not None and second is not None
    assert first.status == "fail"
    assert second.status == "fail"
    assert first.issues == second.issues
    semantic_issue = next(
        issue
        for issue in first.issues
        if issue.rule_id == "public_editorial_quality.semantic_review_unresolved"
    )
    assert "terminal=public_editorial_quality_review_invalid_json" in (
        semantic_issue.message
    )
    assert "inner=public_editorial_quality_report_review_incomplete" in (
        semantic_issue.message
    )
    assert client.calls >= 1
    assert client.calls == calls_after_first


def test_public_editorial_review_reuse_is_invalidated_by_content_changes(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    client = _SemanticPassClient(public_editorial_semantic_review_items(artifacts))
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: AnalysisPackPathResponse(
            schema_version="1.0", output_path=request.pack_name
        )
    )
    capture: list[Any] = []
    _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_before",
        capture=capture,
    )
    changed = deepcopy(artifacts)
    changed["insights_final"][0]["text"] = "A materially different editorial claim."
    _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=changed,
        client=client,
        pack_name="public_editorial_quality_after",
        reuse=capture[0],
    )

    assert client.calls == 2


@pytest.mark.parametrize("change", ["evidence", "editorial_plan"])
def test_public_editorial_review_reuse_is_invalidated_by_evidence_context_changes(
    tmp_path, change
) -> None:
    runtime = _runtime(tmp_path)
    artifacts = _artifacts()
    client = _SemanticPassClient(public_editorial_semantic_review_items(artifacts))
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: AnalysisPackPathResponse(
            schema_version="1.0", output_path=request.pack_name
        )
    )
    capture: list[Any] = []
    _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=deepcopy(artifacts),
        client=client,
        pack_name="public_editorial_quality_before",
        capture=capture,
    )
    changed = deepcopy(artifacts)
    if change == "evidence":
        changed["insights_final"][0]["evidence"] = "A different retained excerpt."
    else:
        changed["editorial_plan"]["themes"].append(
            {"theme": "New theme", "priority": 3, "evidence_ids": ["f3"]}
        )
    _run_quality_review(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=changed,
        client=client,
        pack_name="public_editorial_quality_after",
        reuse=capture[0],
    )

    assert client.calls == 2


def test_public_editorial_review_identity_includes_source_fact_and_review_policy() -> (
    None
):
    base = {
        "source_identity": "source-a",
        "verified_fact_digest": "facts-a",
        "relevant_input_hash": "inputs-a",
        "configuration_policy_hash": "policy-a",
        "prompt_content_hash": "prompt-a",
        "execution_identity": "execution-a",
    }
    identity = _public_editorial_review_input_identity(**base)
    for field, value in (
        ("source_identity", "source-b"),
        ("verified_fact_digest", "facts-b"),
        ("relevant_input_hash", "inputs-b"),
        ("configuration_policy_hash", "policy-b"),
        ("prompt_content_hash", "prompt-b"),
        ("execution_identity", "execution-b"),
    ):
        changed = dict(base)
        changed[field] = value
        assert _public_editorial_review_input_identity(**changed) != identity
