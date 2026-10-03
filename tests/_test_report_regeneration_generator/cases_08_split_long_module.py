# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_regenerate_artifacts_topics_rebuilds_topic_briefs_without_model_calls(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    current_artifacts["toc_topics"] = [
        "Media brand ad equity",
        "Sentiments on generative AI",
    ]
    current_artifacts["toc_topics_expanded"] = [
        {
            "topic": "Media brand ad equity",
            "summary": "Wrong summary",
            "key_points": [],
            "section_id": "section-4",
            "section_title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
            "pages": [25],
        },
        {
            "topic": "Sentiments on generative AI",
            "summary": "Wrong summary",
            "key_points": [],
            "section_id": "section-5",
            "section_title": "Implications for marketers",
            "pages": [27],
        },
    ]
    evidence_packs = _evidence_packs()
    evidence_packs["doc_map"] = {
        "doc_id": "doc-1",
        "title": "Media Reactions",
        "sections": [
            {
                "id": "section-3",
                "title": "Media brands: How do brands interact with people?",
                "summary": "Media-brand Ad Equity rankings with Netflix and OTT platforms leading.",
                "key_points": [
                    "Netflix is the #1 media brand for Ad Equity.",
                    "OTT platforms dominate the rankings.",
                ],
                "pages": [17, 18],
            },
            {
                "id": "section-4",
                "title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                "summary": "Consumer and marketer attitudes to generative AI in advertising.",
                "key_points": [
                    "Consumers worry about fake content.",
                    "Marketers use generative AI for creativity and efficiency.",
                ],
                "pages": [25],
            },
            {
                "id": "section-5",
                "title": "Implications for marketers",
                "summary": "Budget priorities and investment plans for marketers.",
                "key_points": [
                    "Online video and streaming remain top priorities.",
                ],
                "pages": [27],
            },
        ],
    }
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="topics",
                        regenerate_steps=[
                            "toc_entries",
                            "toc_topics",
                            "toc_topics_expanded",
                        ],
                        prompt_namespaces=[],
                        issues=[
                            RegenerationIssue(
                                rule_id="toc_integrity",
                                affected_section="toc_entries:section-3",
                                message="[toc_integrity] TOC coverage is missing section 'Media brands: How do brands interact with people?'.",
                                severity="error",
                                repair_target="topics",
                                entity_id="section-3",
                                evidence_ids=["section-4"],
                                pages=[25],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
    assert response.updated_artifacts["toc_entries"][0]["section_id"] == "section-3"
    assert (
        response.updated_artifacts["toc_entries"][0]["display_title"] == "Media brands"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][0]["section_id"]
        == "section-3"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][0]["section_title"]
        == "Media brands: How do brands interact with people?"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][1]["section_title"]
        == "Sentiments on GenAI: How do APAC consumers perceive AI?"
    )


def test_atomic_metric_source_repair_rebuilds_key_figures_without_model_calls(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    insight = current_artifacts["insights_final"][0]
    evidence_text = (
        "In 2026, 75% of Europe retail-media teams use AI in campaign workflows."
    )
    current_artifacts["insights_final"][0].update(
        {
            "text": "Retail-media teams are using AI in campaign workflows.",
            "evidence": evidence_text,
            "metric": {
                **METRIC,
                "label": "Retail-media teams using AI in campaign workflows",
                "value": "70%",
                "timeframe": "2026",
                "geography": "Europe",
                "segment": "retail-media teams",
                "confidence": "high",
            },
        }
    )
    current_artifacts["insights_candidates"] = [
        {
            **deepcopy(insight),
            "metric": {**insight["metric"], "value": "75%"},
        }
    ]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0].update(
        {"evidence": evidence_text, "text": evidence_text}
    )
    current_artifacts["key_figures"] = build_key_figures(
        metric_spine=derive_metric_spine_from_insights(
            current_artifacts["insights_final"]
        ),
        evidence_packs=evidence_packs,
        summary=current_artifacts["summary"],
        insights_final=current_artifacts["insights_final"],
        editorial_plan=current_artifacts["editorial_plan"],
    )
    issue = ValidationIssue(
        schema_version="1.0",
        message="Retained metric value is unsupported.",
        severity="error",
        affected_section="insights:insight-1.metric",
        rule_id="retained_claim.protected_fact_value_consistency",
        entity_id="insight:insight-1:metric",
        evidence_ids=["f1"],
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=current_artifacts, broad_retry_available=False
    )
    assert plan.targets[0].allowed_paths == [
        "insights_final[item=insight-1].metric.value"
    ]

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.updated_artifacts["insights_final"][0]["metric"]["value"] == "75%"
    assert response.updated_artifacts["key_figures"][0]["figure"] == "75%"
    assert response.updated_artifacts["summary"]["tldr"] == "Old TLDR."
    assert response.updated_artifacts["summary"]["executive_summary"] == "Old summary"
    assert [item["text"] for item in response.updated_artifacts["insights_final"]] == [
        item["text"] for item in current_artifacts["insights_final"]
    ]
    assert [item["text"] for item in response.updated_artifacts["quotes_final"]] == [
        "Old quote"
    ]
    assert (
        response.updated_artifacts["expert_comment"]
        == current_artifacts["expert_comment"]
    )
    assert (
        response.updated_artifacts["linkedin_post"]
        == current_artifacts["linkedin_post"]
    )
    assert openai_client.calls == []
    assert prompt_client.render_calls == []
    assert openai_client.calls == []
    assert prompt_client.render_calls == []
