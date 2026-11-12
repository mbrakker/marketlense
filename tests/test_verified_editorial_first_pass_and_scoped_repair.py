from __future__ import annotations

import json
from copy import deepcopy

import pytest

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
    payload = generate_artifacts(
        report_id="verified-transient-editorial-repair",
        report_name="Verified transient editorial repair",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
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
