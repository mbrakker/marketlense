import json
from copy import deepcopy

from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import AnalysisPackPathResponse
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue
from src.generators.public_editorial_quality_generator import (
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
from src.services.prompt_service import load_prompt_set
from tests._test_atomic_regeneration_contract._split_support_test_atomic_regeneration_contract import (  # noqa: E501
    _insight_artifacts,
)
from tests._test_report_analysis_generator._shared import _artifacts, _deps, _runtime
from tests.test_public_editorial_review_reuse import (
    _run_quality_review,
    _SemanticPassClient,
)


def _nomination(insight_id, leaf):
    return ValidationIssue(
        message="Revise this editorial contribution to make the pair distinct.",
        severity="error",
        affected_section=f"insights:{insight_id}.{leaf}",
        rule_id="public_editorial_quality.semantic_collective_editorial_repair",
        repair_target="insights_bundle",
        entity_id=f"insight:{insight_id}:{leaf}",
        evidence_ids=["evidence-1"],
    )


def test_reviewer_instructed_to_explicitly_nominate_both_coupled_leaves():
    prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/validate/public_editorial_quality",
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    text = " ".join(prompt.system.text.split())
    assert "nominate both so_what and now_what as separate repair_items" in text
    assert "Do not nominate the sibling merely because it exists" in text


def test_pair_nominations_create_one_target_with_only_both_editorial_leaves():
    artifacts = _insight_artifacts()
    plan = _build_regeneration_plan(
        issues=[
            _nomination("insight-1", "so_what"),
            _nomination("insight-1", "now_what"),
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert plan.mode == "targeted"
    assert len(plan.targets) == 1
    assert set(plan.targets[0].allowed_paths) == {
        "insights_final[item=insight-1].so_what",
        "insights_final[item=insight-1].now_what",
    }
    changed = deepcopy(artifacts)
    changed["insights_final"][0]["so_what"] = "New implication."
    changed["insights_final"][0]["now_what"] = "New action."
    assert (
        _scope_validation_report(before=artifacts, after=changed, plan=plan).status
        == "pass"
    )
    for field, value in (
        ("evidence_id", "other"),
        ("text", "Changed fact."),
        ("pages", [99]),
    ):
        invalid = deepcopy(changed)
        invalid["insights_final"][0][field] = value
        assert (
            _scope_validation_report(before=artifacts, after=invalid, plan=plan).status
            == "fail"
        )
    changed["insights_final"][0]["metric"]["value"] = "99%"
    assert (
        _scope_validation_report(before=artifacts, after=changed, plan=plan).status
        == "fail"
    )


def test_single_nomination_does_not_authorize_sibling():
    artifacts = _insight_artifacts()
    plan = _build_regeneration_plan(
        issues=[_nomination("insight-1", "so_what")],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert plan.targets[0].allowed_paths == ["insights_final[item=insight-1].so_what"]
    changed = deepcopy(artifacts)
    changed["insights_final"][0]["now_what"] = "Unauthorized action."
    assert (
        _scope_validation_report(before=artifacts, after=changed, plan=plan).status
        == "fail"
    )


def test_explicit_reviewer_pair_reaches_one_scoped_plan(tmp_path):
    artifacts = _artifacts()
    artifacts["insights_final"][0]["so_what"] = "Original implication."
    artifacts["insights_final"][0]["now_what"] = "Original action."
    items = public_editorial_semantic_review_items(artifacts)
    selected = [
        item
        for item in items
        if item.get("artifact") == "insights_final"
        and item.get("field")
        in {"insights:insight-1.so_what", "insights:insight-1.now_what"}
    ]
    assert len(selected) == 2

    class PairClient(_SemanticPassClient):
        def openai_chat_json(self, request, ctx):
            response = super().openai_chat_json(request, ctx)
            payload = response.parsed_json
            ids = {item["public_item_id"] for item in selected}
            for verdict in payload["verdicts"]:
                if verdict["item_id"] in ids:
                    verdict["classification"] = "analyst_interpretation"
            report = payload["report_verdict"]
            report.update(
                status="fail",
                severity="error",
                rule_id="public_editorial_quality.semantic_distinctness",
                hard_fail_class="editorial_quality",
                reason="The implication and action repeat each other.",
                repair_items=[
                    {
                        "item_id": item["public_item_id"],
                        "reason": "Give this leaf a distinct role.",
                        "evidence_ids": list(item["evidence_ids"]),
                        "repair_target": item["repair_target"],
                    }
                    for item in selected
                ],
            )
            report["dimensions"]["distinctness"] = {
                "status": "fail",
                "reason": "The pair repeats the same analysis.",
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                model=request.model,
            )

    quality, _ = _run_quality_review(
        runtime=_runtime(tmp_path),
        dependencies=_deps(
            analysis_store_pack=lambda request, _ctx: AnalysisPackPathResponse(
                schema_version="1.0", output_path=request.pack_name
            )
        ),
        artifacts=artifacts,
        client=PairClient(items),
        pack_name="public_editorial_quality_before",
    )
    plan = _build_regeneration_plan(
        issues=quality.issues, artifacts=artifacts, broad_retry_available=False
    )
    assert len(plan.targets) == 1
    assert set(plan.targets[0].allowed_paths) == {
        "insights_final[item=insight-1].so_what",
        "insights_final[item=insight-1].now_what",
    }
