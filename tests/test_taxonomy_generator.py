import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptSet,
    PromptTemplate,
)
from src.contracts.run_context import RunContext
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.generators.taxonomy_generator import extract_taxonomy
from src.utils.errors import AppError


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        system = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/system",
            text="system",
            sha256="sys-sha",
        )
        user = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/user",
            text="user {{ report_title }} {{ allowed_tags_json }}",
            sha256="user-sha",
        )
        return PromptSet(
            schema_version="1.0",
            system=system,
            user=user,
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
        return SimpleNamespace(text=request.template.text)


class FakeOpenAI:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        self.last_request = None

    def openai_respond_with_vector_store(self, req, ctx):
        self.calls += 1
        self.last_request = req
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(self.payload),
            parsed_json=self.payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )


class FailIfCalledOpenAI:
    def __init__(self):
        self.calls = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.calls += 1
        raise AssertionError(
            "openai_respond_with_vector_store should not be called on cache hit"
        )


class RetryableFailingOpenAI:
    def openai_respond_with_vector_store(self, req, ctx):
        del req, ctx
        raise AppError(
            code="openai_request_failed",
            message="retry taxonomy extraction",
            retryable=True,
        )


class InvalidJsonOpenAI:
    def openai_respond_with_vector_store(self, req, ctx):
        del ctx
        return OpenAIResponseResult(
            schema_version="1.0",
            text='{"taxonomy": ["digital_payments"]',
            parsed_json=None,
            input_tokens=11,
            output_tokens=7,
            tool_calls=0,
            model=req.model,
        )


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="taxonomy", span_id="s")


def _write_mapping(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: '1.2'",
                "categories:",
                "  - id: payments",
                "    label: Payments",
                "    description: Payments category",
                "    definition: Reports whose main subject is payment systems, payment adoption, or payment infrastructure.",
                "    include_when:",
                "      - Evidence repeatedly focuses on payment behavior, rails, wallets, or checkout infrastructure.",
                "    exclude_when:",
                "      - Reject when payments appear only as one supporting section inside a broader retail report.",
                "    tags:",
                "      - digital_payments",
                "      - retail_logistics",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_mapping_with_inference_rule(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: '1.2'",
                "categories:",
                "  - id: ai_automation",
                "    label: AI",
                "    description: AI category",
                "    definition: Reports mainly about AI systems, agents, and automation.",
                "    include_when:",
                "      - Evidence repeatedly focuses on AI systems, agents, automation, or AI operating models.",
                "    exclude_when:",
                "      - Reject when AI is only one enabling tool inside a broader industry report.",
                "    core_tags:",
                "      - Generative AI and AI agents",
                "      - Synthetic data and augmented audiences",
                "  - id: agentic_commerce",
                "    label: Agentic Commerce",
                "    description: Agentic commerce category",
                "    definition: Reports mainly about AI agents acting directly in shopping, buying, or checkout journeys.",
                "    include_when:",
                "      - Evidence repeatedly covers AI-led shopping, purchase, or checkout execution.",
                "    exclude_when:",
                "      - Reject when commerce is only one example inside a broader AI trends report.",
                "    core_tags:",
                "      - agentic_commerce",
                "inference_rules:",
                "  - name: ai_agents_to_agentic_commerce",
                "    target_category_id: agentic_commerce",
                "    trigger_tags:",
                "      - Generative AI and AI agents",
                "    inferred_tag: agentic_commerce",
                "    inferred_tier: secondary",
                "    context_keywords_any:",
                "      - purchase",
                "      - shopping",
                "      - checkout",
                "      - commerce",
                "      - retail",
                "    remove_tags:",
                "      - Synthetic data and augmented audiences",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _settings(
    tmp_path: Path, mapping_path: Path, *, vector_store_keep: bool = True
) -> AppSettings:
    return AppSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        publisher_profiles_path=str(tmp_path / "publisher-profiles.json"),
        category_mapping_path=str(mapping_path),
        cover_style_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        taxonomy_temperature=0.2,
        openai_seed=7,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=vector_store_keep,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.003,
                "output_tokens_per_1k_usd": 0.006,
                "tool_call_usd": 0.0,
            }
        },
    )


def _request(settings: AppSettings) -> TaxonomyExtractRequest:
    return TaxonomyExtractRequest(
        schema_version="1.0",
        report_id="report-1",
        report_title="Retail Trends 2026",
        vector_store_id="vs_1",
        settings=settings,
        md5="md5-report-1",
        vector_store_content_hash="verified-vector-content",
        report_slug="report-1-slug",
    )


