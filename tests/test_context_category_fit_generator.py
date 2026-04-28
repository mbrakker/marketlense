from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.contracts.categories import (
    CategoryClassificationConfig,
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ReportCategoryContext,
    ReportContextBuildRequest,
)
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.run_context import RunContext
from src.generators.context_category_fit_generator import (
    fit_report_categories_from_context,
)
from src.generators.report_context_generator import build_report_category_context


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class RecordingPromptClient:
    def load_prompt_set(self, request, ctx):
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/system.yaml",
                text="System prompt",
                sha256="system-sha",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/user.yaml",
                text="User prompt {report_context_json} {category_profiles_json}",
                sha256="user-sha",
            ),
        )

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text.format(**request.variables))


class RecordingOpenAIClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []

    def openai_chat_json(self, request, ctx):
        self.requests.append((request, ctx))
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(self.payload),
            parsed_json=self.payload,
            input_tokens=100,
            output_tokens=50,
            tool_calls=0,
            model=request.model,
            total_tokens=150,
            request_id="req-1",
        )


def test_build_report_category_context_compacts_evidence_packs(
    tmp_path: Path,
    assert_no_defaulted_required_fields,
) -> None:
    doc_map_path = tmp_path / "doc_map.json"
    scope_path = tmp_path / "scope.json"
    methods_path = tmp_path / "methods.json"
    findings_path = tmp_path / "findings.json"
    limitations_path = tmp_path / "limitations.json"
    doc_map_path.write_text(
        json.dumps(
            {
                "title": "Tech Trends 2026",
                "publisher": "Deloitte",
                "summary": "A report about major enterprise technology shifts and AI adoption.",
                "sections": [
                    {
                        "id": "1",
                        "title": "AI platforms",
                        "summary": "Enterprise AI platforms are becoming operating layers.",
                        "key_points": [
                            "Agentic systems are moving into production.",
                            "Infrastructure choices matter more than novelty.",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    scope_path.write_text(
        json.dumps({"scope": "Global enterprise technology outlook for 2026."}),
        encoding="utf-8",
    )
    methods_path.write_text(
        json.dumps({"methods": ["Interviews with CIOs", "Cross-industry survey"]}),
        encoding="utf-8",
    )
    findings_path.write_text(
        json.dumps(
            {
                "findings": [
                    {"id": "f1", "text": "AI agents are becoming operational tooling."},
                    {"id": "f2", "text": "Cybersecurity remains a core board concern."},
                ]
            }
        ),
        encoding="utf-8",
    )
    limitations_path.write_text(
        json.dumps({"limitations": ["Forward-looking analysis includes uncertainty."]}),
        encoding="utf-8",
    )
    report = ReportMetadataGetResponse(
        schema_version="1.1",
        file_id="file-1",
        title="Tech Trends 2026",
        created_at=1,
        updated_at=2,
        file_name="tech-trends.pdf",
        publisher="Deloitte",
        taxonomy=[],
        categories=[],
        region="Global",
        time_period="2026",
        source_url=None,
        html_path=None,
        md5=None,
        page_count=None,
        contents_page_number=0,
        pdf_metadata={},
        analysis_mode="vector_store",
        vector_store_id="vs",
        evidence_pack_paths={
            "doc_map": str(doc_map_path),
            "scope": str(scope_path),
            "methods": str(methods_path),
            "findings": str(findings_path),
            "limitations": str(limitations_path),
        },
    )

    context = build_report_category_context(
        ReportContextBuildRequest(schema_version="1.0", report=report),
        _ctx(),
    )

    assert "enterprise technology shifts" in context.overview
    assert context.methods == ["Interviews with CIOs", "Cross-industry survey"]
    assert context.key_findings[0] == "AI agents are becoming operational tooling."
    assert context.sections[0].section_label == "AI platforms"
    assert context.sections[0].source_pack == "doc_map"
    assert_no_defaulted_required_fields(context)
    assert_no_defaulted_required_fields(context.sections[0])


def test_fit_report_categories_from_context_returns_selected_categories(
    assert_no_defaulted_required_fields,
) -> None:
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-1",
        title="Tech Trends 2026",
        publisher="Deloitte",
        region="Global",
        time_period="2026",
        overview="A report about enterprise technology shifts and AI adoption.",
        methods=["Interviews with CIOs"],
        key_findings=["AI agents are becoming operational tooling."],
        limitations=["Forward-looking analysis includes uncertainty."],
        sections=[],
    )
    mappings = CategoryMappings(
        schema_version="1.0",
        categories=[
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Reports about major technology shifts, enterprise systems, and innovation.",
                definition="Reports whose primary subject is enterprise technology platforms, infrastructure, and technology change.",
                include_when=[
                    "Repeated evidence centers on enterprise technology shifts or infrastructure decisions."
                ],
                exclude_when=[
                    "Reject when technology is only an enabling theme inside a broader consumer or media report."
                ],
            ),
            CategoryDefinition(
                id="ai_automation",
                label="AI & Automation",
                description="Reports whose central subject is AI systems, automation, and agentic execution.",
                definition="Reports mainly about AI systems, automation, agents, or workflow transformation driven by AI.",
                include_when=[
                    "Evidence repeatedly focuses on AI agents, automation systems, or AI operating models."
                ],
                exclude_when=[
                    "Reject when AI is only one feature inside a broader technology market overview."
                ],
            ),
        ],
        classification=CategoryClassificationConfig(),
        inference_rules=[],
        uncategorized=[],
    )

    def mapping_client(request, ctx):
        return CategoryMappingLoadResponse(
            schema_version="1.0",
            mappings=mappings,
        )

    openai_client = RecordingOpenAIClient(
        payload={
            "schema_version": "1.0",
            "selected_category_ids": ["technology", "ai_automation"],
            "category_fits": [
                {
                    "category_id": "technology",
                    "label": "Technology & Innovation",
                    "fit_score": 0.93,
                    "decision": "primary",
                    "why_fit": "The report is centrally about major enterprise technology shifts.",
                    "why_not_fit": "",
                    "evidence_sections": ["Overview"],
                },
                {
                    "category_id": "ai_automation",
                    "label": "AI & Automation",
                    "fit_score": 0.79,
                    "decision": "secondary",
                    "why_fit": "AI agents are one of the report's main recurring themes.",
                    "why_not_fit": "",
                    "evidence_sections": ["Key finding 1"],
                },
                {
                    "category_id": "consumer_behavior",
                    "label": "Consumer Behavior & Insights",
                    "fit_score": 0.11,
                    "decision": "reject",
                    "why_fit": "",
                    "why_not_fit": "The report is not mainly about shoppers or audiences.",
                    "evidence_sections": [],
                },
            ],
        }
    )
    settings = SimpleNamespace(
        openai_model="gpt-5-mini",
        openai_models={},
        openai_api_key="test-key",
        openai_seed=None,
        openai_timeout_seconds=30.0,
        cost_ledger_path="./out/cost-ledger.jsonl",
        cost_daily_path="./out/cost-daily.json",
        model_pricing={"gpt-5-mini": {}},
    )

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=settings,
            category_mapping_path="unused",
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert response.categories == ["technology", "ai_automation"]
    assert response.category_labels == ["Technology & Innovation", "AI & Automation"]
    assert response.fits[0].decision == "primary"
    assert response.fits[1].decision == "secondary"
    assert openai_client.requests[0][0].model == "gpt-5-mini"
    assert "enterprise technology platforms" in openai_client.requests[0][0].user_prompt
    assert "include_when" in openai_client.requests[0][0].user_prompt
    assert "exclude_when" in openai_client.requests[0][0].user_prompt
    assert_no_defaulted_required_fields(response)
    assert_no_defaulted_required_fields(response.fits[0])


def test_fit_report_categories_from_context_defaults_missing_optional_fields() -> None:
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-1",
        title="Tech Trends 2026",
        publisher="Deloitte",
        region="Global",
        time_period="2026",
        overview="A report about enterprise technology shifts and AI adoption.",
        methods=["Interviews with CIOs"],
        key_findings=["AI agents are becoming operational tooling."],
        limitations=["Forward-looking analysis includes uncertainty."],
        sections=[],
    )
    mappings = CategoryMappings(
        schema_version="1.0",
        categories=[
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Reports about major technology shifts, enterprise systems, and innovation.",
                definition="Reports whose primary subject is enterprise technology platforms, infrastructure, and technology change.",
                include_when=[
                    "Repeated evidence centers on enterprise technology shifts or infrastructure decisions."
                ],
                exclude_when=[
                    "Reject when technology is only an enabling theme inside a broader consumer or media report."
                ],
            )
        ],
        classification=CategoryClassificationConfig(),
        inference_rules=[],
        uncategorized=[],
    )

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(
            schema_version="1.0",
            mappings=mappings,
        )

    openai_client = RecordingOpenAIClient(
        payload={
            "schema_version": "1.0",
            "selected_category_ids": ["technology"],
            "category_fits": [
                {
                    "category_id": "technology",
                    "label": "Technology & Innovation",
                    "fit_score": 0.93,
                    "decision": "primary",
                    "why_fit": "The report is centrally about major enterprise technology shifts.",
                }
            ],
        }
    )
    settings = SimpleNamespace(
        openai_model="gpt-5-mini",
        openai_models={},
        openai_api_key="test-key",
        openai_seed=None,
        openai_timeout_seconds=30.0,
        cost_ledger_path="./out/cost-ledger.jsonl",
        cost_daily_path="./out/cost-daily.json",
        model_pricing={"gpt-5-mini": {}},
    )

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=settings,
            category_mapping_path="unused",
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert response.categories == ["technology"]
    assert response.fits[0].why_not_fit == ""
    assert response.fits[0].evidence_sections == []
