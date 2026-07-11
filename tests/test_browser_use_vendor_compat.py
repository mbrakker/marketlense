from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

VENDORED_BROWSER_USE_ROOT = (
    Path(__file__).resolve().parents[1] / "tools" / "browser-use"
)
if str(VENDORED_BROWSER_USE_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDORED_BROWSER_USE_ROOT))

from browser_use.agent.service import Agent
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
from browser_use.tokens.service import TokenCost
from browser_use.tools.views import StructuredOutputAction
from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.browser import (
    _configure_browser_use_usage_recorder,
)
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle


class _ExampleOutput(BaseModel):
    name: str
    value: int


def test_structured_output_action_accepts_flattened_payload() -> None:
    parsed = StructuredOutputAction[_ExampleOutput].model_validate(
        {
            "name": "example",
            "value": 7,
            "success": True,
        }
    )

    assert parsed.success is True
    assert parsed.data.name == "example"
    assert parsed.data.value == 7


def test_agent_enhance_task_mentions_done_data_wrapper() -> None:
    agent = Agent.__new__(Agent)

    enhanced = Agent._enhance_task_with_schema(
        agent,
        "Acquire the report.",
        _ExampleOutput,
    )

    assert "done.data" in enhanced
    assert '"name"' in enhanced


def test_browser_use_usage_callback_records_each_provider_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/reports/market-outlook",
        settings=BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key="",
            model="gpt-5-mini",
            temperature=0.0,
            timeout_seconds=30.0,
            max_steps=3,
            output_dir=str(tmp_path / "downloads"),
            state_db=str(tmp_path / "browser-state.sqlite"),
            reports_db=str(tmp_path / "reports.sqlite"),
            identity_config_path=str(tmp_path / "identity.yaml"),
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[],
            ),
        ),
        report_title="Market Outlook",
        publisher_name="Example Research",
    )
    token_cost_service = TokenCost()
    primary_llm = _UsageReportingLLM(
        model="gpt-5-mini",
        provider="openai",
        request_id="req-openai",
        prompt_tokens=120,
        cached_tokens=20,
        completion_tokens=30,
    )
    fallback_llm = _UsageReportingLLM(
        model="openai/gpt-5-mini",
        provider="openrouter",
        request_id="req-openrouter",
        prompt_tokens=80,
        cached_tokens=None,
        completion_tokens=20,
    )
    token_cost_service.register_llm(primary_llm)
    _configure_browser_use_usage_recorder(
        request=request,
        ctx=RunContext(
            schema_version="1.0",
            run_id="browser-usage-run",
            task_id="browser-usage-task",
            span_id="browser-usage-span",
        ),
        normalized_url=request.url,
        prompt_bundle=BrowserDownloadPromptBundle(
            schema_version="1.0",
            namespace="browser_download/agent",
            system_prompt_path="system.yaml",
            user_prompt_path="user.yaml",
            system_prompt_sha256="system-hash",
            user_prompt_sha256="prompt-hash",
            rendered_system_prompt="system",
            rendered_user_prompt="user",
            task_prompt="task",
        ),
        llm_clients=SimpleNamespace(
            primary_provider="openai",
            primary_model="gpt-5-mini",
            fallback_provider="openrouter",
            fallback_model="openai/gpt-5-mini",
        ),
        agent=SimpleNamespace(token_cost_service=token_cost_service),
    )

    asyncio.run(primary_llm.ainvoke([]))
    token_cost_service.register_llm(fallback_llm)
    asyncio.run(fallback_llm.ainvoke([]))

    with sqlite3.connect(tmp_path / "state" / "llm_usage.sqlite") as connection:
        rows = connection.execute(
            """
            select provider, action, model, request_id, publisher_name, report_name,
                   source_url, input_tokens, output_tokens, total_tokens,
                   cached_input_tokens, provider_decision
            from llm_usage_events
            order by id
            """
        ).fetchall()

    assert rows == [
        (
            "openai",
            "browser_use_llm_call",
            "gpt-5-mini",
            "req-openai",
            "Example Research",
            "Market Outlook",
            "https://example.com/reports/market-outlook",
            120,
            30,
            150,
            20,
            "openai_primary",
        ),
        (
            "openrouter",
            "browser_use_llm_call",
            "openai/gpt-5-mini",
            "req-openrouter",
            "Example Research",
            "Market Outlook",
            "https://example.com/reports/market-outlook",
            80,
            20,
            100,
            None,
            "openrouter_fallback",
        ),
    ]


class _UsageReportingLLM:
    def __init__(
        self,
        *,
        model: str,
        provider: str,
        request_id: str,
        prompt_tokens: int,
        cached_tokens: int | None,
        completion_tokens: int,
    ) -> None:
        self.model = model
        self.provider = provider
        self._request_id = request_id
        self._prompt_tokens = prompt_tokens
        self._cached_tokens = cached_tokens
        self._completion_tokens = completion_tokens

    async def ainvoke(
        self,
        messages: list[object],
        output_format=None,
        **kwargs: object,
    ) -> ChatInvokeCompletion[str]:
        del messages, output_format, kwargs
        return ChatInvokeCompletion(
            completion="ok",
            usage=ChatInvokeUsage(
                prompt_tokens=self._prompt_tokens,
                prompt_cached_tokens=self._cached_tokens,
                prompt_cache_creation_tokens=None,
                prompt_image_tokens=None,
                completion_tokens=self._completion_tokens,
                total_tokens=self._prompt_tokens + self._completion_tokens,
            ),
            request_id=self._request_id,
        )
