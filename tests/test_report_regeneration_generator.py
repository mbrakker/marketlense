from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.ingest import IngestSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import (
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
        )

    def render_prompt(self, req, ctx):
        del ctx
        rendered = f"{req.template.text}|{json.dumps(req.variables, sort_keys=True, ensure_ascii=False)}"
        self.render_calls.append(
            {"path": req.template.path, "variables": dict(req.variables), "text": rendered}
        )
        return PromptRenderResponse(schema_version="1.0", text=rendered)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def openai_chat_json(self, req, ctx):
        del ctx
        self.calls.append(req)
        if (
            "system::report_vs/artifacts/regenerate/insights_final"
            in req.system_prompt
        ):
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
                text='{"summary":{"tldr":"Repaired TLDR","executive_summary":"Repaired executive summary","claim_evidence_map":[{"claim":"Grounded claim","evidence_id":"f1","evidence":"Evidence text","pages":[1]}]}}',
                parsed_json={
                    "summary": {
                        "tldr": "Repaired TLDR",
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
    )


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def _current_artifacts() -> dict:
    return {
        "schema_version": "1.0",
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "Old TLDR",
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
            }
        ],
        "quotes_final": [
            {
                "text": "Old quote",
                "speaker": "Speaker",
                "citation": "Section",
                "page": 1,
                "evidence_id": "q1",
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
            "sections": [{"id": "sec-1", "title": "Topic", "summary": "Topic summary", "pages": [1]}],
        },
        "findings": {
            "findings": [
                {"id": "f1", "evidence": "Evidence text", "text": "Finding text"}
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {"id": "q1", "text": "Old quote", "source": "Section"}
            ]
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
    assert response.updated_artifacts["insights_candidates"][0]["text"] == "Repaired candidate"
    assert response.updated_artifacts["insights_final"][0]["text"] == "Repaired final insight"
    assert response.updated_artifacts["expert_comment"] == "Old expert"
    assert response.updated_artifacts["linkedin_post"] == "Old linkedin"
    assert [call.path for call in response.updated_artifacts and []] == []

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
    assert response.updated_artifacts["summary"]["tldr"] == "Repaired TLDR"
    assert response.updated_artifacts["insights_final"][0]["text"] == "Old final insight"
    assert response.updated_artifacts["quotes_final"][0]["text"] == "Old quote"


def test_regenerate_artifacts_propagates_retryable_app_error(tmp_path, assert_app_error):
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
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FailingPromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="prompt_not_found",
        retryable=False,
        severity="error",
    )
