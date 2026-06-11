# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_publisher_inventory_candidate_screening_generator.py")

import json

import logging

from dataclasses import replace

from types import SimpleNamespace

from src.contracts.openai import OpenAIResponseResult

from src.contracts.prompts import PromptSet, PromptTemplate

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventorySettings,
)

from src.generators.publisher_inventory_candidate_screening_generator import (
    _resolve_candidate_screening_batch_size,
    screen_publisher_inventory_candidates,
)

from src.contracts.run_context import RunContext

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

class BatchAwareOpenAIClient:
    def __init__(self) -> None:
        self.requests = []

    def openai_chat_json(self, request, ctx):
        self.requests.append((request, ctx))
        payload = json.loads("\n".join(request.user_prompt.splitlines()[2:]))
        decisions = [
            {
                "canonical_url": item["canonical_url"],
                "accepted": True,
                "reason": "Looks report-like.",
            }
            for item in payload
        ]
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"decisions": decisions}),
            parsed_json={"decisions": decisions},
            input_tokens=20,
            output_tokens=10,
            tool_calls=0,
            model=request.model,
            total_tokens=30,
            request_id=f"req-{len(self.requests)}",
        )

class RepairingOpenAIClient:
    def __init__(self) -> None:
        self.requests = []

    def openai_chat_json(self, request, ctx):
        self.requests.append((request, ctx))
        payload = json.loads("\n".join(request.user_prompt.splitlines()[2:]))
        if len(payload) > 1:
            kept = payload[0]
            decisions = [
                {
                    "canonical_url": kept["canonical_url"],
                    "accepted": True,
                    "reason": "Looks report-like.",
                }
            ]
        else:
            only = payload[0]
            decisions = [
                {
                    "canonical_url": only["canonical_url"],
                    "accepted": True,
                    "reason": "Looks report-like.",
                }
            ]
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps({"decisions": decisions}),
            parsed_json={"decisions": decisions},
            input_tokens=20,
            output_tokens=10,
            tool_calls=0,
            model=request.model,
            total_tokens=30,
            request_id=f"req-{len(self.requests)}",
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
        candidate_screening_batch_size=20,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
    )



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
