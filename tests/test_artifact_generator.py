import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.artifact_generator import generate_artifacts
from src.services.schema_validator_service import validate_schema
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/system", text="system", sha256="s")
        user = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/user", text="user", sha256="u")
        return PromptSet(schema_version="1.0", system=tmpl, user=user)

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class FakeOpenAI:
    def __init__(self, responses, *, sleep_seconds=0.0, prerequisites=None):
        self.responses = responses if isinstance(responses, dict) else list(responses)
        self.sleep_seconds = float(sleep_seconds)
        self.prerequisites = prerequisites or {}
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
            return self.responses.get(step, {})
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
            input_tokens=0,
            output_tokens=0,
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
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(self, output_dir, report_id, pack_name, payload, ctx, report_slug=None):
        slug = slugify(report_slug or report_id)
        path = Path(output_dir) / slug / "report_analysis" / f"{pack_name}.json"
        self.stored.append((output_dir, report_id, pack_name, payload))
        return str(path)


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
        artifact_parallel_workers=4,
        artifact_global_max_in_flight=4,
        artifact_global_min_interval_ms=0,
        analysis_mode="vector_store",
        use_vector_store=True,
        vector_store_keep=True,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={"gpt-4.1-mini": {"input_tokens_per_1k_usd": 0.003, "output_tokens_per_1k_usd": 0.006, "tool_call_usd": 0.0}},
    )


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _doc_map():
    return {"doc_id": "r1", "title": "Report", "sections": [{"id": "s1", "title": "Intro"}]}


def _evidence_packs():
    return {
        "findings": {"findings": [{"id": "f1", "text": "Revenue up 10%", "evidence": "Revenue +10% YoY", "pages": [2]}]},
        "quote_candidates": {"quote_candidates": [{"text": "We are expanding rapidly", "source": "CEO", "page": 3}]},
    }


def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_generate_artifacts_validates_schema_and_evidence_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": {"summary": {"tldr": "TLDR", "executive_summary": "Exec", "claim_evidence_map": [{"claim": "Claim", "evidence_id": "f1", "evidence": "Revenue +10%", "pages": [2]}]}},
        "insights_candidates": {
            "insights_candidates": [
                {"id": "c1", "text": "Insight 1", "evidence_id": "f1", "evidence": "E1", "metric": {"value": "10", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "US", "segment": "", "sample_size": "", "confidence": ""}, "pages": [2], "score": 0.9},
                {"id": "c2", "text": "Insight 2", "evidence_id": "f2", "evidence": "E2", "metric": {"value": "5", "unit": "%", "trend": "-", "timeframe": "2023", "geography": "EU", "segment": "", "sample_size": "", "confidence": ""}, "pages": [3], "score": 0.8},
                {"id": "c3", "text": "Insight 3", "evidence_id": "f3", "evidence": "E3", "metric": {"value": "2", "unit": "pt", "trend": "+", "timeframe": "Q1", "geography": "", "segment": "", "sample_size": "", "confidence": ""}, "pages": [4], "score": 0.7},
                {"id": "c4", "text": "Insight 4", "evidence_id": "f4", "evidence": "E4", "metric": {"value": "12", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "APAC", "segment": "", "sample_size": "", "confidence": ""}, "pages": [5], "score": 0.6},
                {"id": "c5", "text": "Insight 5", "evidence_id": "f5", "evidence": "E5", "metric": {"value": "3", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "", "segment": "", "sample_size": "", "confidence": ""}, "pages": [6], "score": 0.5},
            ]
        },
        "insights_final": {
            "insights_final": [
                {"id": "f1", "text": "Top 1", "evidence_id": "f1", "evidence": "E1", "metric": {}, "pages": [2]},
                {"id": "f2", "text": "Top 2", "evidence_id": "f2", "evidence": "E2", "metric": {}, "pages": [3]},
                {"id": "f3", "text": "Top 3", "evidence_id": "f3", "evidence": "E3", "metric": {}, "pages": [4]},
                {"id": "f4", "text": "Top 4", "evidence_id": "f4", "evidence": "E4", "metric": {}, "pages": [5]},
                {"id": "f5", "text": "Top 5", "evidence_id": "f5", "evidence": "E5", "metric": {}, "pages": [6]},
            ]
        },
        "quotes": {"quotes_final": [{"text": "We are expanding rapidly", "speaker": "CEO", "citation": "Earnings call", "page": 3, "evidence_id": "q1"}]},
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    fake_openai = FakeOpenAI(responses)
    analysis_store = FakeAnalysisStore()
    payload = generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert all(item["evidence_id"] for item in payload["insights_candidates"])
    assert all(item["evidence_id"] for item in payload["insights_final"])
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 7
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="artifacts"),
        _ctx(),
    )
    assert analysis_store.stored and analysis_store.stored[0][2] == "artifacts"


