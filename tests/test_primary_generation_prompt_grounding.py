from __future__ import annotations

import json
import re
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
MANDATORY_PRESSURE_PATTERNS = (
    ("executive implication", r"\bstate (?:the )?executive implication\b"),
    (
        "observation-to-action",
        r"\bmove from observation to implication to (?:an? )?executive action\b",
    ),
    (
        "decision implication",
        r"\badd one distinct (?:source-supported )?"
        r"(?:interpretation or )?decision implication\b",
    ),
    ("why this matters", r"\bexplain why (?:the selected angle|this) matters\b"),
)
IAS_UNSUPPORTED_CLAIM_GUARDS = {
    "predictions": "do not invent predictions",
    "causality": "causality",
    "budget movement": "budget movement",
    "performance outcomes": "performance effects",
    "operational benefits": "operational benefits",
    "mandatory actions": "mandatory actions",
}


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
    return " ".join(value.casefold().split())


def _render_primary_prompt(namespace: str, variables: dict[str, str]) -> str:
    prompt_set = load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace, force_reload=True),
        _ctx(),
    )
    return render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        _ctx(),
    ).text


def _scenario_render_variables(case: dict) -> dict[str, dict[str, str]]:
    evidence = [
        {"id": f"evidence-{index}", "text": text}
        for index, text in enumerate(case["source_evidence"], start=1)
    ]
    doc_map = json.dumps(
        {"title": case["title"], "scope": case["scope"], "findings": evidence},
        ensure_ascii=False,
    )
    editorial_plan = json.dumps(
        {
            "report_thesis": case["report_thesis"],
            "themes": [
                {
                    "theme": case["title"],
                    "evidence_ids": [item["id"] for item in evidence],
                }
            ],
        },
        ensure_ascii=False,
    )
    evidence_json = json.dumps({"findings": evidence}, ensure_ascii=False)
    expert_context = json.dumps(
        {
            "themes": [{"theme": case["title"], "evidence": evidence}],
            "insight_implications": case["candidate_implications"],
            "limitations": case["limitations"],
            "counter_signals": [],
        },
        ensure_ascii=False,
    )
    insights = json.dumps(
        [
            {"id": item["id"], "text": item["text"], "evidence_id": item["id"]}
            for item in evidence
        ],
        ensure_ascii=False,
    )
    return {
        "report_vs/artifacts/summary": {
            "doc_map_json": doc_map,
            "evidence_json": evidence_json,
            "editorial_plan_json": editorial_plan,
        },
        "report_vs/artifacts/expert_comment": {
            "editorial_plan_json": editorial_plan,
            "expert_synthesis_context_json": expert_context,
            "metric_spine_json": "[]",
        },
        "report_vs/artifacts/linkedin_post": {
            "editorial_plan_json": editorial_plan,
            "doc_map_json": doc_map,
            "insights_final_json": insights,
            "metric_spine_json": "[]",
        },
    }


def _mandatory_pressure_conflicts(prompt: str) -> tuple[str, ...]:
    normalised = _normalise_whitespace(prompt)
    conflicts: list[str] = []
    for name, pattern in MANDATORY_PRESSURE_PATTERNS:
        for match in re.finditer(pattern, normalised):
            window = normalised[max(0, match.start() - 96) : match.end() + 96]
            conditional = re.search(
                r"\b(?:when|only when|if|unless)\b.{0,80}"
                r"\b(?:support|evidence|source|ground)",
                window,
            )
            if conditional is None:
                conflicts.append(name)
    return tuple(conflicts)


@pytest.mark.parametrize(
    "policy_case", _cases()["policy_cases"], ids=lambda case: case["name"]
)
def test_policy_case_supplies_renderable_evidence_context(policy_case: dict) -> None:
    assert policy_case["source_evidence"]
    assert policy_case["candidate_implications"] is not None
    assert policy_case["limitations"] is not None
    assert policy_case["expected_policy"]


@pytest.mark.parametrize("namespace", PRIMARY_NAMESPACES)
@pytest.mark.parametrize(
    "policy_case", _cases()["policy_cases"], ids=lambda case: case["name"]
)
def test_primary_generation_prompt_renders_each_policy_scenario(
    namespace: str, policy_case: dict
) -> None:
    rendered = _render_primary_prompt(
        namespace, _scenario_render_variables(policy_case)[namespace]
    )
    normalised = _normalise_whitespace(rendered)

    for evidence in policy_case["source_evidence"]:
        assert _normalise_whitespace(evidence) in normalised
    for expectation in policy_case["expected_policy"]:
        assert _normalise_whitespace(expectation) in normalised
    for expectation in policy_case["namespace_expectations"][namespace]:
        assert _normalise_whitespace(expectation) in normalised


@pytest.mark.parametrize("namespace", PRIMARY_NAMESPACES)
def test_primary_generation_prompt_has_no_unconditional_mandatory_pressure(
    namespace: str,
) -> None:
    rendered = _render_primary_prompt(
        namespace, _scenario_render_variables(_cases()["policy_cases"][0])[namespace]
    )

    assert _mandatory_pressure_conflicts(rendered) == ()


def test_mandatory_pressure_conflict_detector_rejects_historical_contradiction(
) -> None:
    conflicting_prompt = (
        "Do not invent unsupported implications. "
        "You must state the executive implication."
    )

    assert _mandatory_pressure_conflicts(conflicting_prompt) == (
        "executive implication",
    )


def test_mandatory_pressure_conflict_detector_allows_supported_condition() -> None:
    conditional_prompt = (
        "State the executive implication only when supported by supplied evidence."
    )

    assert _mandatory_pressure_conflicts(conditional_prompt) == ()


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
    rendered = _render_primary_prompt(namespace, variables)

    for value in variables.values():
        assert value in rendered
    normalised = _normalise_whitespace(rendered)
    for guard in IAS_UNSUPPORTED_CLAIM_GUARDS.values():
        assert guard in normalised
    assert _mandatory_pressure_conflicts(rendered) == ()
