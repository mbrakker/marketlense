import json
from pathlib import Path
from types import SimpleNamespace

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.generators.artifact_generator import generate_artifacts
from src.utils.schema_validator import validate_schema


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/system", text="system", sha256="s")
        user = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/user", text="user", sha256="u")
        return PromptSet(schema_version="1.0", system=tmpl, user=user)

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class FakeOpenAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def _next(self):
        if not self.responses:
            return {}
        return self.responses.pop(0)

    def openai_chat_json(self, req, ctx):
        self.requests.append(("chat", req))
        payload = self._next()
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
        self.requests.append(("vector", req.vector_store_id))
        payload = self._next()
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

    def store_pack(self, output_dir, report_id, pack_name, payload, ctx):
        self.stored.append((output_dir, report_id, pack_name, payload))
        return f"{output_dir}/{report_id}/{pack_name}.json"


def _settings(tmp_path, *, use_vector_store=True):
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
        analysis_mode="vector_store" if use_vector_store else "local_text",
        use_vector_store=use_vector_store,
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
    responses = [
        {"toc_topics": ["Topic 1", "Topic 2"]},
        {"summary": {"tldr": "TLDR", "executive_summary": "Exec", "claim_evidence_map": [{"claim": "Claim", "evidence_id": "f1", "evidence": "Revenue +10%", "pages": [2]}]}},
        {
            "insights_candidates": [
                {"id": "c1", "text": "Insight 1", "evidence_id": "f1", "evidence": "E1", "metric": {"value": "10", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "US", "segment": "", "sample_size": "", "confidence": ""}, "pages": [2], "score": 0.9},
                {"id": "c2", "text": "Insight 2", "evidence_id": "f2", "evidence": "E2", "metric": {"value": "5", "unit": "%", "trend": "-", "timeframe": "2023", "geography": "EU", "segment": "", "sample_size": "", "confidence": ""}, "pages": [3], "score": 0.8},
                {"id": "c3", "text": "Insight 3", "evidence_id": "f3", "evidence": "E3", "metric": {"value": "2", "unit": "pt", "trend": "+", "timeframe": "Q1", "geography": "", "segment": "", "sample_size": "", "confidence": ""}, "pages": [4], "score": 0.7},
                {"id": "c4", "text": "Insight 4", "evidence_id": "f4", "evidence": "E4", "metric": {"value": "12", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "APAC", "segment": "", "sample_size": "", "confidence": ""}, "pages": [5], "score": 0.6},
                {"id": "c5", "text": "Insight 5", "evidence_id": "f5", "evidence": "E5", "metric": {"value": "3", "unit": "%", "trend": "+", "timeframe": "2024", "geography": "", "segment": "", "sample_size": "", "confidence": ""}, "pages": [6], "score": 0.5},
            ]
        },
        {
            "insights_final": [
                {"id": "f1", "text": "Top 1", "evidence_id": "f1", "evidence": "E1", "metric": {}, "pages": [2]},
                {"id": "f2", "text": "Top 2", "evidence_id": "f2", "evidence": "E2", "metric": {}, "pages": [3]},
                {"id": "f3", "text": "Top 3", "evidence_id": "f3", "evidence": "E3", "metric": {}, "pages": [4]},
                {"id": "f4", "text": "Top 4", "evidence_id": "f4", "evidence": "E4", "metric": {}, "pages": [5]},
                {"id": "f5", "text": "Top 5", "evidence_id": "f5", "evidence": "E5", "metric": {}, "pages": [6]},
            ]
        },
        {"quotes_final": [{"text": "We are expanding rapidly", "speaker": "CEO", "citation": "Earnings call", "page": 3, "evidence_id": "q1"}]},
        {"expert_comment": "Grounded comment"},
        {"linkedin_post": "Post summary"},
    ]
    fake_openai = FakeOpenAI(responses)
    analysis_store = FakeAnalysisStore()
    payload = generate_artifacts(
        report_id="r1",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path, use_vector_store=True),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert all(item["evidence_id"] for item in payload["insights_candidates"])
    assert all(item["evidence_id"] for item in payload["insights_final"])
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 1
    validate_schema(payload, "artifacts", _ctx())
    assert analysis_store.stored and analysis_store.stored[0][2] == "artifacts"


def test_generate_artifacts_backfills_missing_ids(tmp_path):
    responses = [
        {"toc_topics": ["Topic"]},
        {"summary": {"tldr": "", "executive_summary": "", "claim_evidence_map": [{"claim": "Claim", "evidence": "Support"}]}},
        {"insights_candidates": [{"id": "c1", "text": "Candidate 1", "metric": {}, "pages": []}]},
        {"insights_final": []},
        {"quotes_final": [{"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1}]},
        {"expert_comment": "Comment"},
        {"linkedin_post": "Post"},
    ]
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="r2",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path, use_vector_store=False),
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
    validate_schema(payload, "artifacts", _ctx())


def test_generate_artifacts_short_circuits_on_low_text(tmp_path):
    analysis_store = FakeAnalysisStore()
    fake_openai = FakeOpenAI([])
    payload = generate_artifacts(
        report_id="low_text",
        doc_map={},
        evidence_packs={},
        settings=_settings(tmp_path, use_vector_store=True),
        vector_store_id="vs_1",
        source_status=_low_text_status(),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert payload["source_status"]["not_available"] is True
    assert "text_density_below_threshold" in payload["source_status"]["reason"]
    assert "Not available from text" in payload["toc_topics"][0]
    assert fake_openai.requests == []
    validate_schema(payload, "artifacts", _ctx())
    assert analysis_store.stored
