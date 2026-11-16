from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.generators._artifact_generator.generation import (
    _build_semantic_repair_scope,
    _merge_scoped_insight_repair,
    _validate_scoped_insight_patch,
    _verified_editorial_obligation_context,
    generate_artifacts,
)
from src.generators.artifact_normalization import (
    validate_substantive_editorial_theme_coverage,
)
from src.services.prompt_service import load_prompt_set, render_prompt
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


def _candidate(candidate_id: str, fact_id: str, *, score: float = 0.9) -> dict:
    evidence_id = f"verified-fact:{fact_id}"
    return {
        "id": candidate_id,
        "text": f"Source finding for {fact_id}.",
        "evidence_id": evidence_id,
        "evidence_ids": [evidence_id],
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
            "observations": [{"cohort": "all buyers", "value": "42%"}],
        },
        "score": score,
        "verified_fact_id": fact_id,
    }


def _fact(fact_id: str, statement: str, *, qualifier: str) -> dict:
    return {
        "fact_id": fact_id,
        "statement": statement,
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
            "observations": [
                {"cohort": "all buyers", "value": "42%"},
                {"cohort": "repeat buyers", "value": "58%"},
            ],
        },
        "qualifiers": [qualifier],
    }


def _plan() -> dict:
    return {
        "themes": [
            {
                "theme": "Demand comparison",
                "importance": "essential",
                "coverage_obligation": (
                    "Develop both populations and preserve the directional comparison."
                ),
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "feasible_candidate_ids": ["candidate-1", "candidate-2"],
                "merge_group": "demand",
            },
            {
                "theme": "Qualified signal",
                "importance": "essential",
                "coverage_obligation": "Retain the conditional source limitation.",
                "evidence_ids": ["verified-fact:f3"],
                "feasible_candidate_ids": ["candidate-3"],
                "merge_group": "",
            },
            {
                "theme": "Optional context",
                "importance": "optional",
                "coverage_obligation": "Use only if distinct.",
                "evidence_ids": ["verified-fact:f4"],
                "feasible_candidate_ids": ["candidate-4"],
                "merge_group": "",
            },
        ]
    }


def test_verified_obligations_bind_complete_essential_source_context() -> None:
    candidates = [_candidate("candidate-1", "f1"), _candidate("candidate-2", "f2")]
    facts = [
        _fact(
            "f1",
            "All buyers reached 42%; repeat buyers reached 58%.",
            qualifier="Survey estimates exclude non-respondents.",
        ),
        _fact(
            "f2",
            "A second population moved in the opposite direction.",
            qualifier="Observed only in 2026.",
        ),
    ]

    context = _verified_editorial_obligation_context(_plan(), candidates, facts)

    assert [theme["theme"] for theme in context["themes"]] == [
        "Demand comparison",
        "Qualified signal",
        "Optional context",
    ]
    demand = context["themes"][0]
    assert demand["coverage_obligation"].startswith("Develop both populations")
    assert demand["evidence_ids"] == ["verified-fact:f1", "verified-fact:f2"]
    assert demand["feasible_candidate_ids"] == ["candidate-1", "candidate-2"]
    assert context["authoritative_facts"][0]["qualifiers"] == [
        "Survey estimates exclude non-respondents."
    ]
    assert (
        context["authoritative_facts"][0]["metric"]["observations"][1]["cohort"]
        == "repeat buyers"
    )


def test_verified_first_pass_prompt_receives_executable_obligations(tmp_path) -> None:
    candidates = [
        _insight(f"f{index}", score=1.0 - index / 100) for index in range(1, 6)
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
            }
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
    )
    prompt_client = CapturingPromptClient()

    generate_artifacts(
        report_id="verified-editorial-obligation-prompt",
        report_name="Verified editorial obligation prompt",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="o" * 64
        ),
    )

    final_variables = [
        call["variables"]
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/insights_final/user"
    ][0]
    obligations = json.loads(final_variables["verified_editorial_obligations_json"])
    assert obligations["themes"]
    assert all(theme["coverage_obligation"] for theme in obligations["themes"])
    assert all(theme["feasible_candidate_ids"] for theme in obligations["themes"])


