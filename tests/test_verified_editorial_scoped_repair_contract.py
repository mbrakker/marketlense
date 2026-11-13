from __future__ import annotations

import json
from copy import deepcopy

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.generators._artifact_generator.generation import (
    _merge_scoped_insight_repair,
)
from src.generators.artifact_normalization import normalize_artifact_insights
from src.services.prompt_service import load_prompt_set, render_prompt
from tests.test_verified_editorial_first_pass_and_scoped_repair import (
    _candidate,
    _ctx,
)


def test_localized_regeneration_prompt_is_not_a_full_roster_request() -> None:
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/regenerate/insights_final",
            force_reload=True,
        ),
        _ctx(),
    )
    variables = {
        "attempt_index": 1,
        "target_section": "insights_bundle",
        "current_section_json": json.dumps(
            [
                {
                    "id": "insight-1",
                    "text": "Original wording.",
                    "evidence_id": "verified-fact:f1",
                }
            ]
        ),
        "insights_candidates_json": json.dumps(
            [
                {
                    "id": "insight-1",
                    "text": "Canonical source proposition.",
                    "evidence_id": "verified-fact:f1",
                }
            ]
        ),
        "failure_reasons_json": json.dumps(
            [{"message": "The wording loses the source denominator."}]
        ),
        "fix_checklist_json": "[]",
        "grounding_package_json": json.dumps(
            {
                "relevant_evidence": [
                    {
                        "id": "verified-fact:f1",
                        "text": "The source denominator is repeat buyers.",
                        "page": 4,
                    }
                ]
            }
        ),
        "editorial_plan_json": "{}",
        "final_insight_target_count": 1,
        "repair_context_json": json.dumps(
            {
                "allowed_paths": ["insights_final[item=insight-1].text"],
                "allowed_evidence_ids": ["verified-fact:f1"],
            }
        ),
        "prior_repair_memory_json": "[]",
    }
    prompt = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        _ctx(),
    ).text
    full_prompt = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables={**variables, "final_insight_target_count": 3},
        ),
        _ctx(),
    ).text

    assert "insights_final[item=insight-1].text" in prompt
    assert "repeat buyers" in prompt
    assert "denominator" in prompt
    assert "every editorial theme" not in prompt
    assert "fill the final roster" not in prompt
    assert "every retained insight" not in prompt
    assert "18 words or fewer" not in prompt
    assert "compact card" not in prompt
    assert "neighboring source fact" in prompt
    assert "each theme" in full_prompt
    assert "fill the remaining slots" in full_prompt
    assert "compact card" in full_prompt


def test_scoped_repair_preserves_omitted_editorial_fields_after_normalization() -> None:
    candidate = _candidate("candidate-1", "f1")
    current = {
        **deepcopy(candidate),
        "text": "Original source-backed wording.",
        "so_what": "The original commercial implication.",
        "now_what": "The original conditional action.",
        "metric_public_copy": "The original reader-facing metric.",
        "coverage_role": "behavior_shift",
        "report_type_lens": "consumer_behavior",
        "score": 0.71,
        "decision_relevance_score": 0.82,
        "metric_strength_score": 0.63,
        "novelty_score": 0.54,
    }
    raw_patch = [
        {
            "id": "candidate-1",
            "text": "Corrected source-backed wording.",
            "evidence_id": "verified-fact:f1",
        }
    ]
    normalized_patch = normalize_artifact_insights(
        raw_patch, prefix="insight", verified_mode=True
    )
    merged = _merge_scoped_insight_repair(
        current_insights=[current],
        repaired_insights=normalized_patch,
        raw_repaired_insights=raw_patch,
        repair_scope={"targeted_insight_ids": ["candidate-1"]},
    )

    assert merged[0]["text"] == "Corrected source-backed wording."
    for field_name in (
        "so_what",
        "now_what",
        "metric_public_copy",
        "coverage_role",
        "report_type_lens",
        "score",
        "decision_relevance_score",
        "metric_strength_score",
        "novelty_score",
    ):
        assert merged[0][field_name] == current[field_name]


def test_scoped_repair_changes_an_explicit_editorial_field_only() -> None:
    current = {
        **_candidate("candidate-1", "f1"),
        "so_what": "Original implication.",
        "now_what": "Original action.",
        "metric_public_copy": "Original metric copy.",
    }
    raw_patch = [
        {
            "id": "candidate-1",
            "text": current["text"],
            "evidence_id": current["evidence_id"],
            "so_what": "Updated implication.",
        }
    ]
    merged = _merge_scoped_insight_repair(
        current_insights=[current],
        repaired_insights=normalize_artifact_insights(
            raw_patch, prefix="insight", verified_mode=True
        ),
        raw_repaired_insights=raw_patch,
        repair_scope={"targeted_insight_ids": ["candidate-1"]},
    )

    assert merged[0]["so_what"] == "Updated implication."
    assert merged[0]["now_what"] == current["now_what"]
    assert merged[0]["metric_public_copy"] == current["metric_public_copy"]
