from __future__ import annotations

from types import SimpleNamespace

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ReportCategoryContext,
)
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyReuseResponse,
)
from src.generators.context_category_fit_generator import (
    fit_report_categories_from_context,
)
from tests.test_context_category_fit_generator import (
    RecordingPromptClient,
    _ctx,
    _execution_policies,
)


def test_context_category_fit_reuses_retained_primary_output_before_model_call() -> None:
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-reused",
        title="Technology outlook",
        publisher="Deloitte",
        region="Global",
        time_period="2026",
        overview="Enterprise technology and AI adoption.",
        methods=[],
        key_findings=["AI agents are operational tooling."],
        limitations=[],
        sections=[],
    )
    mappings = CategoryMappings(
        schema_version="1.0",
        categories=[
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Technology reports.",
                definition="Technology subject matter.",
                portal_exposed=True,
                core_tags=["technology"],
                include_when=["technology"],
            )
        ],
        inference_rules=[],
        uncategorized=[],
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
        llm_execution_policies=_execution_policies(),
        reports_db="unused.sqlite",
        output_dir="./out",
    )
    calls: list[object] = []

    def reader(_request, _ctx):
        return PromptFamilyReuseResponse(
            schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
            reusable=True,
            reason="reused",
            output_payload={
                "schema_version": "1.0",
                "selected_category_ids": ["technology"],
                "category_fits": [
                    {
                        "category_id": "technology",
                        "label": "Technology & Innovation",
                        "fit_score": 0.95,
                        "decision": "primary",
                        "why_fit": "Technology is the central topic.",
                        "why_not_fit": "",
                        "evidence_sections": ["Overview"],
                    }
                ],
            },
        )

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=settings,
            category_mapping_path="unused",
            source_id="md5:file-reused",
        ),
        _ctx(),
        openai_client=SimpleNamespace(
            openai_chat_json=lambda *_args: calls.append("model_called")
        ),
        prompt_client=RecordingPromptClient(),
        mapping_client=lambda _request, _ctx: CategoryMappingLoadResponse(
            schema_version="1.0", mappings=mappings
        ),
        prompt_family_reuse_reader=reader,
        prompt_family_materializer=lambda *_args: None,
    )

    assert calls == []
    assert response.categories == ["technology"]
