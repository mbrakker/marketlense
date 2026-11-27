from copy import deepcopy
from hashlib import sha256

import pytest

from src.contracts.artifact_generation import EditorialCoverageChallengeResponse
from src.generators._artifact_generator.generation import generate_artifacts
from src.orchestrators._report_analysis_orchestrator.coverage_challenge import (
    challenge_editorial_coverage,
)
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


def test_bound_refutation_skips_unnecessary_repair_and_keeps_original_review(tmp_path):
    candidates = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 6)]
    initial = [
        {**deepcopy(item), "evidence_id": f"verified-fact:{item['id']}"}
        for item in candidates
    ]
    initial[1]["text"] = "The reported figure includes the stated population."
    responses = _generation_responses(candidates, plan_evidence_ids=["f2", "f1"])
    responses["insights_final"] = {"insights_final": initial}
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{initial[1]['id']}"
    )
    coverage = _theme_coverage_response(
        candidates, ["f2", "f1"], covered_evidence_ids={"f1", "f2"}
    )
    coverage.update(
        report_completeness="incomplete",
        diagnosis="material_report_completeness",
        recovery_action="targeted_rewrite",
        material_gaps=[
            {
                "verified_fact_ids": [initial[1]["id"]],
                "evidence_ids": [f"verified-fact:{initial[1]['id']}"],
                "final_insight_ids": [initial[1]["id"]],
                "explanation": "The population is not stated.",
            }
        ],
    )
    responses["editorial_theme_coverage"] = coverage
    calls = []
    responses["coverage_challenge"] = {
        "verdicts": [
            {
                "gap_index": 0,
                "verdict": "refuted",
                "explanation": "The insight states the population.",
                "supporting_insight_id": initial[1]["id"],
                "supporting_quote": (
                    "The reported figure includes the stated population."
                ),
            }
        ]
    }
    client = FakeOpenAI(responses)
    prompt_client = CapturingPromptClient()
    settings = _settings(tmp_path)

    def challenge(request):
        calls.append(request)
        return challenge_editorial_coverage(
            request,
            settings=settings,
            openai_client=client,
            prompt_client=prompt_client,
            report_id="coverage-challenge",
            report_name="Coverage challenge",
        )

    result = generate_artifacts(
        report_id="coverage-challenge",
        report_name="Coverage challenge",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=settings,
        ctx=_ctx(),
        openai_client=client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="t" * 64
        ),
        coverage_gap_challenger=challenge,
    )
    assert len(calls) == 1
    assert calls[0].original_assessment["material_gaps"] == coverage["material_gaps"]
    retained = result["_cache"]["family_outputs"][
        "report_vs/artifacts/editorial_theme_coverage"
    ]
    assert retained["material_gaps"] == coverage["material_gaps"]
    final_coverage = result["_cache"]["candidate_generation"][
        "editorial_plan_coverage"
    ]["final_selected_theme_coverage"]
    assert final_coverage["omitted_themes"] == []
    assert final_coverage["coverage_challenge"]["verdicts"] == ["refuted"]
    detail = final_coverage["coverage_challenge"]["verdict_details"][0]
    assert detail == {
        "gap_index": 0,
        "verdict": "refuted",
        "supporting_insight_id": initial[1]["id"],
        "supporting_quote_sha256": sha256(
            initial[1]["text"].encode("utf-8")
        ).hexdigest(),
        "explanation_sha256": sha256(b"The insight states the population.").hexdigest(),
    }


