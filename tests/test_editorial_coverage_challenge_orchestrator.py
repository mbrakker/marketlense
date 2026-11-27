import json

from src.contracts.artifact_generation import EditorialCoverageChallengeRequest
from src.orchestrators._report_analysis_orchestrator.coverage_challenge import (
    challenge_editorial_coverage,
)
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests.test_editorial_coverage_challenge_resolution import _context


def test_orchestrated_challenge_keeps_original_and_canonical_inputs(tmp_path):
    plan, candidates, insights, original, challenge = _context()
    facts = [{"fact_id": "fact-1", "statement": "The population is specified."}]
    request = EditorialCoverageChallengeRequest(
        schema_version="1.0",
        original_assessment=original,
        editorial_plan=plan,
        final_insights=insights,
        candidate_insights=candidates,
        verified_facts=facts,
        original_essential_obligations=[],
        require_original_obligation_assessment=False,
        ctx=_ctx(),
    )
    prompt_client = CapturingPromptClient()
    response = challenge_editorial_coverage(
        request,
        settings=_settings(tmp_path),
        openai_client=FakeOpenAI([challenge]),
        prompt_client=prompt_client,
        report_id="report-1",
        report_name="Report",
    )
    assert response.verdicts == challenge["verdicts"]
    assert response.prompt_identity["prompt_content_hash"]
    assert response.prompt_identity["execution_identity"]
    assert response.prompt_identity["model_name"]
    variables = prompt_client.variables_for_namespace(
        "report_vs/artifacts/editorial_coverage_challenge"
    )
    assert json.loads(variables["original_assessment_json"]) == original
    assert json.loads(variables["verified_facts_json"]) == facts
    assert json.loads(variables["final_insights_json"]) == insights