def test_verified_first_pass_prompt_requires_complete_factual_propositions() -> None:
    full_prompt = _render_final_insight_user_prompt(
        verified_editorial_obligations_json=json.dumps(
            {
                "themes": [
                    {
                        "theme": "Demand comparison",
                        "coverage_obligation": (
                            "Develop both populations and direction."
                        ),
                        "feasible_candidate_ids": ["candidate-1"],
                        "evidence_ids": ["verified-fact:f1"],
                    }
                ],
                "authoritative_facts": [
                    {
                        "fact_id": "f1",
                        "statement": (
                            "All buyers reached 42%; repeat buyers reached 58%."
                        ),
                        "metric": {
                            "value": "42%",
                            "observations": [{"cohort": "all buyers"}],
                        },
                        "qualifiers": ["Survey estimates exclude non-respondents."],
                    }
                ],
            }
        )
    )
    legacy_prompt = _render_final_insight_user_prompt(verified_mode=False)

    assert "complete source-backed proposition" in full_prompt
    assert "factual proposition" in full_prompt
    assert "authoritative checklist" in full_prompt
    assert "text" in full_prompt and "so_what" in full_prompt
    assert "metric_public_copy" in full_prompt
    assert "Before returning JSON" in full_prompt
    assert "do not force one insight per theme" in full_prompt
    assert "additional distinct admitted candidate-backed insight" in full_prompt
    assert "18 words or fewer" not in full_prompt
    assert "empty string for the primary ID" not in full_prompt
    assert "18 words or fewer" in legacy_prompt
    assert "empty string for the primary ID" in legacy_prompt


def test_scoped_prompt_exposes_only_focal_verified_fact_context() -> None:
    focal_context = [
        {
            "fact_id": "f2",
            "statement": "Repeat buyers reached 58% while all buyers reached 42%.",
            "metric": {
                "value": "58%",
                "unit": "%",
                "observations": [{"cohort": "repeat buyers", "value": "58%"}],
            },
            "qualifiers": ["Survey estimates exclude non-respondents."],
            "evidence_id": "verified-fact:f2",
            "authorized_candidate_ids": ["candidate-2"],
            "affected_final_insight_ids": ["candidate-1"],
            "gap_explanation": "The second population is absent from the proposition.",
        }
    ]
    prompt = _render_final_insight_user_prompt(
        semantic_theme_repair_scope_json=json.dumps(
            {
                "mode": "targeted_rewrite",
                "authorized_candidate_ids": ["candidate-1", "candidate-2"],
            }
        ),
        semantic_theme_allowed_patch_ids_json='["candidate-1", "candidate-2"]',
        semantic_theme_focal_facts_json=json.dumps(focal_context),
        semantic_theme_coverage_feedback_json='{"diagnosis":"planned_theme_execution"}',
    )

    assert "Focal verified-fact repair context JSON" in prompt
    assert "Repeat buyers reached 58%" in prompt
    assert "Survey estimates exclude non-respondents." in prompt
    assert "candidate-2" in prompt
    assert "The second population is absent" in prompt
    assert "exact material proposition" in prompt
    assert "Executable verified editorial obligations JSON" not in prompt


def test_partial_repair_scope_replaces_only_the_authorized_existing_entry() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    current = [
        {
            "id": "candidate-1",
            "text": "Incomplete comparison.",
            "evidence_id": "verified-fact:f1",
        },
        {
            "id": "candidate-3",
            "text": "Unaffected qualifier.",
            "evidence_id": "verified-fact:f3",
        },
    ]
    assessment = {
        "theme_coverage": [
            {
                "theme": "Demand comparison",
                "status": "partial",
                "supporting_insight_ids": ["candidate-1"],
                "explanation": "The comparison is incomplete.",
            }
        ],
        "diagnosis": "planned_theme_execution",
        "recovery_action": "targeted_rewrite",
    }
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment=assessment,
        error_context={
            "material_gaps": [
                {
                    "verified_fact_ids": ["f1"],
                    "evidence_ids": ["verified-fact:f1"],
                    "final_insight_ids": ["candidate-1"],
                    "explanation": "The comparison is incomplete.",
                }
            ]
        },
        current_insights=current,
        candidate_insights=candidates,
    )
    patch = [
        {
            **deepcopy(current[0]),
            "text": (
                "The two populations move in opposite directions, changing the "
                "planning choice."
            ),
        }
    ]

    _validate_scoped_insight_patch(
        {"insights_final": patch},
        repair_scope=scope,
        candidate_insights=candidates,
    )
    merged = _merge_scoped_insight_repair(
        current_insights=current,
        repaired_insights=patch,
        repair_scope=scope,
    )

    assert [item["id"] for item in merged] == ["candidate-1", "candidate-3"]
    assert merged[0]["text"].startswith("The two populations")
    assert merged[1] == current[1]


