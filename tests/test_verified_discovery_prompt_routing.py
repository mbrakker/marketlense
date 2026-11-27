import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
    resolve_routing_policy,
    routing_policies_from_config,
)
from tests._test_evidence_pack_generator._shared import (
    FakeAnalysisStore,
    FakePromptClient,
    RecordingPromptClient,
    RoutedOpenAIClient,
    _ctx,
    _settings,
    substantive_doc_map,
)


def test_verified_discovery_exposes_methodology_page_without_keyword_filter(tmp_path):
    source = "The methodology describes 3,000 respondents across two regions."
    doc_map = {
        "doc_id": "report",
        "title": "Research report",
        "summary": "Study scope and population.",
        "sections": [
            {
                "id": "methods",
                "title": "Methodology",
                "summary": source,
                "key_points": [source],
                "pages": [4],
            }
        ],
    }
    prompts = RecordingPromptClient()
    generate_evidence_packs(
        report_id="report",
        report_name="report.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=[{"id": "p4", "page": 4, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": doc_map,
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "text": source,
                            "evidence": source,
                            "pages": [4],
                            "section_id": "methods",
                            "section_title": "Methodology",
                        }
                    ]
                },
            }
        ),
        prompt_client=prompts,
        analysis_store=FakeAnalysisStore(),
    )
    assert any(
        entry["page"] == 4
        for entry in json.loads(
            prompts.findings_variables["findings_target_source_pages_json"]
        )
    )


def test_verified_discovery_leaves_paraphrase_coverage_to_fallback_model(tmp_path):
    source = "The study found a 40 percent response rate among retailers."
    doc_map = {
        "doc_id": "report",
        "title": "Research report",
        "summary": "Survey findings.",
        "sections": [
            {
                "id": "results",
                "title": "Results",
                "summary": source,
                "key_points": ["Four in ten retailers responded."],
                "pages": [4],
            }
        ],
    }

    class RecordingClient(RoutedOpenAIClient):
        def __init__(self):
            super().__init__(
                {
                    "doc_map": doc_map,
                    "findings": {
                        "findings": [
                            {
                                "id": "f1",
                                "text": source,
                                "evidence": source,
                                "pages": [4],
                                "section_id": "results",
                                "section_title": "Results",
                            }
                        ]
                    },
                }
            )
            self.tasks = []

        def openai_respond_with_vector_store(self, request, ctx):
            self.tasks.append(ctx.task_id)
            return super().openai_respond_with_vector_store(request, ctx)

        def openai_chat_json(self, request, ctx):
            self.tasks.append(ctx.task_id)
            return super().openai_chat_json(request, ctx)

    client = RecordingClient()
    prompts = RecordingPromptClient()
    generate_evidence_packs(
        report_id="report",
        report_name="report.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=[{"id": "p4", "page": 4, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=client,
        prompt_client=prompts,
        analysis_store=FakeAnalysisStore(),
    )
    assert sum("targeted_fallback" in task for task in client.tasks) == 1
    assert (
        json.loads(prompts.findings_variables["findings_existing_json"])[0]["id"]
        == "f1"
    )


def test_verified_discovery_uses_declared_page_hints_without_semantic_page_ranking(
    tmp_path,
):
    doc_map = {
        "doc_id": "report",
        "title": "Research report",
        "summary": "Study.",
        "sections": [
            {
                "id": "topic",
                "title": "Section",
                "summary": "Context.",
                "key_points": ["Rocket revenue reached 10 percent."],
                "pages": [4],
            }
        ],
    }
    source = "Page four has different contextual text."
    prompts = RecordingPromptClient()
    generate_evidence_packs(
        report_id="report",
        report_name="report.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=[
            {"id": "p4", "page": 4, "text": source},
            {"id": "p5", "page": 5, "text": "Rocket revenue reached 10 percent."},
        ],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": doc_map,
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "text": "A provisional claim.",
                            "evidence": source,
                            "pages": [4],
                            "section_id": "topic",
                            "section_title": "Section",
                        }
                    ]
                },
            }
        ),
        prompt_client=prompts,
        analysis_store=FakeAnalysisStore(),
    )
    pages = json.loads(prompts.findings_variables["findings_target_source_pages_json"])
    assert [page["page"] for page in pages] == [4]


