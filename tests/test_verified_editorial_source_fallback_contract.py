from __future__ import annotations

from copy import deepcopy

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
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
    _verified_generation_responses,
)
from tests.test_verified_claims_visual_authority_canary import _verified_admission


def test_verified_generation_fails_closed_without_source_bound_editorial_fallback(
    tmp_path,
):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
    ]
    narrow_final = [
        {
            **deepcopy(candidates[0]),
            "evidence_id": f"verified-fact:{candidates[0]['id']}",
        },
        {
            **deepcopy(candidates[1]),
            "evidence_id": f"verified-fact:{candidates[1]['id']}",
            "text": "A narrow detail from the second signal.",
        },
        *[
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
            }
            for candidate in candidates[2:]
        ],
    ]
    responses = _verified_generation_responses(
        candidates, plan_evidence_ids=["f2", "f1"]
    )
    responses["insights_final"] = [
        {"insights_final": narrow_final},
        {
            "insights_final": [
                {
                    **deepcopy(narrow_final[1]),
                    "text": "The second signal remains too narrow.",
                }
            ]
        },
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[1]['id']}"
    )
    failed_coverage = {
        "theme_coverage": [
            {
                "theme": "Theme 1",
                "status": "uncovered",
                "resolution": "unresolved",
                "supporting_insight_ids": [],
                "explanation": "The central theme is not developed.",
            },
            {
                "theme": "Theme 2",
                "status": "covered",
                "resolution": "retained",
                "supporting_insight_ids": [candidates[0]["id"]],
                "explanation": "The second theme is developed.",
            },
        ],
        "report_completeness": "incomplete",
        "diagnosis": "material_report_completeness",
        "recovery_action": "targeted_rewrite",
    }
    responses["editorial_theme_coverage"] = [failed_coverage, failed_coverage]
    openai_client = FakeOpenAI(responses)

    with pytest.raises(AppError, match="omitted an essential theme") as error:
        generate_artifacts(
            report_id="verified-semantic-theme-source-fallback",
            report_name="Verified semantic theme source fallback",
            doc_map=_doc_map(5),
            evidence_packs=_generation_evidence(5),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=openai_client,
            prompt_client=CapturingPromptClient(),
            analysis_store=FakeAnalysisStore(),
            visual_authority_admitter=lambda shortlisted: _verified_admission(
                shortlisted, digest="y" * 64
            ),
        )

    assert error.value.context["semantic_theme_repair"]["status"] == (
        "blocked_incomplete_roster"
    )
    assert (
        len(
            [
                request
                for request in openai_client.requests
                if request[2] == "editorial_theme_coverage"
            ]
        )
        == 2
    )
