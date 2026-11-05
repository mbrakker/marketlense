from __future__ import annotations

from copy import deepcopy

from src.contracts.prompts import PromptLoadRequest
from src.generators._artifact_generator.generation import generate_artifacts
from src.services.prompt_service import load_prompt_set
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
from tests.test_verified_claims_visual_authority_snapshot_integrity import (
    _theme_coverage_response,
)


def test_editorial_prompts_require_complete_material_theme_coverage() -> None:
    editorial_plan = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/editorial_plan",
            force_reload=True,
        ),
        _ctx(),
    )
    final_insights = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/insights_final",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "assign each materially distinct fact to a theme's evidence_ids" in (
        editorial_plan.user.text
    )
    assert "do not leave a distinct admitted fact unrepresented" in (
        editorial_plan.user.text
    )
    final_text = " ".join(final_insights.user.text.split()).casefold()
    assert "at least one selected insight substantively developing each planned" in (
        final_text
    )
    assert "treat the omitted-theme list as a hard acceptance checklist" in final_text
    coverage = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/editorial_theme_coverage",
            force_reload=True,
        ),
        _ctx(),
    )
    coverage_text = " ".join(coverage.user.text.split()).casefold()
    assert (
        "single final insight may support more than one planned theme"
        in coverage_text
    )
    assert "instead of demanding a redundant one-to-one insight" in coverage_text


def test_editorial_plan_and_findings_prompts_require_representative_counterbalance(
) -> None:
    editorial_plan = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/editorial_plan",
            force_reload=True,
        ),
        _ctx(),
    )
    findings = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/evidence_packs/findings",
            force_reload=True,
        ),
        _ctx(),
    )

    assert "DocMap is the authority for report breadth" in editorial_plan.user.text
    assert "counterbalancing" in editorial_plan.user.text
    assert "executive-summary" in editorial_plan.user.text
    findings_text = " ".join(findings.user.text.split()).casefold()
    assert "counterbalancing" in findings.user.text
    assert (
        "if retrieved body evidence supports a material key point, include it as a "
        "finding"
        in findings_text
    )


def test_editorial_plan_prompt_retains_substantive_central_forecasts() -> None:
    editorial_plan = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/editorial_plan",
            force_reload=True,
        ),
        _ctx(),
    )

    prompt_text = editorial_plan.user.text.casefold()
    assert "materially central" in prompt_text
    assert "page position" in prompt_text
    assert "promotional" in prompt_text
    assert "forecast" in prompt_text


def test_verified_ten_fact_roster_can_retain_seven_material_planned_themes(tmp_path):
    candidates = [
        _insight(f"f{i}", score=1.0 - i / 100, coverage_role="proof_point")
        for i in range(1, 11)
    ]
    plan_ids = [f"f{i}" for i in range(1, 8)]
    responses = _generation_responses(candidates, plan_evidence_ids=plan_ids)
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
                "evidence_spans": [],
            }
            for candidate in candidates[:7]
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        plan_ids,
        covered_evidence_ids=set(plan_ids),
    )

    payload = generate_artifacts(
        report_id="verified-ten-fact-theme-roster",
        report_name="Verified ten-fact theme roster",
        doc_map=_doc_map(10),
        evidence_packs=_generation_evidence(10),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=lambda shortlisted: _verified_admission(
            shortlisted, digest="t" * 64
        ),
    )

    assert len(payload["verified_facts"]) == 10
    assert len(payload["insights_final"]) == 7
    assert {item["evidence_id"] for item in payload["insights_final"]} == {
        f"verified-fact:{candidate['id']}" for candidate in candidates[:7]
    }
    coverage = payload["_cache"]["candidate_generation"]["editorial_plan_coverage"]
    assert coverage["final_selected_theme_coverage"]["omitted_themes"] == []
    assert len(coverage["final_selected_theme_coverage"]["theme_coverage"]) == 7
