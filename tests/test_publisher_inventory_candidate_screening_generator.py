from __future__ import annotations

import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventorySettings,
)
from src.generators.publisher_inventory_candidate_screening_generator import (
    screen_publisher_inventory_candidates,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class RecordingPromptClient:
    def load_prompt_set(self, request, ctx):
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/system.yaml",
                text="System {{ value | default('') }}",
                sha256="system-sha",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{request.namespace}/user.yaml",
                text=(
                    "Publisher {{ publisher_name }}\n"
                    "Insights {{ insights_url }}\n"
                    "{{ candidate_items_json }}"
                ),
                sha256="user-sha",
            ),
        )

    def render_prompt(self, request, ctx):
        text = request.template.text
        for key, value in request.variables.items():
            text = text.replace(f"{{{{ {key} }}}}", str(value))
        return SimpleNamespace(text=text)


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
            input_tokens=20,
            output_tokens=10,
            tool_calls=0,
            model=request.model,
            total_tokens=30,
            request_id="req-1",
        )


def _settings() -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="google/gemini-2.5-flash-lite",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=10,
        output_dir="./out/publisher_inventory_discovery",
        reports_db="./state/reports.sqlite",
        google_sa_path="./sa.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=10,
        http_timeout_seconds=30.0,
        openrouter_http_referer=None,
        headed=False,
        force_browser=True,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
        openai_api_key="openai-key",
        openai_models={},
        openai_seed=123,
        candidate_screening_enabled=True,
        candidate_screening_model="gpt-5-nano",
        candidate_screening_temperature=1.0,
        candidate_screening_timeout_seconds=45.0,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
    )


def test_screen_publisher_inventory_candidates_filters_rejected_items(
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one",
            title="Report One",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/facebook",
            title="Facebook",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Substantive report asset.",
                },
                {
                    "canonical_url": "https://example.com/facebook",
                    "accepted": False,
                    "reason": "Social link, not a report.",
                },
            ]
        }
    )
    caplog.set_level(
        logging.INFO,
        logger="market_lense.publisher_inventory_candidate_screening_generator",
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/facebook"
    ]
    assert openai_client.requests[0][0].model == "gpt-5-nano"
    assert '"canonical_url": "https://example.com/report-one"' in openai_client.requests[0][0].user_prompt
    assert response.request_id == "req-1"
    assert_no_defaulted_required_fields(response)
    assert_no_defaulted_required_fields(response.decisions[0])
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name
        == "market_lense.publisher_inventory_candidate_screening_generator"
    ]
    assert_logs_have_required_fields(records)


def test_screen_publisher_inventory_candidates_requires_decision_for_every_candidate(
    assert_app_error,
) -> None:
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Substantive report asset.",
                }
            ]
        }
    )

    with pytest.raises(AppError) as err:
        screen_publisher_inventory_candidates(
            PublisherInventoryCandidateScreeningRequest(
                schema_version="1.0",
                publisher_name="Example Publisher",
                insights_url="https://example.com/insights",
                candidates=[
                    PublisherInventoryCandidateScreeningItem(
                        schema_version="1.0",
                        canonical_url="https://example.com/report-one",
                        title="Report One",
                        discovered_on_page_number=1,
                        source_page_url="https://example.com/insights",
                    ),
                    PublisherInventoryCandidateScreeningItem(
                        schema_version="1.0",
                        canonical_url="https://example.com/report-two",
                        title="Report Two",
                        discovered_on_page_number=1,
                        source_page_url="https://example.com/insights",
                    ),
                ],
                settings=_settings(),
            ),
            _ctx(),
            openai_client=openai_client,
            prompt_client=RecordingPromptClient(),
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_candidate_screen_incomplete",
        retryable=False,
    )


def test_screen_publisher_inventory_candidates_skips_llm_when_disabled() -> None:
    settings = replace(_settings(), candidate_screening_enabled=False)

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/report-one",
                    title="Report One",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=settings,
        ),
        _ctx(),
        openai_client=None,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one"
    ]
    assert response.model == "screening_disabled"


def test_screen_publisher_inventory_candidates_collapses_duplicate_titles_after_llm() -> None:
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one?promo=hero",
            title="2026 Global Retail Outlook",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one",
            title="2026 Global Retail Outlook",
            discovered_on_page_number=2,
            source_page_url="https://example.com/insights?page=2",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-two",
            title="Substantive Market Outlook 2026",
            discovered_on_page_number=3,
            source_page_url="https://example.com/insights?page=3",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one?promo=hero",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://example.com/report-two",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one",
        "https://example.com/report-two",
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/report-one?promo=hero"
    ]
    duplicate_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url == "https://example.com/report-one?promo=hero"
    )
    assert duplicate_decision.accepted is False
    assert duplicate_decision.reason.startswith("duplicate_in_run")


def test_screen_publisher_inventory_candidates_hard_rejects_publisher_success_titles() -> None:
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://business.adobe.com/resources/reports/leader-email-service-providers",
            title="Read now Adobe named a Leader in Email Service Providers.",
            discovered_on_page_number=1,
            source_page_url="https://business.adobe.com/resources/reports.html",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement",
            title="Read now 2025 AI and Digital Trends in Customer Engagement.",
            discovered_on_page_number=2,
            source_page_url="https://business.adobe.com/resources/reports.html?page=2",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://business.adobe.com/resources/reports/leader-email-service-providers",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Adobe",
            insights_url="https://business.adobe.com/resources/reports.html",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://business.adobe.com/resources/reports/leader-email-service-providers"
    ]
    hard_reject_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url
        == "https://business.adobe.com/resources/reports/leader-email-service-providers"
    )
    assert hard_reject_decision.accepted is False
    assert hard_reject_decision.reason == "publisher_success_marketing"