def test_localized_repair_keeps_complete_family_materialization_and_audits_patch(
    tmp_path,
) -> None:
    candidates = [
        _insight(f"f{index}", score=1.0 - index / 100) for index in range(1, 6)
    ]
    initial = [
        {
            **deepcopy(candidate),
            "evidence_id": f"verified-fact:{candidate['id']}",
        }
        for candidate in candidates
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])
    responses["insights_final"] = [
        {"insights_final": initial},
        {
            "insights_final": [
                {
                    **deepcopy(initial[1]),
                    "text": (
                        "The second source signal is developed without changing the "
                        "rest."
                    ),
                }
            ]
        },
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f2-0.98"
    )
    responses["editorial_theme_coverage"] = [
        _theme_coverage_response(
            candidates,
            ["f2", "f1"],
            covered_evidence_ids={"f1"},
        ),
        _theme_coverage_response(
            candidates,
            ["f2", "f1"],
            covered_evidence_ids={"f1", "f2"},
        ),
    ]
    responses["editorial_theme_coverage"][0]["material_gaps"] = [
        {
            "verified_fact_ids": [initial[1]["id"]],
            "evidence_ids": [f"verified-fact:{initial[1]['id']}"],
            "final_insight_ids": [initial[1]["id"]],
            "explanation": "The second source proposition is not developed.",
        }
    ]
    prompt_client = CapturingPromptClient()
    payload = generate_artifacts(
        report_id="verified-transient-editorial-repair",
        report_name="Verified transient editorial repair",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="t" * 64
        ),
    )

    family = "report_vs/artifacts/insights_final"
    cached_family = payload["_cache"]["family_outputs"][family]
    final_by_id = {item["id"]: item for item in payload["insights_final"]}
    assert cached_family[1]["text"] != final_by_id[cached_family[1]["id"]]["text"]
    repair = payload["_cache"]["candidate_generation"]["editorial_plan_coverage"][
        "final_selected_theme_coverage"
    ]["semantic_repair"]
    assert repair["transient_prompt_identity"]
    assert repair["transient_family_reuse"]["regeneration_reason"] == (
        "transient_repair_no_reuse"
    )
    final_calls = [
        call
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/insights_final/user"
    ]
    assert len(final_calls) == 2
    repair_variables = final_calls[-1]["variables"]
    authorized_ids = json.loads(
        repair_variables["final_insight_allowed_candidate_ids_json"]
    )
    repair_candidates = json.loads(repair_variables["insights_candidates_json"])
    focal_facts = json.loads(repair_variables["semantic_theme_focal_facts_json"])
    assert authorized_ids == json.loads(
        repair_variables["semantic_theme_allowed_patch_ids_json"]
    )
    assert {item["id"] for item in repair_candidates} <= set(authorized_ids)
    assert [item["fact_id"] for item in focal_facts] == [initial[1]["id"]]
    assert focal_facts[0]["authorized_candidate_ids"] == [initial[1]["id"]]
    assert repair_variables["verified_editorial_obligations_json"] == ""
    assert repair_variables["current_insights_final_json"] == ""
    assert [
        item["id"]
        for item in json.loads(
            repair_variables["semantic_theme_targeted_insights_json"]
        )
    ] == [initial[1]["id"]]


