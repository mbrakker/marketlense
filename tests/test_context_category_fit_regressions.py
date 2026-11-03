from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.categories import (
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryMappings,
)
from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ReportCategoryContext,
)
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyReuseResponse,
)
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.generators.context_category_fit_generator import (
    _rule_id,
    fit_report_categories_from_context,
)
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class _RecordingPromptClient:
    def load_prompt_set(self, request, ctx):
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate("1.0", "system.yaml", "System", "a" * 64),
            user=PromptTemplate(
                "1.0",
                "user.yaml",
                "User {report_context_json} {category_profiles_json}",
                "b" * 64,
            ),
            dependency_manifest=PromptDependencyManifest(
                schema_version="1.0",
                namespace=request.namespace,
                system_root=PromptDependency(
                    "1.0", "system.yaml", "a" * 64, "system_root"
                ),
                user_root=PromptDependency("1.0", "user.yaml", "b" * 64, "user_root"),
                prompt_content_hash="c" * 64,
            ),
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, request, ctx):
        try:
            text = request.template.text.format(**request.variables)
        except KeyError:
            text = request.template.text
        return SimpleNamespace(text=text)


class _RecordingOpenAIClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def openai_chat_json(self, request, ctx):
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


class _SequenceOpenAIClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.requests = []

    def openai_chat_json(self, request, ctx):
        self.requests.append((request, ctx))
        payload = self.payloads[min(len(self.requests) - 1, len(self.payloads) - 1)]
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            input_tokens=100,
            output_tokens=50,
            tool_calls=0,
            model=request.model,
            total_tokens=150,
            request_id=f"req-{len(self.requests)}",
        )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_model="gpt-5-mini",
        temperature=1.0,
        openai_models={},
        openai_api_key="test-key",
        openai_seed=None,
        openai_timeout_seconds=30.0,
        cost_ledger_path="./out/cost-ledger.jsonl",
        cost_daily_path="./out/cost-daily.json",
        model_pricing={"gpt-5-mini": {}},
        llm_execution_policies={
            "report_vs": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 1.0,
                "timeout_seconds": 30.0,
                "max_output_tokens": 800,
            }
        },
        reports_db="unused.sqlite",
        output_dir="./out",
    )


def _recorded_cases() -> list[dict]:
    path = (
        Path(__file__).parent
        / "fixtures/docpacks/golden/category_fit_regressions/cases.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _recorded_context(case: dict) -> ReportCategoryContext:
    context = case["context"]
    return ReportCategoryContext(
        schema_version="1.0",
        report_id=context["report_id"],
        title=context["title"],
        publisher="",
        region="",
        time_period="",
        overview=context["overview"],
        key_findings=list(context["key_findings"]),
    )


def _explicit_exclusion_mappings() -> CategoryMappings:
    return CategoryMappings(
        schema_version="1.3",
        categories=[
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Reports about technology shifts.",
                definition="Reports whose primary subject is enterprise technology.",
                include_when=["Evidence centers on enterprise technology shifts."],
                exclude_when=[
                    "Reject when technology is only an enabling theme inside a broader consumer or media report."
                ],
            )
        ],
        inference_rules=[],
        uncategorized=[],
    )


