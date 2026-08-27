# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_artifact_generator.py"
)

import json
import logging
import threading
import time
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
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators.artifact_generator import (
    _load_cached_artifacts,
    assemble_artifacts_payload,
    build_chart_insight_cards,
    build_executive_advisory_artifacts,
    build_key_figures,
    build_topic_briefs,
    build_topics_covered,
    derive_metric_spine,
    derive_metric_spine_from_insights,
    generate_artifacts,
)
from src.generators.artifact_normalization import normalize_artifact_quotes
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.slugify import slugify


def _cover_semantics():
    return {
        "evidence_shape": "trend",
        "direction": "rising",
        "geography_scope": "global",
        "evidence_density": "metric_rich",
        "domain_layer": "grid",
        "selection_reason": "Rising time-series evidence dominates the report.",
    }


def _cover_semantics_response():
    return {"cover_semantics": _cover_semantics()}


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
            text="user",
            sha256="u",
        )
        manifest = PromptDependencyManifest(
            schema_version="1.0",
            namespace=request.namespace,
            system_root=PromptDependency(
                schema_version="1.0",
                path=f"prompts/{request.namespace}/system.yaml",
                sha256="s",
                kind="system_root",
            ),
            user_root=PromptDependency(
                schema_version="1.0",
                path=f"prompts/{request.namespace}/user.yaml",
                sha256="u",
                kind="user_root",
            ),
            prompt_content_hash="a" * 64,
        )
        return PromptSet(
            schema_version="1.0",
            system=tmpl,
            user=user,
            dependency_manifest=manifest,
            prompt_content_hash=manifest.prompt_content_hash,
        )

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class CapturingPromptClient(FakePromptClient):
    def __init__(self):
        self.render_calls = []

    def render_prompt(self, request, ctx):
        self.render_calls.append(
            {"path": request.template.path, "variables": dict(request.variables)}
        )
        return super().render_prompt(request, ctx)

    def variables_for_namespace(self, namespace):
        for call in self.render_calls:
            if call["path"] == f"{namespace}/system":
                return call["variables"]
        return {}


class FakeOpenAI:
    def __init__(
        self,
        responses,
        *,
        sleep_seconds=0.0,
        prerequisites=None,
        input_tokens=0,
        output_tokens=0,
    ):
        self.responses = responses if isinstance(responses, dict) else list(responses)
        self.sleep_seconds = float(sleep_seconds)
        self.prerequisites = prerequisites or {}
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.requests = []
        self._events = {}
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def _step(self, ctx):
        task_id = getattr(ctx, "task_id", "")
        return task_id.rsplit(":", 1)[-1] if ":" in task_id else task_id

    def _next(self, step):
        if isinstance(self.responses, dict):
            if step == "cover_semantics" and step not in self.responses:
                return _cover_semantics_response()
            response = self.responses.get(step, {})
            if isinstance(response, list):
                return response.pop(0) if response else {}
            return response
        if not self.responses:
            return {}
        return self.responses.pop(0)

    def _mark_started(self):
        with self._lock:
            self._in_flight += 1
            if self._in_flight > self.max_in_flight:
                self.max_in_flight = self._in_flight

    def _mark_completed(self, step):
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            event = self._events.get(step)
            if event is None:
                event = threading.Event()
                self._events[step] = event
            event.set()

    def _check_dependencies(self, step):
        for dep in self.prerequisites.get(step, []):
            event = self._events.get(dep)
            if event is None:
                event = threading.Event()
                self._events[dep] = event
            if not event.is_set():
                raise AssertionError(f"{step} called before dependency {dep}")

    def _payload_for_step(self, step):
        self._check_dependencies(step)
        self._mark_started()
        try:
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)
            return self._next(step)
        finally:
            self._mark_completed(step)

    def openai_chat_json(self, req, ctx):
        step = self._step(ctx)
        self.requests.append(("chat", req, step))
        payload = self._payload_for_step(step)
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=payload,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=0,
            model=req.model,
        )

    def openai_respond_with_vector_store(self, req, ctx):
        step = self._step(ctx)
        self.requests.append(("vector", req.vector_store_id, step))
        payload = self._payload_for_step(step)
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=payload,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=0,
            model=req.model,
        )


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
    artifacts_use_vector_store: bool = False,
    validation_grounding_use_vector_store: bool = False,
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
        temperature=0.1,
        ingest_lock_ttl_seconds=1.0,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        artifact_parallel_workers=4,
        artifact_global_max_in_flight=4,
        artifact_global_min_interval_ms=0,
        vector_store_keep=True,
        artifacts_use_vector_store=artifacts_use_vector_store,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.003,
                "output_tokens_per_1k_usd": 0.006,
                "tool_call_usd": 0.0,
            }
        },
        llm_execution_policies={
            "report_vs": {
                "model": "gpt-4.1-mini",
                "temperature": 0.1,
                "timeout_seconds": 5.0,
            }
        },
    )


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _doc_map():
    return {
        "doc_id": "r1",
        "title": "Report",
        "sections": [{"id": "s1", "title": "Intro"}],
    }


def _evidence_packs():
    return {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Revenue up 10%",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                },
                {
                    "id": "f2",
                    "text": "Margin pressure in EU",
                    "evidence": "Margin declined",
                    "pages": [3],
                },
                {
                    "id": "f3",
                    "text": "Retention stabilizing",
                    "evidence": "Retention improved",
                    "pages": [4],
                },
                {
                    "id": "f4",
                    "text": "APAC demand up",
                    "evidence": "APAC growth accelerated",
                    "pages": [5],
                },
                {
                    "id": "f5",
                    "text": "Ad spend efficiency up",
                    "evidence": "CPA improved",
                    "pages": [6],
                },
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "q1",
                    "text": "We are expanding rapidly",
                    "source": "CEO",
                    "page": 3,
                }
            ]
        },
    }


def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
