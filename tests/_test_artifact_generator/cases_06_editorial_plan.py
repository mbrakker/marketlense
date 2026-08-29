# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.generators import artifact_normalization
from src.generators._artifact_generator.storage import _artifact_cache_meta
from src.services.schema_validator_service import validate_evidence_references
from src.utils.errors import AppError

from ._shared import *  # noqa: F401,F403


def _editorial_plan() -> dict[str, object]:
    return {
        "report_thesis": (
            "Growth is shifting from broad expansion to retention-led efficiency."
        ),
        "themes": [
            {
                "theme": "Retention efficiency",
                "priority": 1,
                "evidence_ids": ["f3", "f1", "s1"],
            },
            {
                "theme": "Margin pressure",
                "priority": 2,
                "evidence_ids": ["f2"],
            },
        ],
    }


def test_editorial_plan_normalizes_priority_and_rejects_unknown_evidence_id():
    normalize = getattr(
        artifact_normalization, "normalize_artifact_editorial_plan", None
    )
    assert callable(normalize)

    plan = normalize(_editorial_plan())

    assert plan == _editorial_plan()
    with pytest.raises(AppError, match="unknown identifiers"):
        validate_evidence_references(
            {
                "editorial_plan": {
                    **plan,
                    "themes": [
                        {
                            "theme": "Unknown",
                            "priority": 1,
                            "evidence_ids": ["missing"],
                        }
                    ],
                }
            },
            {**_evidence_packs(), "doc_map": _doc_map()},
            _ctx(),
        )


def test_editorial_plan_is_the_shared_basis_for_summary_insights_and_expert(tmp_path):
    plan = _editorial_plan()
    responses = {
        "editorial_plan": {"editorial_plan": plan},
        "summary": {
            "summary": {
                "tldr": "Retention efficiency is becoming the central growth lever.",
                "card_tldr_compact": "Retention efficiency now leads growth.",
                "executive_summary": "The report thesis is that growth is shifting toward retention-led efficiency. Margin pressure makes this prioritization more urgent.",
                "claim_evidence_map": [{"claim": "Retention is stabilizing.", "evidence_id": "f3", "evidence": "Retention improved", "pages": [4]}],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {"id": "candidate-1", "text": "Retention efficiency is the main growth lever.", "evidence_id": "f3", "evidence": "Retention improved", "metric": {}, "pages": [4], "score": 0.8},
                {"id": "candidate-2", "text": "Margin pressure constrains expansion.", "evidence_id": "f2", "evidence": "Margin declined", "metric": {}, "pages": [3], "score": 0.9},
            ]
        },
        "quotes": {"quotes_final": [{"text": "We are expanding rapidly", "speaker": "CEO", "citation": "", "page": 3, "evidence_id": "q1"}]},
        "insights_final": {
            "insights_final": [
                {"id": "candidate-2", "text": "Margin pressure constrains expansion.", "evidence_id": "f2", "evidence": "Margin declined", "metric": {}, "pages": [3], "score": 0.9},
                {"id": "candidate-1", "text": "Retention efficiency is the main growth lever.", "evidence_id": "f3", "evidence": "Retention improved", "metric": {}, "pages": [4], "score": 0.8},
            ]
        },
        "expert_comment": {"expert_comment": "The thesis points to a different operating tradeoff: retain demand efficiently while protecting margin."},
        "linkedin_post": {"linkedin_post": "Retention efficiency is changing the planning outlook."},
    }
    prompt_client = CapturingPromptClient()

    payload = generate_artifacts(
        report_id="editorial-plan",
        report_name="Editorial Plan",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["editorial_plan"] == plan
    for namespace in (
        "report_vs/artifacts/summary",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/expert_comment",
    ):
        assert json.loads(
            prompt_client.variables_for_namespace(namespace)["editorial_plan_json"]
        ) == plan
    assert [item["evidence_id"] for item in payload["insights_final"]] == ["f3", "f2"]
    assert "retention-led efficiency" in payload["summary"]["executive_summary"].lower()
    assert "operating tradeoff" in payload["expert_comment"].lower()


def test_editorial_plan_prompt_and_inputs_invalidate_artifact_cache_identity(tmp_path):
    class PlanPromptClient(FakePromptClient):
        def __init__(self, prompt_hash: str):
            self.prompt_hash = prompt_hash

        def load_prompt_set(self, request, ctx):
            prompt_set = super().load_prompt_set(request, ctx)
            if request.namespace != "report_vs/artifacts/editorial_plan":
                return prompt_set
            return replace(
                prompt_set,
                prompt_content_hash=self.prompt_hash,
                dependency_manifest=replace(
                    prompt_set.dependency_manifest,
                    prompt_content_hash=self.prompt_hash,
                ),
            )

    common = {
        "md5": "editorial-plan-md5",
        "doc_map": _doc_map(),
        "evidence_packs": _evidence_packs(),
        "availability": {"not_available": False, "reason": ""},
        "expert_domain": "",
        "category_ids": [],
        "retrieval_mode": "chat_json",
        "settings": _settings(tmp_path),
        "ctx": _ctx(),
    }
    first = _artifact_cache_meta(
        **common, prompt_client=PlanPromptClient("a" * 64)
    )
    changed_prompt = _artifact_cache_meta(
        **common, prompt_client=PlanPromptClient("b" * 64)
    )
    changed_inputs = _artifact_cache_meta(
        **{**common, "doc_map": {**_doc_map(), "title": "Changed report"}},
        prompt_client=PlanPromptClient("a" * 64),
    )

    family = "report_vs/artifacts/editorial_plan"
    assert (
        first["prompts"][family]["prompt_content_hash"]
        != changed_prompt["prompts"][family]["prompt_content_hash"]
    )
    assert first["inputs_sha256"] != changed_inputs["inputs_sha256"]


__all__ = [
    "test_editorial_plan_normalizes_priority_and_rejects_unknown_evidence_id",
    "test_editorial_plan_is_the_shared_basis_for_summary_insights_and_expert",
    "test_editorial_plan_prompt_and_inputs_invalidate_artifact_cache_identity",
]
