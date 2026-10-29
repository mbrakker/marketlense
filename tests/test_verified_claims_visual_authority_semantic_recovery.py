from __future__ import annotations

from copy import deepcopy

from src.generators._artifact_generator.generation import generate_artifacts
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


def test_verified_semantic_recovery_replaces_selected_fact_with_admitted_alternative(
    tmp_path,
):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The selected central signal is narrow."),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
        _insight("f6", score=0.94, text="The alternative central signal is material."),
    ]
    discovery_plan = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])[
        "editorial_plan"
    ]
    verified_plan = {
        "editorial_plan": {
            "report_thesis": "The admitted findings define two decision signals.",
            "themes": [
                {
                    "theme": "Central signal",
                    "priority": 1,
                    "evidence_ids": [
                        "verified-fact:insight-f2-0.98",
                        "verified-fact:insight-f6-0.94",
                    ],
                },
                {
                    "theme": "Secondary signal",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:insight-f1-0.99"],
                },
            ],
        }
    }
    narrow_final = [
        {
            **deepcopy(candidate),
            "evidence_id": f"verified-fact:{candidate['id']}",
        }
        for candidate in candidates[:5]
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])
    responses["editorial_plan"] = [discovery_plan, verified_plan]
    responses["insights_final"] = [
        {"insights_final": narrow_final},
        {"insights_final": narrow_final},
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    failed_coverage = {
        "theme_coverage": [
            {
                "theme": "Central signal",
                "status": "uncovered",
                "supporting_insight_ids": [],
                "explanation": "The selected central wording is too narrow.",
            },
            {
                "theme": "Secondary signal",
                "status": "covered",
                "supporting_insight_ids": ["insight-f1-0.99"],
                "explanation": "The secondary signal is developed.",
            },
        ]
    }
    responses["editorial_theme_coverage"] = [
        failed_coverage,
        failed_coverage,
        {
            "theme_coverage": [
                {
                    "theme": "Central signal",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-f6-0.94"],
                    "explanation": (
                        "The admitted alternative develops the central signal."
                    ),
                },
                {
                    "theme": "Secondary signal",
                    "status": "covered",
                    "supporting_insight_ids": ["insight-f1-0.99"],
                    "explanation": "The secondary signal is developed.",
                },
            ]
        },
    ]

    payload = generate_artifacts(
        report_id="verified-semantic-theme-alternative-replacement",
        report_name="Verified semantic theme alternative replacement",
        doc_map=_doc_map(6),
        evidence_packs=_generation_evidence(6),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="a" * 64
        ),
    )

    assert [item["id"] for item in payload["insights_final"]] == [
        "insight-f1-0.99",
        "insight-f2-0.98",
        "insight-f3-0.97",
        "insight-f4-0.96",
        "insight-f6-0.94",
    ]
    assert (
        next(
            item["text"]
            for item in payload["insights_final"]
            if item["id"] == "insight-f6-0.94"
        )
        == "The alternative central signal is material."
    )
