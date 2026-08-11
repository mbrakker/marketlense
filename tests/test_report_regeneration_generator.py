from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.ingest import IngestSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptRenderResponse,
    PromptSet,
    PromptTemplate,
)
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.run_context import RunContext
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.utils.errors import AppError

METRIC = {
    "value": "",
    "unit": "",
    "trend": "",
    "timeframe": "",
    "geography": "",
    "segment": "",
    "sample_size": "",
    "confidence": "",
}


class _FakePromptClient:
    def __init__(self) -> None:
        self.render_calls: list[dict] = []

    def load_prompt_set(self, req, ctx):
        del ctx
        manifest = PromptDependencyManifest(
            schema_version="1.0",
            namespace=req.namespace,
            system_root=PromptDependency(
                schema_version="1.0",
                path=f"{req.namespace}/system.yaml",
                sha256="a" * 64,
                kind="system_root",
            ),
            user_root=PromptDependency(
                schema_version="1.0",
                path=f"{req.namespace}/user.yaml",
                sha256="b" * 64,
                kind="user_root",
            ),
        )
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{req.namespace}/system.yaml",
                text=f"system::{req.namespace}",
                sha256=f"sys-{req.namespace}",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{req.namespace}/user.yaml",
                text=f"user::{req.namespace}",
                sha256=f"user-{req.namespace}",
            ),
            dependency_manifest=manifest,
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, req, ctx):
        del ctx
        rendered = f"{req.template.text}|{json.dumps(req.variables, sort_keys=True, ensure_ascii=False)}"
        self.render_calls.append(
            {
                "path": req.template.path,
                "variables": dict(req.variables),
                "text": rendered,
            }
        )
        return PromptRenderResponse(schema_version="1.0", text=rendered)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def openai_chat_json(self, req, ctx):
        del ctx
        self.calls.append(req)
        if "system::report_vs/artifacts/cover_semantics" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text=(
                    '{"cover_semantics":{"evidence_shape":"trend",'
                    '"direction":"rising","geography_scope":"global",'
                    '"evidence_density":"metric_rich","domain_layer":"grid",'
                    '"selection_reason":"A rising time series is the strongest visual story."}}'
                ),
                parsed_json={
                    "cover_semantics": {
                        "evidence_shape": "trend",
                        "direction": "rising",
                        "geography_scope": "global",
                        "evidence_density": "metric_rich",
                        "domain_layer": "grid",
                        "selection_reason": (
                            "A rising time series is the strongest visual story."
                        ),
                    }
                },
                request_id="req-cover",
            )
        if "system::report_vs/artifacts/regenerate/insights_final" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"insights_final":[{"id":"insight-1","text":"Repaired final insight","evidence_id":"f1","evidence":"Evidence text","metric":{"value":"","unit":"","trend":"","timeframe":"","geography":"","segment":"","sample_size":"","confidence":""},"pages":[1]}]}',
                parsed_json={
                    "insights_final": [
                        {
                            "id": "insight-1",
                            "text": "Repaired final insight",
                            "evidence_id": "f1",
                            "evidence": "Evidence text",
                            "metric": dict(METRIC),
                            "pages": [1],
                        }
                    ]
                },
                request_id="req-final",
            )
        if (
            "system::report_vs/artifacts/regenerate/insights_candidates"
            in req.system_prompt
        ):
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"insights_candidates":[{"id":"candidate-1","text":"Repaired candidate","evidence_id":"f1","evidence":"Evidence text","metric":{"value":"","unit":"","trend":"","timeframe":"","geography":"","segment":"","sample_size":"","confidence":""},"pages":[1],"score":1.0}]}',
                parsed_json={
                    "insights_candidates": [
                        {
                            "id": "candidate-1",
                            "text": "Repaired candidate",
                            "evidence_id": "f1",
                            "evidence": "Evidence text",
                            "metric": dict(METRIC),
                            "pages": [1],
                            "score": 1.0,
                        }
                    ]
                },
                request_id="req-candidates",
            )
        if "system::report_vs/artifacts/regenerate/summary" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"summary":{"tldr":"Repaired TLDR.","card_tldr_compact":"Repaired TLDR.","executive_summary":"Repaired executive summary","claim_evidence_map":[{"claim":"Grounded claim","evidence_id":"f1","evidence":"Evidence text","pages":[1]}]}}',
                parsed_json={
                    "summary": {
                        "tldr": "Repaired TLDR.",
                        "card_tldr_compact": "Repaired TLDR.",
                        "executive_summary": "Repaired executive summary",
                        "claim_evidence_map": [
                            {
                                "claim": "Grounded claim",
                                "evidence_id": "f1",
                                "evidence": "Evidence text",
                                "pages": [1],
                            }
                        ],
                    }
                },
                request_id="req-summary",
            )
        if "system::report_vs/artifacts/regenerate/quotes" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"quotes_final":[{"text":"A paraphrased section summary","speaker":"Unknown","citation":"Topic","page":1,"evidence_id":"sec-1"}]}',
                parsed_json={
                    "quotes_final": [
                        {
                            "text": "A paraphrased section summary",
                            "speaker": "Unknown",
                            "citation": "Topic",
                            "page": 1,
                            "evidence_id": "sec-1",
                        }
                    ]
                },
                request_id="req-quotes",
            )
        raise AssertionError(
            f"Unexpected prompt payload: {req.system_prompt} {req.user_prompt}"
        )

    def openai_respond_with_vector_store(self, req, ctx):
        return self.openai_chat_json(req, ctx)


