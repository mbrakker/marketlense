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
                "claim_evidence_map": [
                    {
                        "claim": "Retention is stabilizing.",
                        "evidence_id": "f3",
                        "evidence": "Retention improved",
                        "pages": [4],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "candidate-1",
                    "text": "Retention efficiency is the main growth lever.",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.8,
                },
                {
                    "id": "candidate-2",
                    "text": "Margin pressure constrains expansion.",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.9,
                },
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "We are expanding rapidly",
                    "speaker": "CEO",
                    "citation": "",
                    "page": 3,
                    "evidence_id": "q1",
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "candidate-2",
                    "text": "Margin pressure constrains expansion.",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.9,
                },
                {
                    "id": "candidate-1",
                    "text": "Retention efficiency is the main growth lever.",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.8,
                },
            ]
        },
        "expert_comment": {
            "expert_comment": "The thesis points to a different operating tradeoff: retain demand efficiently while protecting margin."
        },
        "linkedin_post": {
            "linkedin_post": "Retention efficiency is changing the planning outlook."
        },
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
        "report_vs/artifacts/linkedin_post",
    ):
        assert (
            json.loads(
                prompt_client.variables_for_namespace(namespace)["editorial_plan_json"]
            )
            == plan
        )
    assert [item["evidence_id"] for item in payload["insights_final"]] == [
        "f3",
        "f2",
        "f1",
        "f2",
        "f3",
    ]
    assert "retention-led efficiency" in payload["summary"]["executive_summary"].lower()
    assert "operating tradeoff" in payload["expert_comment"].lower()


