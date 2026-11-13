from __future__ import annotations

import json

from tests.test_verified_editorial_first_pass_and_scoped_repair import (
    _render_final_insight_user_prompt,
)


def test_verified_full_prompt_keeps_facts_candidate_local() -> None:
    prompt = _render_final_insight_user_prompt(
        semantic_theme_repair_scope_json="",
        verified_editorial_obligations_json='{"authoritative_facts":[{"fact_id":"f1"},{"fact_id":"f2"}]}',
        insights_candidates_json=json.dumps(
            [
                {
                    "id": "candidate-1",
                    "evidence_id": "verified-fact:f1",
                    "text": "Fact one has its own population and metric.",
                },
                {
                    "id": "candidate-2",
                    "evidence_id": "verified-fact:f2",
                    "text": "Fact two has a distinct population and metric.",
                },
            ]
        ),
    ).lower()

    assert "candidate-local factual rule" in prompt
    assert (
        "do not import numeric series, populations, categories, or comparisons"
        in prompt
    )
    assert "explicitly included in the authorized evidence binding" in prompt
    scoped_prompt = _render_final_insight_user_prompt(
        semantic_theme_repair_scope_json='{"mode":"targeted_rewrite"}',
        semantic_theme_allowed_patch_ids_json='["candidate-1"]',
        semantic_theme_targeted_insight_ids_json='["candidate-1"]',
        semantic_theme_targeted_insights_json='[{"id":"candidate-1"}]',
    ).lower()
    assert "do not emit a metric object" in scoped_prompt