def test_challenge_after_targeted_repair_preserves_both_reviews(tmp_path):
    candidates = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 6)]
    final = [
        {**deepcopy(item), "evidence_id": f"verified-fact:{item['id']}"}
        for item in candidates
    ]
    final[0]["text"] = "The reported figure includes the stated population."
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = [
        {"insights_final": final},
        {"insights_final": [final[0]]},
    ]
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = final[0][
        "evidence_id"
    ]
    coverage = _theme_coverage_response(
        candidates, ["f1", "f2"], covered_evidence_ids={"f1", "f2"}
    )
    coverage.update(
        report_completeness="incomplete",
        diagnosis="material_report_completeness",
        recovery_action="targeted_rewrite",
        material_gaps=[
            {
                "verified_fact_ids": [final[0]["id"]],
                "evidence_ids": [final[0]["evidence_id"]],
                "final_insight_ids": [final[0]["id"]],
                "explanation": "The population is not stated.",
            }
        ],
    )
    responses["editorial_theme_coverage"] = [deepcopy(coverage), deepcopy(coverage)]
    requests = []

    def challenge(request):
        requests.append(request)
        verdict = {
            "gap_index": 0,
            "verdict": "confirmed",
            "explanation": "The gap remains.",
            "supporting_insight_id": "",
            "supporting_quote": "",
        }
        if len(requests) == 2:
            verdict.update(
                verdict="refuted",
                explanation="The population is stated.",
                supporting_insight_id=final[0]["id"],
                supporting_quote=final[0]["text"],
            )
        return EditorialCoverageChallengeResponse(
            schema_version="1.0", verdicts=[verdict], request_id=str(len(requests))
        )

    result = generate_artifacts(
        report_id="repair-challenge",
        report_name="Repair challenge",
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
        coverage_gap_challenger=challenge,
    )
    assert len(requests) == 2
    assert requests[0].ctx.task_id != requests[1].ctx.task_id
    assert not requests[1].require_original_obligation_assessment
    final_coverage = result["_cache"]["candidate_generation"][
        "editorial_plan_coverage"
    ]["final_selected_theme_coverage"]
    assert final_coverage["semantic_repair"]["status"] == "succeeded"
    assert [
        entry["verdicts"] for entry in final_coverage["coverage_challenge"]["history"]
    ] == [["confirmed"], ["refuted"]]


@pytest.mark.parametrize("after_repair", [False, True])
def test_challenge_after_replan_keeps_original_obligations(tmp_path, after_repair):
    candidates = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 6)]
    final = [
        {**deepcopy(item), "evidence_id": f"verified-fact:{item['id']}"}
        for item in candidates
    ]
    final[0]["text"] = "The reported figure includes the stated population."
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["editorial_plan"].append(deepcopy(responses["editorial_plan"][1]))
    responses["insights_final"] = (
        [{"insights_final": final}, {"insights_final": [final[0]]}]
        if after_repair
        else {"insights_final": final}
    )
    responses["replanned_insights_final"] = {"insights_final": final}
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = final[0][
        "evidence_id"
    ]
    initial = _theme_coverage_response(
        candidates, ["f1", "f2"], covered_evidence_ids={"f1"}
    )
    initial.update(diagnosis="infeasible_plan", recovery_action="replan")
    later = _theme_coverage_response(
        candidates, ["f1", "f2"], covered_evidence_ids={"f1", "f2"}
    )
    later.update(
        report_completeness="incomplete",
        diagnosis="material_report_completeness",
        recovery_action="targeted_rewrite",
        material_gaps=[
            {
                "verified_fact_ids": [final[0]["id"]],
                "evidence_ids": [final[0]["evidence_id"]],
                "final_insight_ids": [final[0]["id"]],
                "explanation": "The population is not stated.",
            }
        ],
        original_essential_obligation_assessments=[
            {
                "theme": f"Theme {i + 1}",
                "evidence_ids": [final[i]["evidence_id"]],
                "status": "covered",
                "supporting_insight_ids": [final[i]["id"]],
                "explanation": "The original obligation remains explicit.",
            }
            for i in range(2)
        ],
    )
    if after_repair:
        first = deepcopy(later)
        first.pop("original_essential_obligation_assessments")
        responses["editorial_theme_coverage"] = [first, initial]
        responses["replanned_editorial_theme_coverage"] = (
            FakeOpenAI._complete_legacy_theme_coverage_contract(later)
        )
    else:
        responses["editorial_theme_coverage"] = [initial, later]
    requests = []

    def challenge(request):
        requests.append(request)
        verdict = {
            "gap_index": 0,
            "verdict": "refuted",
            "explanation": "The population is stated.",
            "supporting_insight_id": final[0]["id"],
            "supporting_quote": final[0]["text"],
        }
        if after_repair and len(requests) == 1:
            verdict.update(
                verdict="confirmed",
                explanation="The gap remains.",
                supporting_insight_id="",
                supporting_quote="",
            )
        return EditorialCoverageChallengeResponse(
            schema_version="1.0", verdicts=[verdict]
        )

    result = generate_artifacts(
        report_id="replan-challenge",
        report_name="Replan challenge",
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
        coverage_gap_challenger=challenge,
    )
    assert len(requests) == (2 if after_repair else 1)
    assert requests[-1].require_original_obligation_assessment
    assert len(requests[-1].original_essential_obligations) == 2
    coverage = result["_cache"]["candidate_generation"]["editorial_plan_coverage"][
        "final_selected_theme_coverage"
    ]
    assert coverage["semantic_repair"]["replan"]["status"] == "succeeded"
    assert coverage["coverage_challenge"]["verdicts"] == ["refuted"]