def test_uncovered_theme_empty_supporting_ids_authorizes_feasible_addition() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    current = [
        {
            "id": "candidate-1",
            "text": "Existing insight.",
            "evidence_id": "verified-fact:f1",
        }
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Qualified signal",
                    "status": "uncovered",
                    "supporting_insight_ids": [],
                    "explanation": "No final entry develops the limitation.",
                }
            ],
            "diagnosis": "material_report_completeness",
            "recovery_action": "targeted_rewrite",
        },
        error_context={},
        current_insights=current,
        candidate_insights=candidates,
    )
    patch = [
        {
            "id": "candidate-3",
            "text": "The qualified signal remains limited to the observed segment.",
            "evidence_id": "verified-fact:f3",
        }
    ]

    assert scope["targeted_insight_ids"] == []
    assert scope["allowed_addition_candidate_ids"] == ["candidate-3"]
    _validate_scoped_insight_patch(
        {"insights_final": patch},
        repair_scope=scope,
        candidate_insights=candidates,
    )
    merged = _merge_scoped_insight_repair(
        current_insights=current,
        repaired_insights=patch,
        repair_scope=scope,
    )
    assert [item["id"] for item in merged] == ["candidate-1", "candidate-3"]


@pytest.mark.parametrize(
    "patch",
    [
        [
            {
                "id": "candidate-4",
                "text": "Unrelated.",
                "evidence_id": "verified-fact:f4",
            }
        ],
        [{"id": "unknown", "text": "Unknown.", "evidence_id": "verified-fact:f1"}],
        [
            {"id": "candidate-1", "text": "First.", "evidence_id": "verified-fact:f1"},
            {
                "id": "candidate-1",
                "text": "Duplicate.",
                "evidence_id": "verified-fact:f1",
            },
        ],
        [
            {
                "id": "candidate-1",
                "text": "Wrong binding.",
                "evidence_id": "verified-fact:f2",
            }
        ],
    ],
)
def test_scoped_repair_rejects_unauthorized_patch_without_merging(
    patch: list[dict],
) -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    current = [
        {"id": "candidate-1", "text": "Incomplete.", "evidence_id": "verified-fact:f1"}
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Demand comparison",
                    "status": "partial",
                    "supporting_insight_ids": ["candidate-1"],
                    "explanation": "Incomplete.",
                }
            ],
            "diagnosis": "planned_theme_execution",
            "recovery_action": "targeted_rewrite",
        },
        error_context={},
        current_insights=current,
        candidate_insights=candidates,
    )

    with pytest.raises(AppError):
        _validate_scoped_insight_patch(
            {"insights_final": patch},
            repair_scope=scope,
            candidate_insights=candidates,
        )
    assert current == [
        {"id": "candidate-1", "text": "Incomplete.", "evidence_id": "verified-fact:f1"}
    ]


def test_scoped_repair_does_not_accept_an_empty_removal_patch() -> None:
    current = [
        {
            "id": "candidate-1",
            "text": "Incomplete.",
            "evidence_id": "verified-fact:f1",
        }
    ]
    scope = {
        "targeted_insight_ids": ["candidate-1"],
        "allowed_addition_candidate_ids": [],
    }

    with pytest.raises(AppError):
        _merge_scoped_insight_repair(
            current_insights=current,
            repaired_insights=[],
            repair_scope=scope,
        )
    assert current[0]["text"] == "Incomplete."