@pytest.mark.parametrize("workers", [1, 3])
@pytest.mark.parametrize("verified", [False, True])
def test_findings_discovery_selects_mode_specific_prompt(tmp_path, workers, verified):
    class RecordingPrompts(FakePromptClient):
        def __init__(self):
            self.namespaces = []

        def load_prompt_set(self, request, ctx):
            self.namespaces.append(request.namespace)
            return super().load_prompt_set(request, ctx)

    prompts = RecordingPrompts()
    generate_evidence_packs(
        report_id="discovery",
        report_name="discovery.pdf",
        vector_store_id="vs_discovery",
        settings=replace(
            _settings(
                tmp_path, evidence_pack_registry=["doc_map", "findings", "scope"]
            ),
            evidence_pack_parallel_workers=workers,
        ),
        ctx=replace(_ctx(), task_id="discovery"),
        openai_client=RoutedOpenAIClient({"doc_map": substantive_doc_map()}),
        prompt_client=prompts,
        analysis_store=FakeAnalysisStore(),
        visual_ambiguity_source_identity="source:test" if verified else "",
    )
    expected = "report_vs/evidence_packs/findings"
    if verified:
        expected += "/visual_discovery"
    assert expected in prompts.namespaces
    assert "report_vs/evidence_packs/scope" in prompts.namespaces
    assert ("report_vs/evidence_packs/findings" in prompts.namespaces) is not verified


@pytest.mark.parametrize(
    "parent",
    ["report_vs/evidence_packs/findings", "report_vs/artifacts/insights_candidates"],
)
def test_visual_discovery_inherits_model_and_execution_policy(parent):
    config = yaml.safe_load(Path("src/config/app.yaml").read_text(encoding="utf-8"))
    models = config["openai_models"]
    routing = routing_policies_from_config(
        config["llm_routing"], model_overrides=models
    )
    policies = execution_policies_from_config(
        config.get("llm_execution_policies", {}),
        model_overrides=models,
        legacy_routing=config["llm_routing"],
        default_model="gpt-6-luna",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=None,
    )
    child = parent + "/visual_discovery"
    first = resolve_routing_policy(parent, routing, default_model="gpt-6-luna")
    second = resolve_routing_policy(child, routing, default_model="gpt-6-luna")
    assert first.model == second.model
    assert first.tier == second.tier
    assert first.max_input_tokens == second.max_input_tokens
    options = {
        "default_model": "gpt-6-luna",
        "default_temperature": 1.0,
        "default_seed": None,
        "default_timeout_seconds": None,
        "require_registered_namespace": True,
    }
    assert resolve_execution_policy(parent, policies, **options).policy == (
        resolve_execution_policy(child, policies, **options).policy
    )


def test_candidate_prompt_defers_chart_relationships_only_in_provisional_mode():
    normal_prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0", namespace="report_vs/artifacts/insights_candidates"
        ),
        _ctx(),
    )
    verified_prompt = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="report_vs/artifacts/insights_candidates/visual_discovery",
        ),
        _ctx(),
    )
    variables = {
        "doc_map_json": "{}",
        "evidence_json": "{}",
        "editorial_plan_json": "{}",
        "candidate_allowed_evidence_ids_json": "[]",
    }

    def render(prompt):
        return render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt.user,
                variables=variables,
            ),
            _ctx(),
        ).text

    verified = render(verified_prompt)
    normal = render(normal_prompt)
    assert "provisional hypotheses" in verified
    assert "Use numbers only when its" not in verified
    assert "Use numbers only when its" in normal