@pytest.mark.parametrize(
    "recorded_case", _recorded_cases(), ids=lambda case: case["id"]
)
def test_retained_category_fit_regression_cases(recorded_case: dict) -> None:
    """Close known contradictions with retained report/response evidence."""

    candidate = {
        **recorded_case["candidate"],
        "label": recorded_case["candidate"]["category_id"],
        # These retained cases now exercise the model-owned semantic verdict.
        # The technical boundary still canonicalizes the references and rejects
        # unknown rule identifiers, but it must not reconstruct the decision
        # from configured topic wording.
        "evidence_sections": ["overview"],
        "rule_evidence_sections": ["overview"],
        "centrality_evidence_sections": (
            ["title", "overview"] if recorded_case["expected"]["selected"] else []
        ),
        "semantic_rule_status": recorded_case["expected"]["status"],
        "supported_topic_rules": (
            ["model-confirmed inclusion"]
            if recorded_case["expected"]["status"] == "supported"
            else []
        ),
        "rejected_topic_rules": (
            ["model-confirmed exclusion"]
            if recorded_case["expected"]["status"] == "rejected"
            else []
        ),
    }
    mapping_client = load_category_mappings
    mapping_path = "src/config/category-mappings.yaml"
    if recorded_case["id"] == "explicit_exclusion_conflict":
        mappings = _explicit_exclusion_mappings()

        def mapping_client(request, ctx):
            del request, ctx
            return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

        mapping_path = "unused"
    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=_recorded_context(recorded_case),
            settings=_settings(),
            category_mapping_path=mapping_path,
            candidate_category_ids=[candidate["category_id"]],
        ),
        _ctx(),
        openai_client=_RecordingOpenAIClient(
            {
                "schema_version": "1.0",
                "selected_category_ids": (
                    [candidate["category_id"]]
                    if recorded_case["expected"]["selected"]
                    else []
                ),
                "category_fits": [candidate],
            }
        ),
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    expected = recorded_case["expected"]
    fit = response.fits[0]
    assert fit.decision == expected["decision"]
    assert fit.semantic_rule_status == expected["status"]
    assert response.categories == (
        [candidate["category_id"]] if expected["selected"] else []
    )
    assert all(
        item.decision in {"primary", "secondary"}
        and item.semantic_rule_status != "ambiguous"
        for item in response.fits
        if item.category_id in response.categories
    )
    if recorded_case["id"] == "explicit_exclusion_conflict":
        assert fit.rejected_topic_rules == ["model-confirmed exclusion"]
        assert fit.rule_evidence_sections == ["overview"]
    else:
        assert not fit.rejected_topic_rule_ids
    if expected["status"] == "supported":
        assert fit.supported_topic_rules == ["model-confirmed inclusion"]
        assert fit.centrality_evidence_sections


def test_model_rejection_is_not_overridden_by_central_context_text() -> None:
    """Category text cannot override the provider's semantic decision."""

    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-1",
        title="Enterprise Technology Shifts",
        publisher="Publisher",
        region="Global",
        time_period="2026",
        overview="Enterprise technology shifts are the report's central subject.",
        key_findings=["Technology shifts shape the operating model."],
    )
    mappings = CategoryMappings(
        schema_version="1.3",
        categories=[
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Reports about technology shifts.",
                definition="Reports whose primary subject is enterprise technology.",
                include_when=["Evidence centers on enterprise technology shifts."],
                exclude_when=[],
            )
        ],
        inference_rules=[],
        uncategorized=[],
        high_confidence_fit_threshold=0.95,
    )

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=_settings(),
            category_mapping_path="unused",
        ),
        _ctx(),
        openai_client=_RecordingOpenAIClient(
            {
                "schema_version": "1.0",
                "selected_category_ids": [],
                "category_fits": [
                    {
                        "category_id": "technology",
                        "label": "Technology & Innovation",
                        "fit_score": 0.95,
                        "decision": "reject",
                        "why_fit": "Enterprise technology is central.",
                        "why_not_fit": "",
                        "evidence_sections": ["overview"],
                    }
                ],
            }
        ),
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert response.categories == []
    assert response.fits[0].decision == "reject"
    assert response.fits[0].semantic_rule_status == "not_evaluated"


