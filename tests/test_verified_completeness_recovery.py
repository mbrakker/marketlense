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
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import _verified_admission
from tests.test_verified_claims_visual_authority_snapshot_integrity import (
    _generation_responses,
    _theme_coverage_response,
)


def test_verified_generation_repairs_completeness_only_failure_without_omitted_themes(
    tmp_path,
):
    candidates = [
        _insight("f1", score=0.99, text="The first decision signal is material."),
        _insight("f2", score=0.98, text="The second decision signal is material."),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
    ]
    final = [
        {
            **deepcopy(candidate),
            "evidence_id": f"verified-fact:{candidate['id']}",
            "evidence_spans": [],
        }
        for candidate in candidates
    ]
    repaired = deepcopy(final)
    repaired[0]["text"] = "The first signal is material for near-term planning."
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = [
        {"insights_final": final},
        {"insights_final": [repaired[0]]},
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    incomplete = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
    )
    incomplete.update(
        {
            "report_completeness": "incomplete",
            "diagnosis": "material_report_completeness",
            "recovery_action": "targeted_rewrite",
        }
    )
    responses["editorial_theme_coverage"] = [
        incomplete,
        _theme_coverage_response(
            candidates,
            ["f1", "f2"],
            covered_evidence_ids={"f1", "f2"},
        ),
    ]
    openai_client = FakeOpenAI(responses)

    payload = generate_artifacts(
        report_id="verified-completeness-only-repair",
        report_name="Verified completeness-only repair",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="z" * 64
        ),
    )

    assert (
        len(
            [
                request
                for request in openai_client.requests
                if request[2] == "insights_final"
            ]
        )
        == 2
    )
    assert payload["insights_final"][0]["text"] == repaired[0]["text"]
