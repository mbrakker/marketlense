from __future__ import annotations

import os

import pytest

from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.services import llm_service


pytestmark = pytest.mark.integration


def test_openai_responses_smoke() -> None:
    if os.getenv("RUN_OPENAI_SMOKE_TEST", "").strip() != "1":
        pytest.skip("Set RUN_OPENAI_SMOKE_TEST=1 to enable live OpenAI smoke test.")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required for live OpenAI smoke test.")

    model = os.getenv("OPENAI_SMOKE_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    response = llm_service.openai_chat_json(
        OpenAIJSONPromptRequest(
            schema_version="1.0",
            system_prompt="Return strict JSON only.",
            user_prompt='Return exactly {"ok":"OK"} as JSON.',
            model=model,
            temperature=0.0,
            api_key=api_key,
            seed=7,
            timeout_seconds=30.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        ),
        RunContext(
            schema_version="1.0", run_id="smoke", task_id="smoke", span_id="smoke"
        ),
    )
    assert response.parsed_json == {"ok": "OK"}
