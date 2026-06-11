# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_validation_generator.py")

from types import SimpleNamespace

import json

import logging

import threading

from pathlib import Path

import pytest

from src.contracts.config import AppSettings

from src.contracts.prompts import PromptSet, PromptTemplate

from src.contracts.report_models import Figure, Quote, ReportPayload

from src.contracts.run_context import RunContext

from src.contracts.validation import ValidationRequest

from src.contracts.openai import OpenAIResponseResult

from src.generators.validation.cache import load_cached_validation

from src.generators.validation.numbers import validate_new_numbers

from src.generators.validation.registry import build_validation_rule_registry

from src.generators.validation_generator import validate_report

from src.utils.errors import AppError

from src.utils.slugify import slugify

class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/system",
            text="system",
            sha256="s",
        )
        user = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/user",
            text="user {{ report_json }}",
            sha256="u",
        )
        return PromptSet(schema_version="1.0", system=tmpl, user=user)

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)

class FakeOpenAI:
    def __init__(self, *payloads, semantic_payload=None, grounding_payload=None):
        self.payloads = list(payloads) or [{}]
        self.semantic_payload = semantic_payload
        self.grounding_payload = grounding_payload
        self.requests = []
        self._lock = threading.Lock()

    def _next_payload(self, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and isinstance(self.semantic_payload, dict):
            return self.semantic_payload
        if task_id.endswith(":grounding") and isinstance(self.grounding_payload, dict):
            return self.grounding_payload
        with self._lock:
            if self.payloads:
                return self.payloads.pop(0)
            return {}

    def openai_chat_json(self, req, ctx):
        payload = self._next_payload(ctx)
        with self._lock:
            self.requests.append(("chat", req.model, str(getattr(ctx, "task_id", ""))))
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )

    def openai_respond_with_vector_store(self, req, ctx):
        with self._lock:
            self.requests.append(
                ("vector", req.vector_store_id, str(getattr(ctx, "task_id", "")))
            )
        return self.openai_chat_json(req, ctx)

class FailingOpenAI(FakeOpenAI):
    def __init__(self, *, semantic_exc=None, grounding_exc=None):
        super().__init__(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={"unsupported": []},
        )
        self.semantic_exc = semantic_exc
        self.grounding_exc = grounding_exc

    def openai_chat_json(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and self.semantic_exc is not None:
            raise self.semantic_exc
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_chat_json(req, ctx)

    def openai_respond_with_vector_store(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_respond_with_vector_store(req, ctx)

class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        slug = slugify(report_slug or report_id)
        path = Path(output_dir) / slug / "report_analysis" / f"{pack_name}.json"
        self.stored.append((output_dir, report_id, pack_name, payload))
        return str(path)

def _settings(
    tmp_path,
    *,
    validation_grounding_use_vector_store: bool = False,
    report_worker_limit: int = 2,
    validation_data_gap_policy: str = "warn",
):
    return AppSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        publisher_profiles_path=str(tmp_path / "publisher-profiles.json"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        report_worker_limit=report_worker_limit,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=True,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
        validation_data_gap_policy=validation_data_gap_policy,
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

def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

def _report():
    return ReportPayload(
        tldr="TLDR",
        title="Report",
        insights=["i1", "i2", "i3", "i4", "i5"],
        quote=Quote(text="Quoted text", author="Analyst"),
        figure=Figure(title="Figure", evidence="Fig"),
        commentary="Commentary",
        source="Source",
    )

def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))



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