def test_missing_material_qualifier_remains_a_semantic_repair_gap() -> None:
    plan = {
        "material_limitation_evidence_ids": [],
        "themes": [
            {
                "theme": "Qualified signal",
                "importance": "essential",
                "coverage_obligation": "Retain the source limitation.",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": ["candidate-1"],
            }
        ],
    }
    candidates = [
        {
            "id": "candidate-1",
            "evidence_id": "verified-fact:f1",
            "verified_fact_id": "f1",
            "verified_fact": {
                "fact_id": "f1",
                "qualifiers": ["Only respondents were surveyed."],
            },
        }
    ]
    final_insights = [{"id": "candidate-1", "evidence_id": "verified-fact:f1"}]
    assessment = {
        "theme_coverage": [
            {
                "theme": "Qualified signal",
                "status": "covered",
                "supporting_insight_ids": ["candidate-1"],
                "explanation": "The source limitation is not developed.",
            }
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
        "material_gaps": [
            {
                "verified_fact_ids": ["f1"],
                "evidence_ids": ["verified-fact:f1"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The source qualifier is missing from the wording.",
            }
        ],
    }

    with pytest.raises(AppError, match="complete material-report"):
        validate_substantive_editorial_theme_coverage(
            payload=assessment,
            editorial_plan=plan,
            final_insights=final_insights,
            candidate_insights=candidates,
        )


def test_changed_scoped_wording_still_fails_when_material_gap_remains() -> None:
    plan = {
        "material_limitation_evidence_ids": [],
        "themes": [
            {
                "theme": "Qualified signal",
                "importance": "essential",
                "coverage_obligation": "Retain the source limitation.",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": ["candidate-1"],
            }
        ],
    }
    candidate = {
        "id": "candidate-1",
        "text": "A source-backed signal.",
        "evidence_id": "verified-fact:f1",
        "verified_fact_id": "f1",
        "verified_fact": {
            "fact_id": "f1",
            "statement": "The signal is present only among survey respondents.",
            "qualifiers": ["Only respondents were surveyed."],
        },
    }
    patch = {
        "theme_coverage": [
            {
                "theme": "Qualified signal",
                "status": "covered",
                "supporting_insight_ids": ["candidate-1"],
                "explanation": (
                    "The wording mentions the signal but not its limitation."
                ),
            }
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
        "material_gaps": [
            {
                "verified_fact_ids": ["f1"],
                "evidence_ids": ["verified-fact:f1"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The respondent-only limitation is still missing.",
            }
        ],
    }

    with pytest.raises(AppError, match="complete material-report"):
        validate_substantive_editorial_theme_coverage(
            payload=patch,
            editorial_plan=plan,
            final_insights=[
                {
                    "id": "candidate-1",
                    "text": "The signal matters for planning decisions.",
                    "evidence_id": "verified-fact:f1",
                }
            ],
            candidate_insights=[candidate],
        )


def test_evidence_insufficiency_never_enters_editorial_repair() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Qualified signal",
                    "status": "uncovered",
                    "supporting_insight_ids": [],
                    "explanation": "The source is insufficient.",
                }
            ],
            "diagnosis": "insufficient_evidence",
            "recovery_action": "quarantine",
        },
        error_context={
            "material_gaps": [
                {
                    "verified_fact_ids": ["f3"],
                    "evidence_ids": ["verified-fact:f3"],
                    "final_insight_ids": [],
                    "explanation": "No source support remains.",
                }
            ]
        },
        current_insights=[],
        candidate_insights=candidates,
    )

    assert scope["mode"] == "fail_closed"


def test_report_wide_failure_is_not_localized() -> None:
    candidates = [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [],
            "diagnosis": "infeasible_plan",
            "recovery_action": "replan",
        },
        error_context={},
        current_insights=[],
        candidate_insights=candidates,
    )
    assert scope["mode"] == "replan"


def _render_final_insight_user_prompt(**overrides: object) -> str:
    variables: dict[str, object] = {
        "insights_candidates_json": json.dumps(
            [
                {
                    "id": "candidate-1",
                    "text": "A source-backed qualified signal.",
                    "evidence_id": "verified-fact:f1",
                    "qualifiers": ["Survey excludes non-respondents."],
                }
            ]
        ),
        "current_insights_final_json": "[]",
        "semantic_theme_targeted_insight_ids_json": "[]",
        "semantic_theme_targeted_insights_json": "[]",
        "semantic_theme_repair_scope_json": "",
        "semantic_theme_focal_facts_json": "[]",
        "semantic_theme_allowed_patch_ids_json": "[]",
        "doc_map_json": "{}",
        "evidence_json": "{}",
        "editorial_plan_json": "{}",
        "verified_editorial_obligations_json": "",
        "semantic_theme_coverage_feedback_json": "",
        "final_insight_target_count": 3,
        "verified_mode": True,
        "final_insight_allowed_candidate_ids_json": '["candidate-1"]',
    }
    variables.update(overrides)
    ctx = _ctx()
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/insights_final",
            force_reload=True,
        ),
        ctx,
    )
    return render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        ctx,
    ).text