def _cache_path(settings: AppSettings) -> Path:
    return (
        Path(settings.output_dir)
        / "report-1-slug"
        / "report_analysis"
        / "taxonomy.json"
    )


def test_taxonomy_invalid_json_is_a_typed_failure_not_empty_success(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping(mapping_path)

    with pytest.raises(AppError) as exc_info:
        extract_taxonomy(
            _request(_settings(tmp_path, mapping_path, vector_store_keep=False)),
            _ctx(),
            openai_client=InvalidJsonOpenAI(),
            prompt_client=FakePromptClient(),
        )

    assert exc_info.value.code == "taxonomy_invalid_json"
    assert exc_info.value.retryable is False
    assert exc_info.value.context["artifact_family"] == "taxonomy"
    assert exc_info.value.context["response_chars"] > 0


def test_taxonomy_materializes_primary_output_with_provenance(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping(mapping_path)
    settings = _settings(tmp_path, mapping_path)
    fake_openai = FakeOpenAI(
        {
            "schema_version": "1.0",
            "taxonomy": ["digital_payments", "wallets"],
            "primary_tags": ["digital_payments"],
            "secondary_tags": ["wallets"],
            "tag_evidence": [
                {
                    "tag": "digital_payments",
                    "tier": "primary",
                    "section_label": "Executive Summary",
                    "evidence": "Payments are shifting to digital rails.",
                },
                {
                    "tag": "wallets",
                    "tier": "secondary",
                    "section_label": "Future Outlook",
                    "evidence": "Wallet adoption keeps rising.",
                },
            ],
            "region": "US",
            "time_period": "2026",
            "not_found_reason": "",
        }
    )

    response = extract_taxonomy(
        _request(settings),
        _ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
    )

    assert fake_openai.calls == 1
    assert response.taxonomy == ["digital_payments", "wallets"]
    assert response.primary_tags == ["digital_payments"]
    assert response.secondary_tags == ["wallets"]
    assert len(response.tag_evidence) == 2
    assert response.tag_evidence[1].tag == "wallets"
    assert response.tag_evidence[1].tier == "secondary"
    assert fake_openai.last_request is not None
    assert fake_openai.last_request.temperature == 0.2
    retained = next((Path(settings.output_dir)).rglob("prompt_family_*.json"))
    retained_payload = json.loads(retained.read_text(encoding="utf-8"))
    assert retained_payload["family_id"] == "report_vs/taxonomy"
    assert retained_payload["output"]["primary_tags"] == ["digital_payments"]
    assert (
        retained_payload["output"]["tag_evidence"][1]["section_label"]
        == "Future Outlook"
    )


def test_taxonomy_materialized_family_bypasses_openai(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping(mapping_path)
    settings = _settings(tmp_path, mapping_path)
    req = _request(settings)

    first_openai = FakeOpenAI(
        {
            "schema_version": "1.0",
            "taxonomy": ["digital_payments", "retail_logistics"],
            "primary_tags": ["digital_payments"],
            "secondary_tags": ["retail_logistics"],
            "tag_evidence": [
                {
                    "tag": "digital_payments",
                    "tier": "primary",
                    "section_label": "Executive Summary",
                    "evidence": "Digital payments are core.",
                },
                {
                    "tag": "retail_logistics",
                    "tier": "secondary",
                    "section_label": "Operations",
                    "evidence": "Logistics upgrades remain material.",
                },
            ],
            "region": "US",
            "time_period": "2026",
            "not_found_reason": "",
        }
    )
    first_response = extract_taxonomy(
        req,
        _ctx(),
        openai_client=first_openai,
        prompt_client=FakePromptClient(),
    )
    assert first_openai.calls == 1

    second_openai = FailIfCalledOpenAI()
    second_response = extract_taxonomy(
        req,
        _ctx(),
        openai_client=second_openai,
        prompt_client=FakePromptClient(),
    )

    assert second_openai.calls == 0
    assert second_response.taxonomy == first_response.taxonomy
    assert second_response.primary_tags == first_response.primary_tags
    assert second_response.secondary_tags == first_response.secondary_tags
    assert second_response.tag_evidence == first_response.tag_evidence
    assert second_response.region == first_response.region
    assert second_response.time_period == first_response.time_period


def test_taxonomy_corrupt_cache_falls_back_to_openai(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping(mapping_path)
    settings = _settings(tmp_path, mapping_path)
    path = _cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    fake_openai = FakeOpenAI(
        {
            "schema_version": "1.0",
            "taxonomy": ["retail_logistics"],
            "region": "EU",
            "time_period": "2025",
            "not_found_reason": "",
        }
    )
    response = extract_taxonomy(
        _request(settings),
        _ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
    )

    assert fake_openai.calls == 1
    assert response.taxonomy == ["retail_logistics"]


def test_taxonomy_infers_agentic_commerce_from_ai_purchase_evidence(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping_with_inference_rule(mapping_path)
    settings = _settings(tmp_path, mapping_path)
    fake_openai = FakeOpenAI(
        {
            "schema_version": "1.0",
            "taxonomy": [
                "Generative AI and AI agents",
                "Synthetic data and augmented audiences",
            ],
            "primary_tags": ["Generative AI and AI agents"],
            "secondary_tags": ["Synthetic data and augmented audiences"],
            "tag_evidence": [
                {
                    "tag": "Generative AI and AI agents",
                    "tier": "primary",
                    "section_label": "Brand building with AI",
                    "evidence": "Purchase decisions will increasingly be mediated by AI agents across commerce journeys.",
                },
                {
                    "tag": "Synthetic data and augmented audiences",
                    "tier": "secondary",
                    "section_label": "Synthetic data",
                    "evidence": "Synthetic data can improve audience modeling accuracy.",
                },
            ],
            "region": "",
            "time_period": "2026",
            "not_found_reason": "",
        }
    )

    response = extract_taxonomy(
        _request(settings),
        _ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
    )

    assert fake_openai.calls == 1
    assert response.primary_tags == ["generative_ai_and_ai_agents"]
    assert response.secondary_tags == ["agentic_commerce"]
    assert response.taxonomy == ["generative_ai_and_ai_agents", "agentic_commerce"]
    inferred = next(
        item for item in response.tag_evidence if item.tag == "agentic_commerce"
    )
    assert inferred.tier == "secondary"
    assert inferred.section_label == "Brand building with AI"


def test_taxonomy_rule_context_matching_normalizes_punctuation(tmp_path):
    mapping_path = tmp_path / "category-mappings.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "schema_version: '1.2'",
                "categories:",
                "  - id: social_commerce",
                "    label: Social Commerce",
                "    description: Social commerce category",
                "    definition: Reports mainly about shopping experiences embedded inside social platforms.",
                "    include_when:",
                "      - Evidence repeatedly focuses on buying and checkout inside social feeds or creator ecosystems.",
                "    exclude_when:",
                "      - Reject when social platforms are only a promotion channel for a broader commerce report.",
                "    core_tags:",
                "      - social_commerce",
                "      - creator_commerce",
                "inference_rules:",
                "  - name: social_checkout_context_to_social_commerce",
                "    target_category_id: social_commerce",
                "    trigger_tags:",
                "      - creator_commerce",
                "    inferred_tag: social_commerce",
                "    inferred_tier: secondary",
                "    context_keywords_any:",
                "      - in-app checkout",
                "uncategorized: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    settings = _settings(tmp_path, mapping_path, vector_store_keep=False)
    fake_openai = FakeOpenAI(
        {
            "schema_version": "1.0",
            "taxonomy": ["creator_commerce"],
            "primary_tags": ["creator_commerce"],
            "secondary_tags": [],
            "tag_evidence": [
                {
                    "tag": "creator_commerce",
                    "tier": "primary",
                    "section_label": "Retail Opportunity",
                    "evidence": "Brands are winning with in app checkout across creator feeds.",
                }
            ],
            "region": "US",
            "time_period": "2026",
            "not_found_reason": "",
        }
    )

    response = extract_taxonomy(
        _request(settings),
        _ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
    )

    assert response.taxonomy == ["creator_commerce", "social_commerce"]
    assert response.secondary_tags == ["social_commerce"]


def test_taxonomy_propagates_retryable_app_error(tmp_path, assert_app_error):
    mapping_path = tmp_path / "category-mappings.yaml"
    _write_mapping(mapping_path)
    settings = _settings(tmp_path, mapping_path)

    with pytest.raises(AppError) as err:
        extract_taxonomy(
            _request(settings),
            _ctx(),
            openai_client=RetryableFailingOpenAI(),
            prompt_client=FakePromptClient(),
        )

    assert_app_error(
        err.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )
