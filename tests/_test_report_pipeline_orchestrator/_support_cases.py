# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

import logging

import threading

import time

from concurrent.futures import ThreadPoolExecutor

from dataclasses import replace

from types import SimpleNamespace

import pytest

from src.contracts.deferred_work import DeferredWorkListRequest

from src.contracts.drive import DriveFile

from src.contracts.ingest import IngestOutcome, IngestSettings

from src.contracts.pipeline_preflight import (
    PipelinePreflightCheck,
    PipelinePreflightReport,
)

from src.contracts.report_generation import ReportGenerationClientBundle

from src.contracts.run_context import RunContext

from src.orchestrators import report_pipeline_orchestrator as orch

from src.orchestrators import retry_orchestrator as retry_orch

from src.orchestrators import workflow_control_orchestrator as workflow_control

from src.services.llm_usage_ledger_service import list_deferred_work

from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="r",
        task_id="t",
        span_id="s",
        admission_decision_hash="test-admission-decision",
    )


def _settings() -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5",
        batch_limit=1,
        output_dir="./out",
        cache_dir="./cache",
        state_db="./state/index.sqlite",
        reports_db="./state/reports.sqlite",
        category_mapping_path="./src/config/category-mappings.yaml",
        cover_style_path="./src/config/cover-styles.yaml",
        ingest_lock_path="./state/ingest.lock",
        ingest_lock_ttl_seconds=7200.0,
        temperature=1.0,
    )


def _events(caplog) -> list[dict]:
    parsed: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.report_pipeline_orchestrator":
            parsed.append(payload)
    return parsed


class _TrackingOpenAIClient:
    def __init__(self, sleep_seconds: float = 0.03) -> None:
        self.sleep_seconds = sleep_seconds
        self._lock = threading.Lock()
        self._active = {"vector": 0, "chat": 0}
        self.max_active = {"vector": 0, "chat": 0}

    def _mark_start(self, kind: str) -> None:
        with self._lock:
            self._active[kind] += 1
            if self._active[kind] > self.max_active[kind]:
                self.max_active[kind] = self._active[kind]

    def _mark_end(self, kind: str) -> None:
        with self._lock:
            self._active[kind] = max(0, self._active[kind] - 1)

    def openai_respond_with_vector_store(self, req, ctx):
        self._mark_start("vector")
        try:
            time.sleep(self.sleep_seconds)
        finally:
            self._mark_end("vector")
        return SimpleNamespace(schema_version="1.0", parsed_json={})

    def openai_chat_json(self, req, ctx):
        self._mark_start("chat")
        try:
            time.sleep(self.sleep_seconds)
        finally:
            self._mark_end("chat")
        return SimpleNamespace(schema_version="1.0", parsed_json={})


__all__ = [name for name in globals() if not name.startswith("__")]
