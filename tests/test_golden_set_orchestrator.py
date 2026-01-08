import json
import os
from pathlib import Path

import pytest

from src.contracts.config import AppSettings
from src.contracts.run_context import RunContext
from src.contracts.vector_store import (
    VectorStoreAttachFileResponse,
    VectorStoreCreateResponse,
    VectorStoreStatusResponse,
    VectorStoreUploadFileResponse,
)
from src.generators import evidence_pack_generator
from src.orchestrators.golden_set_orchestrator import run_golden_set_vector


pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="integration test; set RUN_INTEGRATION_TESTS=1 to run")


class FakeVectorStoreService:
    def __init__(self):
        self.created = []

    def create_vector_store(self, report_id, metadata, ctx=None):
        self.created.append(report_id)
        return VectorStoreCreateResponse(schema_version="1.0", vector_store_id=f"vs_{report_id}")

    def upload_file(self, pdf_path, ctx=None):
        return VectorStoreUploadFileResponse(schema_version="1.0", vector_store_id="vs", openai_file_id="file_id")

    def attach_file(self, vector_store_id, file_id, ctx=None):
        return VectorStoreAttachFileResponse(schema_version="1.0", vector_store_id=vector_store_id, openai_file_id=file_id)

    def wait_until_indexed(self, vector_store_id, timeout_s=300, poll_interval_s=5, ctx=None):
        return VectorStoreStatusResponse(schema_version="1.0", vector_store_id=vector_store_id, status="completed", indexed_at_utc="2026-01-07T00:00:00Z", last_error=None)


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
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
        analysis_mode="vector_store",
        use_vector_store=True,
        vector_store_keep=True,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={"gpt-4.1-mini": {"input_tokens_per_1k_usd": 0.003, "output_tokens_per_1k_usd": 0.006, "tool_call_usd": 0.0}},
    )


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_golden_set_vector_generates_packs(tmp_path, monkeypatch):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    pdf_path = fixtures_dir / "sample.pdf"
    pdf_path.write_bytes(b"PDF")

    fake_vs = FakeVectorStoreService()
    monkeypatch.setattr("src.orchestrators.golden_set_orchestrator.vector_store_service", fake_vs)

    packs = {
        "doc_map": {"doc_id": "d1", "title": "t", "sections": []},
        "scope": {"scope": "s", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": ""},
        "methods": {"scope": "s", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": ""},
        "findings": {"scope": "s", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": ""},
        "limitations": {"scope": "s", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": ""},
        "quote_candidates": {"scope": "s", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": ""},
    }

    def _fake_generate(*args, **kwargs):
        return packs

    monkeypatch.setattr(evidence_pack_generator, "generate_evidence_packs", _fake_generate)

    outcomes = run_golden_set_vector(_settings(tmp_path), fixtures_dir=str(fixtures_dir), limit=1, ctx=_ctx())
    assert outcomes
    # Assert packs written
    golden_dir = Path(_settings(tmp_path).output_dir) / "golden_set"
    pack_files = list(golden_dir.glob("**/packs/*.json"))
    assert pack_files
    data = json.loads(pack_files[0].read_text(encoding="utf-8"))
    assert "scope" in data or "doc_id" in data
