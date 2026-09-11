from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt_set, render_prompt

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    ROOT / "tests/fixtures/prompt_grounding_policy/primary_generation_cases.json"
)
PRIMARY_NAMESPACES = (
    "report_vs/artifacts/summary",
    "report_vs/artifacts/expert_comment",
    "report_vs/artifacts/linkedin_post",
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="prompt-grounding",
        task_id="primary-generation",
        span_id="fixture",
    )


def _cases() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _normalise_whitespace(value: str) -> str:
    return " ".join(value.split())


@pytest.mark.parametrize("namespace", PRIMARY_NAMESPACES)
@pytest.mark.parametrize(
    "policy_case", _cases()["policy_cases"], ids=lambda case: case["name"]
)
def test_primary_generation_prompts_apply_grounding_policy_case(
    namespace: str, policy_case: dict
) -> None:
    prompt_set = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    assert _normalise_whitespace(policy_case["required_text"]) in _normalise_whitespace(
        prompt_set.user.text
    )


def _ias_render_variables(case: dict) -> dict[str, dict[str, str]]:
    doc_map = json.loads((ROOT / case["doc_map_path"]).read_text(encoding="utf-8"))
    findings = json.loads((ROOT / case["findings_path"]).read_text(encoding="utf-8"))
    artifacts = json.loads((ROOT / case["artifacts_path"]).read_text(encoding="utf-8"))
    findings_json = json.dumps(findings, ensure_ascii=False)
    doc_map_json = json.dumps(doc_map, ensure_ascii=False)
    editorial_plan_json = json.dumps(artifacts["editorial_plan"], ensure_ascii=False)
    insights_final_json = json.dumps(artifacts["insights_final"], ensure_ascii=False)
    metric_spine_json = json.dumps(
        [item["metric"] for item in artifacts["insights_final"] if item.get("metric")],
        ensure_ascii=False,
    )
    expert_context_json = json.dumps(
        {
            "themes": artifacts["editorial_plan"]["themes"],
            "evidence": findings["findings"],
            "insight_implications": [],
            "limitations": [],
            "counter_signals": [],
        },
        ensure_ascii=False,
    )
    return {
        "report_vs/artifacts/summary": {
            "doc_map_json": doc_map_json,
            "evidence_json": findings_json,
            "editorial_plan_json": editorial_plan_json,
        },
        "report_vs/artifacts/expert_comment": {
            "editorial_plan_json": editorial_plan_json,
            "expert_synthesis_context_json": expert_context_json,
            "metric_spine_json": metric_spine_json,
        },
        "report_vs/artifacts/linkedin_post": {
            "editorial_plan_json": editorial_plan_json,
            "doc_map_json": doc_map_json,
            "insights_final_json": insights_final_json,
            "metric_spine_json": metric_spine_json,
        },
    }


@pytest.mark.parametrize(
    "case", _cases()["retained_regression_cases"], ids=lambda case: case["name"]
)
@pytest.mark.parametrize("namespace", PRIMARY_NAMESPACES)
def test_retained_ias_case_materializes_each_primary_generation_prompt(
    namespace: str, case: dict
) -> None:
    variables = _ias_render_variables(case)[namespace]
    prompt_set = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )

    rendered = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        _ctx(),
    )

    for value in variables.values():
        assert value in rendered.text
