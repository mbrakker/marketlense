from __future__ import annotations

from copy import deepcopy

import pytest

from src.generators._artifact_generator.generation import (
    _classify_verified_semantic_recovery,
    generate_artifacts,
)
from src.generators.artifact_normalization import build_expert_synthesis_context
from src.utils.errors import AppError
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeAnalysisStore,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import _verified_admission
from tests.test_verified_claims_visual_authority_snapshot_integrity import (
    _generation_responses,
    _theme_coverage_response,
)


@pytest.mark.parametrize(
    ("assessment", "error_context", "expected"),
    [
        ({}, {"evidence_insufficiency": True}, "quarantine"),
        ({"diagnosis": "unrecognised", "recovery_action": "none"}, {}, "fail_closed"),
    ],
)
def test_verified_recovery_classifier_fails_closed_or_quarantines_explicitly(
    assessment: dict, error_context: dict, expected: str
) -> None:
    assert (
        _classify_verified_semantic_recovery(
            assessment=assessment,
            error_context=error_context,
        )
        == expected
    )


def test_legacy_expert_context_keeps_empty_limitations_distinct_from_selection() -> (
    None
):
    context = build_expert_synthesis_context(
        editorial_plan={
            "report_thesis": "Legacy plan",
            "themes": [
                {"theme": "Theme 1", "priority": 1, "evidence_ids": ["e1"]},
                {"theme": "Theme 2", "priority": 2, "evidence_ids": ["e2"]},
            ],
        },
        insights_final=[],
        doc_map={},
        evidence_packs={"limitations": {"limitations": []}},
    )
    assert context["limitations"] == []


def test_verified_replan_failure_is_bounded_and_fails_closed(tmp_path) -> None:
    candidates = [
        _insight("f1", score=0.99),
        _insight("f2", score=0.98),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    verified_plan = deepcopy(responses["editorial_plan"][1])
    verified_plan["editorial_plan"]["themes"][1]["importance"] = "optional"
    responses["editorial_plan"] = [
        responses["editorial_plan"][0],
        verified_plan,
        {"editorial_plan": {}},
    ]

    initial_coverage = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1"},
    )
    initial_coverage["theme_coverage"][1].update(
        {
            "status": "uncovered",
            "resolution": "omitted",
            "supporting_insight_ids": [],
        }
    )
    initial_coverage.update(
        {
            "report_completeness": "incomplete",
            "diagnosis": "redundant_optional_theme",
            "recovery_action": "replan",
        }
    )
    responses["editorial_theme_coverage"] = initial_coverage
    openai_client = FakeOpenAI(responses)

    with pytest.raises(AppError) as error:
        generate_artifacts(
            report_id="verified-replan-failure",
            report_name="Verified replan failure",
            doc_map=_doc_map(5),
            evidence_packs=_generation_evidence(5),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=openai_client,
            prompt_client=CapturingPromptClient(),
            analysis_store=FakeAnalysisStore(),
            visual_authority_admitter=lambda shortlisted: _verified_admission(
                shortlisted, digest="r" * 64
            ),
        )

    assert error.value.context["semantic_theme_repair"]["replan"] == {
        "attempted": True,
        "attempt": 1,
        "status": "failed",
        "trigger": {
            "diagnosis": "redundant_optional_theme",
            "recovery_action": "replan",
        },
    }
    assert [request[2] for request in openai_client.requests].count(
        "editorial_plan"
    ) >= 3


def test_verified_replan_rebuilds_theme_coverage_with_the_accepted_plan(tmp_path):
    candidates = [
        _insight("f1", score=0.99),
        _insight("f2", score=0.98),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    verified_plan = deepcopy(responses["editorial_plan"][1])
    verified_plan["editorial_plan"]["themes"][1]["importance"] = "optional"
    revised_plan = deepcopy(verified_plan)
    revised_plan["editorial_plan"]["themes"][0]["evidence_ids"] = [
        f"verified-fact:{candidates[0]['id']}"
    ]
    revised_plan["editorial_plan"]["themes"][0]["feasible_candidate_ids"] = [
        candidates[0]["id"]
    ]
    revised_plan["editorial_plan"]["themes"][1].update(
        {
            "theme": "Theme 3",
            "evidence_ids": [f"verified-fact:{candidates[2]['id']}"],
            "coverage_obligation": "Develop proposition 3.",
            "feasible_candidate_ids": [candidates[2]["id"]],
        }
    )
    responses["editorial_plan"] = [
        responses["editorial_plan"][0],
        verified_plan,
        revised_plan,
    ]
    final_insights_response = deepcopy(responses["insights_final"])
    responses["insights_final"] = [
        final_insights_response,
        deepcopy(final_insights_response),
    ]
    responses["replanned_insights_final"] = deepcopy(final_insights_response)
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    initial_coverage = _theme_coverage_response(
        candidates, ["f1", "f2"], covered_evidence_ids={"f1"}
    )
    initial_coverage.update(
        {
            "report_completeness": "incomplete",
            "diagnosis": "redundant_optional_theme",
            "recovery_action": "replan",
        }
    )
    revised_coverage = _theme_coverage_response(
        candidates,
        ["f1", "f3"],
        covered_evidence_ids={"f1", "f3"},
        theme_names=["Theme 1", "Theme 3"],
    )
    revised_coverage["original_essential_obligation_assessments"] = [
        {
            "theme": "Theme 1",
            "evidence_ids": [f"verified-fact:{candidates[0]['id']}"],
            "status": "covered",
            "supporting_insight_ids": [candidates[0]["id"]],
            "explanation": "The original essential proposition remains developed.",
        }
    ]
    responses["editorial_theme_coverage"] = [initial_coverage, revised_coverage]
    openai_client = FakeOpenAI(responses)
    prompt_client = CapturingPromptClient()

    payload = generate_artifacts(
        report_id="verified-replan-current-plan",
        report_name="Verified replan current plan",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="s" * 64
        ),
    )

    coverage_variables = [
        call["variables"]
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/editorial_theme_coverage/user"
    ]
    assert len(coverage_variables) == 2
    accepted_plan = coverage_variables[-1]["editorial_plan_json"]
    assert '"Theme 3"' in accepted_plan
    assert '"verified-fact:insight-f3-0.97"' in accepted_plan
    assert '"Theme 2"' not in accepted_plan
    assert payload["editorial_plan"]["themes"][1]["theme"] == "Theme 3"