def test_topic_rule_conflict_reaches_bounded_model_recovery() -> None:
    """Post-coercion topic validation must not bypass structured recovery."""

    mappings = _explicit_exclusion_mappings()
    rule = mappings.categories[0].include_when[0]
    include_rule_id = _rule_id("technology", "include", 0, rule)

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-recovery",
        title="Enterprise technology shifts",
        publisher="Publisher",
        region="Global",
        time_period="2026",
        overview="Technology shifts are the central subject.",
        key_findings=["Technology operating models are changing."],
    )
    invalid = {
        "schema_version": "1.0",
        "selected_category_ids": ["technology"],
        "category_fits": [
            {
                "category_id": "technology",
                "label": "Technology & Innovation",
                "fit_score": 0.9,
                "decision": "primary",
                "why_fit": "Technology is central.",
                "why_not_fit": "",
                "evidence_sections": ["overview"],
                "rejected_topic_rule_ids": [include_rule_id],
            }
        ],
    }
    corrected = {
        **invalid,
        "category_fits": [
            {
                **invalid["category_fits"][0],
                "supported_topic_rule_ids": [include_rule_id],
                "rejected_topic_rule_ids": [],
            }
        ],
    }
    client = _SequenceOpenAIClient([invalid, corrected])

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=_settings(),
            category_mapping_path="unused",
            candidate_category_ids=["technology"],
        ),
        _ctx(),
        openai_client=client,
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert len(client.requests) == 2
    assert response.categories == ["technology"]
    assert response.fits[0].supported_topic_rule_ids == [include_rule_id]


def test_invalid_cached_category_fit_cannot_bypass_binding_validation() -> None:
    mappings = _explicit_exclusion_mappings()
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-cache-recovery",
        title="Enterprise technology shifts",
        publisher="Publisher",
        region="Global",
        time_period="2026",
        overview="Technology shifts are the central subject.",
        key_findings=["Technology operating models are changing."],
    )
    invalid_cached = {
        "schema_version": "1.0",
        "selected_category_ids": ["technology"],
        "category_fits": [
            {
                "category_id": "technology",
                "label": "Technology & Innovation",
                "fit_score": 0.9,
                "decision": "reject",
                "why_fit": "",
                "why_not_fit": "The category is not selected.",
                "evidence_sections": ["overview"],
            }
        ],
    }

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

    def reuse_reader(request, ctx):
        del request, ctx
        return PromptFamilyReuseResponse(
            schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
            reusable=True,
            reason="retained",
            output_payload=invalid_cached,
        )

    client = _SequenceOpenAIClient(
        [
            {
                "schema_version": "1.0",
                "selected_category_ids": ["technology"],
                "category_fits": [
                    {
                        "category_id": "technology",
                        "label": "Technology & Innovation",
                        "fit_score": 0.9,
                        "decision": "primary",
                        "why_fit": "Technology is central.",
                        "why_not_fit": "",
                        "evidence_sections": ["overview"],
                    }
                ],
            }
        ]
    )
    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=_settings(),
            category_mapping_path="unused",
            source_id="md5:file-cache-recovery",
        ),
        _ctx(),
        openai_client=client,
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
        prompt_family_reuse_reader=reuse_reader,
        prompt_family_materializer=lambda *_args: None,
    )

    assert len(client.requests) == 1
    assert response.categories == ["technology"]


def test_category_fit_selected_ids_must_match_declared_decisions() -> None:
    mappings = _explicit_exclusion_mappings()
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id="file-selection-contract",
        title="Enterprise technology shifts",
        publisher="Publisher",
        region="Global",
        time_period="2026",
        overview="Technology shifts are the central subject.",
        key_findings=["Technology operating models are changing."],
    )
    invalid = {
        "schema_version": "1.0",
        "selected_category_ids": [],
        "category_fits": [
            {
                "category_id": "technology",
                "label": "Technology & Innovation",
                "fit_score": 0.9,
                "decision": "primary",
                "why_fit": "Technology is central.",
                "why_not_fit": "",
                "evidence_sections": ["overview"],
            }
        ],
    }
    corrected = {**invalid, "selected_category_ids": ["technology"]}

    client = _SequenceOpenAIClient([invalid, corrected])
    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=context,
            settings=_settings(),
            category_mapping_path="unused",
            candidate_category_ids=["technology"],
        ),
        _ctx(),
        openai_client=client,
        prompt_client=_RecordingPromptClient(),
        mapping_client=lambda request, ctx: CategoryMappingLoadResponse(
            schema_version="1.0", mappings=mappings
        ),
    )

    assert len(client.requests) == 2
    assert response.categories == ["technology"]


