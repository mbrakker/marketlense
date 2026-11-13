import json

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.generators._artifact_generator.generation import (
    _build_semantic_repair_scope,
    _verified_editorial_obligation_context,
    generate_artifacts,
)
from src.generators.validation.grounding import _grounding_batches
from src.services.prompt_service import load_prompt_set, render_prompt
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


def _candidate(candidate_id: str, fact_id: str) -> dict:
    evidence_id = f"verified-fact:{fact_id}"
    return {
        "id": candidate_id,
        "text": f"Finding for {fact_id}.",
        "evidence_id": evidence_id,
        "evidence_ids": [evidence_id],
        "verified_fact_id": fact_id,
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
        },
        "score": 0.9,
    }


def _fact(fact_id: str, statement: str) -> dict:
    return {
        "fact_id": fact_id,
        "statement": statement,
        "metric": {
            "label": f"Metric {fact_id}",
            "value": "42%",
            "unit": "%",
            "timeframe": "2026",
        },
        "qualifiers": [f"Qualifier for {fact_id}"],
    }


def _plan() -> dict:
    return {
        "themes": [
            {
                "theme": "Essential finding",
                "importance": "essential",
                "coverage_obligation": "Develop the selected finding.",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "feasible_candidate_ids": ["candidate-1", "candidate-2"],
                "merge_group": "",
            }
        ]
    }


def _render(namespace: str, variables: dict[str, object]) -> str:
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=namespace,
            force_reload=True,
        ),
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


def _render_system(namespace: str, variables: dict[str, object]) -> str:
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=namespace,
            force_reload=True,
        ),
        _ctx(),
    )
    return render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables=variables,
        ),
        _ctx(),
    ).text


def test_verified_obligations_include_distinct_admitted_facts_outside_themes() -> None:
    candidates = [
        _candidate("candidate-1", "f1"),
        _candidate("candidate-2", "f2"),
        _candidate("candidate-2-duplicate", "f2"),
    ]
    facts = [
        _fact("f1", "The planned finding is 42% in 2026."),
        _fact("f2", "The additional finding compares two populations."),
    ]

    plan = _plan()
    plan["themes"][0]["evidence_ids"] = ["verified-fact:f1"]
    plan["themes"][0]["feasible_candidate_ids"] = ["candidate-1"]
    context = _verified_editorial_obligation_context(plan, candidates, facts)

    assert context["additional_admitted_facts"] == [
        {
            "fact_id": "f2",
            "candidate_id": "candidate-2",
            "evidence_id": "verified-fact:f2",
            "statement": "The additional finding compares two populations.",
            "metric": facts[1]["metric"],
            "qualifiers": facts[1]["qualifiers"],
        }
    ]


def test_verified_full_prompt_explains_report_wide_fact_selection() -> None:
    prompt = _render(
        "report_vs/artifacts/insights_final",
        {
            "insights_candidates_json": "[]",
            "doc_map_json": "{}",
            "evidence_json": "{}",
            "editorial_plan_json": json.dumps(_plan()),
            "verified_mode": True,
            "final_insight_target_count": 2,
            "final_insight_allowed_candidate_ids_json": '["candidate-1"]',
            "verified_editorial_obligations_json": json.dumps(
                {
                    "themes": [],
                    "authoritative_facts": [],
                    "additional_admitted_facts": [
                        {
                            "fact_id": "f2",
                            "candidate_id": "candidate-2",
                            "evidence_id": "verified-fact:f2",
                            "statement": (
                                "The additional finding compares two populations."
                            ),
                        }
                    ],
                }
            ),
        },
    )

    assert "additional_admitted_facts" in prompt
    assert "do not include facts merely to increase the insight count" in prompt.lower()
    assert "minimum count is not a stopping criterion" in prompt
    assert "Do not select several candidates expressing the same proposition" in prompt


def test_verified_summary_receives_only_the_accepted_final_roster(tmp_path) -> None:
    candidates = [
        _insight(f"f{index}", score=1.0 - index / 100) for index in range(1, 7)
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {
                **candidate,
                "evidence_id": f"verified-fact:{candidate['id']}",
            }
            for candidate in candidates[:5]
        ]
    }
    responses["insights_final"]["insights_final"][0]["evidence_ids"] = [
        f"verified-fact:{candidates[0]['id']}",
        f"verified-fact:{candidates[1]['id']}",
    ]
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
        report_id="verified-summary-roster",
        report_name="Verified summary roster",
        doc_map=_doc_map(6),
        evidence_packs=_generation_evidence(6),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="s" * 64
        ),
    )

    summary_variables = [
        call["variables"]
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/summary/user"
    ][0]
    selected = json.loads(summary_variables["selected_final_insights_json"])
    assert summary_variables["verified_mode"] is True
    assert [item["id"] for item in selected] == [
        candidate["id"] for candidate in candidates[:5]
    ]
    assert all(
        set(item) <= {"id", "text", "evidence_id", "evidence_ids", "metric"}
        for item in selected
    )
    evidence = json.loads(summary_variables["evidence_json"])
    assert {
        fact["fact_id"] for fact in evidence["verified_facts"]["verified_facts"]
    } == {candidate["id"] for candidate in candidates[:5]}
    assert {
        finding["verified_fact_id"] for finding in evidence["findings"]["findings"]
    } == {candidate["id"] for candidate in candidates[:5]}
    assert evidence["findings"]["findings"][0]["source_identity"]