def test_editorial_plan_keeps_current_metric_and_central_publisher_forecast(tmp_path):
    current_users_id = "current-users"
    forecast_id = "publisher-forecast"
    promotional_id = "opening-promotion"
    plan = {
        "report_thesis": (
            "Practical Metaverse adoption has current reach and a material "
            "publisher growth forecast."
        ),
        "themes": [
            {
                "theme": "Current reach and forecast growth",
                "priority": 1,
                "evidence_ids": [current_users_id, forecast_id],
            },
            {
                "theme": "Practical operating focus",
                "priority": 2,
                "evidence_ids": ["secondary-economy"],
            },
        ],
    }
    evidence = {
        "findings": {
            "findings": [
                {
                    "id": current_users_id,
                    "text": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "evidence": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "pages": [4],
                },
                {
                    "id": forecast_id,
                    "text": "Activate forecasts 600M+ Metaverse users by 2026, a central forecast repeated in the executive summary and opening takeaways.",
                    "evidence": "Activate forecasts 600M+ Metaverse users by 2026.",
                    "pages": [5],
                },
                {
                    "id": "secondary-economy",
                    "text": "Virtual economies support creator and commerce activity.",
                    "evidence": "Virtual economies support creator and commerce activity.",
                    "pages": [9],
                },
                {
                    "id": "secondary-ai",
                    "text": "Generative AI can reduce creation barriers.",
                    "evidence": "Generative AI can reduce creation barriers.",
                    "pages": [11],
                },
                {
                    "id": "secondary-governance",
                    "text": "Governance remains a planning consideration.",
                    "evidence": "Governance remains a planning consideration.",
                    "pages": [13],
                },
                {
                    "id": promotional_id,
                    "text": "Activate offers consulting services for digital transformation.",
                    "evidence": "Activate offers consulting services for digital transformation.",
                    "pages": [1],
                },
            ]
        },
        "quote_candidates": {"quote_candidates": []},
    }
    responses = {
        "editorial_plan": {"editorial_plan": plan},
        "summary": {
            "summary": {
                "tldr": "Current Metaverse reach sits beside Activate's forecast of 600M+ users by 2026.",
                "card_tldr_compact": "Activate forecasts 600M+ Metaverse users by 2026.",
                "executive_summary": "The report identifies 300M+ active users in Metaverse games and virtual-world platforms today. Activate forecasts 600M+ Metaverse users by 2026. The forecast is a publisher projection, not an observed current-state measure.",
                "claim_evidence_map": [
                    {
                        "claim": "Activate forecasts 600M+ Metaverse users by 2026.",
                        "evidence_id": forecast_id,
                        "evidence": "Activate forecasts 600M+ Metaverse users by 2026.",
                        "pages": [5],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "current-reach",
                    "text": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "evidence_id": current_users_id,
                    "evidence": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "metric": {
                        "label": "Current Metaverse users",
                        "value": "300M+",
                        "unit": "users",
                    },
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "forecast-growth",
                    "text": "Activate forecasts 600M+ Metaverse users by 2026.",
                    "evidence_id": forecast_id,
                    "evidence": "Activate forecasts 600M+ Metaverse users by 2026.",
                    "metric": {
                        "label": "Activate forecast Metaverse users",
                        "value": "600M+",
                        "unit": "users",
                        "timeframe": "2026",
                    },
                    "pages": [5],
                    "score": 0.89,
                },
            ]
        },
        "quotes": {"quotes_final": []},
        "insights_final": {
            "insights_final": [
                {
                    "id": "current-reach",
                    "text": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "evidence_id": current_users_id,
                    "evidence": "300M+ active users currently participate in Metaverse games and virtual-world platforms.",
                    "metric": {
                        "label": "Current Metaverse users",
                        "value": "300M+",
                        "unit": "users",
                    },
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "forecast-growth",
                    "text": "Activate forecasts 600M+ Metaverse users by 2026.",
                    "evidence_id": forecast_id,
                    "evidence": "Activate forecasts 600M+ Metaverse users by 2026.",
                    "metric": {
                        "label": "Activate forecast Metaverse users",
                        "value": "600M+",
                        "unit": "users",
                        "timeframe": "2026",
                    },
                    "pages": [5],
                    "score": 0.89,
                },
            ]
        },
        "expert_comment": {
            "expert_comment": "Current reach gives the forecast context: Activate's forecast of 600M+ Metaverse users by 2026 is a projection, while 300M+ active users is the observed starting point."
        },
        "linkedin_post": {
            "linkedin_post": "Activate forecasts 600M+ Metaverse users by 2026."
        },
    }
    prompt_client = CapturingPromptClient()
    openai_client = FakeOpenAI(responses)

    payload = generate_artifacts(
        report_id="central-forecast",
        report_name="Central Forecast",
        doc_map={
            "title": "Metaverse outlook",
            "sections": [{"id": "s1", "title": "Executive summary"}],
        },
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=openai_client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["editorial_plan"]["themes"][0]["evidence_ids"] == [
        current_users_id,
        forecast_id,
    ]
    assert promotional_id not in {
        evidence_id
        for theme in payload["editorial_plan"]["themes"]
        for evidence_id in theme["evidence_ids"]
    }
    assert (
        "Activate forecasts 600M+ Metaverse users by 2026"
        in payload["summary"]["executive_summary"]
    )
    assert forecast_id in {
        insight["evidence_id"] for insight in payload["insights_final"]
    }
    assert "Activate's forecast" in payload["expert_comment"]
    for namespace in (
        "report_vs/artifacts/summary",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/expert_comment",
    ):
        assert (
            json.loads(
                prompt_client.variables_for_namespace(namespace)["editorial_plan_json"]
            )
            == plan
        )
    assert [step for _, _, step in openai_client.requests].count("editorial_plan") == 1
    assert len(openai_client.requests) == 8


def test_expert_comment_receives_grounded_theme_context_not_summary_prose(tmp_path):
    plan = _editorial_plan()
    evidence = _evidence_packs()
    evidence["limitations"] = {
        "limitations": [
            {
                "id": "lim-1",
                "description": "The report does not compare retention by region.",
                "evidence_id": "f3",
            }
        ]
    }
    responses = {
        "editorial_plan": {"editorial_plan": plan},
        "summary": {
            "summary": {
                "tldr": "A compressed summary that must not be expert input.",
                "card_tldr_compact": "Compressed summary.",
                "executive_summary": "Summary prose must not frame Expert View.",
                "claim_evidence_map": [],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "candidate-1",
                    "text": "Retention stabilizing",
                    "so_what": "Retention changes the growth tradeoff.",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "candidate-2",
                    "text": "Margin pressure in EU",
                    "coverage_role": "counter_signal",
                    "so_what": "Margin pressure limits expansion options.",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.8,
                },
            ]
        },
        "quotes": {"quotes_final": []},
        "insights_final": {
            "insights_final": [
                {
                    "id": "candidate-1",
                    "text": "Retention stabilizing",
                    "so_what": "Retention changes the growth tradeoff.",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "candidate-2",
                    "text": "Margin pressure in EU",
                    "coverage_role": "counter_signal",
                    "so_what": "Margin pressure limits expansion options.",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.8,
                },
            ]
        },
        "expert_comment": {
            "expert_comment": "Retention and margin evidence describe a planning tension."
        },
        "linkedin_post": {"linkedin_post": "Retention is changing planning."},
    }
    prompt_client = CapturingPromptClient()

    generate_artifacts(
        report_id="expert-grounded-context",
        report_name="Expert Grounded Context",
        doc_map=_doc_map(),
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    expert_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/expert_comment"
    )
    assert "summary_json" not in expert_vars
    synthesis_context = json.loads(expert_vars["expert_synthesis_context_json"])
    assert [theme["theme"] for theme in synthesis_context["themes"]] == [
        "Retention efficiency",
        "Margin pressure",
    ]
    assert {
        evidence["evidence_id"]
        for theme in synthesis_context["themes"]
        for evidence in theme["evidence"]
    } == {"f1", "f2", "f3", "s1"}
    assert synthesis_context["insight_implications"] == [
        {
            "evidence_id": "f3",
            "so_what": "Retention changes the growth tradeoff.",
        },
        {
            "evidence_id": "f2",
            "so_what": "Margin pressure limits expansion options.",
        },
    ]
    assert synthesis_context["limitations"] == [
        {
            "evidence_id": "f3",
            "text": "The report does not compare retention by region.",
        }
    ]
    assert synthesis_context["counter_signals"] == [
        {"evidence_id": "f2", "text": "Margin pressure in EU"}
    ]


def test_expert_synthesis_context_keeps_string_limitations_from_evidence_pack():
    context = artifact_normalization.build_expert_synthesis_context(
        editorial_plan=_editorial_plan(),
        insights_final=[],
        doc_map=_doc_map(),
        evidence_packs={
            **_evidence_packs(),
            "limitations": {
                "limitations": ["Sample sizes vary across the report's analyses."]
            },
        },
    )

    assert context["limitations"] == [
        {
            "evidence_id": "",
            "text": "Sample sizes vary across the report's analyses.",
        }
    ]


def test_expert_comment_can_abstain_when_no_distinct_synthesis_is_returned(tmp_path):
    plan = _editorial_plan()
    responses = {
        "editorial_plan": {"editorial_plan": plan},
        "summary": {
            "summary": {
                "tldr": "Retention and margin are separate report findings.",
                "card_tldr_compact": "Retention and margin findings.",
                "executive_summary": "The report contains distinct retention and margin evidence.",
                "claim_evidence_map": [
                    {
                        "claim": "Retention improved.",
                        "evidence_id": "f3",
                        "evidence": "Retention improved",
                        "pages": [4],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "candidate-1",
                    "text": "Retention stabilizing",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "candidate-2",
                    "text": "Margin pressure in EU",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.8,
                },
            ]
        },
        "quotes": {"quotes_final": []},
        "insights_final": {
            "insights_final": [
                {
                    "id": "candidate-1",
                    "text": "Retention stabilizing",
                    "evidence_id": "f3",
                    "evidence": "Retention improved",
                    "metric": {},
                    "pages": [4],
                    "score": 0.9,
                },
                {
                    "id": "candidate-2",
                    "text": "Margin pressure in EU",
                    "evidence_id": "f2",
                    "evidence": "Margin declined",
                    "metric": {},
                    "pages": [3],
                    "score": 0.8,
                },
            ]
        },
        "expert_comment": {"expert_comment": ""},
        "linkedin_post": {"linkedin_post": ""},
    }

    payload = generate_artifacts(
        report_id="expert-abstention",
        report_name="Expert Abstention",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["expert_comment"] == ""
    assert payload["family_status"]["expert_comment"] == {
        "schema_version": "1.0",
        "family": "expert_comment",
        "source": "artifact",
        "status": "abstained",
        "confidence_score": 0.0,
        "policy_action": "abstain",
        "reason": "generated_text_missing",
    }
    prompt_text = (
        Path("src/prompts/report_vs/artifacts/expert_comment/user.yaml")
        .read_text(encoding="utf-8")
        .casefold()
    )
    assert '{"expert_comment": ""}' in prompt_text


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
    first = _artifact_cache_meta(**common, prompt_client=PlanPromptClient("a" * 64))
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
    "test_editorial_plan_keeps_current_metric_and_central_publisher_forecast",
    "test_expert_comment_receives_grounded_theme_context_not_summary_prose",
    "test_expert_synthesis_context_keeps_string_limitations_from_evidence_pack",
    "test_expert_comment_can_abstain_when_no_distinct_synthesis_is_returned",
    "test_editorial_plan_prompt_and_inputs_invalidate_artifact_cache_identity",
]