def test_fit_report_categories_retains_five_evidence_backed_categories() -> None:
    """The public category contract permits one primary and four secondaries."""

    category_ids = ["commerce", "media", "ai", "search", "consumer"]
    mappings = CategoryMappings(
        schema_version="1.0",
        categories=[
            CategoryDefinition(
                id=category_id,
                label=category_id.title(),
                description=f"{category_id} reports.",
                definition=f"Reports about {category_id}.",
                include_when=[f"Evidence centers on {category_id} strategy."],
                semantic_concepts=[category_id],
            )
            for category_id in category_ids
        ],
        inference_rules=[],
        uncategorized=[],
    )

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=ReportCategoryContext(
                schema_version="1.0",
                report_id="file-1",
                title="Commerce, media, AI, search, and consumer behavior outlook",
                publisher="Publisher",
                region="Global",
                time_period="2026",
                overview="The report centrally examines commerce, media, AI, search, and consumer behavior strategy.",
            ),
            settings=_settings(),
            category_mapping_path="unused",
        ),
        _ctx(),
        openai_client=_RecordingOpenAIClient(
            {
                "schema_version": "1.0",
                "selected_category_ids": category_ids,
                "category_fits": [
                    {
                        "category_id": category_id,
                        "label": category_id.title(),
                        "fit_score": 1.0 - (index * 0.1),
                        "decision": "primary" if index == 0 else "secondary",
                        "why_fit": f"{category_id} is central.",
                        "why_not_fit": "",
                        "evidence_sections": ["overview"],
                        "semantic_rule_status": "supported",
                    }
                    for index, category_id in enumerate(category_ids)
                ],
            }
        ),
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert response.categories == category_ids
    assert response.category_labels == [
        category_id.title() for category_id in category_ids
    ]
    assert all(fit.semantic_rule_status == "supported" for fit in response.fits)


def test_fit_report_categories_does_not_rescue_omitted_model_candidates() -> None:
    """An omitted category remains omitted until the model supplies a fit."""

    mappings = CategoryMappings(
        schema_version="1.0",
        categories=[
            CategoryDefinition(
                id="consumer_behavior",
                label="Consumer Behavior & Insights",
                description="Consumer behavior reports.",
                definition="Reports about consumer behavior.",
                include_when=["Evidence studies consumer behavior."],
                semantic_concepts=["consumer time"],
            ),
            CategoryDefinition(
                id="technology",
                label="Technology & Innovation",
                description="Technology reports.",
                definition="Reports about technology.",
                include_when=["Evidence studies enterprise technology."],
            ),
        ],
        inference_rules=[],
        uncategorized=[],
    )

    def mapping_client(request, ctx):
        del request, ctx
        return CategoryMappingLoadResponse(schema_version="1.0", mappings=mappings)

    response = fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=ReportCategoryContext(
                schema_version="1.0",
                report_id="file-1",
                title="Consumer Time & Attention",
                publisher="Publisher",
                region="Global",
                time_period="2026",
                overview="A report about how consumers allocate their daily time.",
            ),
            settings=_settings(),
            category_mapping_path="unused",
        ),
        _ctx(),
        openai_client=_RecordingOpenAIClient(
            {
                "schema_version": "1.0",
                "selected_category_ids": [],
                "category_fits": [
                    {
                        "category_id": "technology",
                        "label": "Technology & Innovation",
                        "fit_score": 0.1,
                        "decision": "reject",
                        "why_fit": "",
                        "why_not_fit": "Technology is not central.",
                        "evidence_sections": [],
                    }
                ],
            }
        ),
        prompt_client=_RecordingPromptClient(),
        mapping_client=mapping_client,
    )

    assert response.categories == []
    assert [fit.category_id for fit in response.fits] == ["technology"]
    assert response.fits[0].semantic_rule_status == "not_evaluated"