def test_verified_summary_prompt_uses_selected_final_roster_as_fact_boundary() -> None:
    prompt = _render(
        "report_vs/artifacts/summary",
        {
            "editorial_plan_json": "{}",
            "selected_lead_insight_json": "{}",
            "selected_final_insights_json": json.dumps(
                [
                    {
                        "id": "candidate-1",
                        "text": (
                            "Private-label demand reached 42% among surveyed buyers."
                        ),
                        "evidence_id": "verified-fact:private-label",
                        "evidence_ids": ["verified-fact:private-label"],
                        "metric": {"value": "42%", "population": "surveyed buyers"},
                    }
                ]
            ),
            "evidence_json": '{"canonical_verified_facts":{}}',
            "doc_map_json": "{}",
            "verified_mode": True,
        },
    ).lower()

    assert "selected_final_insights_json" in prompt
    assert "factual selection boundary" in prompt
    assert "do not introduce an unselected factual finding" in prompt
    assert "do not combine distinct findings" in prompt
    assert "enough `claim_evidence_map` entries" in prompt
    assert "keep 3-5 claim-map items" not in prompt


def test_verified_summary_compact_tldr_may_use_another_accepted_fact() -> None:
    prompt = _render(
        "report_vs/artifacts/summary",
        {
            "editorial_plan_json": "{}",
            "selected_lead_insight_json": json.dumps(
                {
                    "id": "lead",
                    "text": "The lead comparison requires a lengthy qualification.",
                    "evidence_id": "verified-fact:lead",
                }
            ),
            "selected_final_insights_json": json.dumps(
                [
                    {
                        "id": "lead",
                        "text": "The lead comparison requires a lengthy qualification.",
                        "evidence_id": "verified-fact:lead",
                    },
                    {
                        "id": "short",
                        "text": "Repeat buyers reached 42% adoption.",
                        "evidence_id": "verified-fact:short",
                    },
                ]
            ),
            "evidence_json": "{}",
            "doc_map_json": "{}",
            "verified_mode": True,
        },
    )

    assert "standard `tldr`" in prompt
    assert "another accepted final insight" in prompt
    assert "do not clip" in prompt.lower()


def test_verified_grounding_uses_smaller_batches_without_changing_legacy_limits() -> (
    None
):
    payload = {
        "retained_claims_to_ground": [
            {"item_id": f"claim-{index}", "evidence_ids": [f"f{index}"]}
            for index in range(3)
        ],
        "public_factual_items": [
            {"item_id": f"public-{index}", "evidence_ids": [f"f{index}"]}
            for index in range(5)
        ],
    }
    semantic_inputs = ["claim-0", "claim-1", "claim-2"]

    verified_batches = _grounding_batches(payload, semantic_inputs, verified_mode=True)
    legacy_batches = _grounding_batches(payload, semantic_inputs)

    assert [len(inputs) for _payload, inputs in verified_batches] == [2, 1]
    assert [
        len(batch_payload["public_factual_items"])
        for batch_payload, _inputs in verified_batches
    ] == [4, 1]
    assert len(legacy_batches) == 1
    assert len(legacy_batches[0][0]["public_factual_items"]) == 5


def test_grounding_recovery_prompt_requires_complete_batch_roster() -> None:
    variables = {"artifact_family": "validation_grounding"}
    for namespace in (
        "report_vs/structured_output/repair",
        "report_vs/structured_output/regenerate",
    ):
        prompt = " ".join(_render_system(namespace, variables).lower().split())
        assert "complete replacement verdict roster" in prompt
        assert "every exact item id" in prompt
        assert "complete protected-facts dimensions" in prompt


def test_material_gap_authorizes_planned_and_unplanned_candidates() -> None:
    candidates = [
        _candidate("candidate-1", "f1"),
        _candidate("candidate-2", "f2"),
        _candidate("candidate-3", "f3"),
    ]
    scope = _build_semantic_repair_scope(
        editorial_plan=_plan(),
        assessment={
            "theme_coverage": [
                {
                    "theme": "Essential finding",
                    "status": "covered",
                    "supporting_insight_ids": ["candidate-1"],
                    "explanation": "The planned finding is present.",
                }
            ],
            "report_completeness": "incomplete",
            "diagnosis": "material_report_completeness",
            "recovery_action": "targeted_rewrite",
        },
        error_context={
            "material_gaps": [
                {
                    "verified_fact_ids": ["f1", "f3"],
                    "evidence_ids": ["verified-fact:f1", "verified-fact:f3"],
                    "final_insight_ids": ["candidate-1"],
                    "explanation": "A report comparison is incomplete.",
                }
            ]
        },
        current_insights=[
            {
                "id": "candidate-1",
                "text": "The planned finding.",
                "evidence_id": "verified-fact:f1",
            }
        ],
        candidate_insights=candidates,
    )

    assert scope["mode"] == "targeted_rewrite"
    assert scope["targeted_insight_ids"] == ["candidate-1"]
    assert scope["allowed_addition_candidate_ids"] == ["candidate-3"]
    assert set(scope["authorized_candidate_ids"]) == {"candidate-1", "candidate-3"}
