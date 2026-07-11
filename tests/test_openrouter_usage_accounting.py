from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from src.contracts.run_context import RunContext
from src.services._llm_service import openrouter


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run-or",
        task_id="task-or",
        span_id="span-or",
        trace_id="trace-or",
    )


class _FakeHTTPResponse:
    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "id": "or_req_1",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            }
        ).encode("utf-8")


def test_openrouter_chat_json_records_provider_usage_to_sqlite(
    external_boundary_mocks_only,
    tmp_path: Path,
) -> None:
    def _urlopen(request, timeout):
        return _FakeHTTPResponse()

    external_boundary_mocks_only.setattr(openrouter.urllib_request, "urlopen", _urlopen)
    request = SimpleNamespace(
        openrouter_api_key="secret",
        model="openai/gpt-5-mini",
        system_prompt="system",
        user_prompt="user",
        temperature=0.0,
        timeout_seconds=30.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        model_pricing={
            "openai/gpt-5-mini": {
                "input_tokens_per_1k_usd": 0.1,
                "output_tokens_per_1k_usd": 0.2,
            }
        },
        publisher_name="OpenRouter Publisher",
        report_name="OpenRouter Report",
        source_url="https://example.com/openrouter-report",
        prompt_namespace="openrouter/test",
        prompt_hash="prompt-hash",
        provider_decision="openrouter_fallback",
        response_cache_enabled=False,
    )

    result = openrouter.openrouter_chat_json(request, _ctx())

    assert result.parsed_json == {"ok": True}
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.total_tokens == 18
    with sqlite3.connect(tmp_path / "usage.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from llm_usage_events").fetchone()
    assert row is not None
    assert row["provider"] == "openrouter"
    assert row["action"] == "openrouter_chat_json"
    assert row["model"] == "openai/gpt-5-mini"
    assert row["request_id"] == "or_req_1"
    assert row["publisher_name"] == "OpenRouter Publisher"
    assert row["report_name"] == "OpenRouter Report"
    assert row["source_url"] == "https://example.com/openrouter-report"
    assert row["input_tokens"] == 11
    assert row["output_tokens"] == 7
    assert row["total_tokens"] == 18
    assert row["provider_decision"] == "openrouter_fallback"
