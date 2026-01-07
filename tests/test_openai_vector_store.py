import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIResponseRequest
from src.contracts.run_context import RunContext
from src.services import openai_service as svc
from src.utils.errors import AppError


class FakeResponse:
    def __init__(self, text: str):
        self.output_text = text
        self.usage = {"input_tokens": 10, "output_tokens": 20, "total_tool_calls": 2}


class FakeResponsesAPI:
    def __init__(self, text: str):
        self._text = text

    def create(self, **kwargs):
        return FakeResponse(self._text)


class FakeOpenAI:
    def __init__(self, **kwargs):
        self.responses = FakeResponsesAPI(kwargs.get("text", json.dumps({"ok": True})))


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_openai_response_with_vector_store_writes_ledger(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.jsonl"
    daily_path = tmp_path / "daily.json"

    def _fake_client(**kwargs):
        return SimpleNamespace(
            responses=FakeResponsesAPI(json.dumps({"result": "ok"}))
        )

    monkeypatch.setattr(svc, "OpenAI", _fake_client)
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        vector_store_id="vs_123",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        seed=123,
        timeout_seconds=5.0,
        cost_ledger_path=str(ledger_path),
        cost_daily_path=str(daily_path),
        model_pricing={"gpt-4.1-mini": {"input_tokens_per_1k_usd": 0.003, "output_tokens_per_1k_usd": 0.006, "tool_call_usd": 0.0}},
    )
    resp = svc.openai_respond_with_vector_store(req, _ctx())
    assert resp.text
    assert resp.parsed_json == {"result": "ok"}
    assert ledger_path.exists()
    assert daily_path.exists()
    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert ledger_lines and json.loads(ledger_lines[0])["model"] == "gpt-4.1-mini"


def test_openai_response_with_vector_store_requires_vector_store_id():
    req = OpenAIResponseRequest(
        schema_version="1.0",
        system_prompt="s",
        user_prompt="u",
        vector_store_id="",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
    )
    with pytest.raises(AppError) as exc:
        svc.openai_respond_with_vector_store(req, _ctx())
    assert exc.value.code == "vector_store_missing"
