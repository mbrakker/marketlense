# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_evidence_pack_generator.py"
)

import json
import logging
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
from src.generators.evidence_pack_generator import (
    _load_cached_pack,
    _resolve_pack_steps,
    _strip_json_fence,
    generate_evidence_packs,
)
from src.generators.evidence_packs.base import EvidencePackStrategy
from src.generators.evidence_packs.registry import PACK_STRATEGIES
from src.utils.errors import AppError
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(
            schema_version="1.0", path="system", text="sys", sha256="s"
        )
        user = PromptTemplate(
            schema_version="1.0", path="user", text="user", sha256="u"
        )
        return PromptSet(
            schema_version="1.0",
            system=tmpl,
            user=user,
            dependency_manifest=PromptDependencyManifest(
                schema_version="1.0",
                namespace=request.namespace,
                system_root=PromptDependency(
                    schema_version="1.0",
                    path="system",
                    sha256="a" * 64,
                    kind="system_root",
                ),
                user_root=PromptDependency(
                    schema_version="1.0",
                    path="user",
                    sha256="b" * 64,
                    kind="user_root",
                ),
            ),
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self._parsed = parsed

    def openai_respond_with_vector_store(self, req, ctx):
        parsed = self._parsed
        if getattr(req, "artifact_family", "") != "doc_map" and parsed is not None:
            parsed = {"not_found_reason": "fixture_insufficient_evidence"}
        text = "{}" if isinstance(parsed, dict) else ""
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=parsed,
            input_tokens=10,
            output_tokens=20,
            tool_calls=0,
            model=req.model,
        )


class RoutedOpenAIClient:
    def __init__(self, payloads_by_pack, text_by_pack=None):
        self._payloads_by_pack = payloads_by_pack
        self._text_by_pack = text_by_pack or {}

    def openai_respond_with_vector_store(self, req, ctx):
        task_id = getattr(ctx, "task_id", "")
        pack = ""
        for candidate in (
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
            "key_metrics",
            "risk_register",
            "recommendations",
            "contradictions",
        ):
            if task_id.endswith(f":{candidate}"):
                pack = candidate
                break
        parsed = self._payloads_by_pack.get(
            pack, {"not_found_reason": "fixture_insufficient_evidence"}
        )
        text = self._text_by_pack.get(pack, "")
        if not text and isinstance(parsed, (dict, list)):
            text = json.dumps(parsed)
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=parsed,
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class RetryingDocMapClient:
    def __init__(self):
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        if self.call_count == 1:
            payload = None
            text = "not json"
        elif self.call_count == 2:
            payload = {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            }
            text = "{}"
        else:
            payload = {"not_found_reason": "fixture_insufficient_evidence"}
            text = "{}"
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=payload,
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class TextFallbackDocMapClient:
    def __init__(self):
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        if self.call_count == 1:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='```json\n{"doc_id":"d1","title":"title","sections":[{"title":"Overview"}]}\n```',
                parsed_json=None,
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                model=req.model,
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json={"not_found_reason": "fixture_insufficient_evidence"},
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class RetryableErrorOpenAIClient:
    def __init__(self, code="openai_request_failed"):
        self.code = code
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        raise AppError(code=self.code, message="retry", retryable=True)


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        slug = slugify(report_slug or report_id)
        self.stored.append((report_id, pack_name, payload))
        return f"{output_dir}/{slug}/report_analysis/{pack_name}.json"


def _settings(
    tmp_path,
    *,
    evidence_pack_registry=None,
    evidence_pack_enable_new_variety_packs=False,
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
        vector_store_keep=True,
        evidence_pack_registry=evidence_pack_registry
        or [
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
        ],
        evidence_pack_enable_new_variety_packs=evidence_pack_enable_new_variety_packs,
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