def _settings(tmp_path: Path) -> IngestSettings:
    output_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(output_dir),
        cache_dir=str(cache_dir),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "cats.yaml"),
        cover_style_path=str(tmp_path / "cover.yaml"),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
        model_pricing={},
        cost_ledger_path=str(output_dir / "cost-ledger.jsonl"),
        cost_daily_path=str(output_dir / "cost-daily.json"),
        llm_execution_policies={
            "report_vs": {
                "schema_version": "1.0",
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 0.0,
                "seed_policy": "inherit",
                "max_output_tokens": 2048,
                "retrieval_mode": "chat_json",
                "timeout_seconds": 30.0,
                "provider_retry_count": 0,
                "structured_output_mode": "json_object",
                "fallback_policy": "same_provider_only",
                "pricing_key": "gpt-5-mini",
            }
        },
    )


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _current_artifacts() -> dict:
    return {
        "schema_version": "3.0",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "Old TLDR.",
            "card_tldr_compact": "Old TLDR.",
            "executive_summary": "Old summary",
            "claim_evidence_map": [
                {
                    "claim": "Old claim",
                    "evidence_id": "f1",
                    "evidence": "Evidence text",
                    "pages": [1],
                }
            ],
        },
        "cover_semantics": {
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "global",
            "evidence_density": "metric_rich",
            "domain_layer": "grid",
            "selection_reason": "Rising time-series evidence dominates the report.",
        },
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Old candidate",
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "metric": dict(METRIC),
                "pages": [1],
                "score": 1.0,
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Old final insight",
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "metric": dict(METRIC),
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Old final insight 2",
                "evidence_id": "f2",
                "evidence": "Evidence text 2",
                "metric": dict(METRIC),
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Old final insight 3",
                "evidence_id": "f3",
                "evidence": "Evidence text 3",
                "metric": dict(METRIC),
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Old final insight 4",
                "evidence_id": "f4",
                "evidence": "Evidence text 4",
                "metric": dict(METRIC),
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Old final insight 5",
                "evidence_id": "f5",
                "evidence": "Evidence text 5",
                "metric": dict(METRIC),
                "pages": [5],
            },
        ],
        "quotes_final": [
            {
                "text": "Old quote",
                "speaker": "Speaker",
                "citation": "Section",
                "page": 1,
                "evidence_id": "q1",
                "source_pack": "quote_candidates",
            }
        ],
        "expert_comment": "Old expert",
        "linkedin_post": "Old linkedin",
        "source_status": {
            "schema_version": "1.0",
            "text_density": 100.0,
            "density_threshold": 0.0,
            "pages_sampled": 1,
            "char_count": 100,
            "not_available": False,
            "reason": "",
            "evidence_present": True,
        },
    }


def _evidence_packs() -> dict:
    return {
        "doc_map": {
            "doc_id": "doc-1",
            "title": "Doc title",
            "sections": [
                {
                    "id": "sec-1",
                    "title": "Topic",
                    "summary": "Topic summary",
                    "pages": [1],
                }
            ],
        },
        "findings": {
            "findings": [
                {"id": "f1", "evidence": "Evidence text", "text": "Finding text"}
            ]
        },
        "quote_candidates": {
            "quote_candidates": [{"id": "q1", "text": "Old quote", "source": "Section"}]
        },
    }


