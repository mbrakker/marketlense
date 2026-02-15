import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.utils.errors import AppError
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(schema_version="1.0", path="system", text="sys", sha256="s")
        user = PromptTemplate(schema_version="1.0", path="user", text="user", sha256="u")
        return PromptSet(schema_version="1.0", system=tmpl, user=user)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self._parsed = parsed

    def openai_respond_with_vector_store(self, req, ctx):
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=self._parsed,
            input_tokens=10,
            output_tokens=20,
            tool_calls=0,
            model=req.model,
        )


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(self, output_dir, report_id, pack_name, payload, ctx, report_slug=None):
        slug = slugify(report_slug or report_id)
        self.stored.append((report_id, pack_name, payload))
        return f"{output_dir}/{slug}/report_analysis/{pack_name}.json"


class TrackingOpenAIClient:
    def __init__(self, sleep_s: float = 0.02):
        self.sleep_s = sleep_s
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.call_count = 0
        self.started_at: list[float] = []

    def openai_respond_with_vector_store(self, req, ctx):
        with self._lock:
            self.call_count += 1
            call_number = self.call_count
            self._active += 1
            if self._active > self.max_active:
                self.max_active = self._active
            self.started_at.append(time.monotonic())
        try:
            if self.sleep_s > 0:
                time.sleep(self.sleep_s)
        finally:
            with self._lock:
                self._active -= 1
        if call_number == 1:
            payload = {"doc_id": "d1", "title": "title", "sections": [{"id": "s1", "title": "Overview"}]}
        else:
            payload = {"scope": "ok", "methods": [], "findings": [], "limitations": [], "quote_candidates": []}
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=payload,
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


def _settings(tmp_path):
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
        category_mapping_path="cats.yaml",
        cover_style_path=str(Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"),
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


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_generate_evidence_packs_success(tmp_path):
    parsed = {"doc_id": "d1", "title": "title", "sections": []}
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert "doc_map" in packs
    assert packs["doc_map"]["doc_id"] == "d1"
    # ensure store called for each pack
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_handles_missing_json(tmp_path):
    fake_openai = FakeOpenAIClient(parsed=None)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_empty"
    assert len(analysis_store.stored) == 1
    stored_report_id, stored_pack, stored_payload = analysis_store.stored[0]
    assert stored_report_id == "r1"
    assert stored_pack == "doc_map"
    assert stored_payload["not_found_reason"] == "model_returned_no_json"


def test_generate_evidence_packs_normalizes_docmap_wrapper(tmp_path):
    parsed = {"docmap": {"title": "Retail trends", "sections": [{"title": "Section A"}]}}
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "Retail trends"
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0].get("id")
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_docmap_camelcase_wrapper(tmp_path):
    parsed = {
        "docMap": {
            "title": "THE 2026 INDUSTRY PULSE REPORT",
            "publisher": "Integral Ad Science",
            "sections": [{"title": "Top media challenges and opportunities", "page": 5}],
        }
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "THE 2026 INDUSTRY PULSE REPORT"
    assert doc_map["publisher"] == "Integral Ad Science"
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0]["id"] == "top-media-challenges-and-opportunities"
    assert doc_map["sections"][0]["pages"] == [5]
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_document_structure_shape(tmp_path):
    parsed = {
        "docmap_version": "1.0",
        "document": {
            "title": "Six Predictions for 2026 from AI to Gaming",
            "publisher": "Sensor Tower",
            "description": "Executive summary and six predictions.",
        },
        "structure": [{"title": "Executive Summary", "summary": "Overview of six predictions."}],
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "Six Predictions for 2026 from AI to Gaming"
    assert doc_map["publisher"] == "Sensor Tower"
    assert doc_map["summary"] == "Executive summary and six predictions."
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0]["id"] == "executive-summary"
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_parallel_respects_global_in_flight_limit(tmp_path):
    settings = replace(
        _settings(tmp_path),
        evidence_pack_parallel_workers=5,
        evidence_pack_global_max_in_flight=2,
        evidence_pack_global_min_interval_ms=0,
    )
    fake_openai = TrackingOpenAIClient(sleep_s=0.04)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=settings,
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert len(packs) == 6
    assert fake_openai.call_count == 6
    assert fake_openai.max_active <= 2
    assert fake_openai.max_active >= 2


def test_generate_evidence_packs_global_min_interval_throttles_call_starts(tmp_path):
    settings = replace(
        _settings(tmp_path),
        evidence_pack_parallel_workers=5,
        evidence_pack_global_max_in_flight=5,
        evidence_pack_global_min_interval_ms=60,
    )
    fake_openai = TrackingOpenAIClient(sleep_s=0.005)
    generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=settings,
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    starts = sorted(fake_openai.started_at)
    assert len(starts) == 6
    deltas_ms = [(nxt - cur) * 1000.0 for cur, nxt in zip(starts, starts[1:])]
    assert deltas_ms
    assert min(deltas_ms) >= 45.0
