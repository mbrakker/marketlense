"""Selected page text is supporting context, never a substitute for images."""

from src.generators.verified_claims_visual_generator import evaluate_shortlisted_claims
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _claim,
    _ctx,
    _dependencies,
    _request,
    _settings,
)


def test_selected_page_text_reaches_correction_without_unselected_pages(tmp_path):
    request = _request(tmp_path, [_claim("c1", "Provisional conclusion", page=5)])
    request.source_page_text_by_physical_page = {
        5: "Selected page context with a forecast caveat.",
        6: "Unselected page context must not be included.",
    }
    requests = []
    responses = iter([{"claim": "", "status": "unresolved", "issues": []}])

    result = evaluate_shortlisted_claims(
        request=request,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        dependencies=_dependencies(responses, [], requests),
    )

    assert result.claims[0].outcome != "verified"
    assert "Selected page context with a forecast caveat." in requests[1].user_prompt
    assert "Unselected page context" not in requests[1].user_prompt
    assert requests[1].image_paths
