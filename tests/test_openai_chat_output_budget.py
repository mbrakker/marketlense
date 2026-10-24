from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.services import llm_service as svc


def test_max_output_tokens_reaches_provider_and_changes_semantic_cache_key(
    external_boundary_mocks_only, tmp_path
) -> None:
    calls: list[dict] = []

    class _Chat:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                id=f"chat_{len(calls)}",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))
                ],
                usage=SimpleNamespace(
                    prompt_tokens=12, completion_tokens=5, total_tokens=17
                ),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=_Chat())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    base = OpenAIJSONPromptRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        seed=7,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        model_pricing={},
        max_output_tokens=19_661,
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
    )
    context = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    svc.openai_chat_json(base, context)
    svc.openai_chat_json(base, context)
    svc.openai_chat_json(replace(base, max_output_tokens=16_384), context)

    assert len(calls) == 2
    assert [call["max_completion_tokens"] for call in calls] == [19_661, 16_384]
