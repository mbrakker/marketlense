# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

import logging

import sqlite3

from types import SimpleNamespace

import pytest

from src.contracts.openai import (
    OpenAIEmbeddingRequest,
    OpenAIJSONImagePromptRequest,
    OpenAIResponseRequest,
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreDeleteRequest,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreUpdateMetadataRequest,
)

from src.contracts.run_budget import RunBudget, RunBudgetUsageReadRequest

from src.contracts.run_context import RunContext

from src.services import llm_service as svc

from src.services.llm_usage_ledger_service import read_run_budget_usage


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


@pytest.fixture(autouse=True)
def _isolate_default_usage_storage(tmp_path, external_boundary_mocks_only) -> None:
    """Keep default usage-accounting artifacts out of shared repository state."""
    external_boundary_mocks_only.chdir(tmp_path)


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.llm_service.openai":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


@pytest.fixture(autouse=True)
def _isolate_relative_usage_artifacts(tmp_path, external_boundary_mocks_only) -> None:
    """Keep default accounting artifacts isolated to the current test."""
    external_boundary_mocks_only.chdir(tmp_path)


__all__ = [name for name in globals() if not name.startswith("__")]
