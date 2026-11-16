from __future__ import annotations

import json
from copy import deepcopy

from src.generators._artifact_generator.generation import (
    _verified_limitation_evidence_ids,
    generate_artifacts,
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


def test_verified_limitation_vocabulary_excludes_unqualified_facts() -> None:
    facts = [
        {"fact_id": "qualified", "qualifiers": ["Survey scope is limited."]},
        {"fact_id": "ordinary", "qualifiers": []},
        {"fact_id": "blank", "qualifiers": ["  "]},
    ]
    assert _verified_limitation_evidence_ids(facts) == ["verified-fact:qualified"]
    assert _verified_limitation_evidence_ids(facts[1:]) == []


def test_verified_plan_receives_exact_eligible_limitation_ids(tmp_path) -> None:
    candidates = [
        _insight(f"f{index}", score=1.0 - index / 100) for index in range(1, 6)
    ]
    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {**deepcopy(candidate), "evidence_id": f"verified-fact:{candidate['id']}"}
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates, ["f1", "f2"], covered_evidence_ids={"f1", "f2"}
    )
    prompt_client = CapturingPromptClient()
    generate_artifacts(
        report_id="verified-limitation-vocabulary",
        report_name="Verified limitation vocabulary",
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
    variables = next(
        call["variables"]
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/editorial_plan/user"
        and call["variables"].get("editorial_plan_phase") == "verified_facts"
    )
    facts = json.loads(variables["verified_facts_json"])
    expected = [
        f"verified-fact:{fact['fact_id']}"
        for fact in facts
        if any(str(value).strip() for value in fact.get("qualifiers") or [])
    ]
    assert json.loads(variables["verified_limitation_evidence_ids_json"]) == expected