def test_scoped_final_prompt_omits_full_roster_requirements() -> None:
    full_prompt = _render_final_insight_user_prompt(
        verified_editorial_obligations_json='{"marker":"FULL_OBLIGATION_ONLY"}'
    )
    scoped_prompt = _render_final_insight_user_prompt(
        semantic_theme_repair_scope_json=json.dumps(
            {
                "theme_scopes": [
                    {
                        "theme": "Demand comparison",
                        "allowed_addition_candidate_ids": ["candidate-2"],
                    }
                ],
                "authorized_candidate_ids": ["candidate-1", "candidate-2"],
            }
        ),
        semantic_theme_allowed_patch_ids_json='["candidate-1", "candidate-2"]',
        semantic_theme_coverage_feedback_json='{"diagnosis":"planned_theme_execution"}',
        verified_editorial_obligations_json='{"marker":"FULL_OBLIGATION_ONLY"}',
    )

    assert "Minimum final insight target:" in full_prompt
    assert "Select at least" in full_prompt
    assert "every essential theme" in full_prompt
    assert "FULL_OBLIGATION_ONLY" in full_prompt
    assert "Survey excludes non-respondents." in full_prompt
    assert "candidate-1" in scoped_prompt
    assert "candidate-2" in scoped_prompt
    assert "This is a scoped patch" in scoped_prompt
    assert "FULL_OBLIGATION_ONLY" not in scoped_prompt
    assert "Minimum final insight target:" not in scoped_prompt
    assert "Select at least" not in scoped_prompt
    assert "every essential theme" not in scoped_prompt


def test_final_insight_prompt_does_not_allow_null_optional_arrays() -> None:
    prompt = _render_final_insight_user_prompt().lower()

    assert "optional fields that are not available must be omitted" in prompt
    assert "never set to null" in prompt
    assert "optional array is present" in prompt


def _partial_scope(
    *,
    material_gaps: list[dict] | None,
    candidate_insights: list[dict] | None = None,
) -> dict:
    candidates = candidate_insights or [
        _candidate(f"candidate-{index}", f"f{index}") for index in range(1, 5)
    ]
    return _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Demand comparison",
                    "status": "partial",
                    "supporting_insight_ids": ["candidate-1"],
                    "explanation": "The second population is not developed.",
                }
            ],
            "diagnosis": "planned_theme_execution",
            "recovery_action": "targeted_rewrite",
        },
        error_context={"material_gaps": material_gaps or []},
        current_insights=[
            {
                "id": "candidate-1",
                "text": "Existing first population insight.",
                "evidence_id": "verified-fact:f1",
            }
        ],
        candidate_insights=candidates,
    )


def test_partial_theme_gap_authorizes_exactly_matching_feasible_addition() -> None:
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ]
    )

    assert scope["allowed_addition_candidate_ids"] == ["candidate-2"]
    assert scope["authorized_candidate_ids"] == ["candidate-1", "candidate-2"]


@pytest.mark.parametrize(
    "material_gaps",
    [
        [
            {
                "verified_fact_ids": ["f9"],
                "evidence_ids": ["verified-fact:f9"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "No matching candidate exists.",
            }
        ],
        [
            {
                "verified_fact_ids": ["f1"],
                "evidence_ids": ["verified-fact:f1"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The existing fact is incomplete.",
            }
        ],
        [],
    ],
)
def test_partial_theme_does_not_authorize_unbound_or_redundant_additions(
    material_gaps: list[dict],
) -> None:
    scope = _partial_scope(material_gaps=material_gaps)

    assert scope["allowed_addition_candidate_ids"] == []
    assert scope["authorized_candidate_ids"] == ["candidate-1"]


def test_partial_theme_rejects_candidate_with_unrelated_exact_binding() -> None:
    candidates = [
        _candidate("candidate-1", "f1"),
        _candidate("candidate-2", "f3"),
    ]
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ],
        candidate_insights=candidates,
    )

    assert scope["allowed_addition_candidate_ids"] == []


def test_partial_theme_authorized_addition_merges_without_mutating_current_roster() -> (
    None
):
    candidates = [_candidate("candidate-1", "f1"), _candidate("candidate-2", "f2")]
    scope = _partial_scope(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The second population is missing.",
            }
        ],
        candidate_insights=candidates,
    )
    patch = [
        {
            "id": "candidate-2",
            "text": "The second population moves in the opposite direction.",
            "evidence_id": "verified-fact:f2",
        }
    ]

    _validate_scoped_insight_patch(
        {"insights_final": patch},
        repair_scope=scope,
        candidate_insights=candidates,
    )
    merged = _merge_scoped_insight_repair(
        current_insights=[
            {
                "id": "candidate-1",
                "text": "Existing first population insight.",
                "evidence_id": "verified-fact:f1",
            }
        ],
        repaired_insights=patch,
        repair_scope=scope,
    )

    assert [item["id"] for item in merged] == ["candidate-1", "candidate-2"]