def test_regenerate_artifacts_insights_bundle_uses_targeted_steps_and_preserves_untouched_sections(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        regenerate_steps=["insights_candidates", "insights_final"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/insights_candidates",
                            "report_vs/artifacts/regenerate/insights_final",
                        ],
                        issues=[
                            RegenerationIssue(
                                rule_id="metrics",
                                affected_section="insights:insight-1",
                                message="[metrics] Unsupported insight value",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["insights_candidates", "insights_final"]
    assert response.updated_artifacts["insights_candidates"] == []
    assert response.updated_artifacts["insights_final"] == []
    assert (
        response.updated_artifacts["family_status"]["insights_bundle"]["status"]
        == "abstained"
    )
    assert [call.path for call in response.updated_artifacts and []] == []
    assert response.artifacts_path == ""
    assert Path(response.candidate_artifacts_path).is_file()
    assert not (
        tmp_path / "out" / "report-1" / "report_analysis" / "artifacts.json"
    ).exists()

    rendered_paths = [call["path"] for call in prompt_client.render_calls]
    assert rendered_paths == [
        "report_vs/artifacts/regenerate/insights_candidates/system.yaml",
        "report_vs/artifacts/regenerate/insights_candidates/user.yaml",
        "report_vs/artifacts/regenerate/insights_final/system.yaml",
        "report_vs/artifacts/regenerate/insights_final/user.yaml",
    ]
    first_user_prompt = openai_client.calls[0].user_prompt
    assert "Unsupported insight value" in first_user_prompt
    assert "Evidence text" in first_user_prompt


def test_regenerate_artifacts_dispatches_summary_via_target_section_registry(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/wrong"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="executive_summary",
                                message="[grounding] Unsupported summary claim",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["summary"]
    assert response.prompt_namespaces == ["report_vs/artifacts/regenerate/summary"]
    assert [call["path"] for call in prompt_client.render_calls] == [
        "report_vs/artifacts/regenerate/summary/system.yaml",
        "report_vs/artifacts/regenerate/summary/user.yaml",
    ]


def test_regenerate_artifacts_refreshes_cover_semantics_from_retained_analysis(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="cover_semantics",
                        regenerate_steps=["cover_semantics"],
                        prompt_namespaces=["report_vs/artifacts/cover_semantics"],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["cover_semantics"]
    assert response.updated_artifacts["cover_semantics"]["selection_reason"] == (
        "A rising time series is the strongest visual story."
    )
    assert response.prompt_namespaces == ["report_vs/artifacts/cover_semantics"]


def test_regenerate_artifacts_summary_only_keeps_other_sections_unchanged(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="executive_summary",
                                message="[grounding] Unsupported summary claim",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["summary"]
    assert response.updated_artifacts["summary"]["tldr"] == "Repaired TLDR."
    assert (
        response.updated_artifacts["summary"]["card_tldr_compact"] == "Repaired TLDR."
    )
    assert (
        response.updated_artifacts["insights_final"][0]["text"] == "Old final insight"
    )
    assert response.updated_artifacts["quotes_final"][0]["text"] == "Old quote"


def test_regenerate_artifacts_applies_family_policy_to_unsupported_quotes(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    evidence_packs = _evidence_packs()
    evidence_packs["quote_candidates"] = {"quote_candidates": []}
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="quotes",
                        regenerate_steps=["quotes"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/quotes"],
                        issues=[
                            RegenerationIssue(
                                rule_id="quotes",
                                affected_section="quotes:1",
                                message="[quotes] Quote not verbatim",
                                severity="error",
                                evidence_ids=["sec-1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["quotes"]
    assert response.updated_artifacts["quotes_final"] == []
    assert (
        response.updated_artifacts["family_status"]["quotes"]["status"] == "abstained"
    )
    assert (
        response.updated_artifacts["family_status"]["quotes"]["reason"]
        == "quotes_missing_verbatim_source"
    )


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
    assert openai_client.calls == []
    assert prompt_client.render_calls == []


def test_regenerate_artifacts_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    class _RetryingOpenAI(_FakeOpenAIClient):
        def openai_chat_json(self, req, ctx):
            del req, ctx
            raise AppError(
                code="openai_chat_failed",
                message="retry later",
                retryable=True,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_RetryingOpenAI(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_chat_failed",
        retryable=True,
        severity="error",
    )


def test_regenerate_artifacts_propagates_non_retryable_prompt_error(
    tmp_path,
    assert_app_error,
):
    class _FailingPromptClient(_FakePromptClient):
        def load_prompt_set(self, req, ctx):
            del req, ctx
            raise AppError(
                code="prompt_not_found",
                message="missing prompt",
                retryable=False,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FailingPromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="prompt_not_found",
        retryable=False,
        severity="error",
    )


def test_regenerate_artifacts_rejects_unknown_target_section(
    tmp_path,
    assert_app_error,
):
    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="unsupported_section",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="artifact_regeneration_target_unsupported",
        retryable=False,
        severity="error",
    )
