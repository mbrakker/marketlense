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
    _verified_semantic_repair_focal_facts,
    generate_artifacts,
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


def test_material_gap_on_secondary_fact_targets_bound_existing_insight() -> None:
    candidate = _candidate("candidate-1", "f1")
    candidate["evidence_ids"] = ["verified-fact:f1", "verified-fact:f2"]
    alternative = _candidate("candidate-2", "f2")
    gap = {
        "verified_fact_ids": ["f2"],
        "evidence_ids": ["verified-fact:f2"],
        "final_insight_ids": ["candidate-1"],
        "explanation": "The second source-backed comparison is incomplete.",
    }
    plan = {
        "themes": [
            {
                "theme": "First finding",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": ["candidate-1"],
            }
        ]
    }
    assessment = {
        "theme_coverage": [
            {
                "theme": "First finding",
                "status": "covered",
                "supporting_insight_ids": ["candidate-1"],
            }
        ],
        "diagnosis": "material_report_comteness",
        "recovery_action": "targeted_rewrite",
    }
    scope = _build_semantic_repair_scope(
        editorial_plan=plan,
        assessment=assessment,
        error_context={"material_gaps": [gap]},
        current_insights=[candidate],
        candidate_insights=[candidate, alternative],
    )
    assert scope["mode"] == "targeted_rewrite"
    assert scope["targeted_insight_ids"] == ["candidate-1"]
    assert scope["allowed_addition_candidate_ids"] == ["candidate-2"]
    assert scope["authorized_evidence_ids"] == ["verified-fact:f1", "verified-fact:f2"]
    focal = _verified_semantic_repair_focal_facts(
        material_gaps=[gap],
        repair_scope=scope,
        verified_facts=[_fact("f2", "A second finding.", qualifier="Survey only.")],
        candidate_insights=[candidate, alternative],
        current_insights=[candidate],
    )
    assert [(item["fact_id"], item["evidence_id"]) for item in focal] == [
        ("f2", "verified-fact:f2")
    ]
    patch = {
        "insights_final": [
            {
                "id": "candidate-1",
                "text": "The source-backed comparison retains both findings.",
                "evidence_id": "verified-fact:f1",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
            }
        ]
    }
    _validate_scoped_insight_patch(
        patch, repair_scope=scope, candidate_insights=[candidate, alternative]
    )
    merged = _merge_scoped_insight_repair(
        current_insights=[candidate],
        repaired_insights=patch["insights_final"],
        raw_repaired_insights=patch["insights_final"],
        repair_scope=scope,
    )
    assert merged[0]["evidence_ids"] == ["verified-fact:f1", "verified-fact:f2"]
    bad_patch = deepcopy(patch)
    bad_patch["insights_final"][0]["evidence_ids"].append("verified-fact:f3")
    with pytest.raises(AppError):
        _validate_scoped_insight_patch(
            bad_patch, repair_scope=scope, candidate_insights=[candidate, alternative]
        )
    unrelated = {
        **gap,
        "verified_fact_ids": ["f3"],
        "evidence_ids": ["verified-fact:f3"],
    }
    unrelated_candidate = _candidate("candidate-3", "f3")
    rejected = _build_semantic_repair_scope(
        editorial_plan=plan,
        assessment=assessment,
        error_context={"material_gaps": [unrelated]},
        current_insights=[candidate],
        candidate_insights=[candidate, alternative, unrelated_candidate],
    )
    assert rejected["targeted_insight_ids"] == []
    assert rejected["authorized_candidate_ids"] == ["candidate-3"]


def test_theme_repair_scope_preserves_exact_evidence_identity() -> None:
    candidate = _candidate("candidate-1", "f1")
    scope = _build_semantic_repair_scope(
        editorial_plan={
            "themes": [
                {
                    "theme": "First finding",
                    "evidence_ids": ["verified-fact:f1"],
                    "feasible_candidate_ids": ["candidate-1"],
                }
            ]
        },
        assessment={
            "theme_coverage": [
                {
                    "theme": "First finding",
                    "status": "partial",
                    "supporting_insight_ids": ["candidate-1"],
                }
            ],
            "recovery_action": "targeted_rewrite",
        },
        error_context={},
        current_insights=[candidate],
        candidate_insights=[candidate],
    )
    assert scope["authorized_evidence_ids"] == ["verified-fact:f1"]
    assert scope["theme_scopes"][0]["evidence_ids"] == ["verified-fact:f1"]


@pytest.mark.parametrize("reverse", [False, True])
def test_multifact_repair_context_binds_each_fact_to_its_own_evidence(
    reverse: bool,
) -> None:
    candidates = [_candidate("candidate-1", "f1"), _candidate("candidate-2", "f2")]
    if reverse:
        candidates.reverse()
    facts = [
        _fact("f1", "First fact.", qualifier=""),
        _fact("f2", "Second fact.", qualifier=""),
    ]
    focal = _verified_semantic_repair_focal_facts(
        material_gaps=[
            {
                "verified_fact_ids": ["f1", "f2"],
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "final_insight_ids": ["candidate-1", "candidate-2"],
                "explanation": "Both facts need complete treatment.",
            }
        ],
        repair_scope={"authorized_candidate_ids": ["candidate-1", "candidate-2"]},
        verified_facts=facts,
        candidate_insights=candidates,
        current_insights=candidates,
    )
    assert [
        (item["fact_id"], item["evidence_id"], item["authorized_candidate_ids"])
        for item in focal
    ] == [
        ("f1", "verified-fact:f1", ["candidate-1"]),
        ("f2", "verified-fact:f2", ["candidate-2"]),
    ]


def test_multifact_repair_context_retains_explicit_secondary_fact_binding() -> None:
    candidate = _candidate("candidate-1", "f1")
    candidate["evidence_ids"].append("verified-fact:f2")
    focal = _verified_semantic_repair_focal_facts(
        material_gaps=[
            {
                "verified_fact_ids": ["f2"],
                "evidence_ids": ["verified-fact:f2"],
                "final_insight_ids": ["candidate-1"],
                "explanation": "The secondary proposition is missing.",
            }
        ],
        repair_scope={"authorized_candidate_ids": ["candidate-1"]},
        verified_facts=[_fact("f2", "Second fact.", qualifier="")],
        candidate_insights=[candidate],
        current_insights=[candidate],
    )
    assert [
        (item["evidence_id"], item["authorized_candidate_ids"]) for item in focal
    ] == [("verified-fact:f2", ["candidate-1"])]


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
    assert "candidate-shaped entries containing scores" in full_prompt
    assert "candidate-shaped entries containing scores" not in scoped_prompt


def test_final_insight_prompt_does_not_allow_null_optional_arrays() -> None:
    prompt = _render_final_insight_user_prompt().lower()

    assert "optional fields that are not available must be omitted" in prompt
    assert "never set to null" in prompt
    assert "optional array is present" in prompt
