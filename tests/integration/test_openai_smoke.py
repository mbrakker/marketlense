from __future__ import annotations

import os

import pytest
from openai import OpenAI


pytestmark = pytest.mark.integration


def test_openai_responses_smoke() -> None:
    if os.getenv("RUN_OPENAI_SMOKE_TEST", "").strip() != "1":
        pytest.skip("Set RUN_OPENAI_SMOKE_TEST=1 to enable live OpenAI smoke test.")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required for live OpenAI smoke test.")

    model = os.getenv("OPENAI_SMOKE_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [{"type": "input_text", "text": "Reply with OK only."}]}],
    )
    assert (response.output_text or "").strip() == "OK"