def test_generate_artifacts_backfills_missing_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {"summary": {"tldr": "", "executive_summary": "", "claim_evidence_map": [{"claim": "Claim", "evidence": "Support"}]}},
        "insights_candidates": {"insights_candidates": [{"id": "c1", "text": "Candidate 1", "metric": {}, "pages": []}]},
        "insights_final": {"insights_final": []},
        "quotes": {"quotes_final": [{"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1}]},
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="r2",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id=None,
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert payload["summary"]["claim_evidence_map"][0]["evidence_id"] == "claim_1"
    assert payload["insights_candidates"][0]["evidence_id"] == "c1"
    assert len(payload["insights_final"]) == 5
    assert all(item["evidence_id"] for item in payload["insights_final"])
    assert payload["quotes_final"][0]["evidence_id"] == "quote_1"
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="artifacts"),
        _ctx(),
    )


def test_generate_artifacts_ignores_low_text_when_vector_store(tmp_path):
    analysis_store = FakeAnalysisStore()
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {"summary": {"tldr": "TLDR", "executive_summary": "Exec", "claim_evidence_map": [{"claim": "Claim", "evidence_id": "f1", "evidence": "E", "pages": [1]}]}},
        "insights_candidates": {"insights_candidates": [{"id": "c1", "text": "Insight", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1], "score": 0.9}]},
        "insights_final": {"insights_final": [{"id": "f1", "text": "Final", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1]}]},
        "quotes": {"quotes_final": [{"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1, "evidence_id": "q1"}]},
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="low_text",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        source_status=_low_text_status(),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert payload["source_status"]["not_available"] is False
    assert fake_openai.requests and all(req[0] == "vector" for req in fake_openai.requests)
    validate_schema(
        SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="artifacts"),
        _ctx(),
    )
    assert analysis_store.stored


def test_generate_artifacts_parallelizes_with_dependency_order(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": {"summary": {"tldr": "TLDR", "executive_summary": "Exec", "claim_evidence_map": [{"claim": "Claim", "evidence_id": "f1", "evidence": "E", "pages": [1]}]}},
        "insights_candidates": {"insights_candidates": [{"id": "c1", "text": "Insight", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1], "score": 0.9}]},
        "insights_final": {"insights_final": [{"id": "f1", "text": "Final", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1]}]},
        "quotes": {"quotes_final": [{"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1, "evidence_id": "q1"}]},
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    prerequisites = {
        "insights_final": ["insights_candidates"],
        "expert_comment": ["summary", "insights_final", "quotes"],
        "linkedin_post": ["summary", "insights_final"],
    }
    fake_openai = FakeOpenAI(responses, sleep_seconds=0.05, prerequisites=prerequisites)
    payload = generate_artifacts(
        report_id="parallel",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert payload["expert_comment"] == "Grounded comment"
    assert payload["linkedin_post"] == "Post summary"
    assert fake_openai.max_in_flight >= 2
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 7


def test_generate_artifacts_strips_inline_reference_tokens_from_summary_and_linkedin(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Growth accelerated (F-001 / IC-004), especially in Q4.",
                "claim_evidence_map": [{"claim": "Claim", "evidence_id": "f1", "evidence": "E", "pages": [1]}],
            }
        },
        "insights_candidates": {"insights_candidates": [{"id": "c1", "text": "Insight", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1], "score": 0.9}]},
        "insights_final": {"insights_final": [{"id": "f1", "text": "Final", "evidence_id": "f1", "evidence": "E", "metric": {}, "pages": [1]}]},
        "quotes": {"quotes_final": [{"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1, "evidence_id": "q1"}]},
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Leader takeaway (F-002 / IC-001): invest in omnichannel."},
    }
    payload = generate_artifacts(
        report_id="strip_refs",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert "(F-001 / IC-004)" not in payload["summary"]["executive_summary"]
    assert "(F-002 / IC-001)" not in payload["linkedin_post"]
    assert payload["summary"]["executive_summary"] == "Growth accelerated, especially in Q4."
    assert payload["linkedin_post"] == "Leader takeaway: invest in omnichannel."
