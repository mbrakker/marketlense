from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.artifact_normalization import select_artifact_insights
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
    _generation_responses,
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import _verified_admission


def test_verified_selection_keeps_authoritative_composite_for_named_subset() -> None:
    candidate_metric = {
        "label": "AI initiative impact",
        "value": "44% promising; 42% limited; 13% transformational; 2% disappointing",
        "unit": "percent",
        "timeframe": "Impact so far",
        "segment": "Q11 respondents",
        "observations": [
            {"label": "Promising", "value": "44%", "unit": "percent"},
            {"label": "Limited", "value": "42%", "unit": "percent"},
            {"label": "Transformational", "value": "13%", "unit": "percent"},
            {"label": "Disappointing", "value": "2%", "unit": "percent"},
        ],
    }
    candidate = {
        "id": "ai-initiative-impact",
        "text": "The complete retained AI-initiative impact fact.",
        "evidence_id": "verified-fact:ai-initiative-impact",
        "evidence": "The source reports the complete adjective distribution.",
        "pages": [33],
        "metric": candidate_metric,
        "verified_fact": {
            "fact_id": "ai-initiative-impact",
            "statement": "The complete retained AI-initiative impact fact.",
            "metric": candidate_metric,
        },
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ai-initiative-impact",
                "text": (
                    "Promising (44%) and limited (42%) were the leading assessments."
                ),
                "evidence_id": "editorial-only",
                "metric": {
                    "label": "AI initiative impact",
                    "value": "44% promising; 42% limited",
                    "unit": "percent",
                    "timeframe": "Impact so far",
                    "segment": "Q11 respondents",
                },
            }
        ],
        candidate_insights=[candidate],
        editorial_plan={
            "report_thesis": "The admitted survey fact remains authoritative.",
            "themes": [
                {
                    "theme": "AI initiative outcomes",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ai-initiative-impact"],
                },
                {
                    "theme": "Reported distribution",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ai-initiative-impact"],
                },
            ],
        },
        require_final_candidate_lineage=True,
        verified_mode=True,
    )

    assert selected[0]["text"].startswith("Promising")
    assert selected[0]["evidence_id"] == candidate["evidence_id"]
    assert selected[0]["metric"]["label"] == candidate_metric["label"]
    assert selected[0]["metric"]["value"] == candidate_metric["value"]
    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_authoritative_plan_is_generated_from_admitted_facts(tmp_path):
    candidates = [_insight(f"f{i}", score=1.0 - i / 100) for i in range(1, 6)]
    admission = _verified_admission(candidates, digest="v" * 64)
    theme_specs = [
        (
            "Verified proposition 1",
            ["verified-fact:insight-f1-0.99", "verified-fact:insight-f2-0.98"],
        ),
        ("Verified proposition 2", ["verified-fact:insight-f1-0.99"]),
        ("Verified proposition 3", ["verified-fact:insight-f3-0.97"]),
        ("Verified proposition 4", ["verified-fact:insight-f4-0.96"]),
        ("Verified proposition 5", ["verified-fact:insight-f5-0.95"]),
    ]
    discovery_plan = _generation_responses(
        candidates,
        plan_evidence_ids=[f"f{i}" for i in range(1, 6)],
    )["editorial_plan"]
    verified_plan = {
        "editorial_plan": {
            "report_thesis": "Verified findings define five distinct decision signals.",
            "themes": [
                {
                    "theme": theme,
                    "priority": i,
                    "evidence_ids": evidence_ids,
                }
                for i, (theme, evidence_ids) in enumerate(theme_specs, start=1)
            ],
        }
    }
    responses = _generation_responses(
        candidates,
        plan_evidence_ids=[f"f{i}" for i in range(1, 6)],
    )
    responses["editorial_plan"] = [discovery_plan, verified_plan]
    responses["insights_final"] = {
        "insights_final": deepcopy(admission.admitted_candidates)
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[0]['id']}"
    )
    responses["editorial_theme_coverage"] = {
        "theme_coverage": [
            {
                "theme": theme,
                "status": "covered",
                "supporting_insight_ids": [candidates[index]["id"]],
                "explanation": "The final wording develops the verified proposition.",
            }
            for index, (theme, _evidence_ids) in enumerate(theme_specs)
        ]
    }
    prompt_client = CapturingPromptClient()

    payload = generate_artifacts(
        report_id="verified-authoritative-plan",
        report_name="Verified authoritative plan",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda _shortlisted: admission,
    )

    plan_calls = [
        call
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/editorial_plan/system"
    ]
    assert len(plan_calls) == 2
    verified_variables = plan_calls[1]["variables"]
    assert verified_variables["editorial_plan_phase"] == "verified_facts"
    assert json.loads(verified_variables["canonical_evidence_ids_json"]) == [
        f"verified-fact:{candidate['id']}" for candidate in candidates
    ]
    assert (
        json.loads(verified_variables["verified_facts_json"])
        == admission.verified_facts
    )
    verified_evidence = json.loads(verified_variables["evidence_json"])
    assert [finding["id"] for finding in verified_evidence["findings"]["findings"]] == [
        f"verified-fact:{candidate['id']}" for candidate in candidates
    ]
    assert [theme["evidence_ids"] for theme in payload["editorial_plan"]["themes"]] == [
        evidence_ids for _theme, evidence_ids in theme_specs
    ]


def test_verified_authoritative_plan_rejects_unknown_fact_ids(tmp_path):
    candidates = [_insight(f"f{i}", score=1.0 - i / 100) for i in range(1, 6)]
    responses = _generation_responses(
        candidates,
        plan_evidence_ids=[f"f{i}" for i in range(1, 6)],
    )
    discovery_plan = deepcopy(responses["editorial_plan"])
    invalid_plan = deepcopy(discovery_plan)
    invalid_plan["editorial_plan"]["themes"][0]["evidence_ids"] = [
        "verified-fact:not-admitted"
    ]
    responses["editorial_plan"] = [
        discovery_plan,
        invalid_plan,
        invalid_plan,
        invalid_plan,
    ]

    with pytest.raises(AppError) as error:
        generate_artifacts(
            report_id="verified-authoritative-plan-unknown-id",
            report_name="Verified authoritative plan unknown ID",
            doc_map=_doc_map(5),
            evidence_packs=_generation_evidence(5),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=FakeOpenAI(responses),
            prompt_client=CapturingPromptClient(),
            analysis_store=FakeAnalysisStore(),
            visual_authority_admitter=lambda shortlisted: _verified_admission(
                shortlisted, digest="z" * 64
            ),
        )

    assert error.value.code == "artifact_structured_output_invalid"
    assert error.value.context["artifact_family"] == "editorial_plan"
